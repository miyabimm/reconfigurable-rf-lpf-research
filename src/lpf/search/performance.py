"""Performance declarations, interval compilation and finite-grid assessment.

The old scalar consumers remain deliberately restricted. The Stage-3 functions
below do not call them, nor the historical harmonic-group score.
"""
import math
from dataclasses import dataclass, asdict, replace
import csv
import hashlib
import json
from pathlib import Path
import numpy as np
from ..constraint_versions import constraint_fingerprint


def validate_performance(policy):
    p = policy['evaluation']['performance']
    if set(p) != {'objective', 'modes', 'limits', 'margins', 'additional_stopbands'}:
        raise ValueError('Unknown performance fields')
    if p['objective'] != {'metric': 'il_db', 'selector': {'type': 'pass'},
                           'aggregation': 'worst', 'direction': 'minimize'}:
        raise ValueError('Unsupported performance objective')
    if p['modes'] != {'full_lpf': {'excluded_regions': []},
                      'matching_only': {'excluded_regions': ['H2', 'H3']}}:
        raise ValueError('Unsupported performance modes')
    if (set(p['limits']) != {'defaults', 'overrides'} or
            p['limits']['overrides'] != [] or p['margins'] != []):
        raise ValueError('Interval overrides/margins are not implemented in Stage 1')
    rules = p['limits']['defaults']
    expected = {(m, tuple(s.items()), level, bound) for m, s, level, bound in [
        ('attenuation_db', {'region': r}, level, 'min_db')
        for r in ('H2', 'H3') for level in ('mandatory', 'nominal')]} | {
        ('il_db', (('type', 'pass'),), 'nominal', 'max_db')}
    seen = set()
    if not isinstance(rules, list):
        raise ValueError('Expected performance defaults list')
    for rule in rules:
        if not isinstance(rule, dict):
            raise ValueError('Expected performance rule')
        bound = 'min_db' if 'min_db' in rule else 'max_db'
        if set(rule) != {'metric', 'selector', 'level', bound} or not isinstance(rule['selector'], dict):
            raise ValueError('Unknown performance rule fields')
        key = (rule['metric'], tuple(rule['selector'].items()), rule['level'], bound)
        value = rule[bound]
        if key not in expected or key in seen or type(value) not in (int, float) or not math.isfinite(value):
            raise ValueError('Unknown/duplicate/nonfinite performance rule')
        seen.add(key)
    if seen != expected:
        raise ValueError('Incomplete performance defaults')
    extra = p['additional_stopbands']
    if not isinstance(extra, list) or len(extra) > 1:
        raise ValueError('Unsupported additional stopbands')
    if extra:
        from ..constraint_versions import _validate_trial_additional_stopband
        _validate_trial_additional_stopband(extra[0], policy)
    return p


def limit_db(policy, metric='attenuation_db', level='mandatory', region='H2'):
    p = validate_performance(policy)
    selector = {'type': 'pass'} if metric == 'il_db' else {'region': region}
    for rule in p['limits']['defaults']:
        if rule['metric'] == metric and rule['level'] == level and rule['selector'] == selector:
            return rule.get('min_db', rule.get('max_db'))
    raise ValueError('Unsupported scalar requirement')


def harmonic_limit_db(policy, level='mandatory'):
    h2, h3 = (limit_db(policy, level=level, region=r) for r in ('H2', 'H3'))
    if h2 != h3:
        raise ValueError('Scalar harmonic consumer requires equal H2/H3 limits')
    return h2


def additional_stopband(policy):
    extra = validate_performance(policy)['additional_stopbands']
    return extra[0] if extra else None


# Stage 3: no RF forward or solver/runner dependency.


@dataclass(frozen=True)
class Interval:
    segment: int
    identity: str
    csv_line: int | None
    case: str
    region: str
    type: str
    note: str
    setting: int
    low_hz: float
    high_hz: float
    step_hz: int | None = None


@dataclass(frozen=True)
class Requirement:
    interval: Interval
    metric: str
    level: str
    bound: str
    threshold_db: float


@dataclass(frozen=True)
class Requirements:
    policy_id: str
    policy_fingerprint: str
    mode: str
    intervals: tuple[Interval, ...]
    limits: tuple[Requirement, ...]
    objective_segments: tuple[int, ...]
    fingerprint: str


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                    separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def grid_fingerprint(grid):
    from ..rf_core.model import EvaluationGrid
    if not isinstance(grid, EvaluationGrid):
        raise ValueError('Expected frozen EvaluationGrid')
    return _digest([grid.frequency_hz.tolist(), grid.setting.tolist(), grid.segment.tolist()])


def _number(value):
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError('Expected finite numeric declaration')
    return float(value)


def _select(selector, intervals):
    if (not isinstance(selector, dict) or not selector or
            set(selector) - {'case', 'region', 'note', 'type'} or
            any(not isinstance(v, str) for v in selector.values())):
        raise ValueError('Unknown/empty selector')
    selected = [i for i in intervals if all(getattr(i, k) == v for k, v in selector.items())]
    if not selected:
        raise ValueError('Selector matches zero intervals')
    return selected


def _rule(rule):
    if not isinstance(rule, dict):
        raise ValueError('Expected rule object')
    bounds = set(rule) & {'min_db', 'max_db'}
    if len(bounds) != 1:
        raise ValueError('Exactly one bound required')
    bound = next(iter(bounds))
    if (set(rule) != {'metric', 'selector', 'level', bound} or
            rule['metric'] not in {'il_db', 'attenuation_db', 'apl_db', 'in_rl_db', 'out_rl_db'} or
            rule['level'] not in {'mandatory', 'nominal'}):
        raise ValueError('Unsupported metric/level/rule format')
    return bound, _number(rule[bound])


def compile_requirements(policy, bands, mode='full_lpf'):
    """Compile current-schema rules, preserving CSV line identity and all gaps.

    bands is a CSV path or an iterable of CSV dictionaries (in original order).
    Synthetic policies are accepted for rule tests; production policy approval is
    separately enforced by build_rf_model. No policy or band input is mutated.
    """
    if policy.get('schema_version') != 2:
        raise ValueError('Only current performance schema is supported')
    p = policy['evaluation']['performance']
    if set(p) != {'objective', 'modes', 'limits', 'margins', 'additional_stopbands'}:
        raise ValueError('Unknown performance fields')
    if p['objective'] != {'metric': 'il_db', 'selector': {'type': 'pass'},
                           'aggregation': 'worst', 'direction': 'minimize'}:
        raise ValueError('Unsupported objective')
    if p['modes'] != {'full_lpf': {'excluded_regions': []},
                      'matching_only': {'excluded_regions': ['H2', 'H3']}} or mode not in p['modes']:
        raise ValueError('Unsupported mode')
    if isinstance(bands, (str, Path)):
        with open(bands, newline='') as f:
            rows = list(csv.DictReader(f))
    else:
        rows = list(bands)
    from lpf.phase2_models._grid import CASES, validated_band_segments
    validated_band_segments(rows)  # existing six-setting/subband meaning checks
    settings = list(CASES)
    intervals = []
    span = policy['external_port_parasitics']['format']
    for n, r in enumerate(rows):
        if (set(r) != {'case', 'region', 'type', 'low_mhz', 'high_mhz', 'note'} or
                r['region'] not in {'UL', 'DL', 'H2', 'H3'} or
                r['type'] != ('pass' if r['region'] in {'UL', 'DL'} else 'stop')):
            raise ValueError('Invalid band row')
        lo, hi = float(r['low_mhz'])*1e6, float(r['high_mhz'])*1e6
        identity = f"csv:{n+2}:{r['case']}:{r['region']}:{r['type']}:{r['note']}"
        intervals.append(Interval(n, identity, n+2, r['case'], r['region'], r['type'],
                                  r['note'], settings.index(r['case']), lo, hi))
    if not isinstance(p['margins'], list):
        raise ValueError('Expected margins list')
    margins = {}
    for margin in p['margins']:
        if not isinstance(margin, dict) or set(margin) != {'selector', 'lower_mhz', 'upper_mhz'}:
            raise ValueError('Unknown margin format')
        lower, upper = (_number(margin[k])*1e6 for k in ('lower_mhz', 'upper_mhz'))
        if min(lower, upper) < 0:
            raise ValueError('Negative margin')
        for i in _select(margin['selector'], intervals):
            if i.segment in margins:
                raise ValueError('Conflicting/duplicate margin')
            margins[i.segment] = (lower, upper)
    intervals = [replace(i, low_hz=i.low_hz-margins.get(i.segment, (0, 0))[0],
                         high_hz=i.high_hz+margins.get(i.segment, (0, 0))[1]) for i in intervals]
    for i in intervals:
        if (not math.isfinite(i.low_hz+i.high_hz) or i.low_hz <= 0 or i.high_hz < i.low_hz or
                i.low_hz < span['f_start_hz'] or i.high_hz > span['f_stop_hz']):
            raise ValueError('Interval outside fixed S2P span')
    if not isinstance(p['limits'], dict) or set(p['limits']) != {'defaults', 'overrides'}:
        raise ValueError('Invalid limits')
    compiled, overridden = {}, set()
    for group in ('defaults', 'overrides'):
        if not isinstance(p['limits'][group], list):
            raise ValueError('Expected rule list')
        for rule in p['limits'][group]:
            bound, threshold = _rule(rule)
            for i in _select(rule['selector'], intervals):
                key = (i.segment, rule['metric'], rule['level'])
                if group == 'defaults':
                    if key in compiled:
                        raise ValueError('Duplicate/overlapping default')
                elif key not in compiled or key in overridden:
                    raise ValueError('Override without default or conflicting overrides')
                else:
                    overridden.add(key)
                compiled[key] = Requirement(i, rule['metric'], rule['level'], bound, threshold)
    excluded = p['modes'][mode]['excluded_regions']
    active = [i for i in intervals if i.region not in excluded]
    limits = [r for r in compiled.values() if r.interval.region not in excluded]
    extras = p['additional_stopbands']
    if not isinstance(extras, list):
        raise ValueError('Expected additional stopbands list')
    from lpf.constraint_versions import _validate_trial_additional_stopband
    seen_extra = set()
    for n, extra in enumerate(extras):
        _validate_trial_additional_stopband(extra, policy)
        digest = _digest(extra)
        if digest in seen_extra:
            raise ValueError('Duplicate additional stopband')
        seen_extra.add(digest)
        if mode != 'full_lpf':
            continue
        for case in extra['settings']:
            i = Interval(28+n, f'additional:{n}:{case}', None, case, 'additional', 'stop', '',
                         settings.index(case), extra['low_hz'], extra['high_hz'], extra['sample_step_hz'])
            active.append(i)
            limits.append(Requirement(i, 'attenuation_db', 'mandatory', 'min_db',
                                      extra['min_attenuation_db']))
    objective = tuple(i.segment for i in active if i.type == 'pass')
    if not objective or any(not any(r.interval == i for r in limits) for i in active):
        raise ValueError('Every active interval needs a requirement')
    content = dict(policy_id=policy['active_constraint_id'], policy_fingerprint=constraint_fingerprint(policy),
                   mode=mode, intervals=tuple(active), limits=tuple(limits), objective_segments=objective)
    fingerprint = _digest({k: [asdict(v) for v in value] if k in ('intervals', 'limits') else value
                           for k, value in content.items()})
    return Requirements(**content, fingerprint=fingerprint)


def evaluate_requirements(response, requirements, *, requested_grid):
    """Assess a response against an independently frozen *requested* grid.

    Stage 4 owns grid construction. Requiring that grid here prevents a partial
    response from declaring its own completed samples to be the entire request.
    No interpolation, endpoint substitution, tolerance, or RF forwards occur.
    Errors STOP with ValueError, never a finite mandatory-FAIL score.
    """
    from ..rf_core.model import RFResponse
    r, req = response, requirements
    if not isinstance(r, RFResponse) or not isinstance(req, Requirements):
        raise ValueError('Expected RFResponse and compiled Requirements')
    if (r.policy_id, r.policy_fingerprint) != (req.policy_id, req.policy_fingerprint):
        raise ValueError('Response policy mismatch')
    fingerprint = grid_fingerprint(requested_grid)
    if grid_fingerprint(r.grid) != fingerprint:
        raise ValueError('Incomplete response or requested-grid mismatch')
    g = r.grid
    n = len(g.frequency_hz)
    samples = list(zip(g.segment.tolist(), g.setting.tolist(), g.frequency_hz.tolist()))
    if len(set(samples)) != n:
        raise ValueError('Duplicate samples')
    covered = np.zeros(n, bool)
    indices = {}
    for i in req.intervals:
        ix = np.flatnonzero((g.segment == i.segment) & (g.setting == i.setting))
        f = g.frequency_hz[ix]
        if not f.size or np.any(f < i.low_hz) or np.any(f > i.high_hz):
            raise ValueError(f'Missing/invalid interval samples: {i.identity}')
        if i.step_hz is not None:
            expected = np.arange(i.low_hz, i.high_hz+i.step_hz, i.step_hz)
            if not np.array_equal(np.sort(f), expected):
                raise ValueError('Additional stopband requires the complete inclusive grid')
        indices[i.identity] = ix
        covered[ix] = True
    if not np.all(covered):
        raise ValueError('Samples assigned to unknown/excluded interval or wrong setting')
    metrics = {}
    if np.asarray(r.s).shape != (n, 2, 2) or not np.all(np.isfinite(r.s)):
        raise ValueError('Invalid complex response')
    for metric in ('il_db', 'apl_db', 'in_rl_db', 'out_rl_db'):
        a = np.asarray(getattr(r, metric))
        if a.shape != (n,) or a.dtype.kind not in 'fiu' or np.any(np.isnan(a)) or np.any(np.isneginf(a)):
            raise ValueError('Undefined dB response')
        # +inf is valid only for an exact zero amplitude, as in Stage 2.
        amplitude = np.abs(r.s[:, 1, 0] if metric in ('il_db', 'apl_db') else
                           r.s[:, 0, 0] if metric == 'in_rl_db' else r.s[:, 1, 1])
        if np.any(np.isposinf(a) & (amplitude != 0)):
            raise ValueError('Unexplained infinite dB')
        metrics[metric] = a
    metrics['attenuation_db'] = metrics['il_db']
    rows, violations, solver_g = [], [], []
    for rule in req.limits:
        ix = indices[rule.interval.identity]
        obs = metrics[rule.metric][ix]
        e = obs-rule.threshold_db if rule.bound == 'max_db' else rule.threshold_db-obs
        worst = int(np.argmax(e))
        violation = max(0., float(e[worst]))
        rows.append(dict(requirement=rule, sample_indices=tuple(map(int, ix)),
                         observations_db=tuple(map(float, obs)), residuals_db=tuple(map(float, e)),
                         sample_pass=tuple(map(bool, e <= 0)), passed=bool(np.all(e <= 0)),
                         worst_observation_db=float(obs[worst]), worst_residual_db=float(e[worst]),
                         worst_frequency_hz=float(g.frequency_hz[ix[worst]]),
                         worst_setting=int(g.setting[ix[worst]]), violation_db=violation))
        if rule.level == 'mandatory':
            violations.append(violation)
            solver_g.extend(map(float, -e))
    objective_ix = np.flatnonzero(np.isin(g.segment, req.objective_segments))
    worst_il = float(np.max(r.il_db[objective_ix]))
    return dict(status='evaluated', policy_id=req.policy_id, policy_fingerprint=req.policy_fingerprint,
                mode=req.mode, requirements_fingerprint=req.fingerprint, grid_fingerprint=fingerprint,
                requirements=req, samples=tuple(samples), rows=tuple(rows), mandatory_g=tuple(solver_g),
                strict_feasible=all(v == 0 for v in violations), worst_il_db=worst_il,
                max_violation_db=max(violations, default=0.), sum_violation_db=sum(violations))

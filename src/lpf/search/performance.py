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


# Compatibility names for pure declaration checks/lookups. Requirement
# compilation, grids and interval scoring remain owned by this module.
from ..policy_schema import (
    validate_performance, limit_db, harmonic_limit_db, additional_stopband,
)


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
    s2p_span_hz: tuple[float, float]
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
    from lpf.rf_core._grid import CASES, validated_band_segments
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
                   mode=mode, intervals=tuple(active), limits=tuple(limits), objective_segments=objective,
                   s2p_span_hz=(span['f_start_hz'], span['f_stop_hz']))
    fingerprint = _digest({k: [asdict(v) for v in value] if k in ('intervals', 'limits') else value
                           for k, value in content.items()})
    return Requirements(**content, fingerprint=fingerprint)


# A static allocation safety limit, not a scientific density or budget default.
MAX_GRID_SAMPLES = 1_000_000


def build_evaluation_grid(requirements, points_per_interval):
    """Freeze interval-major, ascending inclusive samples, without RF forwards.

    The complete Requirements fingerprint is checked before allocation. Overlap
    between distinct intervals is intentional and never deduplicated. Fixed-step
    additional intervals keep their JSON density regardless of ordinary points.
    """
    from ..rf_core.model import EvaluationGrid
    from lpf.rf_core._grid import CASES
    req = requirements
    if not isinstance(req, Requirements):
        raise ValueError('Compiled Requirements required')
    content = asdict(req)
    fingerprint = content.pop('fingerprint')
    if _digest(content) != fingerprint:
        raise ValueError('Requirements fingerprint mismatch')
    if type(points_per_interval) is not int or not 2 <= points_per_interval <= MAX_GRID_SAMPLES:
        raise ValueError('points_per_interval must be an integer >=2 within allocation limit')
    if req.mode not in ('full_lpf', 'matching_only'):
        raise ValueError('Unknown evaluation mode')
    ordinary = [i for i in req.intervals if i.csv_line is not None]
    expected = {(case, region, note) for case in CASES
                for region in (('UL', 'DL', 'H2', 'H3') if req.mode == 'full_lpf' else ('UL', 'DL'))
                for note in (case.split('+') if '+' in case else ('',))}
    keys = [(i.case, i.region, i.note) for i in ordinary]
    if len(keys) != len(expected) or set(keys) != expected:
        raise ValueError('Missing/duplicate ordinary interval')
    identities, slots, counts = set(), set(), []
    lo, hi = req.s2p_span_hz
    if not (math.isfinite(lo) and math.isfinite(hi) and 0 <= lo < hi):
        raise ValueError('Invalid S2P span')
    for i in req.intervals:
        slot = (i.segment, i.setting)
        if (i.identity in identities or slot in slots or type(i.segment) is not int or
                i.segment < 0 or type(i.setting) is not int or not 0 <= i.setting < 6 or
                i.case != CASES[i.setting] or not math.isfinite(i.low_hz) or
                not math.isfinite(i.high_hz) or not 0 < i.low_hz < i.high_hz or
                i.low_hz < lo or i.high_hz > hi):
            raise ValueError('Invalid/duplicate interval or S2P extrapolation')
        identities.add(i.identity)
        slots.add(slot)
        if i.csv_line is not None:
            if (i.segment != i.csv_line-2 or not 0 <= i.segment < 28 or i.step_hz is not None or
                    i.type != ('pass' if i.region in ('UL', 'DL') else 'stop')):
                raise ValueError('Invalid ordinary interval identity')
            count = points_per_interval
        else:
            if (req.mode != 'full_lpf' or i.region != 'additional' or i.segment < 28 or
                    type(i.step_hz) is not int or i.step_hz <= 0):
                raise ValueError('Invalid additional interval step')
            steps = (i.high_hz-i.low_hz)/i.step_hz
            if not math.isfinite(steps) or not steps.is_integer():
                raise ValueError('Additional endpoints must align with step')
            count = int(steps)+1
        counts.append(count)
    if sum(counts) > MAX_GRID_SAMPLES:
        raise ValueError('Grid exceeds static allocation limit')
    frequency, setting, segment = [], [], []
    for i, count in zip(req.intervals, counts):
        f = (np.linspace(i.low_hz, i.high_hz, count) if i.step_hz is None else
             i.low_hz + np.arange(count)*i.step_hz)
        if f[-1] != i.high_hz or np.any(np.diff(f) <= 0):
            raise ValueError('Unrepresentable inclusive grid')
        frequency.extend(f)
        setting.extend([i.setting]*count)
        segment.extend([i.segment]*count)
    return EvaluationGrid(frequency, setting, segment)


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

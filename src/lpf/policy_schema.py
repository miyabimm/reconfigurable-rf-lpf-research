"""Pure RF JSON declarations; no search, model, or solver dependency."""
import math
import numpy as np


def interval(spec, unit):
    b = spec.get('bounds')
    if (not isinstance(b, dict) or set(b) != {'min', 'max', 'unit'} or b['unit'] != unit
            or any(type(b[k]) not in (int, float) or not np.isfinite(b[k]) for k in ('min', 'max'))
            or b['min'] > b['max']):
        raise ValueError('Missing/invalid closed bounds or unit')
    return float(b['min']), float(b['max'])


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
        from .constraint_versions import _validate_trial_additional_stopband
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



"""Readback of bounded-evidence development windows, never formal raw.

Search histories are intentionally unavailable. This checks saved identities and
aggregate accounting, not independent reconstruction of discarded observations.
"""
import math

from .evaluation import raw_numbers
from .preflight import nonnegative
from .storage import vector_sha


def _metric(value):
    if isinstance(value, dict) and set(value) == {'nonfinite'}:
        if value['nonfinite'] == '+inf': return float('inf')
        if value['nonfinite'] == '-inf': return float('-inf')
    if type(value) not in (int, float) or math.isnan(value):
        raise ValueError('Invalid saved scientific metric')
    return value


def _key(a, digest):
    if type(a['strict_feasible']) is not bool:
        raise ValueError('Invalid feasibility flag')
    return ((0, _metric(a['worst_il_db']), digest) if a['strict_feasible'] else
            (1, _metric(a['max_violation_db']), _metric(a['sum_violation_db']),
             _metric(a['worst_il_db']), digest))


def readback_summaries(raw, envelope, spec):
    from .runner import _validate_development_result
    d, result = spec.data, envelope['payload']
    confirmed = envelope['confirmed']
    if set(confirmed) != {'forwards', 'requested', 'completed'}:
        raise ValueError('Invalid confirmed fields')
    for n in confirmed.values(): nonnegative(n)
    previous = envelope['previous_confirmed']
    previous_upper = envelope['previous_uncertain_upper']
    if set(previous) != set(confirmed) or set(previous_upper) != set(confirmed):
        raise ValueError('Invalid previous confirmed/reservation fields')
    for k, n in previous.items():
        nonnegative(n); nonnegative(previous_upper[k])
        if not n <= confirmed[k] <= previous_upper[k]:
            raise ValueError('Confirmed progress exceeds prior reservation')
    if (envelope['window'] is not None or envelope['uncertain_upper'] != confirmed or
            'termination' in envelope or result['requested'] != confirmed['requested'] or
            result['completed'] != confirmed['completed'] or
            sum(v['forwards'] for v in result['progress_by_allocation'].values()) != confirmed['forwards'] or
            result.get('unsaved_window_results_may_be_lost') is not True or
            'best_hybrid_observed_by_stage' in result):
        raise ValueError('Window remains uncertain or confirmed totals mismatch')
    imported = _validate_development_result(raw, result, spec, compact=True,
                                            content=envelope, summary_progress=True)
    batches = {}
    for row in result['batches']:
        i = row['batch_index']
        if (type(i) is not int or not 0 <= i <= confirmed['forwards'] or i in batches or
                (i == confirmed['forwards'] and row['status'] != 'rejected')):
            raise ValueError('Invalid saved batch index')
        batches[i] = row
        audit = row['independent']
        if audit['status'] == 'pass':
            import numpy as np
            if (audit.get('passivity') != 'pass_at_samples' or audit.get('power_balance') != 'pass_at_samples' or
                    audit.get('whole_band_checked') is not False or
                    [s['index'] for s in audit['samples']] != audit['sample_indices'] or
                    audit['completed'] != len(audit['samples']) or
                    type(audit['absolute_tolerance']) not in (int, float) or
                    not math.isfinite(audit['absolute_tolerance']) or audit['absolute_tolerance'] <= 0):
                raise ValueError('Independent spot evidence mismatch')
            def numbers(value):
                return [numbers(v) for v in value] if isinstance(value, list) else _metric(value)
            for sample in audit['samples']:
                i = sample['index']
                for key in ('s_real', 's_imag', 'il_db', 'apl_db', 'in_rl_db', 'out_rl_db'):
                    if not np.allclose(numbers(sample[key]), numbers(row['response'][key][i]), rtol=0,
                                       atol=audit['absolute_tolerance']):
                        raise ValueError('Independent spot/response mismatch')
    for scan in result['anytime']:
        if scan['status'] == 'completed':
            batch = batches.get(scan['batch_index'])
            if (batch is None or batch['stage'] != 'anytime' or batch['status'] != 'completed' or
                    type(scan['observation_batch']) is not int or
                    not 0 <= scan['observation_batch'] < scan['batch_index'] or
                    vector_sha(scan['observation_vector']) != scan['observation_vector_sha256'] or
                    batch['vector_sha256'] != scan['observation_vector_sha256']):
                raise ValueError('Anytime observation mismatch')
    best = result['best_observed_by_stage']
    stages = {k for k, v in result['progress_by_allocation'].items()
              if k.startswith(d['arm']+'/') and v['completed']}
    if set(best) != stages:
        raise ValueError('Missing stage best')
    for stage, b in best.items():
        a, physical = b['assessment'], b['physical_checks']
        digest = b['vector_sha256']
        if (vector_sha(b['vector']) != digest or b['grid_sha256'] != d['plan']['grids'][stage]['sha256'] or
                type(b['batch_index']) is not int or not 0 <= b['batch_index'] < confirmed['forwards'] or
                b['_key'] != raw_numbers(_key(a, digest)) or type(a['nominal_pass']) is not bool or
                a['status'] != 'evaluated' or a['grid_fingerprint'] != b['grid_sha256'] or
                a['policy_id'] != d['plan']['config']['rf']['constraint_id'] or
                a['policy_fingerprint'] != d['plan']['requirements']['policy_fingerprint'] or
                a['requirements_fingerprint'] != d['plan']['requirements']['fingerprint'] or
                a['mode'] != d['plan']['config']['objective'] or
                physical['component_policy_pass'] is not True or physical['checked_settings'] != 6):
            raise ValueError('Best candidate identity or physical evidence mismatch')
        requirements = d['plan']['requirements']
        if a.get('requirements') != requirements or len(a.get('rows', [])) != len(requirements['limits']):
            raise ValueError('Best interval evidence missing or mismatched')
        mandatory, nominal = [], []
        for row, limit in zip(a['rows'], requirements['limits']):
            if row['requirement'] != limit or type(row['passed']) is not bool:
                raise ValueError('Best requirement identity mismatch')
            violation = _metric(row['violation_db'])
            if violation < 0 or row['passed'] != (violation == 0):
                raise ValueError('Best interval violation mismatch')
            if limit['level'] == 'mandatory': mandatory.append(violation)
            if limit['level'] == 'nominal': nominal.append(row['passed'])
        if (a['strict_feasible'] != all(v == 0 for v in mandatory) or
                a['nominal_pass'] != all(nominal) or
                _metric(a['max_violation_db']) != max(mandatory, default=0.) or
                _metric(a['sum_violation_db']) != sum(mandatory)):
            raise ValueError('Best aggregate evidence mismatch')
        minimum = physical['min_L_eigenvalue_H']
        n = len(d['definition']['inductor_tree']['edges'])
        if (n and (type(minimum) not in (int, float) or not math.isfinite(minimum) or minimum <= 0)) or (not n and minimum is not None):
            raise ValueError('Best inductance matrix evidence mismatch')
    selection = result['selection']
    ranked = selection['ranked']
    if ranked and selection['status'] != 'completed':
        raise ValueError('Ranked selection without completed selection')
    solver = {c['vector_sha256'] for step in result['steps'] for c in step['candidates'] if c.get('status') == 'unrun'}
    keys = []
    for row in ranked:
        batch = batches.get(row['batch_index'])
        if batch is None:
            raise ValueError('Missing selection evidence')
        a, digest = batch['assessment'], batch['vector_sha256']
        key = _key(a, digest)
        if (batch['stage'] != 'selection' or batch['status'] != 'completed' or digest not in solver or
                row['vector_sha256'] != digest or row['vector'] != batch['vector'] or row['assessment'] != a or
                row['plan_sha256'] != spec.plan_sha256 or row['grid_sha256'] != batch['grid_sha256'] or
                row['rank_key'] != raw_numbers(key) or row['status'] != ('pass' if a['strict_feasible'] else 'fail')):
            raise ValueError('Selection candidate/batch identity or rank mismatch')
        keys.append(key)
    if keys != sorted(keys) or len({r['vector_sha256'] for r in ranked}) != len(ranked):
        raise ValueError('Selection order or uniqueness mismatch')
    complete = result['status'] in ('converged', 'not_converged')
    if complete and {r['batch_index'] for r in ranked} != {i for i, b in batches.items() if b['stage'] == 'selection' and b['status'] == 'completed'}:
        raise ValueError('Completed Job omitted assessed selection')
    terminal = result['terminal']
    candidates = terminal['candidates']
    cap = min(len(ranked), d['plan']['config']['selection']['top_k'])
    if (candidates and terminal['status'] != 'completed') or len(candidates) > cap or (complete and len(candidates) != cap):
        raise ValueError('Terminal status/count mismatch')
    for candidate, selected in zip(candidates, ranked):
        batch = batches.get(candidate['batch_index'])
        if (batch is None or batch['stage'] != 'terminal' or batch['status'] != 'completed' or
                candidate['vector_sha256'] != selected['vector_sha256'] or candidate['vector_sha256'] != batch['vector_sha256']):
            raise ValueError('Terminal/selection/batch mismatch')
    if complete:
        for step in result['steps']:
            if (step['status'] not in ('converged', 'not_converged') or
                    vector_sha(step['input_vector']) != step['input_vector_sha256'] or
                    vector_sha(step['output_vector']) != step['output_vector_sha256']):
                raise ValueError('Completed step/vector mismatch')
    number, io = envelope['checkpoint_number'], envelope['io_before']
    imported['worker_io'] = dict(atomic_writes=number, payload_bytes=io['written_bytes']+len(raw),
        atomic_readbacks=io['read_calls']+1, readback_bytes=io['read_bytes']+len(raw), scope='worker_raw_only')
    return imported

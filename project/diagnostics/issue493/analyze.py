#!/usr/bin/env python3
"""Verify #493 raw receipts and construct an exclusive solver wall breakdown."""
import hashlib
import json
import math
from pathlib import Path
import statistics
import sys

root = Path(sys.argv[1])
cache_paths = [Path(p) for p in sys.argv[2:]]
load = lambda p: json.loads(p.read_text())
sha = lambda b: hashlib.sha256(b).hexdigest()
rows = [json.loads(s) for s in (root/'measurements.jsonl').read_text().splitlines()]
assert len(rows) == 14 and all(r['exit_code'] == 0 and r['status'] == 'completed' for r in rows)
refs = {}; diagnostics = {}; checkpoint_counts = []
for row in rows:
    path = root/row['name']
    run = load(path/'run.json'); job = run['jobs'][0]
    assert run['status'] == job['status'] == 'completed'
    assert sha((path/'plan.json').read_bytes()) == run['plan_raw']['sha256']
    raw = path/job['raw_path']; receipt = load(raw/'receipt.json')
    for name, info in job['raw'].items():
        data = (raw/name).read_bytes()
        assert len(data) == info['bytes'] and sha(data) == info['sha256']
    assert receipt['files'] == {k:v for k,v in job['raw'].items() if k != 'receipt.json'}
    result = load(raw/'result.json')
    cps = [load(p) for p in sorted((raw/'checkpoints').glob('*.json'))]
    key = 'warm' if row['name'].startswith('warm-') else 'run'
    if key in refs:
        assert (result, cps) == refs[key], row['name']
    else:
        refs[key] = (result, cps)
    if row['mode'] != 'plain':
        diag = load(root/(row['name']+'.timing.json'))
        assert diag['status'] == 'completed'
        diagnostics[row['name']] = diag['jobs'][0]
        if row['mode'] == 'timed':
            assert not any('/objective/' in k or k.endswith(('batch/parent', 'batch/apply', 'batch/residuals', 'scalar/rf_evaluate', 'scalar/post_rf', 'scipy/minimize', 'scipy/callback')) for k in diag['jobs'][0]['regions'])
result, cps = refs['run']; checkpoint_counts = [c['forward_count'] for c in cps]
assert len(cps) == 99 and all(n % 26 == 0 for n in checkpoint_counts)
assert result['costs']['search_forwards'] == 100022
assert result['rf_profile']['effective_sha256'] == 'd50e6c9fef3e41b8258c00cbd14436a3bcb1d84444d50cf4a445ccf5d288e417'
assert result['steps'][0]['stop_reason'] == 'evaluation_budget_exhausted'
trace = [r for r in rows if r['trace']]
assert len(trace) == 2 and trace[0]['callbacks'] == trace[1]['callbacks'] == 100022
assert trace[0]['trace_sha256'] == trace[1]['trace_sha256']
candidate = result['terminal']['candidates'][0]; response = candidate['response']
assert candidate['independent']['status'] == 'pass'
assert candidate['external_passivity'] == candidate['power_balance'] == 'checked_on_terminal_grid'
assert candidate['physical']['component_policy_pass'] and candidate['physical']['min_L_eigenvalue_H'] > 0

def finite(value):
    if isinstance(value, dict): return all(finite(v) for v in value.values())
    if isinstance(value, list): return all(finite(v) for v in value)
    return isinstance(value, (int, float)) and math.isfinite(value)
for key in ('s', 'il_db', 'apl_db', 'in_rl_db', 'out_rl_db'):
    assert len(response[key]) == 476 and finite(response[key])
for spot in candidate['independent']['spots']:
    for key in ('il_db', 'apl_db', 'in_rl_db', 'out_rl_db'):
        assert abs(response[key][spot['index']] - spot['reference'][key]) <= 1e-9
    for a, b in zip(response['s'][spot['index']], spot['reference']['s'], strict=True):
        for x, y in zip(a, b, strict=True):
            assert abs(complex(x['real'], x['imag']) - complex(y['real'], y['imag'])) <= 1e-9
caches = [d['steps']['search']['rf_cache']['counters'] for name,d in diagnostics.items() if not name.startswith('warm-')]
assert all(c == caches[0] for c in caches)
assert (caches[0]['lk_hits'], caches[0]['lk_misses'], caches[0]['computed_samples']) == (73102, 26920, 4308640)
replays = {}
for path in cache_paths:
    row, counters = map(json.loads, Path(str(path)+'.log').read_text().splitlines())
    assert row['callbacks'] == 100022 and row['trace_sha256'] == trace[0]['trace_sha256']
    assert counters['search_cache'] == caches[0]
    assert load(path/'job-0001/result.json') == result
    assert [load(p) for p in sorted((path/'job-0001/checkpoints').glob('*.json'))] == cps
    replays[path.name] = dict(trace=row, counters=counters)
assert len(replays) == 2
breakdowns = {}
for name in ('warm-deep', '1-deep', '2-deep', '3-deep'):
    r = diagnostics[name]['regions']; prefix = 'baseline/search/'
    get = lambda k: r[prefix+k]['wall_ns']
    expected = 312 if name.startswith('warm') else 100022
    batches = 12 if name.startswith('warm') else 3847
    assert r[prefix+'objective/prepare']['count'] == expected+1
    assert r[prefix+'objective/prepare']['failed'] == 1
    assert r[prefix+'objective/scalar']['failed'] == 1
    assert r[prefix+'scipy/minimize']['failed'] == 1
    assert all(v['failed'] == 0 for k,v in r.items() if k not in {prefix+'objective/prepare', prefix+'objective/scalar', prefix+'scipy/minimize'})
    for k, count in [('batch/parent', batches), ('batch/apply', batches), ('batch/consume', expected-batches), ('objective/value', expected), ('scalar/rf_evaluate', batches)]:
        assert r[prefix+k]['count'] == count
    sci = get('scipy/minimize')-get('batch/parent')-get('objective/scalar')-get('scipy/callback')
    terms = {
        'rf': get('rf_evaluate'), 'checkpoint': get('checkpoint'), 'mask': get('batch/mask_build'),
        'batch_vectors': get('batch/vectors'), 'batch_list': get('batch/list'),
        'batch_consume': get('batch/consume'), 'scalar_post_rf': get('scalar/post_rf'),
        'objective_prepare': get('objective/prepare'), 'objective_value': get('objective/value'),
        'objective_state': get('objective/state'), 'scipy_callback': get('scipy/callback'),
        'scipy_dispatch_residual': sci,
        'objective_wrapper_residual': get('objective/batch')+get('objective/scalar')-sum(get(k) for k in ('objective/prepare','objective/raw_scalar','objective/raw_batch','objective/value','objective/state')),
        'scalar_raw_other': get('objective/raw_scalar')-get('scalar/rf_evaluate')-get('scalar/post_rf'),
        'batch_raw_other': get('objective/raw_batch')-get('batch/consume'),
        'batch_rf_other': get('batch/residuals')-get('batch/mask_build')-(get('rf_evaluate')-get('scalar/rf_evaluate')),
        'batch_apply_dispatch': get('batch/apply')-get('objective/batch'),
        'batch_other': get('batch/parent')-sum(get(k) for k in ('batch/list','batch/vectors','batch/residuals','batch/apply','batch/group_callback')),
        'callbacks_and_solver_other': get('batch/group_callback')+get('solver')-get('scipy/minimize')-get('checkpoint'),
    }
    assert all(v >= 0 for v in terms.values()), (name, terms)
    assert sum(terms.values()) == get('solver')
    breakdowns[name] = dict(solver_ns=get('solver'), exclusive_ns=terms)
measured = [r for r in rows if not r['trace'] and not r['name'].startswith('warm-')]
summary = {}
for mode in ('plain','timed','deep'):
    values = [r['runner_wall_s'] for r in measured if r['mode'] == mode]
    summary[mode] = dict(median=statistics.median(values), minimum=min(values), maximum=max(values), sample_sd=statistics.stdev(values))
print(json.dumps(dict(environment=load(root/'environment.json'), rows=rows, summary=summary,
    result_identity=dict(source=result['source'], source_sha256=result['source_sha256'], plan_sha256=result['plan_sha256'], rf_profile=result['rf_profile'], initial_vector_sha256=result['initial_vector_sha256'], grids=result['plan']['grids'], costs=result['costs'], stop=result['steps'][0]['stop_reason'], checkpoints=checkpoint_counts, trace_sha256=trace[0]['trace_sha256'], cache=caches[0], terminal_finite_spd_passivity_power_mna=True),
    cache_replays=replays, diagnostics=diagnostics, exclusive=breakdowns), indent=2, allow_nan=False))

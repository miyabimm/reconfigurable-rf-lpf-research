#!/usr/bin/env python3
"""Verify #491 raw runs, then emit an aggregate; see report.md for formulas."""
import json
import math
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]
preflight, run, cache_plain, cache_deep = map(Path, sys.argv[1:5])
load = lambda path: json.loads(path.read_text())
rows = [json.loads(x) for x in (preflight/'measurements.jsonl').read_text().splitlines()]
assert len(rows) == 14 and all(r['exit_code'] == 0 and r['status'] == 'completed' for r in rows)
for r in rows:
    result = load(preflight/r['name']/'job-0001/result.json')
    assert result['costs']['search_forwards'] == 312
    assert result == load(preflight/'1-plain/job-0001/result.json')
trace = [r for r in rows if r['trace']]
assert len(trace) == 2 and trace[0]['callbacks'] == trace[1]['callbacks'] == 312
assert trace[0]['trace_sha256'] == trace[1]['trace_sha256']
pre = {}
for name in ('1-deep', '2-deep', '3-deep'):
    regions = load(preflight/(name+'.timing.json'))['jobs'][0]['regions']
    assert all(v['failed'] == 0 for v in regions.values())
    prefix = 'baseline/search/'
    keys = ['solver', 'rf_evaluate', 'checkpoint', 'batch/mask_build', 'batch/vectors',
            'batch/consume', 'objective/value', 'objective/state', 'objective/group_callback']
    pre[name] = {k: regions[prefix+k] for k in keys}
    for k, count in [('batch/vectors', 12), ('batch/consume', 300),
                     ('objective/value', 312), ('objective/state', 312), ('objective/group_callback', 12)]:
        assert pre[name][k]['count'] == count
    assert pre[name]['objective/group_callback']['wall_ns'] <= pre[name]['objective/state']['wall_ns']
regions = load(preflight/'1-timed.timing.json')['jobs'][0]['regions']
assert not any('/objective/' in k or k.endswith(('batch/vectors', 'batch/consume')) for k in regions)

# The earlier analyzer verifies each receipt/file hash, result/checkpoint equality,
# MNA/passivity/SPD, all timing failures, and the 100022-candidate trace.
a = json.loads(subprocess.check_output([sys.executable, str(ROOT/'project/diagnostics/issue487/analyze.py'), str(run)]))
all_caches = [d['steps']['search']['rf_cache']['counters'] for name, d in a['diagnostics'].items()
              if not name.startswith('warm-')]
assert all(c == all_caches[0] for c in all_caches)
assert all_caches[0]['lk_hits'] == 73102 and all_caches[0]['lk_misses'] == 26920
assert all_caches[0]['computed_samples'] == 4308640
result = load(run/'1-deep/job-0001/result.json')
assert result['rf_profile']['effective_sha256'] == 'd50e6c9fef3e41b8258c00cbd14436a3bcb1d84444d50cf4a445ccf5d288e417'
checkpoints = [load(p)['forward_count'] for p in sorted((run/'1-deep/job-0001/checkpoints').glob('*.json'))]
assert len(checkpoints) == 99 and all(n % 26 == 0 for n in checkpoints)
# The separate replay exposes counters without adding timers to plain.
cache_replays = {}
for path in (cache_plain, cache_deep):
    lines = Path(str(path)+'.log').read_text().splitlines()
    trace_row, counters = map(json.loads, lines)
    assert trace_row['callbacks'] == 100022 and trace_row['trace_sha256'] == a['rows'][-1]['trace_sha256']
    assert counters['search_cache'] == all_caches[0]
    assert load(path/'job-0001/result.json') == result
    expected = [load(p) for p in sorted((run/'1-deep/job-0001/checkpoints').glob('*.json'))]
    replay_checkpoints = [load(p) for p in sorted((path/'job-0001/checkpoints').glob('*.json'))]
    assert replay_checkpoints == expected
    cache_replays[path.name] = dict(trace=trace_row, **counters)

candidate = result['terminal']['candidates'][0]
response = candidate['response']
def check_finite(value):
    if isinstance(value, dict):
        for v in value.values(): check_finite(v)
    elif isinstance(value, list):
        for v in value: check_finite(v)
    else:
        assert isinstance(value, (int, float)) and math.isfinite(value)
for key in ('s', 'il_db', 'apl_db', 'in_rl_db', 'out_rl_db'):
    assert len(response[key]) == 476
    check_finite(response[key])
for spot in candidate['independent']['spots']:
    for key in ('il_db', 'apl_db', 'in_rl_db', 'out_rl_db'):
        assert abs(response[key][spot['index']] - spot['reference'][key]) <= 1e-9
    for row, reference_row in zip(response['s'][spot['index']], spot['reference']['s'], strict=True):
        for actual, reference in zip(row, reference_row, strict=True):
            assert abs(complex(actual['real'], actual['imag']) - complex(reference['real'], reference['imag'])) <= 1e-9
breakdown = {}
for name in ('1-deep', '2-deep', '3-deep'):
    r = a['diagnostics'][name]['regions']
    get = lambda k: r['baseline/search/'+k]['wall_ns']
    for k, count in [('batch/vectors', 3847), ('batch/consume', 96175),
                     ('objective/value', 100022), ('objective/state', 100022), ('objective/group_callback', 3847)]:
        assert r['baseline/search/'+k]['count'] == count
    original = get('solver') - get('rf_evaluate') - get('checkpoint') - get('batch/mask_build')
    # D/group_callback is wholly inside D and covers any D/checkpoint overlap.
    remaining = original - get('batch/vectors') - get('batch/consume') - get('objective/value') - get('objective/state') + get('objective/group_callback')
    assert remaining > 0
    breakdown[name] = dict(original_residual_ns=original, conservative_residual_ns=remaining)
a['issue491'] = dict(preflight_environment=load(preflight/'environment.json'), preflight_rows=rows,
    preflight_regions=pre, preflight_trace_sha256=trace[0]['trace_sha256'], breakdown=breakdown,
    cache_counters=all_caches[0], cache_replays=cache_replays, checkpoint_forward_counts=checkpoints,
    terminal_finite_476_and_mna_rechecked=True,
    rf_profile=result['rf_profile'], initial_vector_sha256=result['initial_vector_sha256'],
    grid_sha256={k:v['sha256'] for k,v in result['plan']['grids'].items()}, source=result['source'])
print(json.dumps(a, indent=2, allow_nan=False))

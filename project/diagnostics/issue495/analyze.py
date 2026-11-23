#!/usr/bin/env python3
"""Verify all retained run receipts and numerical equality, excluding provenance."""
import hashlib
import json
import math
from pathlib import Path
import statistics
import sys

load = lambda p: json.loads(p.read_text())
rows = []
reference_result = reference_cps = reference_trace = reference_cache = None
for directory in map(Path, sys.argv[1:]):
    batch = [json.loads(line) for line in (directory/'measurements.jsonl').read_text().splitlines()]
    assert len(batch) == 10
    for row in batch:
        assert row['exit_code'] == 0 and row['status'] == 'completed'
        path = directory/row['name']; run = load(path/'run.json'); job = run['jobs'][0]
        assert run['status'] == job['status'] == 'completed'
        assert hashlib.sha256((path/'plan.json').read_bytes()).hexdigest() == run['plan_raw']['sha256']
        raw = path/job['raw_path']; receipt = load(raw/'receipt.json')
        for name, info in job['raw'].items():
            data = (raw/name).read_bytes()
            assert len(data) == info['bytes'] and hashlib.sha256(data).hexdigest() == info['sha256']
        assert receipt['files'] == {k: v for k, v in job['raw'].items() if k != 'receipt.json'}
        result = load(raw/'result.json')
        cps = [load(p) for p in sorted((raw/'checkpoints').glob('*.json'))]
        if row['count'] == 100000:
            result.pop('source'); result.pop('source_sha256')
            for cp in cps: cp.pop('source_sha256')
            if reference_result is None: reference_result, reference_cps = result, cps
            assert result == reference_result and cps == reference_cps, row['name']
            if row['trace']:
                assert row['callbacks'] == 100022
                if reference_trace is None: reference_trace, reference_cache = row['trace_sha256'], row['cache']
                assert row['trace_sha256'] == reference_trace and row['cache'] == reference_cache
        rows.append(dict(session=directory.name, **row))
r = reference_result
assert len(reference_cps) == 99
assert r['rf_profile']['effective_sha256'] == 'd50e6c9fef3e41b8258c00cbd14436a3bcb1d84444d50cf4a445ccf5d288e417'
assert r['costs']['search_forwards'] == 100022
assert r['steps'][0]['stop_reason'] == 'evaluation_budget_exhausted'
assert (reference_cache['lk_hits'], reference_cache['lk_misses'], reference_cache['computed_samples']) == (73102, 26920, 4308640)
c = r['terminal']['candidates'][0]; response = c['response']
assert c['independent']['status'] == 'pass' and c['physical']['min_L_eigenvalue_H'] > 0
assert c['physical']['checked_settings'] == 6 and c['physical']['component_policy_pass']
assert c['external_passivity'] == c['power_balance'] == 'checked_on_terminal_grid'
def finite(v):
    if isinstance(v, dict): return all(finite(x) for x in v.values())
    if isinstance(v, list): return all(finite(x) for x in v)
    return isinstance(v, (int, float)) and math.isfinite(v)
for k in ('s', 'il_db', 'apl_db', 'in_rl_db', 'out_rl_db'):
    assert len(response[k]) == 476 and finite(response[k])
assert [s['index'] for s in c['independent']['spots']] == [0, 111]
for spot in c['independent']['spots']:
    for k in ('il_db', 'apl_db', 'in_rl_db', 'out_rl_db'):
        assert abs(response[k][spot['index']] - spot['reference'][k]) <= 1e-9
    for a, b in zip(response['s'][spot['index']], spot['reference']['s'], strict=True):
        for x, y in zip(a, b, strict=True):
            assert abs(complex(x['real'], x['imag']) - complex(y['real'], y['imag'])) <= 1e-9
summary = {}
for session in {row['session'] for row in rows}:
    summary[session] = {}
    for variant in ('A', 'B'):
        v = [x['runner_wall_s'] for x in rows if x['session'] == session and x['variant'] == variant and x['count'] == 100000 and not x['trace']]
        summary[session][variant] = dict(median=statistics.median(v), min=min(v), max=max(v), sample_sd=statistics.stdev(v))
print(json.dumps(dict(environments={p.name: load(p/'environment.json') for p in map(Path, sys.argv[1:])}, rows=rows, summary=summary,
                      trace_sha256=reference_trace, cache=reference_cache, costs=r['costs'],
                      stop=r['steps'][0]['stop_reason'], checkpoints=len(reference_cps),
                      source_excluded_from_comparison=True, rf_profile=r['rf_profile'],
                      plan_sha256=r['plan_sha256'], initial_vector_sha256=r['initial_vector_sha256'],
                      grid_sha256={k:v['sha256'] for k,v in r['plan']['grids'].items()},
                      terminal_finite_spd_passivity_power_mna=True), indent=2, allow_nan=False))

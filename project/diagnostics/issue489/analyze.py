#!/usr/bin/env python3
"""Check plain A/B, receipts, trajectories, checkpoints, and deep counters."""
import hashlib
import json
from pathlib import Path
import sys

plain, deep = map(Path, sys.argv[1:])
load = lambda p: json.loads(p.read_text())
sha = lambda b: hashlib.sha256(b).hexdigest()
rows = [json.loads(s) for s in (plain/'measurements.jsonl').read_text().splitlines()]
assert len(rows) == 8 and all(r['exit_code'] == 0 and r['status'] == 'completed' for r in rows)
refs = {}
for parent, names in ((plain, [r['name'] for r in rows]), (deep, ['A', 'B'])):
    for name in names:
        p = parent/name
        run = load(p/'run.json'); job = run['jobs'][0]
        assert run['status'] == job['status'] == 'completed'
        assert sha((p/'plan.json').read_bytes()) == run['plan_raw']['sha256']
        raw = p/job['raw_path']
        receipt = load(raw/'receipt.json')
        for file, info in job['raw'].items():
            data = (raw/file).read_bytes()
            assert len(data) == info['bytes'] and sha(data) == info['sha256']
        assert receipt['files'] == {k:v for k,v in job['raw'].items() if k != 'receipt.json'}
        result = load(raw/'result.json')
        candidate = result['terminal']['candidates'][0]
        assert candidate['independent']['status'] == 'pass'
        assert candidate['external_passivity'] == candidate['power_balance'] == 'checked_on_terminal_grid'
        assert candidate['physical']['component_policy_pass'] and candidate['physical']['min_L_eigenvalue_H'] > 0
        source = result.pop('source_sha256'); result.pop('source')
        checkpoints = []
        for file in sorted((raw/'checkpoints').glob('*.json')):
            checkpoint = load(file)
            assert checkpoint.pop('source_sha256') == source
            checkpoints.append(checkpoint)
        key = 'warm' if name.startswith('warm-') else 'run'
        if key in refs:
            assert refs[key] == (result, checkpoints), name
        else:
            refs[key] = (result, checkpoints)
a, b = (load(deep/(tag+'.timing.json'))['jobs'][0] for tag in 'AB')
counters = [d['steps']['search']['rf_cache']['counters'] for d in (a, b)]
assert counters[0] == counters[1]
regions = []
for d in (a, b):
    r = d['regions']; pre = 'baseline/search/rf/'
    names = ('batch', 'batch/decode', 'batch/decode_lk', 'batch/matrices', 'matrices')
    v = {name:r[pre+name] for name in names}
    assert all(item['failed'] == 0 for item in v.values())
    assert v['batch/decode']['count'] == v['batch']['count']
    assert v['batch/matrices']['count'] + v['matrices']['count'] == counters[0]['lk_misses']
    regions.append(v)
traces = [load(deep/(tag+'.log')) for tag in 'AB']
assert traces[0]['trace_sha256'] == traces[1]['trace_sha256']
assert traces[0]['callbacks'] == traces[1]['callbacks'] == 100022
result, checkpoints = refs['run']
print(json.dumps(dict(environment=load(plain/'environment.json'), rows=rows,
                      costs=result['costs'], ledger=result['ledger'],
                      stop=result['steps'][0]['stop_reason'], checkpoints=len(checkpoints),
                      counters=counters[0], deep_regions=regions, trace=traces,
                      results_equal_excluding_source=True, checkpoints_equal_excluding_source=True), indent=2))

#!/usr/bin/env python3
"""Verify retained run receipts and summarize #487 without running RF."""
import hashlib
import json
from pathlib import Path
import statistics
import sys

root = Path(sys.argv[1])
load = lambda path: json.loads(path.read_text())
sha = lambda data: hashlib.sha256(data).hexdigest()
rows = [json.loads(line) for line in (root/'measurements.jsonl').read_text().splitlines()]
assert len(rows) == 14 and all(r['exit_code'] == 0 and r['status'] == 'completed' for r in rows)
refs = {}; diagnostics = {}
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
    result = load(raw/'result.json'); candidate = result['terminal']['candidates'][0]
    assert candidate['independent']['status'] == 'pass'
    assert candidate['external_passivity'] == candidate['power_balance'] == 'checked_on_terminal_grid'
    assert candidate['physical']['component_policy_pass'] and candidate['physical']['min_L_eigenvalue_H'] > 0
    checkpoints = [(c['forward_count'], c['observation']) for c in
                   (load(p) for p in sorted((raw/'checkpoints').glob('*.json')))]
    key = 'warm' if row['name'].startswith('warm-') else 'run'
    value = (result, checkpoints)
    if key in refs: assert value == refs[key], row['name']
    else: refs[key] = value
    row.update(search_forwards=result['costs']['search_forwards'],
               requested_samples=result['costs']['search_requested_samples'],
               plan_sha256=result['plan_sha256'], source_sha256=result['source_sha256'],
               final_vector_sha256=candidate['vector_sha256'], checkpoints=len(checkpoints),
               stop=result['steps'][0]['stop_reason'])
    if row['mode'] != 'plain':
        diag = load(root/(row['name']+'.timing.json'))
        assert diag['status'] == 'completed'
        diagnostics[row['name']] = diag['jobs'][0]
trace = [r for r in rows if r['trace']]
assert len(trace)==2 and trace[0]['callbacks']==trace[1]['callbacks'] == 100022
assert trace[0]['trace_sha256'] == trace[1]['trace_sha256']
batch_breakdown = {}
for name, diag in diagnostics.items():
    if name.endswith('deep'):
        regions = diag['regions']; n = regions['baseline/search/rf/batch']['count']
        for suffix in ('decode_lk','select','stamp','schur_solve','schur_update','y_to_s','output'):
            v = regions['baseline/search/rf/batch/'+suffix]
            assert v['count']==n and v['failed']==0
        assert regions['baseline/search/batch/mask_build']['count']==n
        assert all(v['failed']==0 for v in regions.values())
        prefix = 'baseline/search/rf/'
        if prefix+'batch/decode' in regions:  # older measurement HEADs lack these children
            total = regions[prefix+'batch/decode_lk']
            decode = regions[prefix+'batch/decode']
            matrices = regions.get(prefix+'batch/matrices', dict(count=0, wall_ns=0, failed=0))
            scalar_matrices = regions.get(prefix+'matrices', dict(count=0))
            counters = diag['steps']['search']['rf_cache']['counters']
            assert decode['count']==n and matrices['count'] + scalar_matrices['count']==counters['lk_misses']
            residual = total['wall_ns'] - decode['wall_ns'] - matrices['wall_ns']
            assert residual >= 0
            batch_breakdown[name] = dict(decode_lk=total, decode=decode, matrices=matrices,
                                         residual_wall_ns=residual,
                                         residual_mean_ns_per_batch=residual/n)
measured = [r for r in rows if not r['trace'] and not r['name'].startswith('warm-')]
summary = {}
for mode in ('plain','timed','deep'):
    values = [r['runner_wall_s'] for r in measured if r['mode']==mode]
    summary[mode] = dict(median=statistics.median(values), mean=statistics.mean(values),
                         minimum=min(values), maximum=max(values), sample_sd=statistics.stdev(values))
result, checkpoints = refs['run']; c = result['terminal']['candidates'][0]
print(json.dumps(dict(environment=load(root/'environment.json'), rows=rows, summary=summary,
    scientific=dict(results_and_checkpoints_equal=True, trace_equal=True, costs=result['costs'],
                    ledger=result['ledger'], stop=result['steps'][0]['stop_reason'],
                    solver_result=result['steps'][0]['solver_result'], local_run_details=result['steps'][0]['local_run_details'],
                    terminal_status=result['terminal']['status'], terminal_signed_max_margin_db=c['terminal_signed_max_margin_db'],
                    independent=c['independent'], external_passivity=c['external_passivity'], power_balance=c['power_balance'],
                    physical=c['physical'], checkpoints=len(checkpoints)),
    diagnostics=diagnostics, batch_decode_lk_breakdown=batch_breakdown), indent=2, allow_nan=False))

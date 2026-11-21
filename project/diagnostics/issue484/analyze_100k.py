#!/usr/bin/env python3
"""Audit and summarize the 18 plain runs, without running any RF forwards."""
import hashlib
import json
from pathlib import Path
import statistics
import sys

import numpy as np
from scipy import stats

root = Path(sys.argv[1])
load = lambda p: json.loads(p.read_text())
sha = lambda b: hashlib.sha256(b).hexdigest()
rows = [json.loads(x) for x in (root/'measurements.jsonl').read_text().splitlines() if not x.startswith('{"name": "warm-')]
assert len(rows) == 18
results, checkpoints = {}, {}
for row in rows:
    d = root/row['name']; run = load(d/'run.json'); job = run['jobs'][0]
    assert row['exit_code'] == 0 and run['status'] == job['status'] == 'completed'
    assert sha((d/'plan.json').read_bytes()) == run['plan_raw']['sha256']
    j = d/job['raw_path']; receipt = load(j/'receipt.json')
    for name, info in job['raw'].items():
        data = (j/name).read_bytes()
        assert sha(data) == info['sha256'] and len(data) == info['bytes']
    assert receipt['files'] == {k:v for k,v in job['raw'].items() if k != 'receipt.json'}
    r = load(j/'result.json'); candidate = r['terminal']['candidates'][0]
    assert candidate['independent']['status'] == 'pass'
    assert candidate['external_passivity'] == candidate['power_balance'] == 'checked_on_terminal_grid'
    assert candidate['physical']['component_policy_pass'] and candidate['physical']['min_L_eigenvalue_H'] > 0
    cs = [load(p) for p in sorted((j/'checkpoints').glob('*.json'))]
    observations = [(c['forward_count'], c['observation']) for c in cs]
    mode = row['mode']
    if mode in results:
        assert r == results[mode] and observations == checkpoints[mode]
    else:
        results[mode] = r; checkpoints[mode] = observations
    row.update(runner_wall_s=json.loads((root/row['log']).read_text().splitlines()[-1])['runner_wall_s'],
               search_forwards=r['costs']['search_forwards'], requested_samples=r['costs']['search_requested_samples'],
               stop=r['steps'][0]['stop_reason'], local_runs=r['steps'][0]['local_runs'],
               terminal_J=candidate['terminal_signed_max_margin_db'], initial_sha=r['initial_vector_sha256'],
               final_sha=candidate['vector_sha256'], plan_sha=r['plan_sha256'], source_sha=r['source_sha256'],
               checkpoints=len(cs))

summary = {}
for mode in 'ABC':
    rr = [r for r in rows if r['mode'] == mode]; values = np.array([r['runner_wall_s'] for r in rr])
    summary[mode] = dict(median=float(np.median(values)), mean=float(np.mean(values)), min=float(min(values)),
                         max=float(max(values)), sample_sd=float(np.std(values, ddof=1)),
                         iqr=float(np.percentile(values,75)-np.percentile(values,25)),
                         mean_ms_per_forward=float(1000*sum(values)/sum(r['search_forwards'] for r in rr)))
pairs = {}
for a,b in [('A','B'),('B','C'),('A','C')]:
    av = np.array([next(r['runner_wall_s'] for r in rows if r['name']==f'{i}-{a}') for i in range(1,7)])
    bv = np.array([next(r['runner_wall_s'] for r in rows if r['name']==f'{i}-{b}') for i in range(1,7)])
    delta = av-bv
    pairs[a+b] = dict(delta_s=delta.tolist(), ratios=(bv/av).tolist(), reduction_percent=(100*(1-bv/av)).tolist(),
        mean_delta_ci95=stats.t.interval(.95, 5, loc=np.mean(delta), scale=stats.sem(delta)),
        median_reduction_percent=100*(1-summary[b]['median']/summary[a]['median']))

def numeric_response(c):
    response = c['response']
    return {k: response[k] for k in ('s','il_db','apl_db','in_rl_db','out_rl_db')}
def flatten(x):
    if isinstance(x, dict): return sum((flatten(x[k]) for k in sorted(x)), [])
    if isinstance(x, list): return sum((flatten(i) for i in x), [])
    return [x]
a = results['A']['terminal']['candidates'][0]; b = results['B']['terminal']['candidates'][0]; c = results['C']['terminal']['candidates'][0]
diffs = {k: float(np.max(np.abs(np.array(flatten(numeric_response(a)[k]))-np.array(flatten(numeric_response(b)[k]))))) for k in numeric_response(a)}
comparison = dict(bc_solver_equal=results['B']['steps'][0]['solver_result']==results['C']['steps'][0]['solver_result'],
    bc_locals_equal=results['B']['steps'][0]['local_run_details']==results['C']['steps'][0]['local_run_details'],
    bc_terminal_equal=results['B']['terminal']==results['C']['terminal'], bc_ledger_equal=results['B']['ledger']==results['C']['ledger'],
    bc_checkpoints_equal=checkpoints['B']==checkpoints['C'], ab_checkpoints_equal=checkpoints['A']==checkpoints['B'],
    ab_common_checkpoint_equal=sum(x==y for x,y in zip(checkpoints['A'],checkpoints['B'])),
    ab_response_max_abs=diffs,
    ab_solver_vector_max_abs=float(np.max(np.abs(np.array(results['A']['steps'][0]['solver_result']['x'])-np.array(results['B']['steps'][0]['solver_result']['x'])))),
    locals={m:[{k:x[k] for k in ('nfev','nit','status','success','message')} for x in results[m]['steps'][0]['local_run_details']] for m in 'ABC'},
    ledger={m:results[m]['ledger'] for m in 'ABC'})
out = dict(environment=load(root/'environment.json'), rows=rows, summary=summary, pairs=pairs, comparison=comparison)
print(json.dumps(out, indent=2, allow_nan=False))

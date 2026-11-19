#!/usr/bin/env python3
"""Check two Issue 465 development runs and emit a paired CSV; no RF forwards."""
import csv
import hashlib
import json
import pathlib
import statistics
import sys

old, new, output = map(pathlib.Path, sys.argv[1:4])
root = pathlib.Path(__file__).resolve().parents[3]
sha = lambda b: hashlib.sha256(b).hexdigest()
load = lambda p: json.loads(p.read_bytes())
canonical = lambda x: json.dumps(x, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False).encode()
bands = list(csv.DictReader((root / 'rf/bands.csv').open()))
assert len(bands) == 28

def inspect(path, expected):
    plan = load(path / 'plan.json')
    run = load(path / 'run.json')
    assert sha(canonical(plan)) == run['plan_sha256'] == expected
    assert sha((path / 'plan.json').read_bytes()) == run['plan_raw']['sha256']
    assert run['status'] == 'completed' and len(run['jobs']) == len(plan['jobs']) == 20
    rows = []
    for j, p in zip(run['jobs'], plan['jobs']):
        assert j['status'] == 'completed' and j['seed'] == p['seed']
        d = path / j['raw_path']
        receipt = load(d / 'receipt.json')
        for name, info in j['raw'].items():
            blob = (d / name).read_bytes()
            assert sha(blob) == info['sha256'] and len(blob) == info['bytes']
        for name, info in receipt['files'].items():
            assert j['raw'][name] == info
        i, r = load(d / 'input.json'), load(d / 'result.json')
        assert i['plan_sha256'] == r['plan_sha256'] == expected
        assert i['source_sha256'] == r['source_sha256'] == run['source_sha256']
        assert i['start']['vector'] == p['vector'] == r['initial_vector']
        assert i['start']['vector_sha256'] == p['vector_sha256'] == r['initial_vector_sha256']
        c = r['terminal']['candidates'][0]
        assert c['physical']['component_policy_pass'] and c['physical']['min_L_eigenvalue_H'] > 0
        assert c['independent']['status'] == 'pass' and c['independent']['sample_indices'] == [0, 111]
        assert c['external_passivity'] == c['power_balance'] == 'checked_on_terminal_grid'
        grid = plan['grids']['terminal']; il = c['response']['il_db']; segments = grid['segment']
        assert len(il) == len(segments) == 476
        worst = max(v for v, seg in zip(il, segments) if bands[seg]['type'] == 'pass')
        stop = min(v for v, seg in zip(il, segments) if bands[seg]['type'] == 'stop')
        margin = c['terminal_signed_max_margin_db']
        assert abs(margin - max(worst - .75, 30 - stop)) < 1e-9
        assert c['performance_feasible'] == (margin <= 0)
        rows.append(dict(seed=j['seed'], J=margin, worst_il=worst, min_stop=stop,
                         local_runs=r['steps'][0]['local_runs'], stop_reason=r['steps'][0]['stop_reason'],
                         converged=r['steps'][0]['converged'], search_forwards=r['costs']['search_forwards'],
                         initial_sha=r['initial_vector_sha256'], final_sha=c['vector_sha256'],
                         input_raw_sha=j['raw']['input.json']['sha256'], result_raw_sha=j['raw']['result.json']['sha256'],
                         receipt_raw_sha=j['raw']['receipt.json']['sha256'],
                         checkpoints=sum(k.startswith('checkpoints/') for k in j['raw']),
                         min_eigenvalue=c['physical']['min_L_eigenvalue_H']))
    return plan, run, rows

op, orun, a = inspect(old, 'dc477e77ed0633047345e04f450ccd2df84bfdd3ddbb0a3395bfed1a8d0e69dd')
np, nrun, b = inspect(new, 'b32f4d3e3314cf66eeff0b60c125114de2143d13806fa43560c386755f55eb7d')
assert op['jobs'] == np['jobs'] and op['grids'] == np['grids'] and op['search_bounds'] == np['search_bounds']
rows=[]
for x,y in zip(a,b):
    assert x['seed']==y['seed'] and x['initial_sha']==y['initial_sha']
    rows.append({'seed': x['seed'], **{'old_'+k:v for k,v in x.items() if k!='seed'},
                 **{'new_'+k:v for k,v in y.items() if k!='seed'}, 'delta_J': y['J']-x['J'],
                 'delta_vs_EXP062_A6':y['J']-0.07784114846285017})
with output.open('w', newline='') as f:
    w=csv.DictWriter(f,fieldnames=rows[0].keys(),lineterminator='\n'); w.writeheader(); w.writerows(rows)
for name, data in [('old',a),('new',b)]:
    print(name,'median',statistics.median(x['J'] for x in data),'best',min((x['J'],x['seed']) for x in data),
          'pass',sum(x['J']<=0 for x in data),'search forwards',sum(x['search_forwards'] for x in data),
          'stop reasons',sorted({x['stop_reason'] for x in data}), 'checkpoints',sum(x['checkpoints'] for x in data))
print('improved',sum(r['delta_J']<0 for r in rows),'worsened',sum(r['delta_J']>0 for r in rows),
      'tied',sum(r['delta_J']==0 for r in rows))
print('new source',nrun['source_sha256'],'old source',orun['source_sha256'])
print('new ledger totals', {k:sum(j['actual'][k] for j in nrun['jobs']) for k in nrun['budget']})
print('new ledger released', {k:sum(j['released'][k] for j in nrun['jobs']) for k in nrun['budget']})
print('new ledger unknown', {k:sum(j['unknown'][k] for j in nrun['jobs']) for k in nrun['budget']})

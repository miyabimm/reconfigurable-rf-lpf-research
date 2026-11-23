#!/usr/bin/env python3
"""Check #496 receipts, A/B outputs, traces and terminal validation."""
import copy, hashlib, json, math, pathlib, statistics, sys
root=pathlib.Path(sys.argv[1]); load=lambda p: json.loads(p.read_text()); sha=lambda b: hashlib.sha256(b).hexdigest()
rows=[json.loads(s) for s in (root/'measurements.jsonl').read_text().splitlines()]
assert len(rows)==10 and all(r['exit_code']==0 and r['status']=='completed' for r in rows)
refs={}; identities={}; checkpoint_counts=[]
for row in rows:
    path=root/row['name']; run=load(path/'run.json'); job=run['jobs'][0]
    assert run['status']==job['status']=='completed'
    assert sha((path/'plan.json').read_bytes())==run['plan_raw']['sha256']
    raw=path/job['raw_path']; receipt=load(raw/'receipt.json')
    for name,info in job['raw'].items():
        data=(raw/name).read_bytes(); assert len(data)==info['bytes'] and sha(data)==info['sha256']
    assert receipt['files']=={k:v for k,v in job['raw'].items() if k!='receipt.json'}
    result=load(raw/'result.json'); cps=[load(p) for p in sorted((raw/'checkpoints').glob('*.json'))]
    identities[row['arm']]=dict(source=result['source'], source_sha256=result['source_sha256'])
    comparable=copy.deepcopy(result); comparable.pop('source'); comparable.pop('source_sha256')
    for c in cps: c.pop('source_sha256')
    key='warm' if row['name'].startswith('warm') else 'run'
    if key in refs: assert (comparable,cps)==refs[key], row['name']
    else: refs[key]=(comparable,cps)
    row.update(search_forwards=result['costs']['search_forwards'],requested_samples=result['costs']['search_requested_samples'],
               plan_sha256=result['plan_sha256'],plan_raw_sha256=run['plan_raw']['sha256'],source_sha256=result['source_sha256'],checkpoints=len(cps))
files_a=identities['A']['source']['files']; files_b=identities['B']['source']['files']
assert files_a.keys()==files_b.keys()
diffs=[k for k in files_a if files_a[k]!=files_b[k]]
assert diffs==['src/lpf/optimizers/_objectives.py'],diffs
result,cps=refs['run']; checkpoint_counts=[c['forward_count'] for c in cps]
assert len(cps)==99 and all(n%26==0 for n in checkpoint_counts)
assert result['costs']['search_forwards']==100022 and result['costs']['search_requested_samples']==7001540
assert result['rf_profile']['effective_sha256']=='d50e6c9fef3e41b8258c00cbd14436a3bcb1d84444d50cf4a445ccf5d288e417'
assert result['steps'][0]['stop_reason']=='evaluation_budget_exhausted'
trace=[r for r in rows if r['trace']]
assert len(trace)==2 and trace[0]['callbacks']==trace[1]['callbacks']==100022
assert trace[0]['trace_sha256']==trace[1]['trace_sha256'] and trace[0]['search_cache']==trace[1]['search_cache']
assert (trace[0]['search_cache']['lk_hits'],trace[0]['search_cache']['lk_misses'],trace[0]['search_cache']['computed_samples'])==(73102,26920,4308640)
candidate=result['terminal']['candidates'][0]; response=candidate['response']
assert candidate['independent']['status']=='pass'
assert candidate['external_passivity']==candidate['power_balance']=='checked_on_terminal_grid'
assert candidate['physical']['component_policy_pass'] and candidate['physical']['min_L_eigenvalue_H']>0
assert candidate['physical']['checked_settings']==6 or len(candidate['physical']['checked_settings'])==6

def finite(v):
    if isinstance(v,dict): return all(finite(x) for x in v.values())
    if isinstance(v,list): return all(finite(x) for x in v)
    return isinstance(v,(int,float)) and math.isfinite(v)
for key in ('s','il_db','apl_db','in_rl_db','out_rl_db'):
    assert len(response[key])==476 and finite(response[key])
spots=candidate['independent']['spots']; assert [s['index'] for s in spots]==[0,111]
for spot in spots:
    for key in ('il_db','apl_db','in_rl_db','out_rl_db'):
        assert abs(response[key][spot['index']]-spot['reference'][key])<=1e-9
    for a,b in zip(response['s'][spot['index']],spot['reference']['s'],strict=True):
        for x,y in zip(a,b,strict=True):
            assert abs(complex(x['real'],x['imag'])-complex(y['real'],y['imag']))<=1e-9
summary={}
for arm in 'AB':
    values=[r['runner_wall_s'] for r in rows if r['name'] in [f'{i}-{arm}' for i in range(1,4)]]
    summary[arm]=dict(mean=statistics.mean(values),median=statistics.median(values),min=min(values),max=max(values),sample_sd=statistics.stdev(values))
print(json.dumps(dict(environment=load(root/'environment.json'),rows=rows,summary=summary,micro=load(root/'micro.json'),
    source_identities=identities,source_file_differences=diffs,
    evidence=dict(result_equal_excluding_source=True,checkpoints_equal_excluding_source=True,checkpoint_counts=checkpoint_counts,
    trace_sha256=trace[0]['trace_sha256'],cache=trace[0]['search_cache'],rf_profile=result['rf_profile'],
    plan_sha256=result['plan_sha256'],initial_vector_sha256=result['initial_vector_sha256'],
    grid_sha256={k:v['sha256'] for k,v in result['plan']['grids'].items()},costs=result['costs'],ledger=result['ledger'],
    stop=result['steps'][0]['stop_reason'],solver_result=result['steps'][0]['solver_result'],
    terminal_signed_max_margin_db=candidate['terminal_signed_max_margin_db'],physical=candidate['physical'],
    independent=candidate['independent'],external_passivity=candidate['external_passivity'],power_balance=candidate['power_balance'],
    terminal_finite_all_s_il_apl_both_rl=True)),indent=2,allow_nan=False))

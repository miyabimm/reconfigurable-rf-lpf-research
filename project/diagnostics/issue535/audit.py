#!/usr/bin/env python3
"""Audit completed standard CLI evidence and compare paired results; no RF evaluation."""
import csv
import hashlib
import json
from pathlib import Path
import sys
import numpy as np

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT/'src'))
from lpf.search.storage import sha, vector_sha

RAW = Path(sys.argv[1])
PRE = Path(sys.argv[2])
OPTIONS = {'A': (1e-6, 1.0), 'B': (1e-7, 1.0), 'C': (1e-7, 'jac'), 'D': (1e-8, 'jac')}
def load(path): return json.loads(path.read_text())
def digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def entry(path): return {'bytes': path.stat().st_size, 'sha256': digest(path)}
def audit(variant):
    raw = RAW/variant
    pre = load(PRE)
    assert load(RAW/f'{variant}-execution.json')['exit'] in (0,4)
    plan, state = load(raw/'plan.json'), load(raw/'run.json')
    starts, bounds = load(OUT/'inputs/starts.json'), load(OUT/'inputs/bounds.json')
    assert plan == pre['plans'][variant]['plan'] and sha(plan) == state['plan_sha256'] == pre['plans'][variant]['plan_sha256']
    assert state['status'] == 'completed' and state['source_sha256'] == pre['source_sha256'] and state['plan_raw'] == entry(raw/'plan.json')
    assert plan['rf_profile']['effective_sha256'] == 'd50e6c9fef3e41b8258c00cbd14436a3bcb1d84444d50cf4a445ccf5d288e417'
    assert plan['search_bounds'] == bounds and plan['spot_checks'] == {'terminal':[0,111]}
    cfg = plan['config']['arms'][0]['steps'][0]
    assert (cfg['solver'],cfg['objective'],cfg['aggregation'],cfg['effective_options']) == ('trf','signed_margin_db','sum',dict(max_evaluations=20000,ftol=OPTIONS[variant][0],x_scale=OPTIONS[variant][1],restart_sigma=.1))
    assert len(plan['grids']['baseline/search']['frequency_hz']) == 70 and len(plan['grids']['terminal']['frequency_hz']) == 476
    bands = list(csv.DictReader((ROOT/'rf/bands.csv').open()))
    box = np.array(bounds); lo=box[:,0]; width=box[:,1]-lo; free=width>0
    rows=[]
    for js,jp in zip(state['jobs'],plan['jobs'],strict=True):
        job=raw/js['job_id']; seed=js['seed']
        inp,result,receipt=(load(job/f'{name}.json') for name in ('input','result','receipt'))
        assert js['status']=='completed' and js['arm']==jp['arm']=='baseline' and seed==jp['seed']==inp['seed']==result['seed']
        assert inp['plan']==result['plan']==plan and inp['plan_sha256']==result['plan_sha256']==state['plan_sha256']
        assert inp['source']==result['source']==pre['source'] and inp['source_sha256']==result['source_sha256']==state['source_sha256']
        assert js['reservation']==inp['reservation']==jp['reservation']==dict(rf_forwards=20001,rf_samples=1400476,independent_mna_samples=2)
        start=starts[str(seed)]['baseline']
        assert start==inp['start'] and start['vector_sha256']==jp['vector_sha256']==result['initial_vector_sha256']==vector_sha(result['initial_vector'])
        assert set(receipt['files'])=={'input.json','result.json'} | {f'checkpoints/{p.name}' for p in (job/'checkpoints').iterdir()}
        assert set(js['raw'])==set(receipt['files'])|{'receipt.json'}
        for name, meta in js['raw'].items():
            assert entry(job/name)==meta
            if name!='receipt.json': assert receipt['files'][name]==meta
        step=result['steps'][0]; c=result['terminal']['candidates'][0]; details=step['local_run_details']
        assert step['solver_options']==cfg['effective_options'] and step['grid_sha256']==plan['grids']['baseline/search']['sha256'] and step['rf_cache_mode']=='off'
        assert js['actual']==dict(rf_forwards=step['forward_count']+1,rf_samples=70*step['forward_count']+476,independent_mna_samples=2)
        assert step['forward_count']==20000 and sum(x['sensitivity_evaluations'] for x in details)==20000 and step['restart_count']==len(details)-1
        assert step['stop_reason']=='evaluation_budget_exhausted' and not step['converged']
        assert vector_sha(c['vector'])==c['vector_sha256'] and c['vector']==step['solver_result']['x']
        assert c['physical']['component_policy_pass'] and c['physical']['checked_settings']==6 and c['physical']['min_L_eigenvalue_H']>0 and not c['physical']['connection_role_evidence_incomplete']
        assert c['external_passivity']==c['power_balance']=='checked_on_terminal_grid'
        assert c['independent']['status']=='pass' and c['independent']['sample_indices']==[0,111]
        assert c['independent']['passivity']==c['independent']['power_balance']=='pass_at_samples'
        il,grid=c['response']['il_db'],c['response']['grid']
        assert len(il)==476 and all(grid[k]==plan['grids']['terminal'][k] for k in ('frequency_hz','segment','setting'))
        vals=lambda pred: [v for v,seg in zip(il,grid['segment'],strict=True) if pred(bands[seg])]
        margins=np.array(c['signed_margins_db']); assert np.isclose(max(margins),c['terminal_signed_max_margin_db'],rtol=0,atol=1e-12)
        rng=np.random.default_rng(seed); best=None; cumul=0; observations=[]
        for i,run in enumerate(details):
            assert run['run_index']==i
            for field in ('start_vector','best_vector','final_vector','initial_evaluated_vector'):
                assert vector_sha(run[field])==run[field+'_sha256']
            if i == 0:
                assert run['start_vector'] == start['vector']
            if i:
                center = np.array(details[i-1]['final_vector'])
                z=(center[free]-lo[free])/width[free]; expected=lo.copy()
                expected[free]=np.clip(lo[free]+np.clip(z+rng.normal(0,.1,free.sum()),0,1)*width[free],lo[free],box[free,1])
                np.testing.assert_array_equal(expected,run['start_vector'])
            cumul+=run['sensitivity_evaluations']
            if best is None or run['best_objective']<best['best_objective']: best=run
            observations.append({'forward_count':cumul,'local_best':run['best_objective'],'cumulative_best':best['best_objective'], 'optimality':run['optimality'], 'run':run})
        assert best['best_vector']==step['solver_result']['x'] and best['best_objective']==step['solver_result']['objective']
        cp=[]
        for path in sorted((job/'checkpoints').iterdir()):
            item=load(path); obs=item['observation']; assert vector_sha(obs['vector'])==obs['vector_sha256']
            assert item['plan_sha256']==state['plan_sha256'] and item['source_sha256']==state['source_sha256']
            cp.append({'forward_count':item['forward_count'],'objective':obs['objective'],'sha256':digest(path)})
        # Checkpoints are individual observations; local best is known only by local-run end.
        hits={}
        for limit in (.05,.03):
            counts=[x['forward_count'] for x in observations if x['local_best']<=limit]+[x['forward_count'] for x in cp if x['objective']<=limit]
            hits[str(limit)]=min(counts) if counts else None
        rows.append(dict(seed=seed,job_id=js['job_id'],initial_vector=start['vector'],initial_sha256=start['vector_sha256'],final_sha256=c['vector_sha256'],final_vector=c['vector'],receipt_sha256=digest(job/'receipt.json'),actual=js['actual'],terminal_J_db2=float(np.square(np.maximum(margins,0)).sum()),terminal_max_margin_db=c['terminal_signed_max_margin_db'],feasible=c['performance_feasible'],worst_il_db=max(vals(lambda b:b['type']=='pass')),min_h2_db=min(vals(lambda b:b['region']=='H2')),min_h3_db=min(vals(lambda b:b['region']=='H3')),search_J_db2=step['solver_result']['objective'],local_runs=len(details),restarts=step['restart_count'],stop_reason=step['stop_reason'],converged=step['converged'],min_L_eigenvalue_H=c['physical']['min_L_eigenvalue_H'],local_observations=observations,checkpoints=cp,threshold_upper_bound_forward=hits,local_wall_s=sum(r['wall_s'] for r in details),job_input_to_receipt_s=(job/'receipt.json').stat().st_mtime-(job/'input.json').stat().st_mtime))
    assert len(rows)==8
    return {'head':pre['head'],'plan_sha256':state['plan_sha256'],'source_sha256':state['source_sha256'],'run_sha256':digest(raw/'run.json'),'execution':load(RAW/f'{variant}-execution.json'),'rows':rows,'actual':{k:sum(r['actual'][k] for r in rows) for k in rows[0]['actual']}}
def main():
    pre=load(PRE); manifest=load(OUT/'inputs/manifest.json')
    assert digest(OUT/'inputs/manifest.json') == pre['input_manifest_sha256']
    for name, expected in manifest['files_sha256'].items(): assert digest(OUT/'inputs'/name)==expected
    results={v:audit(v) for v in OPTIONS}
    assert all(x['actual']==dict(rf_forwards=160008,rf_samples=11203808,independent_mna_samples=16) for x in results.values())
    metrics=('terminal_max_margin_db','terminal_J_db2','worst_il_db','min_h2_db','min_h3_db','search_J_db2')
    def summary(values):
        a=np.array(values); return dict(zip(('min','q1','median','q3','max'),map(float,np.quantile(a,[0,.25,.5,.75,1])),strict=True))
    stats={v:{k:summary([r[k] for r in data['rows']]) for k in metrics} for v,data in results.items()}
    pairs={}
    for v in OPTIONS:
        pairs[v]=[]
        for a,b in zip(results['A']['rows'],results[v]['rows'],strict=True):
            assert a['seed']==b['seed'] and a['initial_sha256']==b['initial_sha256']
            pairs[v].append({'seed':a['seed'],'delta_from_A':{k:b[k]-a[k] for k in metrics}})
            obs=[(x['forward_count'],x['local_best']) for x in b['local_observations']]+[(x['forward_count'],x['objective']) for x in b['checkpoints']]
            b['observed_best_by_forward']={str(n):min((j for f,j in obs if f<=n),default=None) for n in (5000,10000,15000,20000)}
    report={'conditions':results,'paired_deltas':pairs,'stats':stats,'notes':['Finite 476-point terminal grid, external ports; no continuous-frequency or physical-realization guarantee.', 'Selected starts only; no generalization to broad search or other budgets.', 'Checkpoint objectives are instantaneous observations, not cumulative best; local best at run end gives an upper bound for threshold crossing.', 'Terminal positive-violation sum of squares and Search objective use their respective recorded definitions; compare like-for-like only.']}
    path=Path(sys.argv[3]) if len(sys.argv)>3 else OUT/'results.json'
    assert not path.exists(); path.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    print('PASS: 32 jobs, receipt bytes, RF validations, budgets, and every seeded restart; results.json')
if __name__=='__main__': main()

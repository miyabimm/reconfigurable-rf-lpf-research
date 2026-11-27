#!/usr/bin/env python3
"""Audit standard CLI raw receipts and generate compact paired evidence; no RF evaluations."""
import csv
import gzip
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import numpy as np

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
RAW = Path(sys.argv[1])
PRE = Path(sys.argv[2])
sys.path.insert(0, str(ROOT/'src'))
from lpf.search.storage import sha, vector_sha

load = lambda p: json.loads(p.read_text())
def digest(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def entry(p): return {'bytes':p.stat().st_size,'sha256':digest(p)}
def summary(values):
    a = np.asarray(values, dtype=float)
    return dict(min=float(np.min(a)), q1=float(np.quantile(a,.25)), median=float(np.median(a)), q3=float(np.quantile(a,.75)), max=float(np.max(a)))

def main():
    pre = load(PRE); manifest = load(OUT/'inputs/manifest.json')
    assert digest(OUT/'inputs/manifest.json') == pre['input_manifest_sha256']
    for name, value in pre['files_sha256'].items(): assert digest(OUT/'inputs'/name) == value
    blob = subprocess.check_output(['git','show',manifest['source_commit']+':project/diagnostics/issue529/artifacts/stage2-plan.json.gz'],cwd=ROOT)
    old_plan = json.loads(gzip.decompress(blob))
    old_compact = json.loads(subprocess.check_output(['git','show',manifest['source_commit']+':project/diagnostics/issue529/compact-results.json'],cwd=ROOT))
    old = {r['seed']:r for r in old_compact['2']['rows']}
    starts, bounds = load(OUT/'inputs/starts.json'), load(OUT/'inputs/bounds.json')
    bands = list(csv.DictReader((ROOT/'rf/bands.csv').open()))
    results = {}
    for i in range(1,9):
        name=f'A{i}'; raw=RAW/name; plan,state=load(raw/'plan.json'),load(raw/'run.json')
        execution=load(RAW/f'{name}-execution.json'); assert execution['exit'] in (0,4)
        assert plan == pre['plans'][name]['plan'] and sha(plan) == state['plan_sha256'] == pre['plans'][name]['plan_sha256']
        assert state['status']=='completed' and state['source_sha256']==pre['source_sha256'] and state['plan_raw']==entry(raw/'plan.json')
        assert all(plan[k]==old_plan[k] for k in ('grids','rf_profile','search_bounds'))
        cfg=plan['config']['arms'][0]['steps'][0]; rows=[]
        for js,jp in zip(state['jobs'],plan['jobs'],strict=True):
            job=raw/js['job_id']; seed=js['seed']
            inp,result,receipt=(load(job/f'{n}.json') for n in ('input','result','receipt'))
            assert js['status']=='completed' and js['arm']==jp['arm']=='baseline' and seed==jp['seed']==inp['seed']==result['seed']
            assert inp['plan']==result['plan']==plan and inp['plan_sha256']==result['plan_sha256']==state['plan_sha256']
            assert inp['source']==result['source']==pre['source'] and inp['source_sha256']==result['source_sha256']==state['source_sha256']
            assert js['reservation']==inp['reservation']==jp['reservation']==dict(rf_forwards=10001,rf_samples=700476,independent_mna_samples=2)
            start=starts[str(seed)]['baseline']; orig=old[seed]
            assert start==inp['start'] and start['vector']==orig['final_vector']==result['initial_vector']
            assert start['vector_sha256']==orig['final_sha256']==jp['vector_sha256']==result['initial_vector_sha256']==vector_sha(start['vector'])
            assert set(receipt['files'])=={'input.json','result.json'}|{f'checkpoints/{p.name}' for p in (job/'checkpoints').iterdir()}
            assert set(js['raw'])==set(receipt['files'])|{'receipt.json'}
            for path,meta in js['raw'].items():
                assert entry(job/path)==meta
                if path!='receipt.json': assert receipt['files'][path]==meta
            step=result['steps'][0]; c=result['terminal']['candidates'][0]; details=step['local_run_details']
            assert step['solver_options']==cfg['effective_options'] and step['grid_sha256']==plan['grids']['baseline/search']['sha256'] and step['rf_cache_mode']=='off'
            assert js['actual']==dict(rf_forwards=step['forward_count']+1,rf_samples=70*step['forward_count']+476,independent_mna_samples=2)
            assert 1<=step['forward_count']<=10000 and step['local_runs']==len(details)==1 and step['restart_count']==0
            run=details[0]; assert run['run_index']==0 and run['sensitivity_evaluations']==step['forward_count'] and run['start_vector']==start['vector']
            for field in ('start_vector','best_vector','final_vector','initial_evaluated_vector'): assert vector_sha(run[field])==run[field+'_sha256']
            initial_delta=max(abs(a-b) for a,b in zip(run['initial_evaluated_vector'],start['vector'],strict=True))
            assert initial_delta < 1e-7 and run['best_vector']==step['solver_result']['x']==c['vector']
            assert run['best_objective']==step['solver_result']['objective'] and vector_sha(c['vector'])==c['vector_sha256']
            assert c['physical']['component_policy_pass'] and c['physical']['checked_settings']==6 and c['physical']['min_L_eigenvalue_H']>0 and not c['physical']['connection_role_evidence_incomplete']
            assert c['external_passivity']==c['power_balance']=='checked_on_terminal_grid'
            assert c['independent']['status']=='pass' and c['independent']['sample_indices']==[0,111]
            assert c['independent']['passivity']==c['independent']['power_balance']=='pass_at_samples'
            il,grid=c['response']['il_db'],c['response']['grid']
            assert len(il)==476 and all(grid[k]==plan['grids']['terminal'][k] for k in ('frequency_hz','segment','setting'))
            vals=lambda pred: [v for v,seg in zip(il,grid['segment'],strict=True) if pred(bands[seg])]
            margins=np.array(c['signed_margins_db']); assert np.isclose(max(margins),c['terminal_signed_max_margin_db'],rtol=0,atol=1e-12)
            cp=[]
            for path in sorted((job/'checkpoints').iterdir()):
                item=load(path); obs=item['observation']; assert vector_sha(obs['vector'])==obs['vector_sha256']
                assert item['plan_sha256']==state['plan_sha256'] and item['source_sha256']==state['source_sha256']
                cp.append({'forward_count':item['forward_count'],'objective':obs['objective'],'vector_sha256':obs['vector_sha256'],'sha256':digest(path)})
            rows.append(dict(seed=seed,job_id=js['job_id'],initial_vector=start['vector'],initial_sha256=start['vector_sha256'],initial_search_J_db2=orig['search_J_db2'],initial_terminal_max_margin_db=orig['terminal_max_margin_db'],initial_evaluated_max_abs_delta=initial_delta,final_sha256=c['vector_sha256'],final_vector=c['vector'],receipt_sha256=digest(job/'receipt.json'),actual=js['actual'],terminal_J_db2=float(np.square(np.maximum(margins,0)).sum()),terminal_max_margin_db=c['terminal_signed_max_margin_db'],feasible=c['performance_feasible'],worst_il_db=max(vals(lambda b:b['type']=='pass')),min_h2_db=min(vals(lambda b:b['region']=='H2')),min_h3_db=min(vals(lambda b:b['region']=='H3')),search_J_db2=step['solver_result']['objective'],search_improvement_db2=orig['search_J_db2']-step['solver_result']['objective'],local_runs=1,restarts=0,stop_reason=step['stop_reason'],converged=step['converged'],min_L_eigenvalue_H=c['physical']['min_L_eigenvalue_H'],local_run=run,checkpoints=cp,job_input_to_receipt_s=(job/'receipt.json').stat().st_mtime-(job/'input.json').stat().st_mtime))
        assert len(rows)==8
        results[name]=dict(plan_sha256=state['plan_sha256'],run_sha256=digest(raw/'run.json'),execution=execution,rows=rows,actual={k:sum(r['actual'][k] for r in rows) for k in rows[0]['actual']})
    metrics=('search_J_db2','search_improvement_db2','terminal_max_margin_db','terminal_J_db2','worst_il_db','min_h2_db','min_h3_db')
    stats={name:{k:summary([r[k] for r in data['rows']]) for k in metrics} for name,data in results.items()}
    paired={}; dims={}; box=np.array(bounds); widths=box[:,1]-box[:,0]
    for name,data in results.items():
        paired[name]=[]
        for row,base in zip(data['rows'],results['A1']['rows'],strict=True):
            assert row['seed']==base['seed'] and row['initial_sha256']==base['initial_sha256']
            threshold=base['search_J_db2']; observations=[(cp['forward_count'],cp['objective']) for cp in row['checkpoints']]+[(row['local_run']['sensitivity_evaluations'],row['search_J_db2'])]
            hits=[n for n,j in observations if j<=threshold]
            paired[name].append({'seed':row['seed'],'delta_from_A1':{k:row[k]-base[k] for k in metrics},'A1_final_search_J_threshold':threshold,'observed_forward_upper_bound':min(hits) if hits else None})
        v=np.array([r['final_vector'] for r in data['rows']]); dims[name]=[{'index':j,'unit':('nH' if j<4 else 'pF' if j<8 or j>=11 else 'dimensionless k'),'min':float(v[:,j].min()),'median':float(np.median(v[:,j])),'max':float(v[:,j].max()),'range':float(np.ptp(v[:,j])),'bounds_normalized_range':float(np.ptp(v[:,j])/widths[j]) if widths[j] else None} for j in range(v.shape[1])]
    comparisons={}
    pairs=[(f'A{a}',f'A{b}') for a,b in ((1,2),(1,3),(1,4),(5,6),(5,7),(5,8),(1,5),(2,6),(3,7),(4,8))]
    for left,right in pairs:
        lr=results[left]['rows']; rr=results[right]['rows']
        assert [r['seed'] for r in lr]==[r['seed'] for r in rr]
        comparisons[f'{right}_minus_{left}']={'paired': [{'seed':a['seed'], 'delta':{k:b[k]-a[k] for k in metrics},'forward_delta':b['actual']['rf_forwards']-a['actual']['rf_forwards']} for a,b in zip(lr,rr,strict=True)], 'delta_statistics':{k:summary([b[k]-a[k] for a,b in zip(lr,rr,strict=True)]) for k in metrics}}
    totals={k:sum(v['actual'][k] for v in results.values()) for k in ('rf_forwards','rf_samples','independent_mna_samples')}
    assert totals['rf_forwards']<=640064 and totals['rf_samples']<=44830464 and totals['independent_mna_samples']==128
    output={'source_head':pre['head'],'source_sha256':pre['source_sha256'],'totals':totals,'conditions':results,'statistics':stats,'paired_vs_A1':paired,'factor_comparisons':comparisons,'coordinate_spread':dims,'notes':['Reference initial J is #529 saved search best; no additional RF forward was used to recompute it.','Checkpoint values are instantaneous; local best is observed only by local-run completion. Threshold hits are upper bounds, missing observations do not prove non-attainment.','optimality belongs to final local iterate, which can differ from retained best vector.','Trial RF-T010, finite grids, external ports; no continuous-frequency, physical-realization or global-optimality guarantee.']}
    path=Path(sys.argv[3]) if len(sys.argv)>3 else OUT/'results.json'
    assert not path.exists(); path.write_text(json.dumps(output,indent=2,allow_nan=False)+'\n')
    print('PASS 64 jobs, receipts, all bounds/source/grids, validation, local runs and budgets', totals)
if __name__=='__main__': main()

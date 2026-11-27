#!/usr/bin/env python3
"""Audit completed Issue 529 CLI jobs, rank them, and freeze next inputs; no RF forwards."""
import csv
import hashlib
import json
from pathlib import Path
import sys
import yaml
import numpy as np

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT/'project/diagnostics/issue529'
RAW = Path('/home/user/src/issue529-persistent-raw')
sys.path.insert(0, str(ROOT/'src'))
from lpf.search.component_constraints import validate_values
from lpf.search.development_plan import freeze_run
from lpf.search.plan import Loader
from lpf.search.storage import sha, vector_sha

SOURCE_SHA = 'f97c8b3de5a9bc90a5db00f4ca04a82e8e89ee5313579732732c023beb1080fb'
RF_SHA = 'd50e6c9fef3e41b8258c00cbd14436a3bcb1d84444d50cf4a445ccf5d288e417'

def load(path): return json.loads(path.read_text())
def load_audit(stage):
    import gzip
    path = OUT/f'stage{stage}-audit.json'
    if path.exists(): return load(path)
    with gzip.open(path.with_suffix('.json.gz'), 'rt') as f: return json.load(f)
def digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def save(path, data):
    assert not path.exists(), path
    path.write_text(json.dumps(data,indent=2,allow_nan=False)+'\n')
def audit(stage):
    assert stage in (1,2,3)
    inpdir = OUT/f'stage{stage}-inputs'
    raw = RAW/f'stage{stage}'
    meta = load(inpdir/'manifest.json')
    for name, expected in meta['files_sha256'].items():
        assert digest(inpdir/name) == expected, name
    plan, state = load(raw/'plan.json'), load(raw/'run.json')
    config = yaml.load((inpdir/'config.yaml').read_text(),Loader=Loader)
    starts, box = load(inpdir/'starts.json'), load(inpdir/'bounds.json')
    if stage > 1:
        previous = load_audit(stage-1)
        expected = previous['ranking'][:8 if stage == 2 else 1]
        by_seed = {r['seed']:r for r in previous['rows']}
        assert config['seeds'] == expected
        assert meta['selected_from_stage'] == stage-1
        for seed, rec in zip(expected, meta['selected'], strict=True):
            row = by_seed[seed]
            parent = load(RAW/f'stage{stage-1}'/row['job_id']/'result.json')['terminal']['candidates'][0]
            start = starts[str(seed)]['baseline']
            assert rec == dict(seed=seed, vector_sha256=row['final_sha256'], job_id=row['job_id'])
            assert start['vector'] == row['final_vector'] == parent['vector']
            assert start['vector_sha256'] == row['final_sha256'] == parent['vector_sha256'] == vector_sha(start['vector'])
    spots = meta['spot_checks']
    expected_n = 28028 if stage == 3 else 476
    search_n = 196 if stage == 3 else 70
    cap = {1:5000,2:85000,3:1000}[stage]
    assert state['status'] == 'completed' and sha(plan) == state['plan_sha256'] == meta['plan_sha256']
    assert state['source_sha256'] == SOURCE_SHA
    assert state['plan_raw'] == {'bytes':(raw/'plan.json').stat().st_size,'sha256':digest(raw/'plan.json')}
    assert plan['search_bounds'] == box == load(OUT/'stage1-inputs/bounds.json')
    assert sha(box) == plan['search_bounds_sha256'] == meta['search_bounds_sha256']
    assert plan['rf_profile']['effective_sha256'] == RF_SHA and plan['spot_checks'] == spots
    assert plan['config']['seeds'] == config['seeds'] and len(state['jobs']) == len(plan['jobs']) == len(config['seeds'])
    assert [j['seed'] for j in state['jobs']] == config['seeds']
    assert len(plan['grids']['baseline/search']['frequency_hz']) == search_n
    assert len(plan['grids']['terminal']['frequency_hz']) == expected_n
    grids = load(OUT/'preflight-grid-budget.json')['grids']
    assert plan['grids']['baseline/search']['sha256'] == grids['search3' if stage==3 else 'search12']['sha256']
    assert plan['grids']['terminal']['sha256'] == grids['terminal3' if stage==3 else 'terminal12']['sha256']
    step_cfg=plan['config']['arms'][0]['steps'][0]
    assert (step_cfg['solver'],step_cfg['objective'],step_cfg['aggregation'],step_cfg['effective_options']) == ('trf','signed_margin_db','sum',dict(max_evaluations=cap,ftol=1e-6,x_scale=1.0,restart_sigma=0.1))
    bands=list(csv.DictReader((ROOT/'rf/bands.csv').open()))
    rows=[]
    for jobstate, jobplan in zip(state['jobs'],plan['jobs'],strict=True):
        seed=jobstate['seed']; job=raw/jobstate['job_id']
        inp,result,receipt=(load(job/f'{name}.json') for name in ('input','result','receipt'))
        assert jobstate['status']=='completed' and jobstate['arm']==jobplan['arm']=='baseline'
        assert seed==jobplan['seed']==inp['seed']==result['seed']
        assert inp['plan']==plan==result['plan'] and inp['plan_sha256']==result['plan_sha256']==state['plan_sha256']
        assert jobstate['reservation']==inp['reservation']==jobplan['reservation']
        assert sha(inp['source'])==inp['source_sha256']==result['source_sha256']==SOURCE_SHA
        assert inp['source']==result['source'] and inp['source']['environment']['threads']=={k:'1' for k in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS')}
        initial=starts[str(seed)]['baseline']
        assert initial==inp['start'] and initial['vector_sha256']==jobplan['vector_sha256']==result['initial_vector_sha256']==vector_sha(result['initial_vector'])
        assert set(receipt['files'])=={'input.json','result.json'} | {f'checkpoints/{p.name}' for p in (job/'checkpoints').iterdir()}
        assert set(jobstate['raw'])==set(receipt['files'])|{'receipt.json'}
        for name,entry in jobstate['raw'].items():
            path=job/name
            assert entry=={'bytes':path.stat().st_size,'sha256':digest(path)}
            if name!='receipt.json': assert receipt['files'][name]==entry
        step=result['steps'][0]; c=result['terminal']['candidates'][0]
        assert vector_sha(c['vector'])==c['vector_sha256']
        assert step['solver_options']==step_cfg['effective_options'] and step['grid_sha256']==plan['grids']['baseline/search']['sha256']
        assert step['rf_cache_mode']=='off'
        assert jobstate['actual']==dict(rf_forwards=step['forward_count']+1,rf_samples=search_n*step['forward_count']+expected_n,independent_mna_samples=len(spots['terminal']))
        assert sum(x['scipy_nfev'] for x in step['local_run_details'])==step['forward_count']
        assert c['physical']['component_policy_pass'] and c['physical']['checked_settings']==6 and c['physical']['min_L_eigenvalue_H']>0 and not c['physical']['connection_role_evidence_incomplete']
        assert c['external_passivity']==c['power_balance']=='checked_on_terminal_grid'
        assert c['independent']['status']=='pass' and c['independent']['sample_indices']==spots['terminal']
        assert c['independent']['passivity']==c['independent']['power_balance']=='pass_at_samples'
        grid,il=c['response']['grid'],c['response']['il_db']
        assert len(il)==expected_n and all(grid[k]==plan['grids']['terminal'][k] for k in ('frequency_hz','segment','setting'))
        def vals(predicate): return [v for v,seg in zip(il,grid['segment'],strict=True) if predicate(bands[seg])]
        margins=np.asarray(c['signed_margins_db']); assert np.isclose(max(margins),c['terminal_signed_max_margin_db'],rtol=0,atol=1e-12)
        cp=[]
        for path in sorted((job/'checkpoints').iterdir()):
            item=load(path); obs=item['observation']; assert vector_sha(obs['vector'])==obs['vector_sha256']
            cp.append(dict(forward_count=item['forward_count'],objective=obs['objective'],sha256=digest(path),vector_sha256=obs['vector_sha256']))
        a=np.asarray(box); x=np.asarray(c['vector']); assert np.all(x>=a[:,0]) and np.all(x<=a[:,1])
        rows.append(dict(seed=seed,job_id=jobstate['job_id'],initial_sha256=initial['vector_sha256'],final_sha256=c['vector_sha256'],receipt_sha256=digest(job/'receipt.json'),raw=jobstate['raw'],actual=jobstate['actual'],terminal_J_db2=float(np.square(np.maximum(margins,0)).sum()),terminal_max_margin_db=c['terminal_signed_max_margin_db'],feasible=c['performance_feasible'],worst_il_db=max(vals(lambda b:b['type']=='pass')),min_h2_db=min(vals(lambda b:b['region']=='H2')),min_h3_db=min(vals(lambda b:b['region']=='H3')),search_J_db2=step['solver_result']['objective'],checkpoints=cp,local_runs=step['local_runs'],local_run_details=step['local_run_details'],restarts=step['restart_count'],stop_reason=step['stop_reason'],converged=step['converged'],min_L_eigenvalue_H=c['physical']['min_L_eigenvalue_H'],final_vector=c['vector'],boundary_distance_fraction=((x-a[:,0])/(a[:,1]-a[:,0])).tolist()))
    ranking=sorted(rows,key=lambda r:(r['terminal_max_margin_db'],r['terminal_J_db2'],r['seed']))
    return dict(stage=stage,plan_sha256=sha(plan),plan_raw_sha256=digest(raw/'plan.json'),run_sha256=digest(raw/'run.json'),source_sha256=SOURCE_SHA,rf_profile=plan['rf_profile'],bounds_sha256=plan['search_bounds_sha256'],grids={k:v['sha256'] for k,v in plan['grids'].items()},rows=rows,ranking=[r['seed'] for r in ranking]),ranking

def make_next(stage, ranking):
    next_stage=stage+1; selected=ranking[:8 if stage==1 else 1]
    config=yaml.load((OUT/'stage1-inputs/config.yaml').read_text(),Loader=Loader)
    config['seeds']=[r['seed'] for r in selected]
    cap=85000 if next_stage==2 else 1000
    search_n=70 if next_stage==2 else 196
    terminal_n=476 if next_stage==2 else 28028
    mna=2 if next_stage==2 else 84
    config['terminal_points']=17 if next_stage==2 else 1001
    config['budget']=dict(rf_samples=len(selected)*(search_n*cap+terminal_n),rf_forwards=len(selected)*(cap+1),independent_mna_samples=len(selected)*mna)
    step=config['arms'][0]['steps'][0]
    step['points_per_interval']=2 if next_stage==2 else 5
    step['stop_points_per_interval']=3 if next_stage==2 else 9
    step['options']['max_evaluations']=cap
    starts={str(r['seed']):{'baseline':dict(vector=r['final_vector'],vector_sha256=r['final_sha256'])} for r in selected}
    assert all(vector_sha(r['final_vector'])==r['final_sha256'] for r in selected)
    reference=load(OUT/'reference-compact.json')['vector_sha256']
    assert all(r['final_sha256']!=reference for r in selected)
    box=load(OUT/'stage1-inputs/bounds.json')
    spots={'terminal':[0,111] if next_stage==2 else load(OUT/'preflight-grid-budget.json')['grids']['terminal3']['spot_indices']}
    plan,d,profile,model,_=freeze_run(config,starts,root=ROOT,spot_checks=spots,search_bounds=box,checkpoint_interval=1000)
    assert profile.fingerprint==RF_SHA
    for r in selected:
        physical=validate_values(d,model.schema,r['final_vector'],json.loads(profile.base_json))
        assert physical['component_policy_pass'] and physical['min_L_eigenvalue_H']>0
    assert all(j['reservation']==dict(rf_samples=search_n*cap+terminal_n,rf_forwards=cap+1,independent_mna_samples=mna) for j in plan.data['jobs'])
    assert len(plan.data['grids']['baseline/search']['frequency_hz'])==search_n and len(plan.data['grids']['terminal']['frequency_hz'])==terminal_n
    dest=OUT/f'stage{next_stage}-inputs'; dest.mkdir(exist_ok=False)
    files={'config.yaml':yaml.safe_dump(config,sort_keys=False),'starts.json':json.dumps(starts,indent=2,allow_nan=False)+'\n','bounds.json':json.dumps(box,indent=2,allow_nan=False)+'\n'}
    for name,text in files.items(): (dest/name).write_text(text)
    manifest=dict(files_sha256={name:digest(dest/name) for name in files},plan_sha256=plan.sha256,search_bounds_sha256=plan.data['search_bounds_sha256'],spot_checks=spots,checkpoint_interval_forwards=1000,selected_from_stage=stage,selected=[dict(seed=r['seed'],vector_sha256=r['final_sha256'],job_id=r['job_id']) for r in selected])
    save(dest/'manifest.json',manifest)
    print('PASS stage',next_stage,'inputs; seeds',config['seeds'],'plan',plan.sha256)

if __name__=='__main__':
    stage=int(sys.argv[1]); assert stage in (1,2,3)
    report,ranking=audit(stage)
    save(OUT/f'stage{stage}-audit.json',report)
    if stage<3: make_next(stage,ranking)
    print('PASS audit',stage,'jobs',len(ranking),'ranking',[r['seed'] for r in ranking])

#!/usr/bin/env python3
"""Audit every raw receipt and produce compact paired #520 statistics."""
import csv
import hashlib
import json
import math
from pathlib import Path
import statistics
import sys
import numpy as np
from compare20 import ROOT, SEEDS, save
from lpf.search.storage import sha,vector_sha

METRICS=('search_J','terminal_J','terminal_max_margin_db','worst_il_db','min_h2_db','min_h3_db',
         'nfev','njev','restarts','wall_s','cpu_s')

def stats(v):
    v=np.asarray(v,dtype=float); assert len(v)==20 and np.isfinite(v).all()
    q=np.quantile(v,[0,.25,.5,.75,1])
    return dict(min=float(q[0]),q1=float(q[1]),median=float(q[2]),q3=float(q[3]),max=float(q[4]),mean=float(v.mean()))

def audit(out,row):
    path=out/f"{row['phase']}-{row['seed']}-{row['mode']}"; job=path/'job-0001'
    state=json.loads((path/'run.json').read_text()); plan=json.loads((path/'plan.json').read_text())
    result=json.loads((job/'result.json').read_text()); receipt=json.loads((job/'receipt.json').read_text())
    assert state['status']==row['status']=='completed' and sha(plan)==state['plan_sha256']==row['plan_sha256']
    assert result['source_sha256']==row['source_sha256'] and result['plan_sha256']==row['plan_sha256']
    assert result['initial_vector_sha256']==row['initial_sha']==vector_sha(result['initial_vector'])
    c=result['terminal']['candidates'][0]; assert vector_sha(c['vector'])==row['final_sha']
    assert row['result_raw_sha256']==hashlib.sha256((job/'result.json').read_bytes()).hexdigest()
    assert row['receipt_raw_sha256']==hashlib.sha256((job/'receipt.json').read_bytes()).hexdigest()
    assert set(receipt['files'])=={'input.json','result.json'}|{f'checkpoints/{p.name}' for p in (job/'checkpoints').iterdir()}
    for name,info in receipt['files'].items():
        raw=(job/name).read_bytes(); assert len(raw)==info['bytes'] and hashlib.sha256(raw).hexdigest()==info['sha256']
    step=result['steps'][0]; assert step['solver_result']['x']==c['vector']
    assert row['nfev']==step['forward_count']<=row['budget']
    assert row['actual']==dict(rf_samples=70*row['nfev']+476,rf_forwards=row['nfev']+1,independent_mna_samples=2)
    assert row['independent_status']=='pass' and row['independent_indices']==[0,111]
    assert row['external_passivity']==row['power_balance']=='checked_on_terminal_grid'
    assert row['component_pass'] and row['min_L_eigenvalue_H']>0
    assert row['terminal_J']==float(np.square(np.maximum(c['signed_margins_db'],0)).sum())
    assert math.isclose(row['terminal_max_margin_db'],max(c['signed_margins_db']),abs_tol=1e-12)
    assert c['performance_feasible']==(row['terminal_max_margin_db']<=0)


def main(directory,observer,output):
    out=Path(directory); data=json.loads((out/'summary.json').read_text()); ob=json.loads((Path(observer)/'summary.json').read_text())
    assert data['complete'] and not data['errors'] and len(data['quality'])==140 and len(data['calibration'])==16
    for row in data['calibration']+data['quality']: audit(out,row)
    assert len(ob['runs'])==12
    for r in ob['runs']:
        assert r['count']==5000 and r['best_points'][-1]['forward']==5000
        assert all(a['best_J']>=b['best_J'] for a,b in zip(r['best_points'],r['best_points'][1:]))
        path=Path(observer)/f"{r['seed']}-{r['mode']}"; job=path/'job-0001'
        state=json.loads((path/'run.json').read_text()); plan=json.loads((path/'plan.json').read_text())
        raw_result=(job/'result.json').read_bytes(); rr=json.loads(raw_result)
        receipt_bytes=(job/'receipt.json').read_bytes(); receipt=json.loads(receipt_bytes)
        assert sha(plan)==state['plan_sha256']==rr['plan_sha256']
        assert rr['initial_vector_sha256']==vector_sha(rr['initial_vector'])
        assert rr['steps'][0]['solver_result']['objective']==r['search_J']
        assert state['jobs'][0]['actual']==r['actual']
        assert set(receipt['files'])=={'input.json','result.json'}|{f'checkpoints/{p.name}' for p in (job/'checkpoints').iterdir()}
        for name,info in receipt['files'].items():
            raw=(job/name).read_bytes(); assert len(raw)==info['bytes'] and hashlib.sha256(raw).hexdigest()==info['sha256']
        r.update(plan_sha256=state['plan_sha256'],source_sha256=rr['source_sha256'],
                 initial_sha=rr['initial_vector_sha256'],final_sha=rr['terminal']['candidates'][0]['vector_sha256'],
                 result_raw_sha256=hashlib.sha256(raw_result).hexdigest(),
                 receipt_raw_sha256=hashlib.sha256(receipt_bytes).hexdigest(),
                 checkpoint_sha256={k:v['sha256'] for k,v in receipt['files'].items() if k.startswith('checkpoints/')})
    rows=data['quality']; scenarios={}
    def get(phase,mode):
        rr=[r for r in rows if r['phase']==phase and r['mode']==mode]
        assert len(rr)==20 and {r['seed'] for r in rr}==set(SEEDS)
        return sorted(rr,key=lambda r:r['seed'])
    baseline=get('fixed','base')
    for phase,mode in [('fixed','base')]+[(phase,mode) for phase in ('fixed','time') for mode in ('A','B','AB')]:
        rr=get(phase,mode); key=f'{phase}-{mode}'
        scenarios[key]={'distribution':{k:stats([r[k] for r in rr]) for k in METRICS},
            'finite_grid_feasible_count':sum(r['feasible'] for r in rr),
            'stop_reasons':{s:sum(r['stop_reason']==s for r in rr) for s in sorted({r['stop_reason'] for r in rr})}}
        if mode!='base':
            paired={}
            for k in METRICS:
                d=[a[k]-b[k] for a,b in zip(rr,baseline,strict=True)]
                # Positive is better only for H2/H3; report direction explicitly.
                direction=1 if k in ('min_h2_db','min_h3_db') else -1
                paired[k]={'difference_candidate_minus_base':stats(d),'values':d,
                           'candidate_better':sum(direction*x>0 for x in d),
                           'candidate_worse':sum(direction*x<0 for x in d),'tie':sum(x==0 for x in d)}
            scenarios[key]['paired']=paired
    profile=data['quality'][0]['rf_profile']; grids=data['quality'][0]['grid_sha256']; bounds=data['quality'][0]['bounds_sha256']
    for row in data['calibration']+rows:
        assert row['rf_profile']==profile and row['grid_sha256']==grids and row['bounds_sha256']==bounds
        del row['rf_profile'],row['grid_sha256'],row['bounds_sha256']
    result={'metadata':data['metadata'],'rf_profile':profile,'grid_sha256':grids,'bounds_sha256':bounds,
      'calibration':data['calibration'],'calibration_ratios':data['calibration_ratios'],
      'frozen_time_budgets':data['frozen_time_budgets'],'quality_runs':rows,'scenarios':scenarios,
      'observer':ob,'audit':'156 calibration+quality jobs: receipt file hashes, plan, starts, costs and Terminal checks PASS; 12 observer jobs: receipt file hashes, plan, starts, costs and best objective PASS'}
    save(Path(output),result)

if __name__=='__main__': main(*sys.argv[1:])

#!/usr/bin/env python3
"""#520 additional paired 20-seed diagnostic, no production switches or EXP.

Fresh /tmp destination only; every completed/failed job and checkpoint remains.
Calibration: 4 full warmups then 3 seeds x 4 alternating 5000-forward runs.
Before quality runs, freeze budgets by median(base wall/candidate wall) x 5000,
rounded to nearest 100, and save. Compare 5000 and approximate-time budgets.
"""
import csv
import hashlib
import json
import os
from pathlib import Path
import platform
import statistics
import subprocess
import sys
import time
import traceback

from probe import ROOT, THREADS, activate, restore
import numpy as np
import scipy
from lpf.minimax_profile import load_minimax_profile
from lpf.search import _development_runner as runner
from lpf.search.proposals import definition_from_data
from lpf.search.starts import generate_for_definition
from lpf.search.storage import sha, vector_sha

SEEDS=tuple(range(1001,1021)); CAL=(1001,1010,1020); MODES=('base','A','B','AB')


def prepare(seed, budget):
    profile=load_minimax_profile('RF-T010',root=ROOT,allow_trial=True)
    assert profile.fingerprint=='d50e6c9fef3e41b8258c00cbd14436a3bcb1d84444d50cf4a445ccf5d288e417'
    definition=json.loads((ROOT/'project/diagnostics/issue361/definition.json').read_text())
    assert sha(definition)=='bc50042a1b0b1ebf19c0272fb2ee944b52cd76e14eb8d44673bfa57f6033c068'
    record=generate_for_definition(definition_from_data(definition),json.loads(profile.base_json),seed)
    with (ROOT/'project/diagnostics/issue513/paired.csv').open() as f:
        prior={int(r['seed']):r['initial_sha'] for r in csv.DictReader(f)}
    assert set(prior)==set(SEEDS) and record['vector_sha256']==prior[seed]
    config=json.loads((ROOT/'project/diagnostics/issue470/config.json').read_text())
    config['seeds']=[seed]
    config['arms'][0]['steps'][0].update(solver='trf',options=dict(max_evaluations=budget,restart_sigma=.1,ftol=1e-6,x_scale=1.0))
    config['budget']=dict(rf_samples=70*budget+476,rf_forwards=budget+1,independent_mna_samples=2)
    starts={str(seed):{'baseline':{k:record[k] for k in ('vector','vector_sha256')}}}
    spots={'terminal':[0,111]}
    plan,_,_,_,_=runner.freeze_run(config,starts,root=ROOT,spot_checks=spots,search_bounds=None,checkpoint_interval=1000)
    assert len(plan.data['grids']['baseline/search']['frequency_hz'])==70
    assert len(plan.data['grids']['terminal']['frequency_hz'])==476
    for grid in plan.data['grids'].values():
        assert set(grid['setting'])==set(range(6)) and set(grid['segment'])==set(range(28))
    return config,starts,spots,plan


def save(path, data):
    tmp=path.with_suffix('.tmp'); tmp.write_text(json.dumps(data,indent=2,allow_nan=False)+'\n'); tmp.replace(path)


def summarize(out, state, plan, seed, mode, budget, wall, cpu):
    job=out/'job-0001'; result=json.loads((job/'result.json').read_text()); step=result['steps'][0]
    candidate=result['terminal']['candidates'][0]; response=candidate['response']; grid=response['grid']
    bands=list(csv.DictReader((ROOT/'rf/bands.csv').open()))
    il=response['il_db']; assert len(il)==len(grid['segment'])==476
    il_for=lambda pred:[v for v,seg in zip(il,grid['segment'],strict=True) if pred(bands[seg])]
    margins=np.asarray(candidate['signed_margins_db'])
    checkpoints=[]
    for path in sorted((job/'checkpoints').iterdir()):
        c=json.loads(path.read_text()); obs=c['observation']; assert vector_sha(obs['vector'])==obs['vector_sha256']
        checkpoints.append({'sha256':hashlib.sha256(path.read_bytes()).hexdigest(), 'forward_count':c['forward_count'],
                            'vector_sha256':obs['vector_sha256'],'objective':obs['objective']})
    return {'seed':seed,'mode':mode,'budget':budget,'status':state['status'],'job_status':state['jobs'][0]['status'],
      'plan_sha256':plan.sha256,'grid_sha256':{k:v['sha256'] for k,v in plan.data['grids'].items()},
      'bounds_sha256':plan.data['search_bounds_sha256'],'rf_profile':plan.data['rf_profile'],
      'initial_sha':result['initial_vector_sha256'],'final_sha':candidate['vector_sha256'],
      'result_raw_sha256':hashlib.sha256((job/'result.json').read_bytes()).hexdigest(),
      'receipt_raw_sha256':hashlib.sha256((job/'receipt.json').read_bytes()).hexdigest(),
      'source_sha256':result['source_sha256'],'search_J':step['solver_result']['objective'],
      'terminal_J':float(np.square(np.maximum(margins,0)).sum()),'terminal_max_margin_db':candidate['terminal_signed_max_margin_db'],
      'worst_il_db':max(il_for(lambda b:b['type']=='pass')),
      'min_h2_db':min(il_for(lambda b:b['region']=='H2')),'min_h3_db':min(il_for(lambda b:b['region']=='H3')),
      'feasible':candidate['performance_feasible'],'external_passivity':candidate['external_passivity'],
      'power_balance':candidate['power_balance'],'independent_status':candidate['independent']['status'],
      'independent_indices':candidate['independent']['sample_indices'],
      'component_pass':candidate['physical']['component_policy_pass'],
      'min_L_eigenvalue_H':candidate['physical']['min_L_eigenvalue_H'],
      'nfev':sum(z['scipy_nfev'] for z in step['local_run_details']),
      'njev':sum(z['scipy_njev'] for z in step['local_run_details']),
      'local_runs':step['local_runs'],'restarts':step['restart_count'],'stop_reason':step['stop_reason'],
      'converged':step['converged'],'actual':state['jobs'][0]['actual'],'wall_s':wall,'cpu_s':cpu,'checkpoints':checkpoints}


def main(directory):
    assert all(os.environ.get(k)=='1' for k in THREADS)
    out=Path(directory).resolve(); assert out.parent==Path('/tmp') and not out.exists(); out.mkdir()
    metadata={'baseline':'be0bdb2bf3662512b30408091efc3906389c1f6e',
      'head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
      'git_status':subprocess.check_output(['git','status','--porcelain'],cwd=ROOT,text=True),
      'python':sys.version,'numpy':np.__version__,'scipy':scipy.__version__,'platform':platform.platform(),
      'threads':{k:os.environ[k] for k in THREADS},'seeds':SEEDS,'calibration_seeds':CAL,
      'order':'cyclic Latin four-arm order by seed index; time arms cyclic 3-arm order; no filtering',
      'budget_rule':'median across calibration seeds of 5000 * baseline wall / candidate wall, nearest 100 before quality runs',
      'timing':'plain wall/process CPU, full runner including terminal/save; no observer'}
    data={'metadata':metadata,'calibration':[],'quality':[],'errors':[]}
    summary=out/'summary.json'; save(summary,data)
    def run(seed,mode,budget,phase):
        name=f'{phase}-{seed}-{mode}'; path=out/name
        config,starts,spots,plan=prepare(seed,budget)
        activate(mode); start=time.perf_counter(); cstart=time.process_time()
        try:
            state=runner.run(config,starts,path,root=ROOT,spot_checks=spots,checkpoint_interval=1000)
            row=summarize(path,state,plan,seed,mode,budget,time.perf_counter()-start,time.process_time()-cstart)
        except Exception as exc:
            row={'seed':seed,'mode':mode,'budget':budget,'phase':phase,'status':'error',
                 'error':repr(exc),'traceback':traceback.format_exc(),'wall_s':time.perf_counter()-start,
                 'cpu_s':time.process_time()-cstart,'raw_path':str(path)}
            data['errors'].append(row)
        row['phase']=phase
        data['quality' if phase in ('fixed','time') else 'calibration'].append(row)
        save(summary,data); print(name,row['status'],round(row['wall_s'],3),flush=True)
        return row
    # Full warmups excluded from calibration. All errors preserved; do not silently drop calibration failures.
    for mode in MODES:
        row=run(1001,mode,5000,'warmup')
        if row['status']=='error': raise RuntimeError('warmup failed; cannot calibrate')
    for i,seed in enumerate(CAL):
        order=MODES[i:]+MODES[:i]
        if i%2: order=tuple(reversed(order))
        for mode in order:
            row=run(seed,mode,5000,'calibration')
            if row['status']=='error': raise RuntimeError('calibration failed; cannot freeze budgets')
    budgets={}; ratios={}
    for mode in MODES[1:]:
        vals=[]
        for seed in CAL:
            rows=[r for r in data['calibration'] if r['phase']=='calibration' and r['seed']==seed]
            base=next(r for r in rows if r['mode']=='base'); arm=next(r for r in rows if r['mode']==mode)
            vals.append(base['wall_s']/arm['wall_s'])
        ratios[mode]=vals
        budgets[mode]=int(round(5000*statistics.median(vals)/100)*100)
    data['frozen_time_budgets']=budgets; data['calibration_ratios']=ratios; save(summary,data)
    print('FROZEN',budgets,'ratios',ratios,flush=True)
    for i,seed in enumerate(SEEDS):
        for mode in MODES[i%4:]+MODES[:i%4]: run(seed,mode,5000,'fixed')
        arms=MODES[1:]; order=arms[i%3:]+arms[:i%3]
        for mode in order: run(seed,mode,budgets[mode],'time')
    data['complete']=True; save(summary,data)

if __name__=='__main__':
    try: main(sys.argv[1])
    finally: restore()

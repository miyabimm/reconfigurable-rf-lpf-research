#!/usr/bin/env python3
"""Intrusive best-so-far observation (separate from all plain comparison runs)."""
import os
from pathlib import Path
import sys
import time
import numpy as np
from compare20 import ROOT, THREADS, prepare, save
from probe import activate,restore
from lpf.rf_core.model import RFEvaluator
from lpf.search import _development_runner as runner
from lpf.search.plan import grid_from_record
from lpf.minimax_profile import _margin_parameters, load_minimax_profile


def main(directory):
    assert all(os.environ.get(k)=='1' for k in THREADS)
    out=Path(directory).resolve(); assert out.parent==Path('/tmp') and not out.exists(); out.mkdir()
    data={'note':'intrusive observer; elapsed includes runner and observer; not plain timing; sample every 100 RF evaluations', 'runs':[]}
    for seed in (1001,1010,1020):
        config,starts,spots,plan=prepare(seed,5000)
        profile=load_minimax_profile('RF-T010',root=ROOT,allow_trial=True)
        threshold,direction=_margin_parameters(profile,grid_from_record(plan.data['grids']['baseline/search']))
        for mode in ('base','A','B','AB'):
            activate(mode); original=RFEvaluator.evaluate_with_il_jacobian
            count=[0]; best=[float('inf')]; points=[]; start=time.perf_counter()
            def observed(ev,vector):
                response,jac=original(ev,vector); count[0]+=1
                margin=direction*(response.il_db-threshold)
                j=float(np.square(np.maximum(margin,0)).sum()); best[0]=min(best[0],j)
                if count[0]==1 or count[0]%100==0:
                    points.append({'forward':count[0],'elapsed_s':time.perf_counter()-start,'best_J':best[0]})
                return response,jac
            RFEvaluator.evaluate_with_il_jacobian=observed
            try:
                state=runner.run(config,starts,out/f'{seed}-{mode}',root=ROOT,spot_checks=spots,checkpoint_interval=1000)
            finally: RFEvaluator.evaluate_with_il_jacobian=original
            import json
            r=json.loads((out/f'{seed}-{mode}'/'job-0001/result.json').read_text())
            objective=r['steps'][0]['solver_result']['objective']
            assert np.isclose(best[0],objective,rtol=1e-12,atol=1e-12)
            data['runs'].append({'seed':seed,'mode':mode,'count':count[0],'actual':state['jobs'][0]['actual'],
                                 'search_J':objective,'best_points':points})
            save(out/'summary.json',data)
            print(seed,mode,count[0],objective,flush=True)

if __name__=='__main__':
    try: main(sys.argv[1])
    finally: restore()

#!/usr/bin/env python3
"""Check production AB against fixed b87d4c1 diagnostic AB and three prior jobs.

The historical switch is reconstructed only inside this verification process
from git objects; it is never installed in the production evaluator permanently.
New Runner jobs use the production path with no timing/observer hooks.
"""
import ast
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import textwrap
import time

import numpy as np
import probe
from probe import ROOT, THREADS
from compare20 import prepare, save
from lpf.minimax_profile import least_squares_residual_and_jacobian, load_minimax_profile
from lpf.search import _development_runner as runner
from lpf.search.plan import grid_from_record
from lpf.search.storage import vector_sha

HISTORICAL = 'b87d4c1ea3a10a1d50be6f8754902521a6979506'
PROBE_SHA = 'd92d835c5c11a72636b84cb35a0092f52ef0a81f5200194809bd25dbdaaf398f'


def historical_diagnostic_source():
    path = ROOT/'project/diagnostics/issue519/probe.py'
    assert hashlib.sha256(path.read_bytes()).hexdigest() == PROBE_SHA
    source = subprocess.check_output(['git', 'show', f'{HISTORICAL}:src/lpf/rf_core/model.py'], cwd=ROOT, text=True)
    tree = ast.parse(source)
    klass = next(c for c in tree.body if isinstance(c, ast.ClassDef) and c.name == 'RFEvaluator')
    method = next(f for f in klass.body if isinstance(f, ast.FunctionDef) and f.name == 'evaluate_with_il_jacobian')
    return textwrap.dedent(''.join(source.splitlines(keepends=True)[method.lineno-1:method.end_lineno]))


def digest(array):
    return hashlib.sha256(np.ascontiguousarray(array).tobytes()).hexdigest()


def main(directory, old_directory):
    assert all(os.environ.get(k) == '1' for k in THREADS)
    out = Path(directory).resolve(); assert out.parent == Path('/tmp') and not out.exists(); out.mkdir()
    old = Path(old_directory).resolve()
    vectors = json.loads((ROOT/'project/diagnostics/issue519/vectors.json').read_text())
    probe.SOURCE = historical_diagnostic_source()
    result = {'historical_head': HISTORICAL, 'historical_probe_sha256': PROBE_SHA,
              'note':'fixed vectors compare bitwise; Runner plain production vs retained 20-seed diagnostic raw',
              'fixed': [], 'runs': []}
    save(out/'summary.json', result)
    for seed in (1001, 1010, 1020):
        config, starts, spots, plan = prepare(seed, 5000)
        profile = load_minimax_profile('RF-T010', root=ROOT, allow_trial=True)
        _, _, _, model, _ = runner.freeze_run(config, starts, root=ROOT, spot_checks=spots,
                                               search_bounds=None, checkpoint_interval=1000)
        ev = model.evaluator(grid_from_record(plan.data['grids']['baseline/search']))
        inputs = [('initial', starts[str(seed)]['baseline']['vector'])]
        inputs += [(k,v['vector']) for k,v in vectors.items() if k.startswith(str(seed)+'-')]
        for name, vector in inputs:
            x = np.asarray(vector)
            probe.activate('AB')
            try:
                reference, refjac = ev.evaluate_with_il_jacobian(x)
                refres, refrjac = least_squares_residual_and_jacobian(profile, reference, refjac)
            finally:
                probe.restore()
            actual, jac = ev.evaluate_with_il_jacobian(x)
            res, rjac = least_squares_residual_and_jacobian(profile, actual, jac)
            fields = {k:(getattr(reference,k),getattr(actual,k)) for k in ('s','il_db','apl_db','in_rl_db','out_rl_db')}
            fields.update(jac=(refjac,jac), residual=(refres,res), residual_jac=(refrjac,rjac))
            for key,(a,b) in fields.items():
                np.testing.assert_array_equal(a,b,err_msg=f'{seed} {name} {key}')
            result['fixed'].append({'seed':seed,'vector':name,'vector_sha256':vector_sha(x),
                'bitwise_equal':True,'sha256':{key:digest(b) for key,(a,b) in fields.items()}})
            save(out/'summary.json',result)
        # No candidate patch, trace, or timing collection on this Runner call.
        wall,cpu=time.perf_counter(),time.process_time()
        state=runner.run(config, starts, out/str(seed), root=ROOT, spot_checks=spots, checkpoint_interval=1000)
        wall,cpu=time.perf_counter()-wall,time.process_time()-cpu
        newjob=out/str(seed)/'job-0001'; oldjob=old/f'fixed-{seed}-AB'/'job-0001'
        new=json.loads((newjob/'result.json').read_text()); prior=json.loads((oldjob/'result.json').read_text())
        a,b=new['steps'][0],prior['steps'][0]
        for step in (a,b):
            for local in step['local_run_details']:
                local.pop('wall_s'); local.pop('cpu_s')
        assert a == b, f'{seed} step differs'
        assert new['terminal'] == prior['terminal'], f'{seed} terminal differs'
        checkpoints=[]
        old_files=sorted((oldjob/'checkpoints').iterdir()); new_files=sorted((newjob/'checkpoints').iterdir())
        assert len(old_files)==len(new_files)
        for op,npth in zip(old_files,new_files,strict=True):
            o,n=json.loads(op.read_text()),json.loads(npth.read_text())
            assert (o['sequence'],o['forward_count'],o['observation']) == (n['sequence'],n['forward_count'],n['observation'])
            checkpoints.append({'sequence':n['sequence'],'forward_count':n['forward_count'],
                'observation':n['observation'],'old_sha256':hashlib.sha256(op.read_bytes()).hexdigest(),
                'new_sha256':hashlib.sha256(npth.read_bytes()).hexdigest()})
        assert state['jobs'][0]['actual']=={'rf_forwards':5001,'rf_samples':350476,'independent_mna_samples':2}
        result['runs'].append({'seed':seed,'wall_s':wall,'cpu_s':cpu,'actual':state['jobs'][0]['actual'],
            'plan_sha256':plan.sha256,'source_sha256':new['source_sha256'],
            'prior_source_sha256':prior['source_sha256'],
            'result_sha256':hashlib.sha256((newjob/'result.json').read_bytes()).hexdigest(),
            'prior_result_sha256':hashlib.sha256((oldjob/'result.json').read_bytes()).hexdigest(),
            'step_equal_except_wall_cpu':True,'terminal_equal':True,'checkpoints':checkpoints,
            'search_objective':a['solver_result']['objective'],'selected_sha256':new['terminal']['candidates'][0]['vector_sha256'],
            'nfev':sum(z['scipy_nfev'] for z in a['local_run_details']),
            'njev':sum(z['scipy_njev'] for z in a['local_run_details']),
            'restarts':a['restart_count'],'stop_reason':a['stop_reason'],
            'terminal_mna':new['terminal']['candidates'][0]['independent']['status']})
        save(out/'summary.json',result)
        print(seed, 'fixed bitwise 3/3; step, terminal, checkpoint observations equal', round(wall,3), flush=True)
    result['status']='PASS'; save(out/'summary.json',result)


if __name__=='__main__':
    try: main(sys.argv[1],sys.argv[2])
    finally: probe.restore()

#!/usr/bin/env python3
"""Issue #499 trial-only single local pilot; not a formal experiment or runner."""
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import time
import tracemalloc

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT/'src'))
import numpy as np
import scipy
from lpf.constraint_versions import load_constraint
from lpf.minimax_profile import signed_margins, _margin_parameters
from lpf.optimizers.least_squares import least_squares_local, reported_margin_objective
from lpf.minimax_profile import signed_margin_residual
from lpf.rf_core.independent import evaluate_independent_response
from lpf.rf_core.model import build_rf_model
from lpf.search.component_constraints import _validate_values_with_bounds
from lpf.search.development_plan import freeze_run
from lpf.search.plan import grid_from_record
from lpf.search.storage import plain


def main(output):
    config = json.loads((ROOT/'project/diagnostics/issue470/config.json').read_text())
    starts = json.loads((ROOT/'project/diagnostics/issue470/starts.json').read_text())
    config['arms'][0]['steps'][0]['options'].update(max_search_forwards=100000, batch_fd=True, partial_fd=True)
    config['budget'] = dict(rf_samples=70*(100000+24)+476, rf_forwards=100025, independent_mna_samples=2)
    plan, definition, profile, model, physical_bounds = freeze_run(config, starts, root=ROOT,
        spot_checks={'terminal':[0,111]}, search_bounds=None, checkpoint_interval=1000)
    assert plan.sha256 == '0e2d62841f286281eb9b2c662382a50238f865193b16eafabf6aa3227ba18d90'
    assert profile.fingerprint == 'd50e6c9fef3e41b8258c00cbd14436a3bcb1d84444d50cf4a445ccf5d288e417'
    x0 = np.asarray(starts['1013']['baseline']['vector'])
    bounds = np.asarray(plan.data['search_bounds']); width = bounds[:,1]-bounds[:,0]
    grid = grid_from_record(plan.data['grids']['baseline/search'])
    terminal_grid = grid_from_record(plan.data['grids']['terminal'])
    evaluator = model.evaluator(grid)
    threshold, direction = _margin_parameters(profile, grid)
    metadata = dict(plan_sha256=plan.sha256, grid_sha256={k:v['sha256'] for k,v in plan.data['grids'].items()},
        profile_sha256=profile.fingerprint, profile=plan.data['rf_profile'], start=starts['1013']['baseline'],
        seed=1013, head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        git_status=subprocess.check_output(['git','status','--porcelain'],cwd=ROOT,text=True),
        source_sha256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in
            [ROOT/'src/lpf/rf_core/coupled_lc.py', ROOT/'src/lpf/rf_core/model.py', ROOT/'src/lpf/optimizers/least_squares.py', Path(__file__)]},
        python=sys.version, numpy=np.__version__, scipy=scipy.__version__, platform=platform.platform(),
        threads={k:os.environ.get(k) for k in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS')},
        loadavg=os.getloadavg())
    initial_response = evaluator.evaluate(x0)
    initial_margin = direction*(initial_response.il_db-threshold)
    observations = []
    def callback(x):
        response, jac = evaluator.evaluate_with_il_jacobian(x)
        r, j = signed_margin_residual(profile, response, jac)
        observations.append((float(.5*np.dot(r,r)), x.copy()))
        return r, j
    pilot = {'initial_search_objective': reported_margin_objective(initial_margin), 'max_nfev':100}
    try:
        result = least_squares_local(callback, x0, bounds, max_evaluations=100)
        pilot.update(plain(result))
        chosen = result.x
        pilot['state'] = 'completed' if result.success else 'not_converged'
    except Exception as exc:
        pilot.update(state='STOP', success=False, reason=f'{type(exc).__name__}: {exc}',
                     completed_sensitivity_evaluations=len(observations))
        chosen = min(observations, key=lambda q:q[0])[1] if observations else x0
        pilot['terminal_selection'] = 'best_completed_observation' if observations else 'initial'
    final = evaluator.evaluate(chosen)
    pilot['final_search_objective_legacy'] = reported_margin_objective(direction*(final.il_db-threshold))
    try:
        terminal = model.evaluator(terminal_grid).evaluate(chosen, check_power=True)
        maxmargin, margins = signed_margins(profile, terminal_grid, terminal)
        base = load_constraint('RF-T008', allow_trial=True)
        physical = _validate_values_with_bounds(definition, model.schema, chosen, base, physical_bounds,
                                                 frozen_model=build_rf_model(definition, base))
        spots = []
        for index in (0,111):
            ref = evaluate_independent_response(model, chosen, float(terminal_grid.frequency_hz[index]), int(terminal_grid.setting[index]))
            errors = {name:float(np.max(np.abs(getattr(terminal,name)[index]-ref[name]))) for name in ('s','il_db','apl_db','in_rl_db','out_rl_db')}
            spots.append(dict(index=index, errors=errors, pass_=max(errors.values()) <= 1e-9))
        pilot['terminal'] = dict(signed_max_margin_db=maxmargin, margins=margins.tolist(),
            s_real=terminal.s.real.tolist(), s_imag=terminal.s.imag.tolist(), il_db=terminal.il_db.tolist(),
            apl_db=terminal.apl_db.tolist(), in_rl_db=terminal.in_rl_db.tolist(), out_rl_db=terminal.out_rl_db.tolist(),
            power_balance='checked', physical=plain(physical), mna=spots)
    except Exception as exc:
        pilot['terminal'] = dict(status='STOP', reason=f'{type(exc).__name__}: {exc}')
    # Evaluate one complete sensitivity vs one actual batch/partial forward-FD
    # group at the same seed (base forward counted separately).
    def analytic():
        e = model.evaluator(grid)
        e.evaluate_with_il_jacobian(x0)
        return dict(rf_forwards=1, requested_samples=70, computed_samples=70)
    def partial():
        e = model.evaluator(grid, cache_mode='lk')
        base = e.evaluate(x0)
        vectors = np.tile(x0, (len(x0),1)); h=1e-8
        vectors[np.arange(len(x0)),np.arange(len(x0))] += h*width
        mask = np.ones((len(x0),len(grid.setting)), dtype=bool)
        schema = model.schema
        start = schema.n_inductors + schema.n_fixed + schema.n_coupling + schema.n_ic_fixed
        for j in range(start,len(x0)):
            mask[j] = grid.setting == (j-start)//schema.n_variable
        e.evaluate_partial_batch(vectors, base, mask)
        return dict(rf_forwards=26, requested_samples=26*70, computed_samples=e.cache_stats['computed_samples'])
    analytic(); partial()
    timings = []
    for order in (('analytic','partial'),('partial','analytic'),('analytic','partial'),('partial','analytic')):
        for name in order:
            tracemalloc.start(); wall=time.perf_counter(); cpu=time.process_time()
            counts = (analytic if name == 'analytic' else partial)()
            elapsed, cpu = time.perf_counter()-wall, time.process_time()-cpu
            _, peak = tracemalloc.get_traced_memory(); tracemalloc.stop()
            timings.append(dict(name=name,wall_s=elapsed,cpu_s=cpu,python_peak_bytes=peak,**counts))
    output.write_text(json.dumps(dict(metadata=metadata,pilot=pilot,timing=timings),indent=2,allow_nan=False)+'\n')
    print('pilot:', pilot['state'], 'timings:', len(timings), 'output:', output)


if __name__ == '__main__':
    main(Path(sys.argv[1]))

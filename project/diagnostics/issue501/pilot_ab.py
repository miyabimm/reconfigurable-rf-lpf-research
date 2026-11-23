#!/usr/bin/env python3
"""Alternating single-start TRF pilots; development diagnostic, not an EXP."""
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT/'src'))
import numpy as np
import scipy
import bench
import lpf.rf_core.model as rfmodel
from lpf.constraint_versions import load_constraint
from lpf.minimax_profile import _margin_parameters, signed_margins
from lpf.optimizers.least_squares import least_squares_local, signed_margin_residual, reported_margin_objective
from lpf.rf_core.independent import evaluate_independent_response
from lpf.rf_core.model import build_rf_model
from lpf.search.component_constraints import _validate_values_with_bounds
from lpf.search.development_plan import freeze_run
from lpf.search.plan import grid_from_record
from lpf.search.storage import plain


def main(output):
    base = '58573e2573867dc095e38d8995c29626d9ec32cd'
    path = 'src/lpf/rf_core/model.py'
    original = subprocess.check_output(['git','show',f'{base}:{path}'],cwd=ROOT,text=True)
    candidate = (ROOT/path).read_text()
    implementations = {label: bench.methods(text, 'RFEvaluator', ['evaluate_with_il_jacobian'], vars(rfmodel))['evaluate_with_il_jacobian']
                       for label, text in [('base', original), ('candidate', candidate)]}
    config = json.loads((ROOT/'project/diagnostics/issue470/config.json').read_text())
    starts = json.loads((ROOT/'project/diagnostics/issue470/starts.json').read_text())
    config['arms'][0]['steps'][0]['options'].update(max_search_forwards=100000, batch_fd=True, partial_fd=True)
    config['budget'] = dict(rf_samples=70*(100000+24)+476, rf_forwards=100025, independent_mna_samples=2)
    plan, definition, profile, model, physical_bounds = freeze_run(config, starts, root=ROOT,
        spot_checks={'terminal':[0,111]}, search_bounds=None, checkpoint_interval=1000)
    assert plan.sha256 == '0e2d62841f286281eb9b2c662382a50238f865193b16eafabf6aa3227ba18d90'
    assert profile.fingerprint == 'd50e6c9fef3e41b8258c00cbd14436a3bcb1d84444d50cf4a445ccf5d288e417'
    x0 = np.asarray(starts['1013']['baseline']['vector'])
    bounds = np.asarray(plan.data['search_bounds'])
    search = grid_from_record(plan.data['grids']['baseline/search'])
    terminal_grid = grid_from_record(plan.data['grids']['terminal'])
    evaluator = model.evaluator(search)
    terminal_eval = model.evaluator(terminal_grid)
    threshold, direction = _margin_parameters(profile, search)
    rows = []
    # Warm up each kernel, without running the solver.
    for label in implementations:
        rfmodel.RFEvaluator.evaluate_with_il_jacobian = implementations[label]
        evaluator.evaluate_with_il_jacobian(x0)
    for label in ('base','candidate','candidate','base'):
        rfmodel.RFEvaluator.evaluate_with_il_jacobian = implementations[label]
        trajectory = []
        def callback(x):
            response, jac = evaluator.evaluate_with_il_jacobian(x)
            residual, rjac = signed_margin_residual(profile, response, jac)
            trajectory.append(dict(x=x.tolist(), objective=float(.5*np.dot(residual,residual))))
            return residual, rjac
        try:
            result = least_squares_local(callback, x0, bounds, max_evaluations=100)
            final = evaluator.evaluate(result.x)
            terminal = terminal_eval.evaluate(result.x, check_power=True)
            margin, margins = signed_margins(profile, terminal_grid, terminal)
            spots = []
            for index in (0,111):
                ref = evaluate_independent_response(model, result.x, float(terminal_grid.frequency_hz[index]), int(terminal_grid.setting[index]))
                errors = {name:float(np.max(np.abs(getattr(terminal,name)[index]-ref[name]))) for name in ('s','il_db','apl_db','in_rl_db','out_rl_db')}
                spots.append(dict(index=index, errors=errors, pass_=max(errors.values()) <= 1e-9))
            base_policy = load_constraint('RF-T008', allow_trial=True)
            physical = _validate_values_with_bounds(definition, model.schema, result.x, base_policy, physical_bounds,
                frozen_model=build_rf_model(definition, base_policy))
            rows.append(dict(version=label, result=plain(result), trajectory=trajectory,
                search_max_margin_db=float(np.max(direction*(final.il_db-threshold))),
                terminal_max_margin_db=margin, terminal_objective=reported_margin_objective(margins),
                terminal_power_check='passed', physical=plain(physical), mna=spots))
        except Exception as exc:
            rows.append(dict(version=label, state='STOP', error=f'{type(exc).__name__}: {exc}', trajectory=trajectory))
    metadata = dict(base=base, head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        status=subprocess.check_output(['git','status','--porcelain'],cwd=ROOT,text=True),
        source_sha256={label:hashlib.sha256(text.encode()).hexdigest() for label,text in [('base',original),('candidate',candidate)]},
        profile_sha256=profile.fingerprint, plan_sha256=plan.sha256, grids=plan.data['grids'], start=starts['1013']['baseline'], seed=1013,
        solver='TRF linear exact max_nfev=100, no restart', python=sys.version, numpy=np.__version__, scipy=scipy.__version__,
        platform=platform.platform(), threads={k:os.environ.get(k) for k in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS')}, loadavg=os.getloadavg())
    Path(output).write_text(json.dumps(dict(metadata=metadata, rows=rows), indent=2, allow_nan=False)+'\n')

if __name__ == '__main__':
    main(Path(sys.argv[1]))

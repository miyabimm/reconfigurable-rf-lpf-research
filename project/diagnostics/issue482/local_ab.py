"""Compare first complete SciPy local run, before Hybrid restarts."""
import json
from pathlib import Path
import sys

import numpy as np
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT/'src'))
from lpf.minimax_profile import _margin_parameters, signed_margins
import lpf.optimizers.hybrid as hybrid
from lpf.optimizers.hybrid import hybrid_minimize
from lpf.search.development_plan import freeze_run
from lpf.search.plan import grid_from_record

config = json.loads((ROOT/'project/diagnostics/issue470/config.json').read_text())
starts = json.loads((ROOT/'project/diagnostics/issue470/starts.json').read_text())
compiled = freeze_run(config, starts, root=ROOT, spot_checks={'terminal': [0,111]},
                      search_bounds=None, checkpoint_interval=1000)
plan, _, profile, model, _ = compiled
p = plan.data
x = p['jobs'][0]['vector']

class Done(Exception):
    pass

def run(batch):
    evaluator = model.evaluator(grid_from_record(p['grids']['baseline/search']), cache_mode='lk')
    threshold, direction = _margin_parameters(profile, evaluator.grid)
    observations, local, best, scipy_results = [], [], [], []
    original_minimize = hybrid.minimize
    def instrumented_minimize(*args, **kwargs):
        sol = original_minimize(*args, **kwargs)
        scipy_results.append((sol.nfev, sol.nit, sol.status, sol.success, str(sol.message)))
        return sol
    hybrid.minimize = instrumented_minimize
    def residual(v):
        return direction * (evaluator.evaluate(v).il_db - threshold)
    def residual_batch(vs):
        return [direction * (r.il_db - threshold) for r in evaluator.evaluate_batch(vs)]
    def observe(v, f):
        observations.append((v.copy(), f))
    def progress(v, f, improved):
        if improved:
            best[:] = [(v.copy(), f)]
    def end(r):
        local.append(r)
        raise Done()
    try:
        hybrid_minimize(residual, x, p['search_bounds'], seed=1013, max_evaluations=30000,
                        restart_sigma=.1, batch_fd=batch, residuals_batch=residual_batch,
                        objective_callback=observe, progress_callback=progress, local_run_callback=end)
    except Done:
        pass
    finally:
        hybrid.minimize = original_minimize
    print('SciPy nfev/nit/status/success/message', batch, scipy_results)
    terminal = model.evaluator(grid_from_record(p['grids']['terminal'])).evaluate(best[0][0], check_power=True)
    j, _ = signed_margins(profile, terminal.grid, terminal)
    return observations, local[0], best[0], terminal, j

a, b = run(False), run(True)
print('n observations', len(a[0]), len(b[0]))
print('run scalar', a[1])
print('run batch', b[1])
print('best J, terminal J', a[2][1], b[2][1], a[4], b[4])
n = min(len(a[0]),len(b[0]))
print('max candidate delta', np.max(np.abs(np.asarray([v for v, f in a[0][:n]])-np.asarray([v for v, f in b[0][:n]]))))
print('max objective delta', np.max(np.abs(np.asarray([f for v, f in a[0][:n]])-np.asarray([f for v, f in b[0][:n]]))))
for name in ('s','il_db','apl_db','in_rl_db','out_rl_db'):
    print(name, np.max(np.abs(getattr(a[3],name)-getattr(b[3],name))))

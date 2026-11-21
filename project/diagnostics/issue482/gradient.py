"""Instrumented first 25-probe gradient only; excludes evaluator setup."""
import json
from pathlib import Path
import sys
from time import perf_counter

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT/'src'))
from lpf.minimax_profile import _margin_parameters
from lpf.optimizers.hybrid import hybrid_minimize
from lpf.search.development_plan import freeze_run
from lpf.search.plan import grid_from_record

cfg = json.loads((ROOT/'project/diagnostics/issue470/config.json').read_text())
starts = json.loads((ROOT/'project/diagnostics/issue470/starts.json').read_text())
plan, _, profile, model, _ = freeze_run(cfg, starts, root=ROOT, spot_checks={'terminal': [0,111]},
                                        search_bounds=None, checkpoint_interval=1000)
p = plan.data

def run(batch):
    ev = model.evaluator(grid_from_record(p['grids']['baseline/search']), cache_mode='lk')
    threshold, direction = _margin_parameters(profile, ev.grid)
    times = []
    def scalar(x):
        return direction * (ev.evaluate(x).il_db-threshold)
    def batched(xs):
        return [direction * (r.il_db-threshold) for r in ev.evaluate_batch(xs)]
    hybrid_minimize(scalar, p['jobs'][0]['vector'], p['search_bounds'], seed=1013,
                    max_evaluations=26, restart_sigma=.1, batch_fd=batch, residuals_batch=batched,
                    objective_callback=lambda *_: times.append(perf_counter()))
    assert len(times) == 26
    return (times[25]-times[0])*1000
for batch in (False, True):
    run(batch)
for i in range(6):
    for batch in ((False,True) if i%2 == 0 else (True,False)):
        print(i, 'batch' if batch else 'scalar', run(batch), flush=True)

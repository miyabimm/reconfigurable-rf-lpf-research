#!/usr/bin/env python3
"""Same-candidate RF kernels only; plain timings and separately traced memory."""
import json
import os
from pathlib import Path
import sys
import time
import tracemalloc

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT/'src'))
import numpy as np
from lpf.search.development_plan import freeze_run
from lpf.search.plan import grid_from_record

config = json.loads((ROOT/'project/diagnostics/issue470/config.json').read_text())
starts = json.loads((ROOT/'project/diagnostics/issue470/starts.json').read_text())
config['arms'][0]['steps'][0]['options'].update(max_search_forwards=100000, batch_fd=True, partial_fd=True)
config['budget'] = dict(rf_samples=70*(100000+24)+476, rf_forwards=100025, independent_mna_samples=2)
plan, _, _, model, _ = freeze_run(config, starts, root=ROOT, spot_checks={'terminal':[0,111]},
                                  search_bounds=None, checkpoint_interval=1000)
grid = grid_from_record(plan.data['grids']['baseline/search'])
x = np.asarray(starts['1013']['baseline']['vector'])
bounds = np.asarray(plan.data['search_bounds']); width = bounds[:,1]-bounds[:,0]
analytic_eval = model.evaluator(grid)
partial_eval = model.evaluator(grid, cache_mode='lk')
vectors = np.tile(x, (len(x),1))
vectors[np.arange(len(x)),np.arange(len(x))] += 1e-8*width
mask = np.ones((len(x),len(grid.setting)), bool)
schema = model.schema
start = schema.n_inductors+schema.n_fixed+schema.n_coupling+schema.n_ic_fixed
for j in range(start,len(x)):
    mask[j] = grid.setting == (j-start)//schema.n_variable


def analytic():
    analytic_eval.evaluate_with_il_jacobian(x)
    return dict(rf_forwards=1, requested_samples=70, computed_samples=70)


def partial():
    # Clear L/k cache for a fair independent group, just as a cold candidate.
    partial_eval._lk_cache.clear()
    before = partial_eval.cache_stats['computed_samples']
    base = partial_eval.evaluate(x)
    partial_eval.evaluate_partial_batch(vectors, base, mask)
    return dict(rf_forwards=26, requested_samples=1820,
                computed_samples=partial_eval.cache_stats['computed_samples']-before)


analytic(); partial()  # warmup excluded
rows=[]
for order in (('analytic','partial'),('partial','analytic'))*5:
    for name in order:
        begin, cpu = time.perf_counter(), time.process_time()
        counts = (analytic if name == 'analytic' else partial)()
        rows.append(dict(name=name,wall_s=time.perf_counter()-begin,cpu_s=time.process_time()-cpu,
                         loadavg=os.getloadavg(),**counts))
memory={}
for name, fn in [('analytic',analytic),('partial',partial)]:
    tracemalloc.start(); fn(); _, peak=tracemalloc.get_traced_memory(); tracemalloc.stop()
    memory[name]=peak
Path(sys.argv[1]).write_text(json.dumps(dict(warmups_each=1, rows=rows, python_peak_bytes=memory,
    note='RF kernel only; batch/partial finite difference group, not full Hybrid solver; memory separately traced'),indent=2)+'\n')

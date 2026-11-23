#!/usr/bin/env python3
"""Exclusive-by-root-line instrumented baseline diagnostic, separate from plain timing.

Intervals include child calls made by that root line, but each interval is
assigned once only. sys.settrace overhead is substantial and not subtracted.
"""
import ast
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT/'src'))
import numpy as np
import bench
import lpf.rf_core.model as rfmodel
from lpf.search.development_plan import freeze_run
from lpf.search.plan import grid_from_record

base = '58573e2573867dc095e38d8995c29626d9ec32cd'
source = subprocess.check_output(['git','show',f'{base}:src/lpf/rf_core/model.py'],cwd=ROOT,text=True)
method = bench.methods(source, 'RFEvaluator', ['evaluate_with_il_jacobian'], vars(rfmodel))['evaluate_with_il_jacobian']
rfmodel.RFEvaluator.evaluate_with_il_jacobian = method
config = json.loads((ROOT/'project/diagnostics/issue470/config.json').read_text())
starts = json.loads((ROOT/'project/diagnostics/issue470/starts.json').read_text())
config['arms'][0]['steps'][0]['options'].update(max_search_forwards=100000, batch_fd=True, partial_fd=True)
config['budget'] = dict(rf_samples=70*(100000+24)+476, rf_forwards=100025, independent_mna_samples=2)
plan, _, profile, model, _ = freeze_run(config, starts, root=ROOT, spot_checks={'terminal':[0,111]}, search_bounds=None, checkpoint_interval=1000)
evaluator = model.evaluator(grid_from_record(plan.data['grids']['baseline/search']))
x = np.asarray(starts['1013']['baseline']['vector'])
evaluator.evaluate_with_il_jacobian(x)
totals = {}
last = None
last_time = None
def tracer(frame, event, arg):
    global last, last_time
    if frame.f_code is not method.__code__:
        return None
    now = time.perf_counter_ns()
    if last is not None:
        totals[last] = totals.get(last, 0) + now-last_time
    last = frame.f_lineno if event != 'return' else None
    last_time = now
    return tracer

sys.settrace(tracer)
for _ in range(20):
    evaluator.evaluate_with_il_jacobian(x)
sys.settrace(None)
lines = source.splitlines()
rows = [dict(line=i, source=lines[i-1].strip(), mean_ms=ns/20/1e6) for i, ns in sorted(totals.items())]
Path(sys.argv[1]).write_text(json.dumps(dict(base=base, note='20 traced calls; root-line intervals include descendants once; tracing overhead not subtracted; not plain timing', profile_sha256=profile.fingerprint, plan_sha256=plan.sha256, rows=rows),indent=2)+'\n')

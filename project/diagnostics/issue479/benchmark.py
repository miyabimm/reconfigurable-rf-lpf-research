"""Issue 479 reproducible RF-only diagnostic; no optimizer or EXP execution."""
import hashlib
import json
import os
from pathlib import Path
import platform
import resource
import statistics
import time
import tracemalloc

import numpy as np
import scipy
from lpf.search.development_plan import freeze_run
from lpf.search.plan import grid_from_record

ROOT = Path(__file__).resolve().parents[3]
config = json.loads((ROOT/'project/diagnostics/issue470/config.json').read_text())
starts = json.loads((ROOT/'project/diagnostics/issue470/starts.json').read_text())
plan, definition, profile, model, bounds = freeze_run(config, starts, root=ROOT,
    spot_checks={'terminal': [0, 111]}, search_bounds=None, checkpoint_interval=1000)
grid = grid_from_record(plan.data['grids']['baseline/search'])
x = np.array(starts['1013']['baseline']['vector'])
box = np.array(bounds); lo, hi = box.T; width = hi - lo
free = width > 0
z = (x[free]-lo[free])/width[free]
# SciPy L-BFGS-B jac=None defaults to absolute eps=1e-8 in normalized z.
# Include the unperturbed start, then each free coordinate in schema order.
vectors = [x.copy()]
for j in range(len(z)):
    zj = z.copy(); zj[j] += 1e-8 if z[j] + 1e-8 <= 1 else -1e-8
    y = lo.copy(); y[free] = np.clip(lo[free] + zj*width[free], lo[free], hi[free])
    vectors.append(y)
vectors = np.array(vectors, dtype='<f8')
print(json.dumps(dict(head=os.popen('git rev-parse HEAD').read().strip(),
    profile=profile.fingerprint, base=profile.base_sha256, grid=plan.data['grids']['baseline/search']['sha256'],
    candidates_sha256=hashlib.sha256(vectors.tobytes()).hexdigest(), shape=list(vectors.shape),
    python=platform.python_version(), numpy=np.__version__, scipy=scipy.__version__, platform=platform.platform(),
    threads={k: os.environ.get(k) for k in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS')})))

for B in (1, 5, 10, 25):
    xs = vectors[:1] if B == 1 else vectors[1:B+1]
    for mode in ('off', 'lk'):
        def run(batch):
            ev = model.evaluator(grid, cache_mode=mode)
            if batch: result = ev.evaluate_batch(xs)
            else: result = tuple(ev.evaluate(v) for v in xs)
            return result, ev.cache_stats
        reference, scalar_stats = run(False); actual, stats = run(True)
        differences = {}
        for name in ('s', 'il_db', 'apl_db', 'in_rl_db', 'out_rl_db'):
            a = np.array([getattr(r, name) for r in actual]); b = np.array([getattr(r, name) for r in reference])
            delta = np.abs(a-b)
            differences[name] = dict(abs=float(np.max(delta)), rel=float(np.max(delta/np.maximum(np.abs(b), np.finfo(float).tiny))), bit_equal=bool(np.array_equal(a,b)))
        # Warm both paths. Fresh evaluator per operation, excluded construction
        # from wall by constructing it before the clock; caches always empty.
        def measure(batch, repetitions):
            elapsed = 0
            for _ in range(repetitions):
                ev = model.evaluator(grid, cache_mode=mode)
                t = time.perf_counter_ns()
                if batch: ev.evaluate_batch(xs)
                else: tuple(ev.evaluate(v) for v in xs)
                elapsed += time.perf_counter_ns()-t
            return elapsed / repetitions / 1e6
        measure(False, 2); measure(True, 2)
        times = {False: [], True: []}
        for i in range(6):
            for batch in ((False, True) if i % 2 == 0 else (True, False)):
                times[batch].append(measure(batch, 10))
        # Allocation measurement is separate and not used for speed.
        peaks = {}
        for batch in (False, True):
            ev = model.evaluator(grid, cache_mode=mode)
            tracemalloc.start(); tracemalloc.reset_peak()
            if batch: ev.evaluate_batch(xs)
            else: tuple(ev.evaluate(v) for v in xs)
            peaks[str(batch)] = tracemalloc.get_traced_memory()[1]
            tracemalloc.stop()
        print(json.dumps(dict(B=B, mode=mode, scalar_ms=times[False], batch_ms=times[True],
            speedup=statistics.median(times[False])/statistics.median(times[True]),
            differences=differences, scalar_stats=scalar_stats, batch_stats=stats, peak_tracemalloc_bytes=peaks,
            maxrss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)), flush=True)

#!/usr/bin/env python3
"""Fixed-candidate preparation only; no SciPy, RF or runner timings."""
import json
import statistics
import time
import numpy as np

rng = np.random.default_rng(1013)
lo = rng.uniform(-2, 0, 25); hi = rng.uniform(0.1, 2, 25)
width = hi - lo; free = width > 0
start = rng.random(25); start_x = lo + start * width
zs = [start.copy()] + [rng.random(25) for _ in range(24)]
def physical(z):
    x = lo.copy()
    x[free] = np.clip(lo[free] + z * width[free], lo[free], hi[free])
    return x

def old():
    vectors = [start_x.copy() if np.array_equal(z, start) else physical(z) for z in zs]
    xs = [start_x.copy() if np.array_equal(z, start) else physical(z) for z in zs]
    return vectors, xs

def new():
    vectors = [start_x.copy() if np.array_equal(z, start) else physical(z) for z in zs]
    candidates = [(np.array(z, copy=True), x.copy()) for z, x in zip(zs, vectors)]
    xs = []
    for z, (expected, x) in zip(zs, candidates):
        if not np.array_equal(z, expected): raise RuntimeError('mismatch')
        xs.append(x)
    return vectors, xs

a, b = old(), new()
assert all(np.array_equal(x, y) for xset, yset in zip(a, b) for x, y in zip(xset, yset))
for _ in range(200): old(); new()
rows = []
for i in range(6):
    for name, fun in ((('old', old), ('new', new)) if i % 2 == 0 else (('new', new), ('old', old))):
        start_ns = time.perf_counter_ns()
        for _ in range(1000): fun()
        rows.append({'round': i+1, 'variant': name, 'seconds': (time.perf_counter_ns()-start_ns)/1e9})
print(json.dumps({'batches_per_measurement': 1000, 'warmup_batches_each': 200,
                  'candidate_count': 25, 'equal': True, 'runs': rows,
                  'median_s': {n: statistics.median(r['seconds'] for r in rows if r['variant'] == n) for n in ('old', 'new')}}, indent=2))

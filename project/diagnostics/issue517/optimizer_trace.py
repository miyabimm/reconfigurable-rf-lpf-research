#!/usr/bin/env python3
"""Intrusive optimizer line / SciPy SVD trace on seed 1001 (not plain timing)."""
import collections
import inspect
import os
from pathlib import Path
import sys
import time
from measure import ROOT, THREADS, setup, save
from lpf.search import _development_runner as runner
import lpf.optimizers.trf as optimizer
import scipy.optimize._lsq.trf as scipy_trf


def run(out):
    assert all(os.environ.get(k) == '1' for k in THREADS)
    out = Path(out).resolve()
    assert out.parent == Path('/tmp') and not out.exists()
    out.mkdir()
    config, starts, spots, plan, _, _ = setup(1001)
    totals, counts, last = collections.Counter(), collections.Counter(), {}
    source = inspect.getsourcefile(optimizer._trf_local)
    names = {'calc', '_trf_local', 'trf_minimize'}
    def tracer(frame, event, arg):
        if frame.f_code.co_filename != source or frame.f_code.co_name not in names: return None
        now = time.perf_counter_ns(); key = id(frame)
        if key in last:
            name, line, start = last[key]
            totals[name, line] += now-start
            counts[name, line] += 1
        if event == 'return': last.pop(key, None)
        else: last[key] = frame.f_code.co_name, frame.f_lineno, now
        return tracer
    orig = scipy_trf.svd
    svd = dict(count=0, wall_ns=0, failed=0)
    def observed_svd(*args, **kwargs):
        start = time.perf_counter_ns(); svd['count'] += 1
        try: return orig(*args, **kwargs)
        except BaseException:
            svd['failed'] += 1
            raise
        finally: svd['wall_ns'] += time.perf_counter_ns()-start
    scipy_trf.svd = observed_svd
    sys.settrace(tracer)
    try:
        state = runner.run(config, starts, out/'run', root=ROOT, spot_checks=spots, checkpoint_interval=1000)
    finally:
        sys.settrace(None); scipy_trf.svd = orig
    lines = Path(source).read_text().splitlines()
    save(out/'summary.json', dict(seed=1001, plan_sha256=plan.sha256, actual=state['jobs'][0]['actual'],
        note='Intrusive trace; line intervals include descendants, functions nest, and cannot be added across functions. '
             'SVD wrapper measures only scipy.optimize._lsq.trf.svd, not all SciPy internals.', svd=svd,
        rows=[dict(function=n, line=i, source=lines[i-1].strip(), wall_ns=v, events=counts[n,i])
              for (n,i),v in sorted(totals.items())]))
    print(svd, flush=True)

if __name__ == '__main__': run(sys.argv[1])

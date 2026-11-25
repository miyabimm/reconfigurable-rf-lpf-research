#!/usr/bin/env python3
"""Separate traced replay and intrusive margin/cache observations for #517.

Never use these timings as plain performance. Root-line intervals are exclusive
within each traced function but include child calls. Trace functions separately.
"""
import collections
import hashlib
import inspect
import json
import os
from pathlib import Path
import sys
import time

from measure import ROOT, SEEDS, THREADS, setup, save
import numpy as np
from lpf.minimax_profile import _margin_parameters
from lpf.rf_core.model import RFEvaluator
from lpf.rf_core.coupled_lc import CoupledLCTopology
from lpf.search import _development_runner as runner
from lpf.search.plan import grid_from_record
import lpf.optimizers.trf as trf


def trace_lines(function, evaluator, x):
    totals, last = collections.Counter(), {}
    code = function.__code__
    def tracer(frame, event, arg):
        if frame.f_code is not code: return None
        now = time.perf_counter_ns()
        key = id(frame)
        if key in last:
            line, start = last[key]
            totals[line] += now-start
        if event == 'return': last.pop(key, None)
        else: last[key] = frame.f_lineno, now
        return tracer
    sys.settrace(tracer)
    try:
        for _ in range(10): evaluator.evaluate_with_il_jacobian(x)
    finally:
        sys.settrace(None)
    lines, first = inspect.getsourcelines(function)
    return [dict(line=n, source=lines[n-first].strip(), total_ns=v, calls=10)
            for n,v in sorted(totals.items())]


def run(out):
    assert all(os.environ.get(k) == '1' for k in THREADS)
    out = Path(out).resolve()
    assert out.parent == Path('/tmp') and not out.exists()
    out.mkdir()
    summary = dict(note='Intrusive diagnostic, not plain timing. Three additional 5000-RF Runner jobs; '
                        'line trace is on separate fixed initial vectors, ten calls per function. '
                        'Each root-line interval includes descendants; no summation across functions.', trace={}, runs=[])
    save(out/'summary.json', summary)
    for seed in SEEDS:
        config, starts, spots, plan, profile, model = setup(seed)
        grid = grid_from_record(plan.data['grids']['baseline/search'])
        evaluator = model.evaluator(grid, cache_mode='off')
        x = np.asarray(starts[str(seed)]['baseline']['vector'])
        evaluator.evaluate_with_il_jacobian(x)
        summary['trace'][str(seed)] = {
            'model': trace_lines(RFEvaluator.evaluate_with_il_jacobian, evaluator, x),
            'node': trace_lines(CoupledLCTopology.node_admittance_with_jacobian, evaluator, x)}
        save(out/'summary.json', summary)
        threshold, direction = _margin_parameters(profile, grid)
        bins = [collections.Counter() for _ in range(5)]
        vector_hash = hashlib.sha256()
        counts = collections.Counter()
        original_eval, original_scipy = RFEvaluator.evaluate_with_il_jacobian, trf.least_squares
        def observed(ev, vector):
            response, jac = original_eval(ev, vector)
            index = counts['rf']
            counts['rf'] += 1
            vector_hash.update(np.asarray(vector, dtype='<f8').tobytes())
            bins[min(index//1000, 4)][int(np.count_nonzero(direction*(response.il_db-threshold)>0))] += 1
            return response, jac
        def observed_scipy(fun, z0, *, jac, **kwargs):
            def f(z):
                counts['fun'] += 1
                return fun(z)
            def j(z):
                counts['jac'] += 1
                return jac(z)
            return original_scipy(f, z0, jac=j, **kwargs)
        RFEvaluator.evaluate_with_il_jacobian, trf.least_squares = observed, observed_scipy
        try:
            state = runner.run(config, starts, out/str(seed), root=ROOT, spot_checks=spots, checkpoint_interval=1000)
        finally:
            RFEvaluator.evaluate_with_il_jacobian, trf.least_squares = original_eval, original_scipy
        result = json.loads((out/str(seed)/'job-0001/result.json').read_text())
        s = result['steps'][0]
        summary['runs'].append(dict(seed=seed, plan_sha256=plan.sha256, actual=state['jobs'][0]['actual'],
            counts=dict(counts), cache_hits=counts['fun']+counts['jac']-counts['rf'],
            positive_margin_histograms=[dict(sorted(c.items())) for c in bins], vector_sequence_sha256=vector_hash.hexdigest(),
            local_runs=len(s['local_run_details']), nfev=sum(r['scipy_nfev'] for r in s['local_run_details']),
            njev=sum(r['scipy_njev'] for r in s['local_run_details']),
            selected=s['solver_result'], terminal=result['terminal']['candidates'][0]['vector_sha256']))
        save(out/'summary.json', summary)
        print(seed, dict(counts), flush=True)

if __name__ == '__main__': run(sys.argv[1])

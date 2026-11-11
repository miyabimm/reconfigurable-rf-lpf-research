#!/usr/bin/env python3
"""One bounded paired RF diagnostic; no post-solver forwards or experiment."""
import hashlib
import json
import os
import platform
import time
from dataclasses import asdict
from pathlib import Path

import numpy as np
import scipy
from lpf.constraint_versions import load_constraint
from lpf.search._job_evaluation import source_identity
from lpf.search._worker_next import MinimalWorker
from lpf.search.component_constraints import validate_values
from lpf.search.performance import evaluate_requirements
from lpf.search.plan import ROOT, load_preflight
from lpf.search.proposals import definition_from_data
from lpf.search.starts import load_explicit
from lpf.search.storage import plain, sha, vector_sha

CONFIG = 'project/diagnostics/issue377/baseline.yaml'
STARTS = ROOT / 'project/diagnostics/issue375/starts-1002.json'
EXPECTED = '6203467121a4e37baaa51c471aaecb3174f3374f9ab955d6fbf101f7b5ce935f'


def main():
    if any(os.environ.get(k) != '1' for k in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS')):
        raise ValueError('Single-thread environment required')
    reports, traces = [], []
    for mode in ('legacy', 'prepared'):
        begin = time.perf_counter()
        source = source_identity(ROOT)
        plan = load_preflight(CONFIG)
        cfg = plan.data['config']
        ref = cfg['definition']
        definition = definition_from_data(json.loads((ROOT / ref['path']).read_bytes()) if 'path' in ref else ref)
        policy = load_constraint(cfg['rf']['constraint_id'], root=ROOT, allow_trial=cfg['rf']['allow_trial'])
        initial = load_explicit(STARTS)[1002]
        if vector_sha(initial['vector']) != EXPECTED or initial['vector_sha256'] != EXPECTED:
            raise ValueError('Original vector mismatch')
        worker = MinimalWorker(plan, definition, policy, 'hybrid', 1002, initial['vector'], EXPECTED, root=ROOT)
        if (worker.step['options']['max_evaluations'] != 100 or worker.step['options']['max_restarts'] != 0 or
                len(worker.grid.frequency_hz) != 70 or
                plan.data['grids']['hybrid/coarse']['sha256'] != '6805740a36f6100d7dec3e7308924242e909255f1ea2d287b7c734c400f98f26'):
            raise ValueError('Budget/grid mismatch')
        trace = []
        def evaluate(vector):
            x = np.array(vector, copy=True)
            validate_values(worker.definition, worker.model.schema, x, worker.policy, frozen_model=worker.model)
            x = np.asarray(x, dtype=float)
            x.setflags(write=False)
            response = worker.evaluator.evaluate(x)
            assessment = (evaluate_requirements(response, worker.requirements, requested_grid=worker.grid)
                          if mode == 'legacy' else evaluate_requirements(response, worker.prepared_requirements))
            trace.append((x.copy(), assessment['worst_il_db'], np.asarray(assessment['mandatory_g']).copy()))
            return response, assessment
        worker.evaluate = evaluate
        ready = time.perf_counter()
        result = worker.solve()
        end = time.perf_counter()
        reports.append(dict(mode=mode, setup_s=ready-begin, solver_s=end-ready, total_s=end-begin,
                            solver=asdict(result), count=len(trace), source=source, source_sha=sha(source),
                            plan_sha=plan.sha256, rf_inputs=plan.data['rf_inputs'],
                            policy_fingerprint=worker.model.policy_fingerprint,
                            grid_sha=plan.data['grids']['hybrid/coarse']['sha256']))
        traces.append(trace)
    equal = len(traces[0]) == len(traces[1]) and all(
        np.array_equal(a[0], b[0]) and a[1] == b[1] and np.array_equal(a[2], b[2])
        for a, b in zip(*traces))
    result_equal = plain(reports[0]['solver']) == plain(reports[1]['solver'])
    print(json.dumps(plain(dict(reports=reports, equal_all_forward_vectors_il_g=equal,
        equal_solver=result_equal, vector_sha=EXPECTED, starts_sha=hashlib.sha256(STARTS.read_bytes()).hexdigest(),
        script_sha=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        environment=dict(python=platform.python_version(), numpy=np.__version__, scipy=scipy.__version__,
                         platform=platform.platform()), limitations='One pair; tracing overhead; no variance, post-forward or independent validation')), sort_keys=True, allow_nan=False))
    if not equal or not result_equal:
        raise RuntimeError('Scientific parity failed; do not compare performance')


if __name__ == '__main__':
    main()

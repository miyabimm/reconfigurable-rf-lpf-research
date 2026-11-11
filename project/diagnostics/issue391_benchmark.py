#!/usr/bin/env python3
"""Issue 391 bounded development diagnostic; not a campaign or EXP."""
import argparse
import cProfile
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import platform
import pstats
import time

import numpy as np
import scipy
from lpf.constraint_versions import load_constraint
from lpf.search import _worker_next as wn
from lpf.search._job_evaluation import source_identity
from lpf.search.plan import ROOT, load_preflight
from lpf.search.proposals import definition_from_data
from lpf.search.starts import load_explicit
from lpf.search.storage import plain, sha, vector_sha

EXPECTED = '6203467121a4e37baaa51c471aaecb3174f3374f9ab955d6fbf101f7b5ce935f'
CONFIG = 'project/diagnostics/issue377/baseline.yaml'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--starts', required=True)
    parser.add_argument('--mode', required=True, choices=('plain', 'timed', 'profile'))
    args = parser.parse_args()
    start, cpu = time.perf_counter(), time.process_time()
    source = source_identity(ROOT)
    script_sha = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    plan = load_preflight(CONFIG)
    cfg = plan.data['config']
    ref = cfg['definition']
    definition = definition_from_data(json.loads((ROOT / ref['path']).read_bytes()) if 'path' in ref else ref)
    policy = load_constraint(cfg['rf']['constraint_id'], root=ROOT, allow_trial=cfg['rf']['allow_trial'])
    initial = load_explicit(args.starts)[1002]
    if initial['vector_sha256'] != EXPECTED or vector_sha(initial['vector']) != EXPECTED:
        raise ValueError('Original vector SHA mismatch; no RF executed')
    worker = wn.MinimalWorker(plan, definition, policy, 'hybrid', 1002, initial['vector'], EXPECTED, root=ROOT)
    if worker.step['options']['max_evaluations'] != 100 or worker.step['options']['max_restarts'] != 0:
        raise ValueError('Unexpected budget')
    ready, cpu_ready = time.perf_counter(), time.process_time()
    times = {}
    def wrap(name, func):
        def call(*a, **kw):
            w, c = time.perf_counter(), time.process_time()
            try:
                return func(*a, **kw)
            finally:
                entry = times.setdefault(name, [0, 0., 0.])
                entry[0] += 1
                entry[1] += time.perf_counter()-w
                entry[2] += time.process_time()-c
        return call
    if args.mode == 'timed':
        wn.validate_values = wrap('physical', wn.validate_values)
        wn.evaluate_requirements = wrap('requirements', wn.evaluate_requirements)
        # Instance evaluator is frozen; wrap its class method instead.
        cls = type(worker.evaluator)
        cls.evaluate = wrap('rf', cls.evaluate)
        worker.evaluate = wrap('evaluate_inclusive', worker.evaluate)
        worker.residuals = wrap('residual_inclusive', worker.residuals)
    profile = cProfile.Profile() if args.mode == 'profile' else None
    if profile:
        profile.enable()
    result = worker.solve()
    if profile:
        profile.disable()
    end, cpu_end = time.perf_counter(), time.process_time()
    prof = []
    if profile:
        stats = pstats.Stats(profile)
        for (file, line, name), (cc, nc, own, cum, _) in sorted(stats.stats.items(), key=lambda x: -x[1][3])[:35]:
            prof.append([f'{file}:{line}:{name}', nc, own, cum])
    report = dict(mode=args.mode, setup_wall=ready-start, setup_cpu=cpu_ready-cpu,
                  solver_wall=end-ready, solver_cpu=cpu_end-cpu_ready, timers=times,
                  profile=prof, solver=asdict(result), source_sha=sha(source), script_sha=script_sha,
                  source_identity=source, plan_sha=plan.sha256, rf_inputs=plan.data['rf_inputs'],
                  policy_fingerprint=worker.model.policy_fingerprint,
                  grid_sha=plan.data['grids']['hybrid/coarse']['sha256'],
                  vector_sha=EXPECTED, python=platform.python_version(), numpy=np.__version__,
                  scipy=scipy.__version__, platform=platform.platform(), starts_sha=hashlib.sha256(Path(args.starts).read_bytes()).hexdigest())
    print(json.dumps(plain(report), sort_keys=True, allow_nan=False))


if __name__ == '__main__':
    main()

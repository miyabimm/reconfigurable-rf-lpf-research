#!/usr/bin/env python3
"""One Issue 401 run. Called by the fixed-order batch driver, not a campaign."""
import argparse
from contextlib import nullcontext
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import platform
import time

from lpf.constraint_versions import load_constraint
from lpf.search._job_evaluation import source_identity
from lpf.search._worker_next import MinimalWorker
from lpf.search.plan import ROOT, load_preflight
from lpf.search.proposals import definition_from_data
from lpf.search.starts import load_explicit
from lpf.search.storage import plain, sha, vector_sha
from lpf.timing import TimerCollector
from issue401_timing import instrument

CONFIG = 'project/diagnostics/issue377/baseline.yaml'
STARTS = ROOT / 'project/diagnostics/issue375/starts-1002.json'
VECTOR = '6203467121a4e37baaa51c471aaecb3174f3374f9ab955d6fbf101f7b5ce935f'
STARTS_SHA = '63b671ea269656843df118230b7d920e91515188235809b6dd0efd667ac997ab'
PLAN = '8ac7bab9567918ae5c656fd449807ad2c38c1e1cad9e39c8ed217b95a569043e'
GRID = '6805740a36f6100d7dec3e7308924242e909255f1ea2d287b7c734c400f98f26'
POLICY = 'e682165c72d3a8b9f1384a2529f71bacfebfc9d17164d4af5af879e4a138b532'
WORKER = '74c47f29637ed73bdf57fbc3ab64e6f928de59f020eb29bd030c6c7f41600b15'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--mode', choices=('plain', 'timed', 'deep'), required=True)
    parser.add_argument('--source-sha', required=True)
    args = parser.parse_args()
    wall, cpu = time.perf_counter(), time.process_time()
    identity = source_identity(ROOT)
    if (sha(identity) != args.source_sha or identity['files']['src/lpf/search/_worker_next.py'] != WORKER
            or any(os.environ.get(k) != '1' for k in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS'))):
        raise ValueError('Source, Worker or threading mismatch; STOP before RF')
    if hashlib.sha256(STARTS.read_bytes()).hexdigest() != STARTS_SHA:
        raise ValueError('Starts file mismatch; STOP before RF')
    plan = load_preflight(CONFIG)
    cfg = plan.data['config']
    if (plan.sha256 != PLAN or plan.data['grids']['hybrid/coarse']['sha256'] != GRID
            or cfg['rf'] != {'constraint_id': 'RF-T008', 'allow_trial': True}):
        raise ValueError('RF inputs/plan/grid mismatch; STOP before RF')
    ref = cfg['definition']
    definition = definition_from_data(json.loads((ROOT / ref['path']).read_bytes()) if 'path' in ref else ref)
    policy = load_constraint('RF-T008', root=ROOT, allow_trial=True)
    start = load_explicit(STARTS)[1002]
    if start['vector_sha256'] != VECTOR or vector_sha(start['vector']) != VECTOR:
        raise ValueError('Start vector mismatch; STOP before RF')
    worker = MinimalWorker(plan, definition, policy, 'hybrid', 1002, start['vector'], VECTOR, root=ROOT)
    if (worker.model.policy_fingerprint != POLICY or worker.step['options']['max_evaluations'] != 100
            or worker.step['options']['max_restarts'] != 0):
        raise ValueError('Policy/budget mismatch; STOP before RF')
    ready, cpu_ready = time.perf_counter(), time.process_time()
    timer = TimerCollector() if args.mode != 'plain' else None
    with instrument(worker, timer, deep=args.mode == 'deep') if timer else nullcontext():
        result = worker.solve()
    end, cpu_end = time.perf_counter(), time.process_time()
    if result.nfev != 100:
        raise ValueError(f'Unexpected nfev={result.nfev}; STOP')
    report = dict(mode=args.mode, source_identity=identity, source_sha=sha(identity),
                  setup_wall=ready-wall, setup_cpu=cpu_ready-cpu,
                  solve_wall=end-ready, solve_cpu=cpu_end-cpu_ready,
                  timers=timer.snapshot() if timer else {}, solver=asdict(result),
                  plan_sha=plan.sha256, policy_fingerprint=worker.model.policy_fingerprint,
                  grid_sha=GRID, rf_inputs=plan.data['rf_inputs'], vector_sha=VECTOR,
                  starts_sha=STARTS_SHA, platform=platform.platform(),
                  affinity=sorted(os.sched_getaffinity(0)) if hasattr(os, 'sched_getaffinity') else None)
    print(json.dumps(plain(report), sort_keys=True, allow_nan=False))


if __name__ == '__main__':
    main()

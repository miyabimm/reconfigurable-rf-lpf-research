#!/usr/bin/env python3
"""Development-only single-seed Hybrid benchmark, not a recoverable Job or EXP."""
import argparse
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import platform
import shlex
import subprocess
import sys
from time import perf_counter

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import numpy as np
import scipy
from lpf.constraint_versions import load_constraint
from lpf.search._worker_next import MinimalWorker
from lpf.search._job_evaluation import source_identity
from lpf.search.component_constraints import validate_values
from lpf.search.plan import ROOT, load_preflight
from lpf.search.proposals import definition_from_data
from lpf.search.performance import summarize_mandatory
from lpf.search.starts import load_explicit
from lpf.search.storage import plain, sha, vector_sha


def freeze_source(expected_source_sha, expected_script_sha):
    """Capture once before RF; optionally reject a previously fixed identity."""
    identity = source_identity(ROOT)
    source_sha = sha(identity)
    script_sha = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    if expected_source_sha is not None and expected_source_sha != source_sha:
        raise ValueError('Benchmark source identity SHA mismatch')
    if expected_script_sha is not None and expected_script_sha != script_sha:
        raise ValueError('Benchmark script SHA mismatch')
    return identity, source_sha, script_sha


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', required=True)
    parser.add_argument('--starts', required=True)
    parser.add_argument('--arm', required=True)
    parser.add_argument('--seed', required=True, type=int)
    parser.add_argument('--expected-source-sha256', help='optional previously fixed source identity SHA')
    parser.add_argument('--expected-script-sha256', help='optional previously fixed benchmark script SHA')
    args = parser.parse_args()
    start = perf_counter()
    source, source_sha, script_sha = freeze_source(args.expected_source_sha256, args.expected_script_sha256)
    plan = load_preflight(args.config)
    cfg = plan.data['config']
    ref = cfg['definition']
    definition = definition_from_data(json.loads((ROOT / ref['path']).read_bytes()) if 'path' in ref else ref)
    policy = load_constraint(cfg['rf']['constraint_id'], root=ROOT, allow_trial=cfg['rf']['allow_trial'])
    initial = load_explicit(args.starts)[args.seed]
    worker = MinimalWorker(plan, definition, policy, args.arm, args.seed, initial['vector'], initial['vector_sha256'], root=ROOT)
    options = worker.step['options']
    if options['max_evaluations'] > 100 or options['max_restarts'] != 0:
        raise ValueError('Benchmark limited to <=100 evaluations and zero restarts')
    ready = perf_counter()
    result = worker.solve()
    end = perf_counter()
    observation = None
    if result.best_x is not None:
        physical = validate_values(definition, worker.model.schema, result.best_x, policy, frozen_model=worker.model)
        _, assessment = worker.evaluate(result.best_x)  # post-timing inspection, not optimizer nfev
        summary = summarize_mandatory(assessment, worker.prepared_requirements)
        observation = dict(physical=physical, worst_il_db=assessment['worst_il_db'],
                           strict_feasible=summary['strict_feasible'],
                           max_violation_db=summary['max_violation_db'])
    report = dict(kind='development_only_minimal_worker_benchmark', setup_s=ready-start,
                  solver_s=end-ready, total_s=end-start, solver=asdict(result), observation=observation,
                  plan_sha256=plan.sha256, rf_inputs=plan.data['rf_inputs'],
                  policy_id=worker.model.policy_id, policy_fingerprint=worker.model.policy_fingerprint,
                  grid_sha256=plan.data['grids'][f"{args.arm}/{worker.step['name']}"]['sha256'],
                  initial_vector_sha256=vector_sha(initial['vector']),
                  source_identity=source, source_sha256=source_sha, benchmark_script_sha256=script_sha,
                  source_check='captured once during setup; expected SHA checked only when supplied',
                  head=subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], text=True).strip(),
                  git_status=subprocess.check_output(['git', '-C', str(ROOT), 'status', '--short'], text=True),
                  environment=dict(python=platform.python_version(), numpy=np.__version__, scipy=scipy.__version__,
                                   platform=platform.platform(), threads={k: os.environ.get(k) for k in
                                   ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS')}),
                  command=shlex.join(sys.argv), limitations='separate process, uncontrolled cache and system load; no recovery, ledger, independent or dense validation')
    print(json.dumps(plain(report), sort_keys=True, allow_nan=False))


if __name__ == '__main__':
    main()

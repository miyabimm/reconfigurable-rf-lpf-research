#!/usr/bin/env python3
"""Bounded Issue 369 I/O comparison. Synthetic RF/requirements, never an EXP.

Uses the repository's test fixture and a disposable system temporary directory;
output-path checks are patched ONLY for this mock. No true RF forward or solver
is run. Legacy 100-forward cases can take minutes and write tens of MB.
"""
import argparse
import json
import os
from pathlib import Path
import platform
import sys
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'src'), str(ROOT/'tests')]
import numpy as np
import test_issue315_fixed_stage as fixture
from test_issue317_fixed_worker import FixtureOutput
from lpf.rf_core.model import RFResponse, RFEvaluator
from lpf.search import runner, storage, _job_evaluation, evaluation, _window_evaluation
from lpf.search._job_evaluation import FixedJobEvaluation
from lpf.search._window_evaluation import WindowJobEvaluation
from lpf.search.performance import grid_fingerprint
from lpf.search.storage import vector_sha


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--forwards', type=int, nargs='+', default=[5, 100], choices=range(1, 103))
    parser.add_argument('--modes', nargs='+', choices=('legacy', 'window100'), default=['legacy', 'window100'])
    args = parser.parse_args()
    case = fixture.FixedStageTests('runTest')
    case.setUp()
    print(json.dumps(dict(environment=dict(python=sys.version.split()[0], numpy=np.__version__,
        platform=platform.platform(), threads={k: os.getenv(k) for k in
            ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS')},
        rf='mock RF and mock requirements, zero actual RF forwards',
        grid='RF-F003 fixture: 6 settings, 28 intervals, 56 search samples',
        output='disposable system temporary fixture, not an authoritative development run'))), flush=True)
    try:
        def config(c):
            c['anytime_samples'] = []
            c['arms'][0]['steps'][0]['max_requested_samples'] = 102*56
            c['arms'][0]['steps'][0]['options']['max_evaluations'] = 102
            c['arms'][0]['max_requested_samples'] = c['max_trial_requested_samples'] = 9000
        plan, definition, policy, x = case.setup_model(mutate=config)
        starts = {23: dict(vector=x.tolist(), vector_sha256=vector_sha(x))}
        results = []
        for count in args.forwards:
            for mode in args.modes:
                counts = dict(atomic_writes=0, payload_bytes=0, contract_calls=0, snapshots=0, mock_forwards=0)
                old_write, old_contract, old_snapshot = storage._atomic_data, FixedJobEvaluation._contract, FixedJobEvaluation.snapshot
                def counted_write(path, data):
                    counts['atomic_writes'] += 1
                    counts['payload_bytes'] += len(data)
                    return old_write(path, data)
                def counted_contract(meter):
                    counts['contract_calls'] += 1
                    return old_contract(meter)
                def counted_snapshot(meter):
                    counts['snapshots'] += 1
                    return old_snapshot(meter)
                def fake_response(evaluator, vector):
                    counts['mock_forwards'] += 1
                    n = len(evaluator.grid.frequency_hz)
                    return RFResponse(evaluator.grid, evaluator.model.policy_id, evaluator.model.policy_fingerprint,
                        np.zeros((n, 2, 2), complex), *[np.zeros(n) for _ in range(4)])
                assessments = {}
                assess = evaluation.evaluate_requirements
                def fake_assessment(response, req, *, requested_grid):
                    # Reuse one structurally complete synthetic assessment per grid;
                    # readback still checks best interval identities and aggregates.
                    key = grid_fingerprint(requested_grid)
                    if key not in assessments:
                        assessments[key] = assess(response, req, requested_grid=requested_grid)
                    return assessments[key]
                def solver(callback, vector, bounds, **options):
                    for _ in range(count):
                        callback(vector)
                    return FixtureOutput(np.array(vector))
                output = Path(case.raw.name)/f'{mode}-{count}'
                with patch.object(runner, '_validate_development_output'), \
                     patch.object(WindowJobEvaluation, '_validate_checkpoint'), \
                     patch.object(storage, '_atomic_data', side_effect=counted_write), \
                     patch.object(FixedJobEvaluation, '_contract', counted_contract), \
                     patch.object(FixedJobEvaluation, 'snapshot', counted_snapshot), \
                     patch.object(_job_evaluation, 'source_identity', wraps=_job_evaluation.source_identity) as source, \
                     patch.object(evaluation, 'evaluate_requirements', side_effect=fake_assessment), \
                     patch.object(_window_evaluation, 'evaluate_requirements', side_effect=fake_assessment), \
                     patch.object(RFEvaluator, 'evaluate', autospec=True, side_effect=fake_response), \
                     patch('lpf.search.worker.slsqp_minimize', side_effect=solver):
                    wall, cpu = time.perf_counter(), time.process_time()
                    state = runner.run_development(plan, definition, policy, starts, output,
                                                   solver_kind='fixture', storage_mode=mode)
                    summary = runner.finalize_development(state, output)
                    wall, cpu = time.perf_counter()-wall, time.process_time()-cpu
                if state['status'] != 'completed':
                    raise RuntimeError(state.get('exit_reason'))
                job = state['jobs'][0]
                frozen = json.loads(job['spec']['frozen_json'])
                row = dict(mode=mode, search_forwards=count, wall_s=round(wall, 6), cpu_s=round(cpu, 6),
                    source_identity_calls=source.call_count, source_sha256=state['source_sha256'],
                    source_head=frozen['source']['head'], dirty_patch_sha256=frozen['source']['dirty_patch_sha256'],
                    **counts, requested=job['requested'], completed=job['completed'],
                    selected=summary['jobs'][0]['selection']['ranked_vector_sha256'],
                    terminal=summary['jobs'][0]['terminal']['status'], solver_status=job['worker_status'])
                results.append(row)
                print(json.dumps(row, sort_keys=True), flush=True)
        if set(args.modes) == {'legacy', 'window100'}:
            for count in args.forwards:
                compared = [r for r in results if r['search_forwards'] == count]
                if len(compared) != 2 or any(compared[0][k] != compared[1][k] for k in
                        ('requested', 'completed', 'selected', 'terminal', 'solver_status')):
                    raise ValueError('Fixture comparison mismatch')
            print(json.dumps(dict(comparison='PASS', actual_rf_forwards=0)), flush=True)
    finally:
        case.doCleanups()


if __name__ == '__main__':
    main()

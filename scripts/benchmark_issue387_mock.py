#!/usr/bin/env python3
"""Issue 387: bounded non-RF parent/Worker comparison, not a research Job.

The before case emulates only the removed inactive activate save. It uses the
same current code and source identity otherwise. Mock RF and disposable test
paths are explicit; never use this as a production runner.
"""
import argparse
import collections
import copy
import inspect
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
from test_issue317_fixed_worker import FixtureOutput, FixtureHybrid, FixtureRun
from lpf.rf_core.model import RFResponse, RFEvaluator
from lpf.search import runner, evaluation, _window_evaluation
from lpf.search._forward_window import ForwardJournal
from lpf.search._job_evaluation import FixedJobEvaluation
from lpf.search._window_evaluation import WindowJobEvaluation
from lpf.search.performance import grid_fingerprint
from lpf.search.storage import vector_sha


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--forwards', type=int, nargs='+', default=[0, 1, 99, 100, 101], choices=range(102))
    parser.add_argument('--shape385', action='store_true', help='mock 100 search, two selection, one terminal; no anytime')
    parser.add_argument('--two-steps', action='store_true', help='append one-forward fine grid step')
    args = parser.parse_args()
    if args.shape385 and args.two_steps:
        parser.error('choose only one fixture shape')
    if args.shape385:
        args.forwards = [100]
    case = fixture.FixedStageTests('runTest')
    case.setUp()
    print(json.dumps(dict(environment=dict(python=sys.version.split()[0], numpy=np.__version__,
        platform=platform.platform(), threads={k: os.getenv(k) for k in
        ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS')},
        rf='mock RF, zero real RF forwards; requirements evaluated on synthetic response',
        storage='disposable test fixture, output-path guards patched for tests only'))), flush=True)
    try:
        def config(c):
            c['anytime_samples'] = [56]
            c['arms'][0]['steps'][0]['max_requested_samples'] = 102*56
            c['arms'][0]['steps'][0]['options']['max_evaluations'] = 102
            c['arms'][0]['max_requested_samples'] = c['max_trial_requested_samples'] = 12000
            if args.two_steps:
                second = copy.deepcopy(c['arms'][0]['steps'][0])
                second.update(name='fine', points_per_interval=2, max_requested_samples=168)
                c['arms'][0]['steps'].append(second)
            if args.shape385:
                c['anytime_samples'] = []
                step = c['arms'][0]['steps'][0]
                step.update(solver='hybrid', aggregation='sum', max_requested_samples=100*56,
                    options=dict(maxiter=2, max_restarts=0, max_evaluations=100, restart_sigma=0.1))
        plan, definition, policy, x = case.setup_model(mutate=config)
        starts = {23: dict(vector=x.tolist(), vector_sha256=vector_sha(x))}
        original_activate = WindowJobEvaluation.activate
        original_save = ForwardJournal._save
        original_contract = FixedJobEvaluation._contract
        original_snapshot = WindowJobEvaluation.snapshot
        results = []
        for count in args.forwards:
            pairs = []
            for mode in ('before', 'after'):
                stats = dict(saves=0, written_bytes=0, reads=0, source_calls=0,
                             source_s=0., snapshot_s=0., save_s=0., forwards=0)
                events = []
                def activate(meter, allocation, grid):
                    # Only emulate the removed line; active transitions remain unchanged.
                    if mode == 'before' and meter.journal is not None and meter.active is None:
                        meter.journal.boundary(reserve=False)
                    return original_activate(meter, allocation, grid)
                def save(journal, *, reserve):
                    frame = inspect.currentframe().f_back
                    callers = []
                    while frame:
                        name = frame.f_code.co_name
                        if name in ('start', 'complete_forward', 'activate', 'finish', '_checkpoint', 'spot_check'):
                            callers.append(name)
                        frame = frame.f_back
                    phase = next((n for n in callers if n != '_checkpoint'), '_checkpoint')
                    started = time.perf_counter()
                    value = original_save(journal, reserve=reserve)
                    stats['save_s'] += time.perf_counter()-started
                    stats['saves'] += 1
                    events.append(dict(phase=phase, reserve=reserve,
                        active=journal.last_record['payload']['active'],
                        confirmed=journal.last_record['confirmed']['forwards'],
                        upper=journal.last_record['uncertain_upper']['forwards']))
                    return value
                def contract(meter):
                    started = time.perf_counter()
                    try:
                        return original_contract(meter)
                    finally:
                        stats['source_calls'] += 1
                        stats['source_s'] += time.perf_counter()-started
                def snapshot(meter):
                    started = time.perf_counter()
                    try:
                        return original_snapshot(meter)
                    finally:
                        stats['snapshot_s'] += time.perf_counter()-started
                def fake_response(evaluator, vector):
                    stats['forwards'] += 1
                    n = len(evaluator.grid.frequency_hz)
                    return RFResponse(evaluator.grid, evaluator.model.policy_id, evaluator.model.policy_fingerprint,
                        np.zeros((n, 2, 2), complex), *[np.zeros(n) for _ in range(4)])
                assessments = {}
                assess = evaluation.evaluate_requirements
                def fake_assessment(response, req, *, requested_grid):
                    key = grid_fingerprint(requested_grid)
                    if key not in assessments:
                        assessments[key] = assess(response, req, requested_grid=requested_grid)
                    return assessments[key]
                solver_calls = []
                def solver(callback, vector, bounds, **options):
                    solver_calls.append(1)
                    for _ in range(1 if args.two_steps and len(solver_calls) == 2 else count):
                        callback(vector)
                    if args.shape385:
                        alternate = np.array(vector, copy=True)
                        alternate[0] += 0.01
                        return FixtureHybrid([FixtureRun(list(vector)), FixtureRun(list(alternate))], list(vector))
                    return FixtureOutput(np.array(vector))
                output = Path(case.raw.name)/f'{mode}-{count}'
                with patch.object(runner, '_validate_development_output'), \
                     patch.object(WindowJobEvaluation, '_validate_checkpoint'), \
                     patch.object(WindowJobEvaluation, 'activate', activate), \
                     patch.object(ForwardJournal, '_save', save), \
                     patch.object(FixedJobEvaluation, '_contract', contract), \
                     patch.object(WindowJobEvaluation, 'snapshot', snapshot), \
                     patch.object(_window_evaluation, 'evaluate_requirements', side_effect=fake_assessment), \
                     patch.object(RFEvaluator, 'evaluate', autospec=True, side_effect=fake_response), \
                     patch('lpf.search.worker.hybrid_minimize' if args.shape385 else 'lpf.search.worker.slsqp_minimize', side_effect=solver):
                    wall = time.perf_counter()
                    state = runner.run_development(plan, definition, policy, starts, output,
                                                   solver_kind='fixture', storage_mode='window100')
                    wall = time.perf_counter()-wall
                if state['status'] != 'completed':
                    raise RuntimeError(state.get('exit_reason'))
                job = state['jobs'][0]
                raw = json.loads((output/job['raw_path']).read_bytes())
                # Final record's io_before excludes the final write/read.
                stats['written_bytes'] = raw['io_before']['written_bytes'] + (output/job['raw_path']).stat().st_size
                stats['reads'] = raw['io_before']['read_calls'] + 1
                payload = raw['payload']
                outcome = dict(confirmed=raw['confirmed'], uncertain_upper=raw['uncertain_upper'],
                    payload=payload, parent={k: job[k] for k in
                        ('worker_status', 'requested', 'completed', 'reserved', 'released', 'safe_to_release')})
                pairs.append(outcome)
                phases = collections.Counter(f"{e['phase']}:{'reserve' if e['reserve'] else 'confirm'}" for e in events)
                row = dict(mode=mode, search_forwards=count, wall_s=wall, **stats,
                    phases=dict(phases), events=events, parent=outcome['parent'],
                    source_sha256=state['source_sha256'], plan_sha256=plan.sha256,
                    selected=[r['vector_sha256'] for r in payload['selection']['ranked']],
                    terminal=payload['terminal']['status'], anytime=payload['anytime'])
                print(json.dumps(row, sort_keys=True), flush=True)
                results.append(row)
            if pairs[0] != pairs[1]:
                raise AssertionError(f'Worker/parent outcomes differ for {count} forwards')
        print(json.dumps(dict(comparison='PASS', actual_rf_forwards=0)), flush=True)
    finally:
        case.doCleanups()


if __name__ == '__main__':
    main()

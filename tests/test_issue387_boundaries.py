"""Issue 387 transition failure checks; RF is synthetic, no research Job."""
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import numpy as np
import test_issue319_parent_runner as parent_tests
import test_issue317_fixed_worker as worker_tests
from lpf.rf_core.model import RFEvaluator, RFResponse
from lpf.search import runner
from lpf.search._forward_window import ForwardJournal
from lpf.search._job_evaluation import FixedJobEvaluation
from lpf.search._window_evaluation import WindowJobEvaluation
from lpf.search.storage import atomic_verified, vector_sha


class BoundaryFailureTests(unittest.TestCase):
    setUp = parent_tests.ParentRunnerTests.setUp
    setup_model = parent_tests.ParentRunnerTests.setup_model

    def test_failure_on_each_side_of_inactive_transition_keeps_parent_cap(self):
        plan, definition, policy, x = self.setup_model(mutate=lambda c: c.update(anytime_samples=[]))
        starts = {23: dict(vector=x.tolist(), vector_sha256=vector_sha(x))}
        original_activate = WindowJobEvaluation.activate
        original_contract = FixedJobEvaluation._contract
        for mode in ('before', 'after'):
            for failure in ('finish_save', 'new_source', 'new_save', 'new_readback', 'new_forward'):
                with self.subTest(mode=mode, failure=failure):
                    calls = []
                    failures = []
                    output = Path(self.raw.name)/f'{mode}-{failure}'
                    def activate(meter, allocation, grid):
                        if mode == 'before' and meter.journal is not None and meter.active is None:
                            meter.journal.boundary(reserve=False)
                        return original_activate(meter, allocation, grid)
                    def contract(meter):
                        if failure == 'new_source' and meter.active == 'selection:0':
                            failures.append(1)
                            raise ValueError('fixture source changed')
                        return original_contract(meter)
                    def persist(path, record):
                        active = record['payload']['active']
                        if failure == 'finish_save' and active is None and record['confirmed']['forwards'] == 1:
                            failures.append(1)
                            raise OSError('fixture old finish save')
                        if active == 'selection:0':
                            if failure == 'new_save':
                                failures.append(1)
                                raise OSError('fixture new reservation save')
                            if failure == 'new_readback':
                                failures.append(1)
                                with patch.object(Path, 'read_bytes', return_value=b'corrupt'):
                                    return atomic_verified(path, record)
                        return atomic_verified(path, record)
                    def forward(evaluator, vector):
                        calls.append(1)
                        if failure == 'new_forward' and len(calls) == 2:
                            failures.append(1)
                            raise RuntimeError('fixture forward interrupted')
                        n = len(evaluator.grid.frequency_hz)
                        return RFResponse(evaluator.grid, evaluator.model.policy_id, evaluator.model.policy_fingerprint,
                            np.zeros((n, 2, 2), complex), *[np.zeros(n) for _ in range(4)])
                    def solver(callback, vector, bounds, **kwargs):
                        callback(vector)
                        return worker_tests.FixtureOutput(np.array(vector))
                    with patch.object(runner, '_validate_development_output'), \
                         patch.object(WindowJobEvaluation, '_validate_checkpoint'), \
                         patch.object(WindowJobEvaluation, 'activate', activate), \
                         patch.object(FixedJobEvaluation, '_contract', contract), \
                         patch('lpf.search._forward_window.atomic_verified', side_effect=persist), \
                         patch.object(RFEvaluator, 'evaluate', autospec=True, side_effect=forward), \
                         patch('lpf.search.worker.slsqp_minimize', side_effect=solver):
                        state = runner.run_development(plan, definition, policy, starts, output,
                                                       solver_kind='fixture', storage_mode='window100')
                    self.assertEqual(state['status'], 'unknown')
                    self.assertEqual(len(failures), 1, 'no retry')
                    job = state['jobs'][0]
                    self.assertEqual((job['requested'], job['reserved'], job['released']), (0, job['cap'], 0))
                    self.assertEqual(len(calls), 2 if failure == 'new_forward' else 1)
                    raw = json.loads((output/job['raw_path']).read_bytes())
                    self.assertLessEqual(raw['confirmed']['forwards'], 1)
                    self.assertGreaterEqual(raw['uncertain_upper']['forwards'], 1)
                    if failure in ('new_source', 'new_save'):
                        self.assertIsNone(raw['window'])
                        self.assertEqual(raw['confirmed']['forwards'], 1)
                    if failure in ('new_readback', 'new_forward'):
                        self.assertEqual(raw['payload']['active'], 'selection:0')
                        self.assertGreaterEqual(raw['uncertain_upper']['forwards'], 2)

    def test_budget_stop_before_after_comparison(self):
        def config(c):
            c['anytime_samples'] = []
            c['arms'][0]['steps'][0]['max_requested_samples'] = 112
        plan, definition, policy, x = self.setup_model(mutate=config)
        starts = {23: dict(vector=x.tolist(), vector_sha256=vector_sha(x))}
        original = WindowJobEvaluation.activate
        outcomes = []
        for mode in ('before', 'after'):
            calls = []
            def activate(meter, allocation, grid):
                if mode == 'before' and meter.journal is not None and meter.active is None:
                    meter.journal.boundary(reserve=False)
                return original(meter, allocation, grid)
            def forward(evaluator, vector):
                calls.append(1)
                n = len(evaluator.grid.frequency_hz)
                return RFResponse(evaluator.grid, evaluator.model.policy_id, evaluator.model.policy_fingerprint,
                    np.zeros((n, 2, 2), complex), *[np.zeros(n) for _ in range(4)])
            def solver(callback, vector, bounds, **kwargs):
                for _ in range(3):
                    callback(vector)
                raise AssertionError('must stop before third forward')
            output = Path(self.raw.name)/f'budget-{mode}'
            with patch.object(runner, '_validate_development_output'), \
                 patch.object(WindowJobEvaluation, '_validate_checkpoint'), \
                 patch.object(WindowJobEvaluation, 'activate', activate), \
                 patch.object(RFEvaluator, 'evaluate', autospec=True, side_effect=forward), \
                 patch('lpf.search.worker.slsqp_minimize', side_effect=solver):
                state = runner.run_development(plan, definition, policy, starts, output,
                                               solver_kind='fixture', storage_mode='window100')
            self.assertEqual(len(calls), 2)
            self.assertEqual(state['status'], 'completed')
            job = state['jobs'][0]
            self.assertEqual((job['worker_status'], job['requested'], job['completed']),
                             ('budget_exhausted', 112, 112))
            raw = json.loads((output/job['raw_path']).read_bytes())
            outcomes.append((raw['confirmed'], raw['uncertain_upper'], raw['payload'],
                             {k: job[k] for k in ('requested', 'completed', 'reserved', 'released', 'safe_to_release')}))
        self.assertEqual(outcomes[0], outcomes[1])


if __name__ == '__main__':
    unittest.main()

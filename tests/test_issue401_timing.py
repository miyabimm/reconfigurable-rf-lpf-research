"""Timing instrumentation follows Hybrid's private callback, not public APIs."""
import importlib.util
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

import numpy as np
from lpf.search.plan import ROOT
from lpf.timing import TimerCollector
from test_issue389_minimal_worker import MinimalWorkerTests

spec = importlib.util.spec_from_file_location('issue401_timing', ROOT / 'project/diagnostics/issue401_timing.py')
timing = importlib.util.module_from_spec(spec)
spec.loader.exec_module(timing)


class TimingTests(unittest.TestCase):
    setUp = MinimalWorkerTests.setUp
    setup_model = MinimalWorkerTests.setup_model
    prepare = MinimalWorkerTests.prepare

    def test_solver_path_and_plain_equivalence(self):
        _, _, _, _, plain = self.prepare()
        _, _, _, _, timed = self.prepare()
        expected = plain.solve()
        timer = TimerCollector()
        with timing.instrument(timed, timer), \
             patch.object(timed, 'evaluate', side_effect=AssertionError('public evaluate used')), \
             patch.object(timed, 'residuals', side_effect=AssertionError('public residuals used')):
            actual = timed.solve()
        self.assertEqual(actual.nfev, expected.nfev)
        self.assertEqual(actual.stop_reason, expected.stop_reason)
        self.assertEqual(actual.best_fun, expected.best_fun)
        np.testing.assert_array_equal(actual.best_x, expected.best_x)
        rows = timer.snapshot()
        for region in ('solver_callback', 'rf_forward', 'requirements', 'residual'):
            self.assertEqual(rows[region]['count'], actual.nfev)
            self.assertEqual(rows[region]['failed'], 0)
        self.assertEqual(rows['solve_total']['count'], 1)
        self.assertEqual(rows['hybrid_minimize']['count'], 1)
        self.assertEqual(rows['postsolve_validation']['count'], 2)

    def test_deep_regions_follow_rf_path(self):
        _, _, _, _, worker = self.prepare()
        timer = TimerCollector()
        with timing.instrument(worker, timer, deep=True):
            result = worker.solve()
        rows = timer.snapshot()
        for name in ('l3_port_admittance', 'l3_node_admittance', 'l3_matrices', 'l3_power_response'):
            self.assertEqual(rows[name]['count'], result.nfev)
            self.assertEqual(rows[name]['failed'], 0)

    def test_failure_propagates_and_counts(self):
        _, _, _, _, worker = self.prepare()
        timer = TimerCollector()
        with patch.object(type(worker.evaluator), 'evaluate', side_effect=ArithmeticError('RF failed')):
            with timing.instrument(worker, timer):
                with self.assertRaisesRegex(ArithmeticError, 'RF failed'):
                    worker.solve()
        rows = timer.snapshot()
        for name in ('rf_forward', 'solver_callback', 'hybrid_minimize', 'solve_total'):
            self.assertEqual(rows[name]['failed'], 1)
        self.assertNotIn('requirements', rows)


if __name__ == '__main__':
    unittest.main()

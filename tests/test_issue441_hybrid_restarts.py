"""Hybrid restarts consume one finite forward budget, not an RF verdict."""
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from lpf.optimizers.hybrid import hybrid_minimize


class BudgetRestarts(unittest.TestCase):
    def test_local_end_not_global_best_and_abnormal_restarts(self):
        starts, runs = [], []
        def local(fun, x, **kwargs):
            starts.append(x.copy())
            fun(x)
            # The solver endpoint differs from the best evaluated point.
            end = np.array([.8, .2])
            return SimpleNamespace(x=end, fun=1., success=len(starts) != 1,
                                   status=2 if len(starts) == 1 else 0,
                                   message='ABNORMAL' if len(starts) == 1 else 'success', nit=1)
        with patch('lpf.optimizers.hybrid.minimize', side_effect=local):
            result = hybrid_minimize(lambda x: [x[0]], [.1, .9], [(0, 1), (0, 1)],
                                     seed=4, max_evaluations=3, restart_sigma=.1, local_run_callback=runs.append)
        expected = np.clip(np.array([.8, .2]) + np.random.default_rng(4).normal(0, .1, 2), 0, 1)
        np.testing.assert_array_equal(starts[1], expected)
        self.assertEqual(len(starts), 3)
        self.assertEqual(result.evaluations, 3)
        self.assertEqual(result.stop_reason, 'evaluation_budget_exhausted')
        self.assertEqual(result.x, [.1, .9])
        self.assertEqual(runs[0].message, 'ABNORMAL')

    def test_invalid_residual_stops_and_preserves_best(self):
        calls = []
        def fun(x):
            calls.append(x)
            return [1.] if len(calls) == 1 else [float('nan')]
        result = hybrid_minimize(fun, [.5], [(0, 1)], seed=1,
                                 max_evaluations=10, restart_sigma=.1)
        self.assertEqual(result.stop_reason, 'invalid_residual')
        self.assertEqual(result.evaluations, 2)
        self.assertEqual(result.objective, 1.)

    def test_local_success_restarts_until_budget(self):
        runs = []
        def local(fun, x, **kwargs):
            value = fun(x)
            return SimpleNamespace(x=x, fun=value, success=True, status=0, message='success', nit=0)
        with patch('lpf.optimizers.hybrid.minimize', side_effect=local):
            result = hybrid_minimize(lambda x: [1.], [.5], [(0, 1)], seed=1,
                                     max_evaluations=3, restart_sigma=.1, local_run_callback=runs.append)
        self.assertEqual(len(runs), 3)
        self.assertEqual(result.stop_reason, 'evaluation_budget_exhausted')
        self.assertFalse(hasattr(result, 'max_restarts'))

    def test_invalid_solver_endpoint_stops(self):
        runs = []
        def local(fun, x, **kwargs):
            fun(x)
            return SimpleNamespace(x=np.array([float('nan')]), fun=0.)
        with patch('lpf.optimizers.hybrid.minimize', side_effect=local):
            result = hybrid_minimize(lambda x: [1.], [.5], [(0, 1)], seed=1,
                                     max_evaluations=5, restart_sigma=.1, local_run_callback=runs.append)
        self.assertEqual(result.stop_reason, 'invalid_solver_endpoint')
        self.assertEqual(len(runs), 1)


if __name__ == '__main__':
    unittest.main()

import sys
import unittest
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from lpf.optimizers.minimax import minimize_minimax


class MinimaxTest(unittest.TestCase):
    def solve(self, errors, x0, bounds, **kwargs):
        return minimize_minimax(errors, x0, bounds, max_iterations=100,
                                max_evaluations=1000, **kwargs)

    def test_signed_epigraph_and_equiripple(self):
        r = self.solve(lambda x: [x[0], 1 - x[0]], [0.1], [(0, 1)])
        self.assertTrue(r.success, r)
        self.assertAlmostEqual(r.x[0], .5, places=5)
        self.assertAlmostEqual(r.max_error, .5, places=5)
        r = self.solve(lambda x: [x[0] - 2, -x[0] - 1], [.9], [(0, 1)])
        self.assertTrue(r.success, r)
        self.assertAlmostEqual(r.x[0], .5, places=5)
        self.assertAlmostEqual(r.max_error, -1.5, places=5)
        self.assertEqual(r.slsqp.reason, 'not_run')

    def test_nonlinear_and_active_bound(self):
        r = self.solve(lambda x: [x[0]**2, (1 - x[0])**2], [.05], [(0, 1)])
        self.assertTrue(r.success, r)
        self.assertAlmostEqual(r.x[0], .5, places=4)
        self.assertAlmostEqual(r.max_error, .25, places=5)
        r = self.solve(lambda x: [-x[0]], [0], [(0, 1)])
        self.assertTrue(r.success, r)
        self.assertAlmostEqual(r.x[0], 1)
        r = self.solve(lambda x: [x[0] + x[1], 1 - x[1]],
                       [.2, 0], [(.2, .2), (0, 1)])
        self.assertTrue(r.success, r)
        np.testing.assert_allclose(r.x, [.2, .4], atol=1e-5)

    def test_constraint_and_initial_infeasibility(self):
        r = self.solve(lambda x: [x[0]], [0], [(0, 1)],
                       constraints=lambda x: [x[0] - .7])
        self.assertTrue(r.success, r)
        self.assertTrue(r.feasible)
        self.assertAlmostEqual(r.x[0], .7, places=5)
        self.assertLessEqual(r.max_violation, 1e-7)
        r = self.solve(lambda x: [x[0]], [0], [(0, 1)],
                       constraints=lambda x: [x[0] - 2])
        self.assertFalse(r.success)
        self.assertFalse(r.feasible)
        self.assertGreater(r.max_violation, 0)
        self.assertTrue(r.slp.reason.startswith('lp_failure:'), r)

    def test_nonlinear_actual_acceptance_and_constraint(self):
        seen = []
        def error(x):
            seen.append(float(x[0]))
            return [(x[0] - .4)**2]
        r = self.solve(error, [.8], [(0, 1)], tolerance=1e-5)
        self.assertTrue(r.success, r)
        self.assertAlmostEqual(r.x[0], .4, places=3)
        # The full linearized step from .55 overshoots to .05 and is rejected;
        # the next derivative is again evaluated at the unchanged .55.
        self.assertAlmostEqual(seen[4], .05)
        self.assertAlmostEqual(seen[5], .550001)
        r = self.solve(lambda x: [x[0]], [.8], [(0, 1)],
                       constraints=lambda x: [x[0]**2 - .25])
        self.assertTrue(r.success, r)
        self.assertAlmostEqual(r.x[0], .5, places=5)
        self.assertLessEqual(r.max_violation, 1e-7)
        # Tight tolerance relative to the finite-difference bias can stall;
        # feasibility and numerical convergence must not be conflated.
        r = self.solve(lambda x: [(x[0] - .4)**2], [.8], [(0, 1)])
        self.assertTrue(r.feasible)
        self.assertFalse(r.success)
        self.assertEqual(r.slp.reason, 'step_too_small')

    def test_lp_failure_is_not_success_even_if_feasible(self):
        fail = SimpleNamespace(success=False, status=4, message='numerical trouble')
        with patch('lpf.optimizers.minimax.linprog', return_value=fail):
            r = self.solve(lambda x: [x[0]], [.5], [(0, 1)])
        self.assertTrue(r.feasible)
        self.assertFalse(r.success)
        self.assertIn('lp_failure:4', r.slp.reason)

    def test_budget_counts_both_callbacks_and_differences(self):
        calls = []
        def e(x):
            calls.append('e')
            return [x[0]]
        def g(x):
            calls.append('g')
            return [x[0] + 1]
        r = minimize_minimax(e, [.5], [(0, 1)], constraints=g,
                             max_iterations=5, max_evaluations=3)
        self.assertEqual(calls, ['e', 'g', 'e'])
        self.assertEqual(r.slp.evaluations, 3)
        self.assertEqual(r.slp.reason, 'evaluation_limit')
        self.assertFalse(r.success)
        self.assertTrue(r.feasible)
        self.assertEqual(r.x[0], .5)

    def test_reproducibility_and_iteration_limit(self):
        def run():
            return minimize_minimax(lambda x: [x[0], 1-x[0]], [0], [(0, 1)],
                                    max_iterations=1, max_evaluations=20)
        a, b = run(), run()
        np.testing.assert_array_equal(a.x, b.x)
        self.assertEqual(a.slp, b.slp)
        self.assertEqual(a.slp.reason, 'iteration_limit')
        self.assertFalse(a.success)

    def test_invalid_inputs_and_callbacks(self):
        with self.assertRaises(ValueError):
            self.solve(lambda x: [1], [float('nan')], [(0, 1)])
        with self.assertRaises(ValueError):
            self.solve(lambda x: [1], [0], [(0, float('inf'))])
        for value in ([], [float('nan')], [float('inf')], 1):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.solve(lambda x: value, [0], [(0, 1)])
        with self.assertRaises(ValueError):
            self.solve(lambda x: [1] if x[0] == 0 else [1, 2], [0], [(0, 1)])
        with self.assertRaises(ValueError):
            self.solve(lambda x: [1], [0], [(0, 1)], constraints=lambda x: [np.nan])


if __name__ == '__main__':
    unittest.main()

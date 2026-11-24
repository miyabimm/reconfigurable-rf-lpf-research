import sys
import unittest
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace

import numpy as np
from scipy.optimize import linprog

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from lpf.optimizers.slp import slp_minimize




class SignedMaxTest(unittest.TestCase):
    def solve(self, errors, x0, bounds, **kwargs):
        return slp_minimize(errors, x0, bounds, aggregation='signed_max', max_iterations=100,
                            max_evaluations=1000, **kwargs)

    def test_budget_and_epigraph_shape(self):
        calls = []
        def errors(x):
            calls.append(x.copy())
            return [x[0], 1 - x[0]]
        with patch('lpf.optimizers.slp.linprog', wraps=linprog) as lp:
            result = slp_minimize(errors, [.1], [(0, 1)], max_iterations=1, max_evaluations=2)
        self.assertEqual(lp.call_args.kwargs['A_ub'].shape, (2, 2))
        self.assertEqual((len(calls), result.evaluations, result.stop_reason), (2, 2, 'evaluation_limit'))
        self.assertFalse(result.converged)
        self.assertEqual(result.x[0], .1)

    def test_signed_epigraph_and_equiripple(self):
        r = self.solve(lambda x: [x[0], 1 - x[0]], [0.1], [(0, 1)])
        self.assertTrue(r.converged, r)
        self.assertAlmostEqual(r.x[0], .5, places=5)
        self.assertAlmostEqual(r.objective, .5, places=5)
        r = self.solve(lambda x: [x[0] - 2, -x[0] - 1], [.9], [(0, 1)])
        self.assertTrue(r.converged, r)
        self.assertAlmostEqual(r.x[0], .5, places=5)
        self.assertAlmostEqual(r.objective, -1.5, places=5)

    def test_nonlinear_and_active_bound(self):
        r = self.solve(lambda x: [x[0]**2, (1 - x[0])**2], [.05], [(0, 1)])
        self.assertTrue(r.converged, r)
        self.assertAlmostEqual(r.x[0], .5, places=4)
        self.assertAlmostEqual(r.objective, .25, places=5)
        r = self.solve(lambda x: [-x[0]], [0], [(0, 1)])
        self.assertTrue(r.converged, r)
        self.assertAlmostEqual(r.x[0], 1)
        r = self.solve(lambda x: [x[0] + x[1], 1 - x[1]],
                       [.2, 0], [(.2, .2), (0, 1)])
        self.assertTrue(r.converged, r)
        np.testing.assert_allclose(r.x, [.2, .4], atol=1e-5)


    def test_nonlinear_actual_acceptance_and_constraint(self):
        seen = []
        def error(x):
            seen.append(float(x[0]))
            return [(x[0] - .4)**2]
        r = self.solve(error, [.8], [(0, 1)], tolerance=1e-5)
        self.assertTrue(r.converged, r)
        self.assertAlmostEqual(r.x[0], .4, places=3)
        # The full linearized step from .55 overshoots to .05 and is rejected;
        # the next derivative is again evaluated at the unchanged .55.
        self.assertAlmostEqual(seen[4], .05)
        self.assertAlmostEqual(seen[5], .550001)
        # Tight tolerance relative to the finite-difference bias can stall;
        # feasibility and numerical convergence must not be conflated.
        r = self.solve(lambda x: [(x[0] - .4)**2], [.8], [(0, 1)])
        self.assertFalse(r.converged)
        self.assertEqual(r.stop_reason, 'step_too_small')

    def test_lp_failure_is_not_success_even_if_feasible(self):
        fail = SimpleNamespace(success=False, status=4, message='numerical trouble')
        with patch('lpf.optimizers.slp.linprog', return_value=fail):
            r = self.solve(lambda x: [x[0]], [.5], [(0, 1)])
        self.assertFalse(r.converged)
        self.assertIn('lp_failure:4', r.stop_reason)
        self.assertEqual(r.x[0], .5)


    def test_reproducibility_and_iteration_limit(self):
        def run():
            return slp_minimize(lambda x: [x[0], 1-x[0]], [0], [(0, 1)],
                                aggregation='signed_max', max_iterations=1, max_evaluations=20)
        a, b = run(), run()
        np.testing.assert_array_equal(a.x, b.x)
        self.assertEqual((a.stop_reason, a.evaluations), (b.stop_reason, b.evaluations))
        self.assertEqual(a.stop_reason, 'iteration_limit')
        self.assertFalse(a.converged)

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


if __name__ == '__main__':
    unittest.main()

"""Small deterministic local-solver contract tests."""
import unittest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import numpy as np
from lpf.optimizers.least_squares import least_squares_local


class LeastSquaresTests(unittest.TestCase):
    def test_bounds_fixed_columns_and_fun_jac_share(self):
        calls = []
        def evaluate(x):
            calls.append(x.copy())
            return np.array([x[0] - .3, 2*(x[1] - .4)]), np.array([[1., 0., 0.], [0., 2., 0.]])
        result = least_squares_local(evaluate, [0., 1., 3.], [(0,1), (0,1), (3,3)])
        self.assertTrue(result.success)
        np.testing.assert_allclose(result.x, [.3, .4, 3], atol=1e-6)
        self.assertGreater(result.initial_evaluated_x[0], 0.)
        self.assertLess(result.initial_evaluated_x[1], 1.)
        self.assertEqual(len(calls), result.sensitivity_evaluations)
        self.assertEqual(result.sensitivity_evaluations, result.nfev)
        self.assertEqual(result.computed_samples, len(calls)*2)
        self.assertLess(result.objective, 1e-12)

    def test_fixed_and_stopped_and_errors(self):
        calls = []
        def evaluate(x):
            calls.append(x.copy())
            return np.array([x[0]-1]), np.array([[1.]])
        fixed = least_squares_local(evaluate, [0.], [(0,0)])
        self.assertEqual(len(calls), 1)
        self.assertTrue(fixed.success)
        stopped = least_squares_local(evaluate, [.5], [(0,1)], max_evaluations=1)
        self.assertFalse(stopped.success)
        self.assertEqual(stopped.status, 0)
        with self.assertRaisesRegex(RuntimeError, 'failure'):
            least_squares_local(lambda x: (_ for _ in ()).throw(RuntimeError('failure')), [.5], [(0,1)])
        for x, bounds in [([2.], [(0,1)]), ([float('nan')], [(0,1)]), ([0.], [(1,0)]),
                          ([0.], [(-1e308, 1e308)])]:
            with self.assertRaises(ValueError): least_squares_local(evaluate, x, bounds)


if __name__ == '__main__':
    unittest.main()

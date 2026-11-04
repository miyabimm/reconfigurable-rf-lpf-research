import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
from scipy.optimize import linprog

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from lpf.optimizers.minimax import minimize_minimax
from lpf.optimizers.slp import slp_minimize


class SlpTest(unittest.TestCase):
    def solve(self, residuals, x0=(0.1,), bounds=((0, 1),), **kwargs):
        return slp_minimize(residuals, x0, bounds, max_iterations=150,
                            max_evaluations=1000, **kwargs)

    def test_known_sum_and_max(self):
        def residual(x):
            return [x[0], 2 * (x[0] - 1)]
        for mode, expected in [('sum', .8), ('max', 2/3)]:
            with self.subTest(mode=mode):
                r = self.solve(residual, aggregation=mode)
                self.assertAlmostEqual(r.x[0], expected, places=3)
                self.assertAlmostEqual(r.objective, (sum if mode == 'sum' else max)(
                    np.square(residual(r.x))), places=12)
                self.assertEqual(r.aggregation, mode)
                self.assertTrue(r.feasible)
                # Local finite-difference and HiGHS tolerances may prevent convergence.
                self.assertTrue(r.success or r.slp.reason in ('step_too_small', 'iteration_limit'))

    def test_weighted_and_default(self):
        residual = lambda x: [x[0], 2 * (x[0] - 1)]
        for mode, expected in [('sum', 4/13), ('max', .4)]:
            r = self.solve(residual, weights=[9, 1], aggregation=mode)
            self.assertAlmostEqual(r.x[0], expected, places=3)
            self.assertAlmostEqual(r.objective, (sum if mode == 'sum' else max)(
                np.array([9, 1]) * np.square(residual(r.x))), places=12)
        default = self.solve(residual)
        explicit = self.solve(residual, aggregation='sum', weights=[1, 1])
        np.testing.assert_array_equal(default.x, explicit.x)
        self.assertEqual(default.slp, explicit.slp)

    def test_signed_legacy_identical_including_budget(self):
        errors = lambda x: [x[0] - 2, -x[0] - 1]
        for budget in (3, 1000):
            args = dict(max_iterations=100, max_evaluations=budget,
                        constraints=lambda x: [x[0]**2 - .04])
            old = minimize_minimax(errors, [.9], [(0, 1)], **args)
            new = slp_minimize(errors, [.9], [(0, 1)], aggregation='signed_max', **args)
            np.testing.assert_array_equal(old.x, new.x)
            self.assertEqual(old.max_error, new.objective)
            self.assertLess(new.objective, 0)
            self.assertEqual((old.max_violation, old.feasible, old.success, old.slp, old.slsqp),
                             (new.max_violation, new.feasible, new.success, new.slp, new.slsqp))

    def test_constraints_fixed_and_reproducible(self):
        kw = dict(constraints=lambda x: [x[0]**2 - .49], aggregation='sum')
        def run():
            return self.solve(lambda x: [x[0], x[1]], x0=(.4, .2),
                              bounds=((0, 1), (.2, .2)), **kw)
        a, b = run(), run()
        self.assertTrue(a.feasible)
        self.assertAlmostEqual(a.x[0], .7, places=4)
        self.assertEqual(a.x[1], .2)
        np.testing.assert_array_equal(a.x, b.x)
        self.assertEqual(a.slp, b.slp)
        # This initial linearization is infeasible even in the full box; it
        # must not be reported as a solution or as proof of global infeasibility.
        stalled = self.solve(lambda x: [x[0]], x0=(.2,), **kw)
        self.assertFalse(stalled.feasible)
        self.assertFalse(stalled.success)
        self.assertTrue(stalled.slp.reason.startswith('lp_failure:'))

    def test_budget_and_linearization_shape(self):
        for mode, rows in [('sum', 1), ('max', 2)]:
            calls = []
            def residual(x):
                calls.append(x.copy())
                return [x[0], 2 * (x[0] - 1)]
            with patch('lpf.optimizers.minimax.linprog', wraps=linprog) as lp:
                r = slp_minimize(residual, [.1], [(0, 1)], aggregation=mode,
                                 max_iterations=1, max_evaluations=2)
            self.assertEqual(lp.call_args.kwargs['A_ub'].shape, (rows, 2))
            self.assertEqual(len(calls), 2)
            self.assertEqual(r.slp.evaluations, 2)
            self.assertEqual(r.slp.reason, 'evaluation_limit')
            self.assertFalse(r.success)
            self.assertEqual(r.x[0], .1)
        zero = self.solve(lambda x: [1e300], weights=[0])
        self.assertEqual(zero.objective, 0)

    def test_invalid(self):
        for kw in ({'aggregation': 'bad'}, {'aggregation': None},
                   {'weights': [-1]}, {'weights': [float('nan')]},
                   {'weights': [float('inf')]}, {'weights': [1, 2]},
                   {'weights': [1], 'aggregation': 'signed_max'}):
            with self.subTest(kw=kw), self.assertRaises(ValueError):
                self.solve(lambda x: [1], **kw)
        for values in ([float('nan')], [float('inf')], [1e300]):
            with self.subTest(values=values), self.assertRaises(ValueError):
                self.solve(lambda x: values)


if __name__ == '__main__':
    unittest.main()

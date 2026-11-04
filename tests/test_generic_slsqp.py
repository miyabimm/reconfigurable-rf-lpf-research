import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
from scipy.optimize import OptimizeResult

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from lpf.optimizers.slsqp import slsqp_minimize


class GenericSLSQPTests(unittest.TestCase):
    def run_solver(self, residuals, x0=(0.1,), bounds=((0, 1),), **kwargs):
        options = dict(max_iterations=100, max_evaluations=1000)
        options.update(kwargs)
        return slsqp_minimize(residuals, x0, bounds, **options)

    def test_known_optima_and_weights(self):
        residual = lambda x: [x[0], 2 * (x[0] - 1)]
        for mode, weights, x, fun in (
            ('sum', None, 0.8, 0.8), ('max', None, 2/3, 4/9),
            ('sum', [4, 1], 0.5, 2), ('max', [4, 1], 0.5, 1),
        ):
            with self.subTest(mode=mode, weights=weights):
                r = self.run_solver(residual, aggregation=mode, weights=weights)
                self.assertTrue(r.success, r)
                self.assertTrue(r.feasible)
                self.assertAlmostEqual(r.x[0], x, places=5)
                self.assertAlmostEqual(r.fun, fun, places=6)
                self.assertEqual(r.aggregation, mode)
                if mode == 'max':
                    self.assertLessEqual(r.epigraph_gap, 1e-7)

    def test_epigraph_constraints_and_physical_coordinates(self):
        def solver(fun, z, **kw):
            self.assertEqual(kw['method'], 'SLSQP')
            self.assertEqual(fun(np.array([0.5, 3.])), 3.)
            cs = kw['constraints']
            np.testing.assert_allclose(cs[0]['fun'](np.array([0.5, 3.])), [2, 2, -1])
            np.testing.assert_allclose(cs[1]['fun'](np.array([0.5, 3.])), [0.25])
            return OptimizeResult(x=np.array([0.5, 4.]), success=True, status=0,
                                  message='fake', nit=1)
        seen = []
        def g(x):
            seen.append(x.copy())
            return [x[0] - 0.25]
        with patch('lpf.optimizers.slsqp.minimize', side_effect=solver):
            r = self.run_solver(lambda x: [1, -1, 2], aggregation='max', constraints=g)
        self.assertTrue(r.success)
        self.assertTrue(all(len(x) == 1 for x in seen))

    def test_infeasible_initial_repair_and_impossible(self):
        for mode in ('sum', 'max'):
            with self.subTest(mode=mode):
                r = self.run_solver(lambda x: [x[0]], constraints=lambda x: [x[0] - 0.7],
                                    aggregation=mode)
                self.assertTrue(r.success, r)
                self.assertAlmostEqual(r.x[0], 0.7, places=5)
                r = self.run_solver(lambda x: [x[0]], constraints=lambda x: [x[0]**2 - 0.49],
                                    aggregation=mode)
                self.assertTrue(r.success, r)
                self.assertAlmostEqual(r.x[0], 0.7, places=5)
                r = self.run_solver(lambda x: [x[0]], constraints=lambda x: [x[0] - 2],
                                    aggregation=mode)
                self.assertFalse(r.success)
                self.assertFalse(r.feasible)
                self.assertGreater(r.max_violation, 0.9)

    def test_fixed_coordinates_and_bounds(self):
        seen = []
        def residual(x):
            seen.append(x.copy())
            return [x[0] - 0.3, x[1] - 2]
        r = self.run_solver(residual, [0.9, 2], [(0, 1), (2, 2)], aggregation='max')
        self.assertTrue(r.success, r)
        self.assertAlmostEqual(r.x[0], 0.3, places=4)
        self.assertTrue(all(0 <= x[0] <= 1 and x[1] == 2 for x in seen))
        for feasible in (True, False):
            r = self.run_solver(lambda x: [x[0]], [2], [(2, 2)],
                                constraints=lambda x: [1 if feasible else -1])
            self.assertEqual(r.success, feasible)
            self.assertEqual(r.feasible, feasible)
            self.assertEqual(r.evaluations, 2)
            self.assertIsNone(r.solver_success)

    def test_budget_counts_callbacks_and_no_hidden_calls(self):
        for mode in ('sum', 'max'):
            for budget in (1, 2, 3, 5, 10):
                with self.subTest(mode=mode, budget=budget):
                    calls = [0, 0]
                    def residual(x):
                        calls[0] += 1
                        return [x[0] - .5, x[1]]
                    def g(x):
                        calls[1] += 1
                        return [x[0] + x[1]]
                    r = self.run_solver(residual, [0.8, 0.8], [(0, 1), (0, 1)],
                                        constraints=g, aggregation=mode, max_evaluations=budget)
                    self.assertEqual([r.nfev, r.ncev], calls)
                    self.assertEqual(r.evaluations, sum(calls))
                    self.assertEqual(r.evaluations, budget)
                    self.assertEqual(r.stop_reason, 'evaluation_budget_exhausted')
                    self.assertFalse(r.success)
                    np.testing.assert_array_equal(r.x, [0.8, 0.8])
        # Finite-difference probes invoke and charge both callbacks.
        probes = [[], []]
        def residual(x):
            probes[0].append(x.copy())
            return [x[0] - 0.5]
        def g(x):
            probes[1].append(x.copy())
            return [x[0]]
        r = self.run_solver(residual, constraints=g, max_evaluations=100)
        self.assertTrue(r.success)
        for i, count in enumerate((r.nfev, r.ncev)):
            self.assertEqual(count, len(probes[i]))
            self.assertTrue(any(0 < abs(x[0] - 0.1) < 1e-6 for x in probes[i]))
        # SLSQP reports success but verification itself runs out of budget.
        def fake(fun, z, **kw):
            return OptimizeResult(x=z, success=True, status=0, message='ok', nit=0)
        with patch('lpf.optimizers.slsqp.minimize', side_effect=fake):
            r = self.run_solver(lambda x: [x[0]], max_evaluations=1)
        self.assertFalse(r.success)
        self.assertTrue(r.solver_success)
        self.assertEqual(r.stop_reason, 'evaluation_budget_exhausted')

    def test_solver_success_is_not_verification(self):
        for mode, z in (('sum', [0.2]), ('max', [0.2, 0.001]), ('max', [0.2, 20])):
            with self.subTest(mode=mode, z=z):
                def fake(*args, **kw):
                    return OptimizeResult(x=np.array(z), success=True, status=0, message='ok', nit=1)
                with patch('lpf.optimizers.slsqp.minimize', side_effect=fake):
                    r = self.run_solver(lambda x: [x[0]], aggregation=mode,
                                        constraints=lambda x: [x[0] - 0.5] if mode == 'sum' else [1])
                self.assertTrue(r.solver_success)
                self.assertFalse(r.success)
                self.assertEqual(r.stop_reason, 'verification_failed')

    def test_invalid_inputs_and_callbacks(self):
        for options in ({'weights': [-1]}, {'weights': [np.inf]}, {'weights': [1, 2]},
                        {'aggregation': 'signed_max'}, {'max_iterations': 0},
                        {'max_evaluations': True}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                self.run_solver(lambda x: [1], **options)
        for x, bounds in (([0], [(1, 0)]), ([2], [(0, 1)]), ([0], [(0, np.inf)]),
                          ([np.nan], [(0, 1)])):
            with self.subTest(x=x, bounds=bounds), self.assertRaises(ValueError):
                self.run_solver(lambda x: [1], x, bounds)
        for residual in (lambda x: [np.nan], lambda x: [], lambda x: [1e308]):
            r = self.run_solver(residual)
            self.assertEqual(r.stop_reason, 'invalid_residual')
            self.assertFalse(r.success)
        r = self.run_solver(lambda x: [1], constraints=lambda x: [np.nan])
        self.assertEqual(r.stop_reason, 'invalid_constraint')
        self.assertFalse(r.feasible)
        calls = []
        def changing(x):
            calls.append(1)
            return [1] if len(calls) == 1 else [1, 2]
        r = self.run_solver(changing)
        self.assertEqual(r.stop_reason, 'invalid_residual')
        self.assertEqual(r.nfev, 2)

    def test_determinism_and_iteration_limit(self):
        residual = lambda x: [x[0], 2 * (x[0] - 1)]
        for mode in ('sum', 'max'):
            a = self.run_solver(residual, aggregation=mode)
            b = self.run_solver(residual, aggregation=mode)
            np.testing.assert_array_equal(a.x, b.x)
            self.assertEqual((a.fun, a.nfev, a.ncev, a.nit), (b.fun, b.nfev, b.ncev, b.nit))
            r = self.run_solver(residual, aggregation=mode, max_iterations=1)
            self.assertFalse(r.success)
            self.assertEqual(r.stop_reason, 'solver_failure')
            self.assertEqual(r.status, 9)


if __name__ == '__main__':
    unittest.main()

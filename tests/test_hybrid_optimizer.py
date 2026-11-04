import sys
import unittest
from dataclasses import asdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from lpf.optimizers.hybrid import hybrid_minimize


class HybridTests(unittest.TestCase):
    def run_hybrid(self, residuals, x0, bounds, **kwargs):
        options = dict(seed=4, maxiter=100, max_restarts=0,
                       max_evaluations=1000, restart_sigma=0.7)
        options.update(kwargs)
        return hybrid_minimize(residuals, x0, bounds, **options)

    def test_weighted_unimodal_and_fixed_coordinates(self):
        seen = []
        def residual(x):
            seen.append(x.copy())
            return [x[0] - 0.3, x[1] - 2, 2 * (x[0] - 0.3)]
        result = self.run_hybrid(residual, [0.9, 2], [(0, 1), (2, 2)],
                                 weights=[1, 1, 2])
        self.assertTrue(result.runs[0].success)
        self.assertLess(result.best_fun, 1e-12)
        self.assertLess(result.best_fun, result.runs[0].start_fun)
        self.assertEqual(result.best_x[1], 2)
        self.assertTrue(all(0 <= x[0] <= 1 and x[1] == 2 for x in seen))
        self.assertEqual(result.nfev, len(seen))

    def test_weights_change_the_solution(self):
        residual = lambda x: [x[0], x[0] - 1]
        result = self.run_hybrid(residual, [0.8], [(0, 1)], weights=[3, 1])
        self.assertAlmostEqual(result.best_x[0], 0.25, places=5)
        self.assertAlmostEqual(result.best_fun, 0.75, places=8)

    def test_multimodal_uphill_restarts_and_determinism(self):
        seen = []
        def residual(x):
            seen.append(x.copy())
            return [x[0] ** 2 - 1]
        options = dict(seed=11, max_restarts=10, restart_sigma=0.8)
        a = self.run_hybrid(residual, [0.8], [(-2, 2)], **options)
        b = self.run_hybrid(residual, [0.8], [(-2, 2)], **options)
        self.assertEqual(asdict(a), asdict(b))
        self.assertEqual(a.stop_reason, 'restarts_exhausted')
        ends = [r.end_x[0] for r in a.runs if r.success]
        self.assertTrue(any(x < -0.9 for x in ends))
        self.assertTrue(any(x > 0.9 for x in ends))
        self.assertTrue(any(r.start_fun > a.runs[0].end_fun + 0.01 for r in a.runs[1:]))
        self.assertTrue(all(-2 <= r.start_x[0] <= 2 and -2 <= r.end_x[0] <= 2 for r in a.runs))
        self.assertTrue(all(-2 <= x[0] <= 2 for x in seen))
        self.assertLess(a.best_fun, a.runs[0].start_fun)

    def test_exact_budget_even_mid_gradient_preserves_best(self):
        result = self.run_hybrid(lambda x: [x[0] - 0.2, x[1] - 0.4],
                                 [0.9, 0.9], [(0, 1), (0, 1)], max_evaluations=2)
        self.assertEqual(result.nfev, 2)
        self.assertEqual(result.stop_reason, 'evaluation_budget_exhausted')
        self.assertFalse(result.runs[0].success)
        self.assertIsNone(result.runs[0].status)
        self.assertEqual(result.runs[0].nfev, 2)
        self.assertIsNotNone(result.best_x)
        self.assertIsNotNone(result.runs[0].end_x)

    def test_failure_status_does_not_hide_best(self):
        result = self.run_hybrid(lambda x: [10 * (x[1] - x[0]**2), 1 - x[0]],
                                 [-1.2, 1], [(-2, 2), (-1, 3)], maxiter=1)
        self.assertFalse(result.runs[0].success)
        self.assertIsInstance(result.runs[0].status, int)
        self.assertTrue(result.runs[0].message)
        self.assertEqual(result.runs[0].nit, 1)
        self.assertIsNotNone(result.best_x)
        self.assertEqual(result.stop_reason, 'restarts_exhausted')

    def test_fixed_box_and_invalid_residuals(self):
        result = self.run_hybrid(lambda x: [x[0] - 1], [2], [(2, 2)], max_restarts=5)
        self.assertEqual(result.stop_reason, 'all_coordinates_fixed')
        self.assertEqual(result.nfev, 1)
        self.assertTrue(result.runs[0].success)
        for residual in (lambda x: [], lambda x: [np.nan], lambda x: [np.inf],
                         lambda x: [1e308]):
            with self.subTest(residual=residual):
                result = self.run_hybrid(residual, [0], [(0, 1)])
                self.assertEqual(result.stop_reason, 'invalid_residual')
                self.assertFalse(result.runs[0].success)
                self.assertIsNone(result.best_x)
                self.assertEqual(result.nfev, 1)
        calls = []
        def changes(x):
            calls.append(1)
            return [1] if len(calls) == 1 else [1, 2]
        result = self.run_hybrid(changes, [0.5], [(0, 1)])
        self.assertEqual(result.stop_reason, 'invalid_residual')
        self.assertEqual(result.best_fun, 1)
        self.assertFalse(result.runs[0].success)

    def test_invalid_input(self):
        invalid = [([2], [(0, 1)], {}), ([0], [(1, 0)], {}),
                   ([0], [(0, np.inf)], {}), ([], [], {}),
                   ([0], [(0, 1)], {'maxiter': 0}),
                   ([0], [(0, 1)], {'max_restarts': -1}),
                   ([0], [(0, 1)], {'max_evaluations': 0}),
                   ([0], [(0, 1)], {'restart_sigma': 0}),
                   ([0], [(0, 1)], {'weights': [-1]})]
        for x0, bounds, options in invalid:
            with self.subTest(x0=x0, bounds=bounds, options=options), self.assertRaises(ValueError):
                self.run_hybrid(lambda x: [1], x0, bounds, **options)
        mismatch = self.run_hybrid(lambda x: [1, 2], [0], [(0, 1)], weights=[1])
        self.assertEqual(mismatch.stop_reason, 'invalid_residual')
        self.assertIsNone(mismatch.best_fun)


if __name__ == '__main__':
    unittest.main()

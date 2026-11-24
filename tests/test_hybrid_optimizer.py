import sys
import unittest
from dataclasses import asdict
from pathlib import Path
from unittest.mock import patch

import numpy as np
from scipy.optimize import OptimizeResult

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from lpf.optimizers.lbfgsb import lbfgsb_minimize


class HybridTests(unittest.TestCase):
    def run_hybrid(self, residuals, x0, bounds, **kwargs):
        options = dict(seed=4, max_evaluations=1000, restart_sigma=0.7)
        options.update(kwargs)
        self.runs = []
        options['local_run_callback'] = self.runs.append
        return lbfgsb_minimize(residuals, x0, bounds, **options)

    def test_aggregation_values_and_default_compatibility(self):
        residual = lambda x: [2, -3, 4]
        for mode, expected in (('sum', 20), ('max', 16)):
            with self.subTest(mode=mode):
                result = self.run_hybrid(residual, [0], [(0, 0)], aggregation=mode)
                self.assertEqual(result.objective, expected)
                self.assertEqual(self.runs[0].start_fun, expected)
        default = self.run_hybrid(residual, [0.2], [(0, 1)])
        explicit = self.run_hybrid(residual, [0.2], [(0, 1)], aggregation='sum')
        self.assertEqual(asdict(default), asdict(explicit))

    def test_sum_and_max_have_distinct_best_found(self):
        residual = lambda x: [x[0], 2 * (1 - x[0])]
        summed = self.run_hybrid(residual, [0.1], [(0, 1)], aggregation='sum')
        maximum = self.run_hybrid(residual, [0.1], [(0, 1)], aggregation='max')
        self.assertAlmostEqual(summed.x[0], 0.8, places=5)
        self.assertAlmostEqual(summed.objective, 0.8, places=7)
        self.assertAlmostEqual(maximum.x[0], 2 / 3, places=5)
        self.assertAlmostEqual(maximum.objective, 4 / 9, places=5)
        # Convergence is the solver's report, not inferred from the best point.
        self.assertIsInstance(self.runs[0].success, bool)
        self.assertIsInstance(self.runs[0].status, int)
        self.assertTrue(self.runs[0].message)

    def test_max_keeps_solver_failure_even_at_best_point(self):
        def failed_solver(objective, _x0, **kwargs):
            x = np.array([2 / 3])
            value = objective(x)
            return OptimizeResult(x=x, fun=value, success=False, status=2,
                                  message='line search failed', nit=1)
        with patch('lpf.optimizers.lbfgsb.minimize', side_effect=failed_solver):
            result = self.run_hybrid(lambda x: [x[0], 2 * (1 - x[0])],
                                     [0.1], [(0, 1)], aggregation='max')
        self.assertAlmostEqual(result.x[0], 2 / 3)
        self.assertFalse(self.runs[0].success)
        self.assertEqual(self.runs[0].status, 2)
        self.assertEqual(self.runs[0].message, 'line search failed')

    def test_max_regressions(self):
        options = dict(aggregation='max')
        fixed = self.run_hybrid(lambda x: [x[0], x[1]], [0.5, 2],
                                [(0, 1), (2, 2)], **options)
        self.assertEqual(fixed.x[1], 2)
        budget = self.run_hybrid(lambda x: [x[0], x[1]], [0.5, 0.5],
                                 [(0, 1), (0, 1)], max_evaluations=2, **options)
        self.assertEqual(budget.evaluations, 2)
        self.assertEqual(budget.stop_reason, 'evaluation_budget_exhausted')
        self.assertFalse(self.runs[0].success)
        self.assertIsNone(self.runs[0].status)
        invalid = self.run_hybrid(lambda x: [np.nan], [0], [(0, 1)], **options)
        self.assertEqual(invalid.stop_reason, 'invalid_residual')
        self.assertIsNone(invalid.objective)
        with self.assertRaises(ValueError):
            self.run_hybrid(lambda x: [1], [2], [(0, 1)], **options)
        a = self.run_hybrid(lambda x: [x[0], x[0] - 1], [0.2], [(0, 1)], **options)
        b = self.run_hybrid(lambda x: [x[0], x[0] - 1], [0.2], [(0, 1)], **options)
        self.assertEqual(asdict(a), asdict(b))

    def test_unimodal_and_fixed_coordinates(self):
        seen = []
        def residual(x):
            seen.append(x.copy())
            return [x[0] - 0.3, x[1] - 2, 2 * (x[0] - 0.3)]
        result = self.run_hybrid(residual, [0.9, 2], [(0, 1), (2, 2)])
        self.assertTrue(self.runs[0].success)
        self.assertFalse(result.converged)  # local success does not end budget-only restarts
        self.assertEqual(result.stop_reason, 'evaluation_budget_exhausted')
        self.assertLess(result.objective, 1e-12)
        self.assertLess(result.objective, self.runs[0].start_fun)
        self.assertEqual(result.x[1], 2)
        self.assertTrue(all(0 <= x[0] <= 1 and x[1] == 2 for x in seen))
        self.assertEqual(result.evaluations, len(seen))


    def test_multimodal_uphill_restarts_and_determinism(self):
        seen = []
        def residual(x):
            seen.append(x.copy())
            return [abs(x[0] ** 2 - 1)]
        options = dict(seed=11, restart_sigma=0.8)
        a = self.run_hybrid(residual, [0.8], [(-2, 2)], **options)
        runs = self.runs
        b = self.run_hybrid(residual, [0.8], [(-2, 2)], **options)
        self.assertEqual(asdict(a), asdict(b))
        self.assertEqual(a.stop_reason, 'evaluation_budget_exhausted')
        ends = [r.end_x[0] for r in runs if r.success]
        self.assertTrue(any(x < -0.9 for x in ends))
        self.assertTrue(any(x > 0.9 for x in ends))
        self.assertTrue(any(r.start_fun > runs[0].end_fun + 0.01 for r in runs[1:]))
        self.assertTrue(all(-2 <= r.start_x[0] <= 2 and -2 <= r.end_x[0] <= 2 for r in runs))
        self.assertTrue(all(-2 <= x[0] <= 2 for x in seen))
        self.assertLess(a.objective, runs[0].start_fun)

    def test_exact_budget_even_mid_gradient_preserves_best(self):
        result = self.run_hybrid(lambda x: [x[0] - 0.2, x[1] - 0.4],
                                 [0.9, 0.9], [(0, 1), (0, 1)], max_evaluations=2)
        self.assertEqual(result.evaluations, 2)
        self.assertEqual(result.stop_reason, 'evaluation_budget_exhausted')
        self.assertFalse(self.runs[0].success)
        self.assertIsNone(self.runs[0].status)
        self.assertEqual(self.runs[0].evaluations, 2)
        self.assertIsNotNone(result.x)
        self.assertIsNotNone(self.runs[0].end_x)

    def test_failure_status_does_not_hide_best(self):
        result = self.run_hybrid(lambda x: [10 * (x[1] - x[0]**2), 1 - x[0]],
                                 [-1.2, 1], [(-2, 2), (-1, 3)], max_evaluations=5)
        self.assertFalse(self.runs[0].success)
        self.assertTrue(self.runs[0].message)
        self.assertIsNotNone(result.x)
        self.assertEqual(result.stop_reason, 'evaluation_budget_exhausted')

    def test_fixed_box_and_invalid_residuals(self):
        result = self.run_hybrid(lambda x: [x[0] - 1], [2], [(2, 2)])
        self.assertEqual(result.stop_reason, 'all_variables_fixed')
        self.assertTrue(result.converged)
        self.assertEqual(result.evaluations, 1)
        self.assertTrue(self.runs[0].success)
        for residual in (lambda x: [], lambda x: [np.nan], lambda x: [np.inf],
                         lambda x: [1e308]):
            with self.subTest(residual=residual):
                result = self.run_hybrid(residual, [0], [(0, 1)])
                self.assertEqual(result.stop_reason, 'invalid_residual')
                self.assertFalse(self.runs[0].success)
                self.assertIsNone(result.x)
                self.assertEqual(result.evaluations, 1)
        calls = []
        def changes(x):
            calls.append(1)
            return [1] if len(calls) == 1 else [1, 2]
        result = self.run_hybrid(changes, [0.5], [(0, 1)])
        self.assertEqual(result.stop_reason, 'invalid_residual')
        self.assertEqual(result.objective, 1)
        self.assertFalse(self.runs[0].success)

    def test_deep_boundaries_and_failure_preserve_order(self):
        from lpf.timing import TimerCollector

        def exercise(deep, failure):
            timer = TimerCollector()
            calls = []
            def scalar(x):
                calls.append(('scalar', float(x[0])))
                return [x[0]]
            def batch(vectors):
                calls.append(('batch', len(vectors)))
                def consume():
                    for x in vectors:
                        calls.append(('consume', float(x[0])))
                        yield [x[0]]
                return consume()
            def group(*, force=False):
                calls.append(('group', force))
                if failure and not force:
                    raise RuntimeError('checkpoint')
            def solver(fun, x, **kw):
                fun(x)
                kw['options']['workers'](fun, [x + 0.01, x + 0.02])
                kw['callback'](x)
                return OptimizeResult(x=x, fun=1.0, success=True, status=0, message='ok', nit=1)
            with patch('lpf.optimizers.lbfgsb.minimize', side_effect=solver):
                try:
                    result = lbfgsb_minimize(scalar, [0.5], [(0, 1)], seed=0, max_evaluations=3,
                                             restart_sigma=0.1, batch_fd=True, residuals_batch=batch,
                                             group_callback=group, _timing=(timer, 's') if deep else None)
                    outcome = asdict(result)
                except RuntimeError as exc:
                    outcome = str(exc)
            return outcome, calls, timer.snapshot()

        for failure in (False, True):
            plain, plain_calls, _ = exercise(False, failure)
            deep, calls, regions = exercise(True, failure)
            self.assertEqual((deep, calls), (plain, plain_calls))
            self.assertEqual(regions['s/objective/scalar']['count'], 1)
            if failure:  # scalar group callback aborts before batch
                self.assertEqual(regions['s/objective/state']['failed'], 1)
                self.assertEqual(regions['s/scipy/minimize']['failed'], 1)
            else:
                self.assertEqual(regions['s/objective/batch']['count'], 2)
                self.assertEqual(regions['s/batch/parent']['count'], 1)
                self.assertEqual(regions['s/scipy/callback']['count'], 1)
                self.assertEqual(regions['s/objective/prepare']['count'], 3)
                self.assertTrue(all(row['failed'] == 0 for row in regions.values()))

    def test_plain_hybrid_does_not_read_deep_clock(self):
        with patch('lpf.optimizers.lbfgsb.perf_counter_ns', side_effect=AssertionError('deep clock')):
            result = self.run_hybrid(lambda x: [x[0]], [0.5], [(0, 1)], max_evaluations=3)
        self.assertEqual(result.evaluations, 3)

    def test_deep_batch_exception_and_budget_stop(self):
        from lpf.timing import TimerCollector

        for fail_batch in (False, True):
            timer = TimerCollector()
            calls = []
            def batch(vectors):
                def consume():
                    calls.append('consume')
                    yield RuntimeError('injected') if fail_batch else [1.0]
                return consume()
            def solver(fun, x, **kw):
                fun(x)
                kw['options']['workers'](fun, [x + 0.01])
                fun(x)  # budget _Stop after the completed group
            groups = []
            with patch('lpf.optimizers.lbfgsb.minimize', side_effect=solver):
                if fail_batch:
                    with self.assertRaisesRegex(RuntimeError, 'injected'):
                        lbfgsb_minimize(lambda x: [1.0], [0.5], [(0, 1)], seed=0,
                                        max_evaluations=2, restart_sigma=0.1, batch_fd=True,
                                        residuals_batch=batch, group_callback=lambda **kw: groups.append(kw),
                                        _timing=(timer, 's'))
                else:
                    result = lbfgsb_minimize(lambda x: [1.0], [0.5], [(0, 1)], seed=0,
                                             max_evaluations=2, restart_sigma=0.1, batch_fd=True,
                                             residuals_batch=batch, group_callback=lambda **kw: groups.append(kw),
                                             _timing=(timer, 's'))
                    self.assertEqual((result.evaluations, result.stop_reason), (2, 'evaluation_budget_exhausted'))
            regions = timer.snapshot()
            self.assertEqual(calls, ['consume'])
            self.assertEqual(groups[-1], {'force': True})
            self.assertEqual(regions['s/scipy/minimize']['failed'], 1)
            if fail_batch:
                for name in ('objective/raw_batch', 'objective/batch', 'batch/parent'):
                    self.assertEqual(regions['s/'+name]['failed'], 1)
            else:
                self.assertEqual(regions['s/objective/prepare']['failed'], 1)
                self.assertEqual(regions['s/objective/scalar']['failed'], 1)

    def test_invalid_input(self):
        invalid = [([2], [(0, 1)], {}), ([0], [(1, 0)], {}),
                   ([0], [(0, np.inf)], {}), ([], [], {}),
                   ([0], [(0, 1)], {'max_evaluations': 0}),
                   ([0], [(0, 1)], {'restart_sigma': 0}),
                   ([0], [(0, 1)], {'aggregation': 'mean'}),
                   ([0], [(0, 1)], {'aggregation': None})]
        for x0, bounds, options in invalid:
            with self.subTest(x0=x0, bounds=bounds, options=options), self.assertRaises(ValueError):
                self.run_hybrid(lambda x: [1], x0, bounds, **options)


if __name__ == '__main__':
    unittest.main()

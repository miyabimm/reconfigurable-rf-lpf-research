import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
from scipy.optimize import OptimizeResult

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from lpf.optimizers.hybrid import hybrid_minimize


class PhysicalReuseTests(unittest.TestCase):
    def test_scipy_workers_candidates_match_scalar_and_are_independent(self):
        batches, seen, events = [], [], []

        def residual(x):
            return [x[0] + 2 * x[1]]

        def batch(vectors):
            batches.append([x.copy() for x in vectors])
            events.append(('batch', [x.copy() for x in vectors]))
            def consume():
                for x in vectors:
                    value = residual(x)
                    x[:] = -123  # must not leak into objective callbacks
                    yield value
            return consume()

        result = hybrid_minimize(residual, [0.4, 0.7], [(0, 1), (0, 1)],
                                 seed=1, max_evaluations=20, restart_sigma=0.1,
                                 batch_fd=True, residuals_batch=batch,
                                 objective_callback=lambda x, f: (seen.append((x, f)), events.append(('objective', x.copy()))))
        self.assertGreaterEqual(len(batches), 2)
        self.assertEqual(result.evaluations, len(seen))
        for x, value in seen:
            self.assertTrue(np.all((0 <= x) & (x <= 1)))
            self.assertEqual(value, residual(x)[0] ** 2)
        for i, (kind, vectors) in enumerate(events):
            if kind == 'batch':
                following = events[i + 1:i + 1 + len(vectors)]
                self.assertEqual([k for k, _ in following], ['objective'] * len(vectors))
                for expected, (_, actual) in zip(vectors, following):
                    np.testing.assert_array_equal(actual, expected)

    def test_start_continuous_batches_exception_replay_and_budget(self):
        observed, groups = [], []
        def batch(vectors):
            def consume():
                for i, x in enumerate(vectors):
                    if x[0] == 0.8:
                        raise ValueError('injected')
                    yield [x[0]]
            return consume()
        def solver(fun, z, **kw):
            workers = kw['options']['workers']
            fun(z)
            workers(fun, [z.copy(), np.array([0.6])])
            try:
                workers(fun, [np.array([0.7]), np.array([0.8])])
            except ValueError:
                pass
            fun(np.array([0.9]))  # scalar after generator failure
            return OptimizeResult(x=z, fun=1, success=True, status=0, message='ok', nit=0)
        with patch('lpf.optimizers.hybrid.minimize', side_effect=solver):
            result = hybrid_minimize(lambda x: [x[0]], [0.5], [(0, 1)], seed=1,
                                     max_evaluations=6, restart_sigma=0.1,
                                     batch_fd=True, residuals_batch=batch,
                                     objective_callback=lambda x, f: observed.append((x[0], f)),
                                     group_callback=lambda **kw: groups.append(kw))
        self.assertEqual([x for x, _ in observed], [0.5, 0.5, 0.6, 0.7, 0.9])
        self.assertEqual(result.evaluations, 6)
        self.assertEqual(result.stop_reason, 'evaluation_budget_exhausted')

    def test_wrapper_mismatch_and_missing_objective_fail_closed_then_restore(self):
        for wrapper in (lambda fun, z: fun(z + 0.1), lambda fun, z: 0.0):
            with self.subTest(wrapper=wrapper):
                observed = []
                def solver(fun, z, **kw):
                    workers = kw['options']['workers']
                    with self.assertRaisesRegex(RuntimeError, 'batch objective'):
                        workers(lambda v: wrapper(fun, v), [z.copy()])
                    fun(z)
                    return OptimizeResult(x=z, fun=0.25, success=True, status=0, message='ok', nit=0)
                with patch('lpf.optimizers.hybrid.minimize', side_effect=solver):
                    result = hybrid_minimize(lambda x: [x[0]], [0.5], [(0, 1)], seed=1,
                                             max_evaluations=1, restart_sigma=0.1,
                                             batch_fd=True, residuals_batch=lambda xs: [[1] for x in xs],
                                             objective_callback=lambda x, f: observed.append(x.tolist()))
                self.assertEqual(observed, [[0.5]])
                self.assertEqual(result.evaluations, 1)


if __name__ == '__main__':
    unittest.main()

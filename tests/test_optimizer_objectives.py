import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from lpf.optimizers._objectives import aggregate, squared_terms
from lpf.optimizers.hybrid import hybrid_minimize
from lpf.optimizers.slp import slp_minimize
from lpf.optimizers.slsqp import slsqp_minimize


class SquaredTermsCompatibilityTest(unittest.TestCase):
    def test_old_expression_bits_exceptions_and_input_ownership(self):
        # Include underflow, overflow, signed zeros and nonfinite values, as well
        # as normal finite values; exercise a read-only, strided caller array.
        values = np.array([-np.inf, -1e300, -1., -0., 0., np.nextafter(0., 1.),
                           1e-200, 1e-154, 1., np.sqrt(np.finfo(float).max),
                           1e300, np.inf, np.nan])
        storage = np.repeat(values, 2)
        residuals = storage[::2]
        residuals.flags.writeable = False
        before = storage.tobytes()
        weights_cases = (None, np.array([0., 1., 2., 0., 1., 2., 0., 1.,
                                         2., 0., 1., 2., 0.]))
        for weights in weights_cases:
            for under in ('ignore', 'raise'):
                with self.subTest(weights=weights, under=under), np.errstate(under=under):
                    def old():
                        positive = np.maximum(residuals, 0)
                        with np.errstate(over='ignore', invalid='ignore'):
                            return positive * positive if weights is None else weights * positive * positive
                    try:
                        expected = old()
                    except FloatingPointError:
                        with self.assertRaises(FloatingPointError):
                            squared_terms(residuals, weights)
                        continue
                    actual = squared_terms(residuals, weights)
                    np.testing.assert_array_equal(actual.view(np.uint64), expected.view(np.uint64))
                    self.assertFalse(np.shares_memory(actual, residuals))
                    for mode in ('sum', 'max'):
                        a, b = aggregate(actual, mode), aggregate(expected, mode)
                        self.assertEqual(np.float64(a).view(np.uint64), np.float64(b).view(np.uint64))
        self.assertEqual(storage.tobytes(), before)
        self.assertFalse(residuals.flags.writeable)
        self.assertTrue(storage.flags.writeable)

    def test_finite_writable_inputs_bitwise(self):
        rng = np.random.default_rng(496)
        for residuals in (np.array([-2., -0., 0., 1e-160, 1., 1e150]),
                          rng.normal(size=70)):
            before, writable = residuals.tobytes(), residuals.flags.writeable
            for weights in (None, np.linspace(0., 2., len(residuals))):
                positive = np.maximum(residuals, 0)
                with np.errstate(over='ignore', invalid='ignore'):
                    expected = positive * positive if weights is None else weights * positive * positive
                actual = squared_terms(residuals, weights)
                np.testing.assert_array_equal(actual.view(np.uint64), expected.view(np.uint64))
                self.assertFalse(np.shares_memory(actual, residuals))
                for mode in ('sum', 'max'):
                    self.assertEqual(np.float64(aggregate(actual, mode)).view(np.uint64),
                                     np.float64(aggregate(expected, mode)).view(np.uint64))
            self.assertEqual(residuals.tobytes(), before)
            self.assertEqual(residuals.flags.writeable, writable)


class SharedObjectiveTest(unittest.TestCase):
    def solve(self, residual, weights, mode):
        fun = lambda x: residual
        slp = slp_minimize(fun, [0], [(0, 0)], aggregation=mode, weights=weights,
                           max_iterations=2, max_evaluations=10)
        hybrid = hybrid_minimize(fun, [0], [(0, 0)], aggregation=mode, weights=weights,
                                 seed=0, max_evaluations=10, restart_sigma=.1)
        slsqp = slsqp_minimize(fun, [0], [(0, 0)], aggregation=mode, weights=weights,
                               max_iterations=2, max_evaluations=10)
        return slp, hybrid, slsqp

    def test_fixed_objectives(self):
        for residual, weights, expected in (
            ([-10., 1.], None, (1., 1.)),
            ([-10., -1.], None, (0., 0.)),
            ([1., 2.], None, (5., 4.)),
            ([2., -3., 4.], [2., 3., .5], (16., 8.)),
            ([1e300, 3.], [0., 2.], (18., 18.)),
            ([1e150, 2e150], [2., .5], (4e300, 2e300)),
            ([-1e300, 2.], None, (4., 4.)),
        ):
            for mode, value in zip(('sum', 'max'), expected):
                with self.subTest(residual=residual, weights=weights, mode=mode):
                    slp, hybrid, slsqp = self.solve(residual, weights, mode)
                    np.testing.assert_allclose([slp.objective, hybrid.objective, slsqp.objective],
                                               [value] * 3, rtol=1e-15)
                    # HiGHS may reject enormous LP coefficients; objective
                    # agreement does not imply that SLP converged.
                    self.assertTrue(hybrid.converged and slsqp.converged)

    def test_callbacks_match_transformed_objectives(self):
        for solver in (slp_minimize, hybrid_minimize, slsqp_minimize):
            for mode in ('sum', 'max'):
                with self.subTest(solver=solver.__name__, mode=mode):
                    observed = []
                    def residual(x):
                        return [-10., 1. + x[0], 2. - x[0]]
                    def observe(x, value):
                        terms = np.array([3., 2., .5]) * np.maximum(residual(x), 0)**2
                        expected = np.sum(terms) if mode == 'sum' else np.max(terms)
                        self.assertAlmostEqual(value, expected)
                        observed.append((x.copy(), value))
                    options = (dict(seed=0, restart_sigma=.1) if solver is hybrid_minimize
                               else dict(max_iterations=3))
                    result = solver(residual, [.3], [(0., 1.)], weights=[3., 2., .5],
                                    aggregation=mode, max_evaluations=20,
                                    objective_callback=observe, **options)
                    self.assertTrue(observed)
                    terms = np.array([3., 2., .5]) * np.maximum(residual(result.x), 0)**2
                    self.assertAlmostEqual(result.objective, np.sum(terms) if mode == 'sum' else np.max(terms))

    def test_nonfinite_residuals_are_not_masked(self):
        for value in (np.nan, np.inf, -np.inf):
            for mode in ('sum', 'max'):
                with self.subTest(value=value, mode=mode):
                    with self.assertRaises(ValueError):
                        slp_minimize(lambda x: [value], [0], [(0, 0)], aggregation=mode,
                                     weights=[0], max_iterations=2, max_evaluations=10)
                    for solver, opts in ((hybrid_minimize, dict(seed=0, restart_sigma=.1)),
                                         (slsqp_minimize, dict(max_iterations=2))):
                        result = solver(lambda x: [value], [0], [(0, 0)], aggregation=mode,
                                        weights=[0], max_evaluations=10, **opts)
                        self.assertEqual(result.stop_reason, 'invalid_residual')

    def test_invalid_weights_keep_solver_contracts(self):
        for weights in ([-1], [np.inf], [np.nan], [], [[1]]):
            with self.subTest(weights=weights):
                for mode in ('sum', 'max'):
                    with self.assertRaises(ValueError):
                        self.solve([1], weights, mode)
                    for solver in (hybrid_minimize, slsqp_minimize):
                        kwargs = (dict(seed=0, max_evaluations=10,
                                       restart_sigma=.1) if solver is hybrid_minimize else
                                  dict(max_iterations=2, max_evaluations=10))
                        with self.assertRaises(ValueError):
                            solver(lambda x: [1], [0], [(0, 0)], weights=weights,
                                   aggregation=mode, **kwargs)
        # A length mismatch is detected after evaluating residuals; Hybrid stops,
        # whereas SLP and SLSQP raise ValueError.
        for solver in (slp_minimize, slsqp_minimize):
            with self.assertRaises(ValueError):
                solver(lambda x: [1, 2], [0], [(0, 0)], weights=[1],
                       max_iterations=2, max_evaluations=10)
        hybrid = hybrid_minimize(lambda x: [1, 2], [0], [(0, 0)], weights=[1],
                                 seed=0, max_evaluations=10, restart_sigma=.1)
        self.assertEqual(hybrid.stop_reason, 'invalid_residual')

    def test_overflow_keeps_solver_failure_contracts(self):
        # Terms are finite but their sum overflows; max remains finite.
        residual = [1e154, 1e154]
        slp, hybrid, slsqp = self.solve(residual, None, 'max')
        self.assertTrue(np.isfinite(slp.objective) and np.isfinite(hybrid.objective)
                        and np.isfinite(slsqp.objective))
        with self.assertRaises(ValueError):
            slp_minimize(lambda x: residual, [0], [(0, 0)], max_iterations=2, max_evaluations=10)
        hybrid = hybrid_minimize(lambda x: residual, [0], [(0, 0)], seed=0,
                                 max_evaluations=10, restart_sigma=.1)
        slsqp = slsqp_minimize(lambda x: residual, [0], [(0, 0)], max_iterations=2,
                               max_evaluations=10)
        self.assertEqual(hybrid.stop_reason, 'invalid_residual')
        self.assertEqual(slsqp.stop_reason, 'invalid_residual')

    def test_component_overflow_in_both_modes(self):
        for mode in ('sum', 'max'):
            with self.subTest(mode=mode):
                with self.assertRaises(ValueError):
                    slp_minimize(lambda x: [1e300], [0], [(0, 0)], aggregation=mode,
                                 max_iterations=2, max_evaluations=10)
                hybrid = hybrid_minimize(lambda x: [1e300], [0], [(0, 0)], aggregation=mode,
                                         seed=0, max_evaluations=10, restart_sigma=.1)
                slsqp = slsqp_minimize(lambda x: [1e300], [0], [(0, 0)], aggregation=mode,
                                       max_iterations=2, max_evaluations=10)
                self.assertEqual(hybrid.stop_reason, 'invalid_residual')
                self.assertEqual(slsqp.stop_reason, 'invalid_residual')

    def test_slp_runs_with_only_its_own_modules(self):
        source = Path(__file__).resolve().parents[1] / 'src' / 'lpf' / 'optimizers'
        with tempfile.TemporaryDirectory() as tmp:
            package = Path(tmp) / 'lpf' / 'optimizers'
            package.mkdir(parents=True)
            (package.parent / '__init__.py').touch()
            for name in ('__init__.py', 'slp.py', '_objectives.py', 'result.py'):
                shutil.copy(source / name, package / name)
            code = ("import sys; sys.path.insert(0, sys.argv[1]); "
                    "from lpf.optimizers.slp import slp_minimize; "
                    "r=slp_minimize(lambda x: [-2.], [0], [(0,0)], "
                    "aggregation='signed_max', max_iterations=2, max_evaluations=5); "
                    "assert r.converged and r.objective == -2.")
            subprocess.run([sys.executable, '-I', '-c', code, tmp], check=True)


if __name__ == '__main__':
    unittest.main()

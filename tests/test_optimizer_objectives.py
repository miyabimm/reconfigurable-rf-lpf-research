import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from lpf.optimizers._objectives import aggregate, squared_terms
from lpf.optimizers.lbfgsb import lbfgsb_minimize
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
    def test_unit_weight_objectives_and_callbacks(self):
        for solver in (lbfgsb_minimize, slsqp_minimize):
            for mode, expected in (('sum', 20.), ('max', 16.)):
                observed = []
                opts = dict(seed=0, restart_sigma=.1) if solver is lbfgsb_minimize else dict(max_iterations=2)
                result = solver(lambda x: [2., -3., 4.], [0.], [(0., 0.)], aggregation=mode,
                                max_evaluations=10, objective_callback=lambda x, f: observed.append(f), **opts)
                self.assertEqual(result.objective, expected)
                self.assertEqual(observed, [expected])

    def test_nonfinite_and_overflow_stop(self):
        for solver in (lbfgsb_minimize, slsqp_minimize):
            opts = dict(seed=0, restart_sigma=.1) if solver is lbfgsb_minimize else dict(max_iterations=2)
            for value in (float('nan'), float('inf'), 1e300):
                result = solver(lambda x: [value], [0.], [(0., 0.)], max_evaluations=10, **opts)
                self.assertEqual(result.stop_reason, 'invalid_residual')








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

"""D1/CD1 diagnostic-only regressions; production stays unmodified."""
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

import numpy as np
import test_issue499_sensitivity as issue499
import test_issue519_sensitivity as issue519

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'project/diagnostics/issue521'))
import kernel
from numerics import wave_derivative
from lpf.rf_core import model as rf
from lpf.rf_core.model import power_response
from lpf.rf_core.numerical_diagnostics import CircuitNumericalError
from test_issue307_constraints import make
from test_issue309_rf_core import grid


class CandidateValidationTests(unittest.TestCase):
    def test_candidate_against_existing_baseline_regressions(self):
        # Packed solve injection is inapplicable because D1/CD1 remove those solves.
        old = [name for name in unittest.defaultTestLoader.getTestCaseNames(issue499.NodalSensitivityTests)
               if name != 'test_packed_sensitivity_solves_fail_closed']
        prior = unittest.defaultTestLoader.getTestCaseNames(issue519.Issue519SensitivityTests)
        for mode, c in (('D1', False), ('CD1', True)):
            fn, _ = kernel.variant(c, 'D1')
            with patch.object(rf.RFEvaluator, 'evaluate_with_il_jacobian', fn):
                for klass, names in ((issue499.NodalSensitivityTests, old),
                                     (issue519.Issue519SensitivityTests, prior)):
                    for name in names:
                        with self.subTest(mode=mode, test=name):
                            case = klass(methodName=name)
                            case.setUp()
                            try:
                                getattr(case, name)()
                            finally:
                                case.tearDown()

    def test_remaining_packed_solve_failure(self):
        _, _, model, _, x = make('RF-T008')
        ev = model.evaluator(grid(model.resolved_policy))
        solve = np.linalg.solve
        for mode, c in (('D1', False), ('CD1', True)):
            fn, _ = kernel.variant(c, 'D1')
            for behavior in ('raise', 'nan'):
                calls = []
                def injected(a, b):
                    if a.ndim == 3 and b.ndim == 3 and b.shape[-1] == 2*len(x):
                        calls.append(1)
                        if behavior == 'raise':
                            raise np.linalg.LinAlgError('injected packed sensitivity')
                        result = solve(a, b)
                        result[...] = np.nan
                        return result
                    return solve(a, b)
                with self.subTest(mode=mode, behavior=behavior), patch('numpy.linalg.solve', side_effect=injected):
                    if c:
                        fn(ev, x)
                        self.assertEqual(len(calls), 0)
                    else:
                        with self.assertRaises(CircuitNumericalError) as error:
                            fn(ev, x)
                        self.assertEqual(error.exception.code, 'sensitivity_solve_failed'
                                         if behavior == 'raise' else 'sensitivity_nonfinite')
                        self.assertEqual(len(calls), 1)

    def test_candidate_inductor_sensitivity_failure(self):
        _, _, model, _, x = make('RF-T008')
        ev = model.evaluator(grid(model.resolved_policy))
        solve = np.linalg.solve
        for mode, c in (('D1', False), ('CD1', True)):
            fn, _ = kernel.variant(c, 'D1')
            for behavior in ('raise', 'nan'):
                calls = []
                def injected(a, b):
                    if a.ndim == 2 and b.ndim == 3:
                        calls.append(1)
                        if behavior == 'raise':
                            raise np.linalg.LinAlgError('injected inductor sensitivity')
                        result = solve(a, b)
                        result[...] = np.nan
                        return result
                    return solve(a, b)
                with self.subTest(mode=mode, behavior=behavior), patch('numpy.linalg.solve', side_effect=injected):
                    with self.assertRaises(CircuitNumericalError) as error:
                        fn(ev, x)
                    self.assertEqual(error.exception.code, 'sensitivity_inductor_solve_failed'
                                     if behavior == 'raise' else 'sensitivity_node_nonfinite')
                    self.assertEqual(len(calls), 1)

    def test_fixed_reference_nonfinite_hidden_by_d1(self):
        # Synthetic finite, passive forward input; not proven reachable in the circuit.
        rng = np.random.default_rng(521)
        f = .2*(rng.normal(size=(1, 2, 2))+1j*rng.normal(size=(1, 2, 2)))
        df = 1e307*(rng.normal(size=(1, 1, 2, 2))+1j*rng.normal(size=(1, 1, 2, 2)))
        z = np.array([50, 60-40j], complex)
        self.assertTrue(np.isfinite(df).all())
        s = power_response(f, *z, check_power=True)[0]
        with np.errstate(all='ignore'):
            old = wave_derivative(f, s, z, df, False)
            new = wave_derivative(f, s, z, df, 'D1')
            old_il = -20/np.log(10)*np.real(old[:, :, 1, 0]/s[:, None, 1, 0])
            new_il = -20/np.log(10)*np.real(new[:, :, 1, 0]/s[:, None, 1, 0])
        self.assertFalse(np.isfinite(old_il).all())
        self.assertTrue(np.isfinite(new_il).all())

    def test_fixed_reference_extreme_wave_values(self):
        f = np.array([[[.8, .1], [.1, .2]]], complex)
        z = np.array([50, 60-40j], complex)
        s = power_response(f, *z)[0]
        with np.errstate(all='ignore'):
            for exponent in (0, 100, 125, 200, 300, 305, 306, 307, 308):
                df = np.ones((1, 1, 2, 2), complex)*10.**exponent
                jac = []
                for mode in (False, 'D1'):
                    ds = wave_derivative(f, s, z, df, mode)
                    jac.append(-20/np.log(10)*np.real(ds[:, :, 1, 0]/s[:, None, 1, 0]))
                with self.subTest(exponent=exponent):
                    np.testing.assert_array_equal(np.isfinite(jac[0]), np.isfinite(jac[1]))
                    if np.isfinite(jac[0]).all():
                        np.testing.assert_allclose(jac[0], jac[1], rtol=1e-12, atol=1e-12)


if __name__ == '__main__':
    unittest.main()

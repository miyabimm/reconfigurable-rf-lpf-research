"""Diagnostic C/D algebra and a documented D STOP difference; not production adoption."""
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'project/diagnostics/issue521'))
from numerics import core_derivative, wave_derivative
from lpf.rf_core.model import power_response
from lpf.rf_core import model as rf
from lpf.rf_core.numerical_diagnostics import CircuitNumericalError
from test_issue307_constraints import make
from test_issue309_rf_core import grid


class Issue521DiagnosticTests(unittest.TestCase):
    def test_core_nonreciprocal_all_components_against_fd(self):
        rng = np.random.default_rng(521)
        r = .01*(rng.normal(size=(4, 2, 2))+1j*rng.normal(size=(4, 2, 2)))
        dr = .001*(rng.normal(size=(4, 3, 2, 2))+1j*rng.normal(size=(4, 3, 2, 2)))
        eye = np.eye(2)
        def forward(y):
            return np.linalg.solve(eye+50*y, eye-50*y)
        a, core = eye+50*r, forward(r)
        old = core_derivative(a, core, dr, False)
        new = core_derivative(a, core, dr, True)
        np.testing.assert_allclose(new, old, rtol=1e-12, atol=1e-12)
        for j in range(3):
            h = 1e-5
            fd = (forward(r+h*dr[:, j])-forward(r-h*dr[:, j]))/(2*h)
            np.testing.assert_allclose(new[:, j], fd, rtol=1e-7, atol=1e-9)

    def test_wave_complex_reference_nonreciprocal_zeros_and_50(self):
        rng = np.random.default_rng(522)
        f = .1*(rng.normal(size=(4, 2, 2))+1j*rng.normal(size=(4, 2, 2)))
        f[0, 0, 0] = 0  # reflection zero for matched reference
        f[1, 1, 0] = 0  # transmission zero; complex S derivative still exists
        df = .1*(rng.normal(size=(4, 3, 2, 2))+1j*rng.normal(size=(4, 3, 2, 2)))
        for z in (np.array([50, 50], complex), np.array([31+17j, 80-23j])):
            s = power_response(f, *z)[0]
            old = wave_derivative(f, s, z, df, False)
            new = wave_derivative(f, s, z, df, 'D1')
            d2 = wave_derivative(f, s, z, df, 'D2')
            np.testing.assert_allclose(new, old, rtol=1e-12, atol=1e-12)
            np.testing.assert_allclose(d2, old[:, :, (0, 1, 1), (0, 0, 1)], rtol=1e-12, atol=1e-12)
            for j in range(3):
                h = 1e-5
                fd = (power_response(f+h*df[:, j], *z)[0]-power_response(f-h*df[:, j], *z)[0])/(2*h)
                np.testing.assert_allclose(new[:, j], fd, rtol=1e-7, atol=1e-10)

    def test_production_complex_s_all_columns(self):
        _, _, model, _, x = make('RF-T008')
        ev = model.evaluator(grid(model.resolved_policy))
        captures = []
        cascade = rf._cascade_jacobian
        def observe(a, da, b, db):
            result = cascade(a, da, b, db)
            if db is None:
                captures.append((rf._cascade(a, b), result.copy()))
            return result
        with patch.object(rf, '_cascade_jacobian', observe):
            response, jac = ev.evaluate_with_il_jacobian(x)
        self.assertEqual(len(captures), 1)
        full, dfull = captures[0]
        z = np.asarray([ev.source_ohms, ev.load_ohms])
        compact = wave_derivative(full, response.s, z, dfull, 'D1')
        start = len(x)-6*model.schema.n_variable
        ds = np.zeros((len(ev.grid.setting), len(x), 2, 2), complex)
        ds[:, :start] = compact[:, :start]
        cols = start + ev.grid.setting[:, None]*model.schema.n_variable + np.arange(model.schema.n_variable)
        ds[np.arange(len(ev.grid.setting))[:, None], cols] = compact[:, start:]
        np.testing.assert_allclose(jac, -20/np.log(10)*np.real(ds[:, :, 1, 0]/response.s[:, None, 1, 0]), rtol=1e-12, atol=1e-12)
        for s in range(6):
            columns = slice(start+s*model.schema.n_variable, start+(s+1)*model.schema.n_variable)
            np.testing.assert_array_equal(ds[ev.grid.setting != s, columns], 0)
        for j in range(len(x)):
            h = 1e-5*max(1., abs(x[j]))
            plus, minus = x.copy(), x.copy()
            plus[j] += h; minus[j] -= h
            fd = (ev.evaluate(plus).s-ev.evaluate(minus).s)/(2*h)
            for row, col in ((0, 0), (1, 0), (1, 1)):
                np.testing.assert_allclose(ds[:, j, row, col], fd[:, row, col], rtol=1e-4, atol=1e-7,
                                           err_msg=f'S{row+1}{col+1} column {j}')

    def test_inductor_sensitivity_failure(self):
        _, _, model, _, x = make('RF-T008')
        ev = model.evaluator(grid(model.resolved_policy))
        solve = np.linalg.solve
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
            with self.subTest(behavior=behavior), patch('numpy.linalg.solve', side_effect=injected):
                with self.assertRaises(CircuitNumericalError) as error:
                    ev.evaluate_with_il_jacobian(x)
                self.assertEqual(error.exception.code, 'sensitivity_inductor_solve_failed'
                                 if behavior == 'raise' else 'sensitivity_node_nonfinite')
                self.assertEqual(len(calls), 1)

    def test_fixed_z_old_intermediate_overflow_is_not_a_required_stop(self):
        rng = np.random.default_rng(521)
        f = .2*(rng.normal(size=(1, 2, 2))+1j*rng.normal(size=(1, 2, 2)))
        df = 1e307*(rng.normal(size=(1, 1, 2, 2))+1j*rng.normal(size=(1, 1, 2, 2)))
        z = np.array([50, 60-40j], complex)
        s = power_response(f, *z, check_power=True)[0]
        with np.errstate(all='ignore'):
            old = wave_derivative(f, s, z, df, False)
            new = wave_derivative(f, s, z, df, 'D1')
            old_il = -20/np.log(10)*np.real(old[:, :, 1, 0]/s[:, None, 1, 0])
            new_il = -20/np.log(10)*np.real(new[:, :, 1, 0]/s[:, None, 1, 0])
        self.assertFalse(np.isfinite(old_il).all())
        self.assertTrue(np.isfinite(new_il).all())
        np.testing.assert_allclose(new_il, 1.6304140225710164e308, rtol=1e-14)

    def test_wave_extreme_finite_synthetic_stop_difference(self):
        # This documents a wave-level counterexample, not reachability under RF-T010.
        f = np.array([[[.8, .1], [.1, .2]]], complex)
        z = np.array([1e-200, 1e-200], complex)
        df = np.ones((1, 1, 2, 2), complex)*1e125
        with np.errstate(all='ignore'):
            s = power_response(f, *z)[0]
            self.assertNotEqual(s[0, 1, 0], 0)
            jac = []
            for mode in (False, 'D1', 'D2'):
                ds = wave_derivative(f, s, z, df, mode)
                ds21 = ds[:, :, 1] if mode == 'D2' else ds[:, :, 1, 0]
                jac.append(-20/np.log(10)*np.real(ds21/s[:, None, 1, 0]))
            self.assertTrue(np.isfinite(jac[0]).all())
            self.assertFalse(np.isfinite(jac[1]).all())
            self.assertFalse(np.isfinite(jac[2]).all())


if __name__ == '__main__':
    unittest.main()

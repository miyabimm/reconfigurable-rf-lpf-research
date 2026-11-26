"""Diagnostic C/D algebra and a documented D STOP difference; not production adoption."""
from pathlib import Path
import sys
import unittest

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'project/diagnostics/issue521'))
from numerics import core_derivative, wave_derivative
from lpf.rf_core.model import power_response


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

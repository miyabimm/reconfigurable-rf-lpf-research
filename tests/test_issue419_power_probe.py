"""Diagnostic candidates: retain explicit counterexamples, never install a fast path."""
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'project/diagnostics'))
import issue419_probe as probe
from lpf.rf_core.numerical_diagnostics import CircuitNumericalError


class PowerProbeTests(unittest.TestCase):
    def setUp(self):
        self.funcs = [probe.ORIGINAL, probe.make_candidate('A'), probe.make_candidate('B')]

    @staticmethod
    def code(func, s, zs, zl):
        try:
            with np.errstate(all='ignore'):
                func(s, zs, zl)
        except CircuitNumericalError as exc:
            return exc.code
        return 'ok'

    def test_zero_tiny_complex_and_invalid_inputs(self):
        zero = np.zeros((1, 2, 2), complex)
        tiny = zero.copy(); tiny[0, 1, 0] = 1e-200
        for f in self.funcs:
            self.assertTrue(all(np.isposinf(x[0]) for x in f(zero, 50, 50)[1:]))
            self.assertEqual(f(tiny, 50, 50)[1][0], 4000.)
            for s in (np.full((1,2,2), np.nan), np.full((1,2,2), np.inf), np.zeros((2,2))):
                with self.assertRaises(ValueError): f(s, 50, 60-40j)
            for z in (-50, 0, np.nan, np.inf):
                with self.assertRaises(ValueError): f(zero, z, 50)
            sample = np.array([[[.2+.1j,.3-.1j],[.3-.1j,.1+.1j]]])
            for a, b in zip(probe.ORIGINAL(sample, 48+3j, 60-40j), f(sample, 48+3j, 60-40j)):
                np.testing.assert_allclose(a, b, atol=1e-12, rtol=1e-12)

    def test_singular_and_reflection_boundary(self):
        singular = np.array([[[3.,0.],[0.,3.]]], complex)
        for f in self.funcs:
            self.assertEqual(self.code(f, singular, 100, 100), 'wave_singular')
            for reflection in (1., 1.1):
                s = np.zeros((1,2,2),complex); s[0,1,1] = reflection
                self.assertEqual(self.code(f, s, 50, 50), 'available_gain_undefined')
            s = np.zeros((1,2,2),complex); s[0,1,1] = .999999
            self.assertEqual(self.code(f, s, 50, 50), 'ok')
        # Nearly singular: check outcomes and errors without claiming full conditioning coverage.
        near = singular.copy(); near[0,0,0] += 1e-12; near[0,1,1] += 1e-12
        self.assertEqual([self.code(f, near, 100, 100) for f in self.funcs],
                         ['available_gain_undefined']*3)

    def test_explicit_finite_extreme_stop_mismatches(self):
        minus_eye = -np.eye(2, dtype=complex)[None,:,:]
        zero = np.zeros((1,2,2),complex)
        # A loses the tiny residual in the rearranged coefficients; B's
        # unscaled complex determinant overflows. Both violate the old STOP.
        self.assertEqual([self.code(f, minus_eye, 1e-300, 1e-300) for f in self.funcs],
                         ['available_gain_undefined', 'wave_singular', 'available_gain_undefined'])
        self.assertEqual([self.code(f, zero, 1e-308, 1e-308) for f in self.funcs],
                         ['available_gain_undefined', 'available_gain_undefined', 'wave_nonfinite'])
        self.assertEqual([self.code(f, minus_eye, 1e-320, 1e-320) for f in self.funcs],
                         ['ok', 'wave_singular', 'wave_nonfinite'])

    def test_old_error_codes_and_propagation(self):
        zero = np.zeros((1,2,2),complex)
        for value, code in ((np.full((1,2,2), np.nan+0j), 'wave_nonfinite'),
                            (np.full((1,2,2), 1.7e308+1.7e308j), 'wave_nonfinite')):
            with patch('numpy.linalg.solve', return_value=value):
                self.assertEqual(self.code(probe.ORIGINAL, zero, 50, 50), code)
        with patch('numpy.log10', return_value=np.array([np.nan])):
            for func in self.funcs:
                self.assertEqual(self.code(func, zero, 50, 50), 'db_invalid')
        with patch('numpy.linalg.solve', side_effect=np.linalg.LinAlgError('fixture')):
            self.assertEqual(self.code(probe.ORIGINAL, zero, 50, 50), 'wave_singular')
        with patch('numpy.linalg.solve', side_effect=RuntimeError('propagate')):
            with self.assertRaisesRegex(RuntimeError, 'propagate'):
                probe.ORIGINAL(zero, 50, 50)


if __name__ == '__main__': unittest.main()

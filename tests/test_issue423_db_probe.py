"""Issue 423 candidate must preserve dB and STOP behavior, including fault injection."""
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'project/diagnostics'))
import issue423_current_probe as probe
from lpf.rf_core.numerical_diagnostics import CircuitNumericalError


class DBCheckTests(unittest.TestCase):
    def setUp(self):
        self.funcs = (probe.old_power_response(), probe.PRODUCTION)

    def outcome(self, func, s, zs=50, zl=50):
        try:
            with np.errstate(all='ignore'):
                return ('ok', func(s, zs, zl))
        except Exception as exc:
            return (type(exc).__name__, getattr(exc, 'code', str(exc)))

    def compare(self, s, zs=50, zl=50):
        a, b = (self.outcome(f, s, zs, zl) for f in self.funcs)
        self.assertEqual(a[0], b[0])
        if a[0] == 'ok':
            for x, y in zip(a[1], b[1]):
                self.assertEqual(x.tobytes(), y.tobytes())
        else:
            self.assertEqual(a[1], b[1])
        return a[0] if a[0] == 'ok' else a[1]

    def test_cases(self):
        zero = np.zeros((1, 2, 2), complex)
        self.assertEqual(self.compare(np.zeros((0, 2, 2), complex)), 'ok')
        self.assertEqual(self.compare(zero), 'ok')  # +inf metrics permitted
        tiny = zero.copy(); tiny[0, 1, 0] = 1e-200
        self.assertEqual(self.compare(tiny), 'ok')
        sample = np.array([[[.2+.1j, .3-.1j], [.3-.1j, .1+.1j]]])
        self.assertEqual(self.compare(sample, 48+3j, 60-40j), 'ok')
        for r in (.999999, 1., 1.1):
            s = zero.copy(); s[0, 1, 1] = r
            self.assertEqual(self.compare(s), 'ok' if r < 1 else 'available_gain_undefined')
        singular = np.array([[[3., 0.], [0., 3.]]], complex)
        self.assertEqual(self.compare(singular, 100, 100), 'wave_singular')
        near = singular.copy(); near[0, 0, 0] += 1e-12; near[0, 1, 1] += 1e-12
        self.assertEqual(self.compare(near, 100, 100), 'available_gain_undefined')
        for s, z, expected in ((-np.eye(2, dtype=complex)[None], 1e-300, 'available_gain_undefined'),
                               (zero, 1e-308, 'available_gain_undefined'),
                               (-np.eye(2, dtype=complex)[None], 1e-320, 'ok')):
            self.assertEqual(self.compare(s, z, z), expected)
        for s in (np.full((1, 2, 2), np.nan), np.full((1, 2, 2), np.inf), np.zeros((2, 2))):
            self.assertIn('Expected finite', self.compare(s))
        for z in (0, -50, np.nan, np.inf):
            self.assertIn('Non-passive', self.compare(zero, z, 50))

    def test_fault_injection_and_propagation(self):
        zero = np.zeros((1, 2, 2), complex)
        for index in range(4):
            for val in (np.nan, -np.inf, np.inf, 0.):
                def log10(_):
                    result = np.array([val if log10.calls % 4 == index else 0.])
                    log10.calls += 1
                    return result
                log10.calls = 0
                with patch('numpy.log10', side_effect=log10):
                    # Available-log contributes with positive sign; others are negated.
                    invalid = np.isnan(val) or (val == (-np.inf if index == 1 else np.inf))
                    self.assertEqual(self.compare(zero), 'db_invalid' if invalid else 'ok')
        for val in (np.nan+0j, 1.7e308+1.7e308j):
            with patch('numpy.linalg.solve', return_value=np.full((1, 2, 2), val)):
                self.assertEqual(self.compare(zero), 'wave_nonfinite')
        with patch('numpy.linalg.solve', side_effect=np.linalg.LinAlgError('fixture')):
            self.assertEqual(self.compare(zero), 'wave_singular')
        with patch('numpy.linalg.solve', side_effect=RuntimeError('propagate')):
            self.assertEqual(self.compare(zero), 'propagate')


if __name__ == '__main__':
    unittest.main()

"""Production regression for symmetric Schur and one-fixed-side cascade."""
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import patch
import unittest
import warnings

import numpy as np

from test_issue307_constraints import make
from test_issue309_rf_core import grid
from lpf.rf_core import model as rf
from lpf.rf_core.coupled_lc import CoupledLCTopology
from lpf.rf_core.numerical_diagnostics import CircuitNumericalError


class Issue519SensitivityTests(unittest.TestCase):
    def setUp(self):
        _, _, self.model, _, self.x = make('RF-T008')
        self.ev = self.model.evaluator(grid(self.model.resolved_policy))

    def test_no_internal_nodes_forward_and_jacobian(self):
        top = self.model.topology
        class Projected:
            inductor_tree = SimpleNamespace(node_count=2, source_node=0, load_node=1)
            def matrices(self, values):
                return top.matrices(values)
            def node_admittance(self, *args, **kwargs):
                return top.node_admittance(*args, **kwargs)[:, :2, :2]
            def port_admittance_jacobian(self, values, schema, omega, settings, T, *, matrices):
                lift = np.zeros((len(omega), top.inductor_tree.node_count, 2), complex)
                lift[:, :2] = T
                return top.port_admittance_jacobian(values, schema, omega, settings, lift, matrices=matrices)
        ev = replace(self.model, topology=Projected()).evaluator(self.ev.grid)
        omega = 2*np.pi*ev.grid.frequency_hz
        def forward(x):
            y = ev.model.topology.node_admittance(ev.model.decode(x), omega, ev.grid.setting)
            core = np.linalg.solve(np.eye(2) + 50*y, np.eye(2) - 50*y)
            return rf.power_response(rf._cascade(rf._cascade(ev.pre, core), ev.post), ev.source_ohms, ev.load_ohms)
        response, jac = ev.evaluate_with_il_jacobian(self.x)
        for actual, expected in zip((response.s, response.il_db, response.apl_db, response.in_rl_db, response.out_rl_db), forward(self.x)):
            np.testing.assert_allclose(actual, expected, rtol=1e-12, atol=1e-12)
        for j in range(len(self.x)):
            h = 1e-5*max(1., abs(self.x[j]))
            plus, minus = self.x.copy(), self.x.copy()
            plus[j] += h; minus[j] -= h
            fd = (forward(plus)[1]-forward(minus)[1])/(2*h)
            np.testing.assert_allclose(jac[:, j], fd, rtol=1e-4, atol=1e-5, err_msg=f'column {j}')

    def test_cascade_one_fixed_side_against_directional_difference(self):
        rng = np.random.default_rng(519)
        a = .2*(rng.normal(size=(4, 2, 2)) + 1j*rng.normal(size=(4, 2, 2)))
        b = .2*(rng.normal(size=(4, 2, 2)) + 1j*rng.normal(size=(4, 2, 2)))
        # Nonreciprocal inputs, and fixed/variable reflection/transmission zeros.
        a[0, 0, 1] = 0; b[1, 1, 0] = 0; a[2, 1, 1] = 0; b[3, 0, 0] = 0
        d = rng.normal(size=(4, 3, 2, 2)) + 1j*rng.normal(size=(4, 3, 2, 2))
        h = 1e-6
        for side in ('left_fixed', 'right_fixed'):
            actual = rf._cascade_jacobian(a, None, b, d) if side == 'left_fixed' else rf._cascade_jacobian(a, d, b, None)
            for j in range(d.shape[1]):
                if side == 'left_fixed':
                    expected = (rf._cascade(a, b+h*d[:, j])-rf._cascade(a, b-h*d[:, j]))/(2*h)
                else:
                    expected = (rf._cascade(a+h*d[:, j], b)-rf._cascade(a-h*d[:, j], b))/(2*h)
                np.testing.assert_allclose(actual[:, j], expected, rtol=1e-7, atol=1e-9, err_msg=side)

    def test_forward_cascade_failure_precedes_sensitivity(self):
        with patch.object(rf, '_cascade', side_effect=CircuitNumericalError('cascade_singular', 'injected')), \
             patch.object(CoupledLCTopology, 'port_admittance_jacobian') as sensitivity:
            with self.assertRaises(CircuitNumericalError) as failure:
                self.ev.evaluate_with_il_jacobian(self.x)
            self.assertEqual(failure.exception.code, 'cascade_singular')
            sensitivity.assert_not_called()

    def test_extreme_forward_finite_cascade_derivative_overflow(self):
        for eps in (1e-16, 1e-100, 1e-160, 1e-200, 1e-300):
            for zero in (False, True):
                a = np.ones((1, 2, 2), complex); b = np.ones((1, 2, 2), complex)
                b[0, 0, 0] = 1+1j*eps
                if zero:
                    a[0, 0, 1] = 0
                d = np.ones((1, 1, 2, 2), complex)
                with self.subTest(eps=eps, zero=zero), np.errstate(all='ignore'):
                    self.assertTrue(np.isfinite(rf._cascade(a, b)).all())
                    for da, db in ((None, d), (d, None)):
                        finite = np.isfinite(rf._cascade_jacobian(a, da, b, db))
                        # These masks matched the historical formula in regression20.
                        np.testing.assert_array_equal(finite, np.full_like(finite, eps >= 1e-100))

    def test_nonfinite_and_overflow_sensitivity_fail_closed(self):
        original = CoupledLCTopology.port_admittance_jacobian
        for value in (np.nan, np.inf, 1e308):
            def injected(top, *args, **kwargs):
                dy = original(top, *args, **kwargs)
                dy = dy.copy(); dy[:, 0, :, :] = value
                return dy
            with self.subTest(value=value), patch.object(CoupledLCTopology, 'port_admittance_jacobian', injected):
                with warnings.catch_warnings(), self.assertRaises(CircuitNumericalError) as failure:
                    warnings.simplefilter('ignore', RuntimeWarning)
                    self.ev.evaluate_with_il_jacobian(self.x)
                self.assertEqual(failure.exception.code, 'sensitivity_nonfinite')

    def test_deep_hook_restoration_on_success_and_failure(self):
        from lpf.rf_core import coupled_lc
        from lpf.search._rf_deep_timing import search_rf_timing
        from lpf.timing import TimerCollector
        method, cascade = rf.RFEvaluator.evaluate_with_il_jacobian, rf._cascade_jacobian
        for fail in (False, True):
            with self.subTest(fail=fail):
                with search_rf_timing(TimerCollector(), 'search'):
                    if fail:
                        with patch.object(rf, '_cascade_jacobian', side_effect=RuntimeError('injected')):
                            with self.assertRaisesRegex(RuntimeError, 'injected'):
                                self.ev.evaluate_with_il_jacobian(self.x)
                    else:
                        self.ev.evaluate_with_il_jacobian(self.x)
                self.assertIs(rf.RFEvaluator.evaluate_with_il_jacobian, method)
                self.assertIs(rf._cascade_jacobian, cascade)
                self.assertIsNone(rf._deep_timing)
                self.assertIsNone(coupled_lc._deep_timing)


if __name__ == '__main__':
    unittest.main()

"""Bounded deterministic Stage-2 numerics; no EXP or optimizer execution."""
import copy
from contextlib import ExitStack
import csv
from dataclasses import asdict
import hashlib
import json
from dataclasses import replace
from pathlib import Path
import unittest
import tempfile
from unittest.mock import patch
import numpy as np

from test_issue307_constraints import make
from lpf.constraint_versions import load_constraint, rf_input_file
from lpf.rf_core._grid import validated_band_segments
from lpf.rf_core.coupled_lc import CoupledLCTopology
from lpf.rf_core import build_rf_model, EvaluationGrid
from lpf.rf_core.model import power_response, _cascade
from lpf.rf_core.independent import validate_response, evaluate_independent_response

ROOT = Path(__file__).resolve().parents[1]


def grid(policy):
    with rf_input_file(ROOT, policy['bands_file']).open() as f:
        intervals = validated_band_segments(list(csv.DictReader(f)))
    return EvaluationGrid([v*1e6 for _, _, lo, hi in intervals for v in (lo, hi)],
        [s for s, _, _, _ in intervals for _ in range(2)],
        [j for j in range(28) for _ in range(2)])


class RFCoreTests(unittest.TestCase):
    def test_all_models_frozen_baseline_and_independent_mna(self):
        # Captured on main before D1. This is regression evidence, NOT an
        # independent oracle: the independent check below uses branch currents.
        baseline = json.loads((ROOT/'tests/fixtures/issue343_d1_rf_baseline.json').read_text())
        self.assertEqual(baseline['baseline_commit'], '3df84132cb8f21ec97411a143d56f9272810faf4')
        for cid in ('RF-F003', 'RF-T005', 'RF-T006', 'RF-T007', 'RF-T008'):
            with self.subTest(cid=cid):
                p, d, model, _, x = make(cid)
                x[10], x[13] = .03, -.04  # nonzero signed chip/PCB mutuals
                x[-6*model.schema.n_variable:] = np.linspace(.2, 2.8, 6*model.schema.n_variable)
                expected = baseline['cases'][cid]
                self.assertEqual(json.loads(json.dumps(asdict(d))), expected['definition'])
                np.testing.assert_array_equal(x, expected['vector'])
                for name, digest in expected['input_sha256'].items():
                    self.assertEqual(hashlib.sha256(rf_input_file(ROOT, name).read_bytes()).hexdigest(), digest)
                model = build_rf_model(d, p)
                g = grid(p)
                evaluator = model.evaluator(g)
                response = evaluator.evaluate(x)
                self.assertEqual(response.policy_fingerprint, expected['policy_fingerprint'])
                for name in ('frequency_hz', 'setting', 'segment'):
                    np.testing.assert_array_equal(getattr(g, name), expected['grid'][name])
                np.testing.assert_allclose(response.s.real, expected['s_real'], atol=1e-9, rtol=0)
                np.testing.assert_allclose(response.s.imag, expected['s_imag'], atol=1e-9, rtol=0)
                self.assertEqual(response.s.shape, (56, 2, 2))
                self.assertEqual(response.s.dtype, np.complex128)
                for key in ('il_db', 'apl_db', 'in_rl_db', 'out_rl_db'):
                    a = getattr(response, key)
                    self.assertEqual(a.shape, (56,))
                    self.assertEqual(a.dtype, np.float64)
                    self.assertTrue(np.all(np.isfinite(a)))
                    self.assertFalse(a.flags.writeable)
                    np.testing.assert_allclose(a, expected[key], atol=1e-9, rtol=0)
                self.assertFalse(response.independent_mna_checked)
                np.testing.assert_allclose(response.il_db, expected['legacy_abcd_il_db'], atol=1e-9, rtol=0)
                with patch.object(CoupledLCTopology, 'node_admittance', side_effect=AssertionError('forward reused')), \
                     patch.object(CoupledLCTopology, 'matrices', side_effect=AssertionError('forward reused')), \
                     patch('lpf.rf_core.model._cascade', side_effect=AssertionError('forward reused')):
                    report = validate_response(model, x, response)
                self.assertTrue(report['independent_mna_checked'])
                self.assertEqual(report['samples_checked'], 56)
                self.assertLess(report['max_abs_error'], 1e-9)
                self.assertFalse(report['rf_compliance_certified'])
                self.assertEqual(set(g.segment), set(range(28)))
                self.assertEqual(set(g.setting), set(range(6)))
                with self.assertRaises(ValueError):
                    g.frequency_hz.setflags(write=True)
                changed = x.copy(); changed[-1] += .01
                evaluator.evaluate(changed)
                np.testing.assert_array_equal(evaluator.evaluate(x).s, response.s)
                p['source_ohms']['real'] = 999
                self.assertNotEqual(model.resolved_policy['source_ohms']['real'], 999)

    def test_all_six_settings_on_each_separate_interval(self):
        for cid in ('RF-F003', 'RF-T005', 'RF-T006', 'RF-T007', 'RF-T008'):
            with self.subTest(cid=cid):
                p, d, model, _, x = make(cid)
                x[-12:] = np.linspace(.2, 2.8, 12)  # distinct values for all six rows
                x[10], x[13] = .03, -.04
                canonical = grid(p)
                g = EvaluationGrid(np.tile(canonical.frequency_hz, 6),
                    np.repeat(np.arange(6), 56), np.tile(canonical.segment, 6))
                r = model.evaluator(g).evaluate(x)
                self.assertEqual({(int(s), int(k)) for s, k in zip(g.segment, g.setting)},
                                 {(s, k) for s in range(28) for k in range(6)})
                self.assertEqual(validate_response(model, x, r)['samples_checked'], 336)

    def test_known_through_series_resistor_and_complex_power_references(self):
        # Analytic series R ABCD: [1,R;0,1]. Includes R=0 ideal through.
        zs, zl = 50.+0j, 60.-40j
        for r in (0., 20.):
            s50 = np.array([[[r/(100+r), 100/(100+r)],
                             [100/(100+r), r/(100+r)]]], complex)
            s, il, apl, irl, orl = power_response(s50, zs, zl)
            zin, zout = r+zl, r+zs
            expected11 = (zin-zs.conjugate())/(zin+zs)
            expected22 = (zout-zl.conjugate())/(zout+zl)
            gt = 4*zs.real*zl.real/abs(zs+r+zl)**2
            ga = zs.real/(zs.real+r)
            np.testing.assert_allclose(s[0, 0, 0], expected11, atol=1e-15)
            np.testing.assert_allclose(s[0, 1, 1], expected22, atol=1e-15)
            self.assertAlmostEqual(il[0], -10*np.log10(gt), places=12)
            self.assertAlmostEqual(apl[0], -10*np.log10(ga), places=12)
            self.assertGreater(abs(il[0]-apl[0]), .1)
            np.testing.assert_allclose(irl, -20*np.log10(abs(expected11)))
            np.testing.assert_allclose(orl, -20*np.log10(abs(expected22)))
            self.assertGreaterEqual(np.linalg.eigvalsh(np.eye(2)-s[0].conj().T@s[0])[0], -1e-14)
            if r == 0:
                np.testing.assert_allclose(s[0].conj().T@s[0], np.eye(2), atol=1e-14)

    def test_zeros_are_not_floored_and_invalid_numerics_fail(self):
        zero = np.zeros((1, 2, 2), complex)  # matched perfect absorber
        result = power_response(zero, 50, 50)
        self.assertTrue(all(np.isposinf(a[0]) for a in result[1:]))
        through = np.array([[[0, 1], [1, 0]]], complex)
        np.testing.assert_array_equal(_cascade(through, zero), zero)
        tiny = zero.copy(); tiny[:, 1, 0] = 1e-200
        self.assertEqual(power_response(tiny, 50, 50)[1][0], 4000.)
        # Entire forward path accepts a real transmission zero, not just
        # the public conversion helper (old ABCD path rejected Y21==0).
        p, d, _, _, x = make('RF-F003')
        model = build_rf_model(d, p)
        evaluator = model.evaluator(EvaluationGrid([1e9], [0], [0]))
        with patch.object(CoupledLCTopology, 'port_admittance',
                          return_value=np.array([np.eye(2)/50], complex)):
            self.assertTrue(np.isposinf(evaluator.evaluate(x).il_db[0]))
        with patch.object(CoupledLCTopology, 'port_admittance',
                          return_value=np.array([-np.eye(2)/50], complex)):
            with self.assertRaises(ValueError): evaluator.evaluate(x)
        for s in (np.full((1,2,2), np.nan), np.full((1,2,2), np.inf),
                  np.full((1,2,2), -np.inf), np.zeros((2,2))):
            with self.assertRaises(ValueError): power_response(s, 50, 60-40j)
        with self.assertRaises(ValueError): power_response(through, -50, 50)
        with self.assertRaises(ValueError): EvaluationGrid([1e9], [True], [0])

    def test_independent_zero_and_subnormal_power_transmission(self):
        # Synthetic passive external 2-port fixture, not a new RF policy or
        # S2P file. Real branch-current MNA still solves the connected LC core.
        from lpf.rf_core.port_parasitics import get_two_port_s
        p, d, _, _, x = make('RF-F003')
        model = build_rf_model(d, p)
        g = EvaluationGrid([1e9], [0], [0])
        for transmission in (0., 1e-200):
            def external(policy, role, f):
                if role == 'input_parasitic':
                    return np.array([[.2, transmission], [transmission, .3]], complex)
                return get_two_port_s(policy, role, f)
            with self.subTest(transmission=transmission), ExitStack() as stack:
                for module in ('lpf.rf_core.model', 'lpf.rf_core.independent',
                               'lpf.rf_core.independent_rf'):
                    stack.enter_context(patch(module+'.get_two_port_s', side_effect=external))
                response = model.evaluator(g).evaluate(x)
                for key in ('il_db', 'apl_db'):
                    value = getattr(response, key)[0]
                    self.assertTrue(np.isposinf(value) if transmission == 0 else np.isfinite(value))
                    if transmission != 0:
                        self.assertGreater(value, 3900.)
                # Forbid all forward reductions in the independent check.
                with patch.object(CoupledLCTopology, 'node_admittance', side_effect=AssertionError('forward reused')):
                    self.assertTrue(validate_response(model, x, response)['independent_mna_checked'])
                with self.assertRaisesRegex(ValueError, 'mismatch'):
                    validate_response(model, x, replace(response, il_db=np.array([0.])))
        # A disconnected OPEN output has undefined available power, not a
        # legitimate zero available gain. NaN and singular S also remain FAIL.
        for output in (np.diag([.3, 1.]), np.full((2, 2), np.nan), np.diag([.3, -1.])):
            def external(policy, role, f):
                return output if role == 'output_parasitic' else get_two_port_s(policy, role, f)
            with self.subTest(output=output), ExitStack() as stack:
                for module in ('lpf.rf_core.independent', 'lpf.rf_core.independent_rf'):
                    stack.enter_context(patch(module+'.get_two_port_s', side_effect=external))
                with self.assertRaises(ValueError):
                    evaluate_independent_response(model, x, 1e9, 0)

    def test_t006_endpoints_no_extrapolation_and_sha_gate(self):
        p, d, _, _, x = make('RF-T006')
        model = build_rf_model(d, p)
        g = EvaluationGrid([3e9, 6e9]*6, np.repeat(np.arange(6), 2), [28]*12)
        r = model.evaluator(g).evaluate(x)
        self.assertTrue(validate_response(model, x, r)['independent_mna_checked'])
        with self.assertRaises(ValueError):
            model.evaluator(EvaluationGrid([6e9+1], [0], [28]))
        original = rf_input_file(ROOT, p['external_port_parasitics']['input_parasitic']['path'])
        with tempfile.TemporaryDirectory() as tmp:
            tampered = Path(tmp)/'tampered.s2p'
            tampered.write_bytes(original.read_bytes()+b'! tampered\n')
            with patch('lpf.rf_core.port_parasitics._file_under_repo', return_value=tampered):
                with self.assertRaisesRegex(ValueError, 'SHA256 mismatch'):
                    model.evaluator(g)
                with self.assertRaisesRegex(ValueError, 'SHA256 mismatch'):
                    validate_response(model, x, r)

    def test_reject_unapproved_models_roles_and_mismatches(self):
        p, d, _, _, x = make('RF-T007')
        for cid in ('RF-F001', 'RF-T001', 'RF-T005'):
            with self.assertRaises(ValueError): load_constraint(cid)
        for key, value in [('schema_version', 1), ('unknown_physics', {}), ('active_constraint_id', 'RF-T999')]:
            bad = copy.deepcopy(p); bad[key] = value
            with self.assertRaises(ValueError): build_rf_model(d, bad)
        with self.assertRaises(ValueError):
            build_rf_model(replace(d, variable_roles=('series', 'bridge')), p)
        model = build_rf_model(d, p)
        g = EvaluationGrid([1e9], [0], [0])
        r = model.evaluator(g).evaluate(x)
        for bad in ([True]*len(x), [str(v) for v in x], np.asarray(x, complex), x[:-1]):
            with self.assertRaises(ValueError): model.evaluator(g).evaluate(bad)
        with self.assertRaisesRegex(ValueError, 'shape'):
            validate_response(model, x, replace(r, il_db=r.il_db[:, None]))
        with self.assertRaisesRegex(ValueError, 'tolerance'):
            validate_response(model, x, r, atol=float('nan'))
        with self.assertRaisesRegex(ValueError, 'mismatch'):
            validate_response(model, x, replace(r, il_db=r.il_db+1))
        with self.assertRaisesRegex(ValueError, 'Non-passive'):
            with patch('lpf.rf_core.independent.evaluate_independent_sample', return_value={
                'il_db': 0., 'inductor_loss_w': -1., 'capacitor_loss_w': 0.,
                'input_s2p_loss_w': 0., 'output_s2p_loss_w': 0., 'power_residual_w': 0.}):
                validate_response(model, x, r)
        bad = x.copy(); bad[10] = 2
        with self.assertRaises(ValueError): model.evaluator(g).evaluate(bad)
        with self.assertRaises(ValueError): validate_response(model, bad, r)


if __name__ == '__main__':
    unittest.main()

"""Bounded Issue #410 diagnostic equivalence; no scientific search or EXP."""
import importlib.util
import json
from dataclasses import replace
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

import numpy as np
from test_issue307_constraints import make
from lpf.rf_core import build_rf_model
from lpf.rf_core.coupled_lc import CoupledLCTopology
from lpf.rf_core.independent import validate_response
from lpf.rf_core.numerical_diagnostics import CircuitNumericalError
from lpf.search.plan import load_preflight
from lpf.search.proposals import definition_from_data
from lpf.search.performance import (compile_requirements, prepare_requirements,
                                    evaluate_requirements, build_evaluation_grid)
from lpf.constraint_versions import load_constraint, rf_input_file

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('issue410_probe', ROOT/'project/diagnostics/issue410_probe.py')
probe = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = probe
spec.loader.exec_module(probe)


def fixture():
    plan = load_preflight(ROOT/'project/diagnostics/issue377/baseline.yaml')
    p = load_constraint('RF-T008', allow_trial=True)
    d = definition_from_data(json.loads((ROOT/plan.data['config']['definition']['path']).read_text()))
    model = build_rf_model(d, p)
    # Use the public starts loader, preserving its vector/SHA checks.
    from lpf.search.starts import load_explicit
    x = np.asarray(load_explicit(ROOT/'project/diagnostics/issue401_starts_1002.json')[1002]['vector'])
    return p, model, plan.requested_grid('hybrid/coarse'), x


class CAssemblyTests(unittest.TestCase):
    def compare(self, model, g, vectors, *, independent=False):
        req = prepare_requirements(compile_requirements(model.resolved_policy,
            rf_input_file(ROOT, model.resolved_policy['bands_file']), 'full_lpf'), g)
        baseline = model.evaluator(g)
        candidates = {v: probe.probe_model(model, v) for v in ('six', 'split')}
        evaluators = {v: m.evaluator(g) for v, m in candidates.items()}
        for x in vectors:
            old = baseline.evaluate(x)
            old_g = evaluate_requirements(old, req)
            for variant in ('six', 'split'):
                with self.subTest(variant=variant):
                    new_model = candidates[variant]
                    new = evaluators[variant].evaluate(x)
                    self.assertIs(new.grid, g)
                    for key in ('s', 'il_db', 'apl_db', 'in_rl_db', 'out_rl_db'):
                        a, b = getattr(old, key), getattr(new, key)
                        if key != 's':
                            np.testing.assert_array_equal(np.isposinf(a), np.isposinf(b))
                        np.testing.assert_allclose(a, b, atol=1e-9, rtol=1e-11)
                        self.assertFalse(b.flags.writeable)
                        with self.assertRaises(ValueError): b.setflags(write=True)
                    new_g = evaluate_requirements(new, req)
                    np.testing.assert_allclose(old_g['mandatory_g'], new_g['mandatory_g'], atol=1e-9, rtol=1e-11)
                    self.assertAlmostEqual(old_g['worst_il_db'], new_g['worst_il_db'], places=9)
                    if independent:
                        # Independent branch-current solver must not call the probe.
                        with patch.object(probe.ProbeTopology, 'node_admittance', side_effect=AssertionError('forward reused')):
                            report = validate_response(new_model, x, new)
                        self.assertTrue(report['independent_mna_checked'])
                        self.assertEqual(report['samples_checked'], len(g.setting))

    def test_fixed_start_and_distinct_six_rows(self):
        p, model, g, x = fixture()
        self.assertEqual((len(x), len(g.setting), len(set(g.segment)), len(set(g.setting))), (25, 70, 28, 6))
        changed = x.copy()
        changed[:model.schema.n_inductors + model.schema.n_fixed] *= 1.01
        ic0 = model.schema.n_inductors + model.schema.n_fixed + model.schema.n_coupling
        changed[ic0:ic0 + model.schema.n_ic_fixed] *= 1.01  # no stale fixed/L cache
        changed[-12:] = np.linspace(0, 3, 12)
        self.compare(model, g, [x, changed], independent=True)

    def test_recorded_100_candidate_replay(self):
        _, model, g, _ = fixture()
        record = json.loads((ROOT/'project/diagnostics/issue410_equivalence.json').read_text())
        from lpf.search.storage import vector_sha
        self.assertEqual(len(record['vectors']), 100)
        self.assertEqual([vector_sha(x) for x in record['vectors']], record['vector_sha256'])
        self.compare(model, g, record['vectors'])

    def test_current_models_and_no_variable_branches(self):
        for cid in ('RF-F003', 'RF-T005', 'RF-T006', 'RF-T007', 'RF-T008'):
            p, d, model, _, x = make(cid)
            g = build_evaluation_grid(compile_requirements(p, rf_input_file(ROOT, p['bands_file'])), 2)
            self.compare(model, g, [x])
        p, d, _, _, _ = make('RF-T008')
        placement = replace(d.capacitor_placement, variable_edges=(), ic_fixed_edges=())
        model = build_rf_model(replace(d, capacitor_placement=placement, variable_roles=()), p)
        x = [3.]*7 + [.1, .1, .1] + [0.]*4
        g = build_evaluation_grid(compile_requirements(p, rf_input_file(ROOT, p['bands_file'])), 2)
        self.compare(model, g, [x], independent=True)

    def test_bad_sampling_spd_and_external_values_keep_stop(self):
        _, model, g, x = fixture()
        values = model.decode(x)
        for variant in ('baseline', 'six', 'split'):
            m = probe.probe_model(model, variant)
            t = m.topology
            for omega, setting in (([0.], [0]), ([np.nan], [0]), ([1e9], [6]), ([1e9], [True])):
                with self.assertRaises(ValueError): t.node_admittance(values, omega, setting)
            for k in (2., 1. - 1e-13):  # non-SPD and SPD-but-below-conditioning-threshold
                bad = x.copy()
                bad[model.schema.n_inductors + model.schema.n_fixed] = k
                # Isolate one coupled pair to make the threshold case explicit.
                first = model.schema.n_inductors + model.schema.n_fixed
                bad[first:first + model.schema.n_coupling] = 0.
                bad[first] = k
                with self.assertRaises(CircuitNumericalError) as caught: m.evaluator(g).evaluate(bad)
                self.assertEqual(caught.exception.code, 'mutual_not_spd')
            huge = replace(values, capacitors_pf_by_setting=tuple(
                tuple(1e308 for _ in row) for row in values.capacitors_pf_by_setting))
            with np.errstate(over='ignore', invalid='ignore'):
                with self.assertRaises(CircuitNumericalError) as caught:
                    t.node_admittance(huge, [1e15], [0])
            self.assertEqual(caught.exception.code, 'node_nonfinite')
            self.assertEqual(caught.exception.sample_index, 0)
            rows = list(values.capacitors_pf_by_setting)
            rows[1] = (rows[1][0] + .1,) + rows[1][1:]
            with self.assertRaisesRegex(ValueError, 'differ by setting'):
                m.evaluator(g).evaluate(replace(values, capacitors_pf_by_setting=tuple(rows)))
            for invalid in (np.full_like(x, np.nan), x[:-1]):
                with self.assertRaises(ValueError): m.evaluator(g).evaluate(invalid)

    def test_numerical_stop_and_zero_transmission_unchanged(self):
        # Same existing zero/singular Y boundary, all full response metrics kept.
        _, model, g, x = fixture()
        for variant in ('baseline', 'six', 'split'):
            m = probe.probe_model(model, variant)
            evaluator = m.evaluator(g)
            for sign in (1., -1.):
                y = np.broadcast_to(sign*np.eye(2)/50, (len(g.setting), 2, 2)).copy().astype(complex)
                with patch.object(CoupledLCTopology, 'port_admittance', return_value=y):
                    if sign > 0:
                        r = evaluator.evaluate(x)
                        self.assertTrue(np.all(np.isposinf(r.il_db)))
                        self.assertTrue(np.all(np.isposinf(r.apl_db)))
                    else:
                        with self.assertRaises(CircuitNumericalError) as caught: evaluator.evaluate(x)
                        self.assertEqual(caught.exception.code, 's_singular')


if __name__ == '__main__':
    unittest.main()

"""Current replacements for legacy candidate science; no old ranking/solver API."""
from dataclasses import replace
from unittest.mock import patch
import unittest

import numpy as np

from test_issue323_dependencies import make
from lpf.constraint_versions import load_constraint
from lpf.rf_core import build_rf_model, EvaluationGrid
from lpf.rf_core.independent import validate_response
from lpf.rf_core.independent_rf import evaluate_independent_sample
from lpf.search.component_constraints import physical_bounds, validate_values
from lpf.topology_management import CircuitDefinition, CapacitorPlacement, InductorTree
from lpf.topology_management.enumeration import capacitor_choices, labelled_trees


class CurrentCandidateScienceTests(unittest.TestCase):
    def test_three_and_four_inductor_components_and_trial_stamps(self):
        for cid in ('RF-F003', 'RF-T005', 'RF-T006', 'RF-T007', 'RF-T008'):
            p = load_constraint(cid, allow_trial=cid.startswith('RF-T'))
            for n in (3, 4):
                with self.subTest(cid=cid, n=n):
                    var = ((n, -1), (0, 2))
                    d = CircuitDefinition(
                        InductorTree(n+1, tuple((0, i) for i in range(1, n+1))),
                        ('LQP02HV',)*n, tuple(range(n)), ((0, 1),),
                        CapacitorPlacement(n+1, ((0, 1), (1, -1)), var,
                                           var if cid == 'RF-T008' else ()),
                        ('GJM01', 'PCB_PATTERN_C'), ('shunt_to_ground', 'bridge'))
                    model = build_rf_model(d, p)
                    x = np.mean(physical_bounds(d, model.schema, p), axis=1)
                    report = validate_values(d, model.schema, x, p)
                    self.assertTrue(report['component_policy_pass'])
                    self.assertGreater(report['min_L_eigenvalue_H'], 0)
                    self.assertFalse(report['rf_performance_checked'])
                    self.assertEqual(len(model.decode(x).capacitors_pf_by_setting), 6)
                    self.assertEqual(model.schema.constant_caps_pf, (.5,) if cid == 'RF-T007' else ())
                    self.assertEqual(model.schema.n_ic_fixed, 2 if cid == 'RF-T008' else 0)
                    self.assertEqual(model.topology.capacitor_q[-1],
                                     40 if cid == 'RF-T007' else 60 if cid == 'RF-T008' else 35)
                    with self.assertRaises(ValueError):
                        build_rf_model(replace(d, variable_roles=('bridge', 'bridge')), p)
                    bad = x.copy()
                    bad[n+2] = .9
                    with self.assertRaises(ValueError):
                        validate_values(d, model.schema, bad, p)

    def test_independent_recompute_rejects_bad_power_and_nonfinite_samples(self):
        _, _, model, _, x = make('RF-T008')
        response = model.evaluator(EvaluationGrid([810e6], [0], [0])).evaluate(x)
        self.assertFalse(response.independent_mna_checked)
        for key, value, reason in (
            ('input_s2p_loss_w', -1., 'Non-passive'),
            ('power_residual_w', 1e-6, 'Power balance'),
            ('power_residual_w', float('nan'), 'Power balance'),
            ('il_db', float('nan'), 'Invalid independent'),
        ):
            def corrupt(*args, **kwargs):
                sample = evaluate_independent_sample(*args, **kwargs)
                sample[key] = value
                return sample
            with self.subTest(key=key, value=value), patch(
                    'lpf.rf_core.independent.evaluate_independent_sample', side_effect=corrupt):
                with self.assertRaisesRegex(ValueError, reason):
                    validate_response(model, x, response)
        checked = validate_response(model, x, response)
        self.assertTrue(checked['independent_mna_checked'])
        self.assertFalse(checked['rf_compliance_certified'])
        self.assertFalse(checked['continuous_band_proven'])
        # Independent validation recomputes from the supplied vector, not a
        # prior PASS flag. A different full vector cannot authenticate response.
        changed = x.copy(); changed[-12] += .1
        with self.assertRaisesRegex(ValueError, 'mismatch'):
            validate_response(model, changed, response)
        with self.assertRaisesRegex(ValueError, 'Policy identity'):
            validate_response(model, x, replace(response, policy_fingerprint='0'*64))

    def test_retained_pure_structure_helpers(self):
        for n, count in ((3, 16), (4, 125)):
            trees = labelled_trees(n, limit=1000)
            self.assertEqual(len(trees), count)
            self.assertEqual(trees[:2], labelled_trees(n, limit=2))
            self.assertTrue(all(len(t.edges) == n for t in trees))
        for kind in ('fixed', 'variable'):
            small = capacitor_choices(4, kind=kind, max_branches=2, limit=5)
            large = capacitor_choices(4, kind=kind, max_branches=2, limit=1000)
            self.assertEqual(small, large[:5])
            self.assertEqual(small[0], ())
            self.assertTrue(any(len(layout) == 2 for layout in large))
        choices = capacitor_choices(4, kind='variable', max_branches=1, limit=100)
        self.assertEqual({label for layout in choices for _, label in layout},
                         {'shunt_to_ground', 'bridge', 'series'})
        for edges in (((0, 1), (1, 0), (1, 2)), ((0, 1), (1, 2), (2, 0))):
            with self.assertRaises(ValueError):
                InductorTree(4, edges)

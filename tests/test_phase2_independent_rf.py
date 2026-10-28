"""Limited fixed-vector parity and power evidence; not a dense RF run."""
import json
import importlib.util
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from test_phase2_public_circuit_api import (definition, RUNS, SNAP, exp042,
                                            exp055, exp058_area4l_gjm)
from lpf.constraint_versions import load_constraint
from lpf.phase2_models.api import CircuitDefinition, build_nominal_circuit
from lpf.phase2_models.circuit_layout import CapacitorPlacement, InductorTree
from lpf.phase2_models.independent_scan import scan_independent_rf
from lpf.phase2_models.coupled_lc import CoupledLCTopology
from lpf.phase2_models.independent_rf import evaluate_independent_sample


class IndependentRFTests(unittest.TestCase):
    def test_candidate_audit_never_promotes_on_component_pass(self):
        from lpf.phase2_models.candidate_audit import audit_candidate
        _, x = exp042.policy_and_seed()
        config = definition(exp042.C_EDGES[:4], exp042.C_EDGES[4:],
                            ('GJM01','GJM01','GJM01','PCB_PATTERN_C'),
                            ('shunt_to_ground','shunt_to_ground','bridge'))
        circuit = build_nominal_circuit(load_constraint('RF-T005', allow_trial=True), config)
        report = audit_candidate(circuit, x)
        self.assertTrue(report['component_policy_pass'])
        self.assertEqual(report['constraint_fingerprint'], circuit.policy_fingerprint)
        self.assertTrue(report['connection_role_evidence_complete'])
        self.assertFalse(report['independent_mna_checked'])
        self.assertFalse(report['rf_dense_evaluation_completed'])
        self.assertIsNone(report['optimization_converged'])
        self.assertFalse(report['rf_compliance_certified'])
        self.assertTrue(report['candidate_promotion_blocked'])
        self.assertIn('independent_mna_not_checked', report['promotion_blockers'])
        self.assertIn('dense_rf_not_checked', report['promotion_blockers'])
        with self.assertRaises(TypeError):
            audit_candidate(circuit, x, independent_mna_checked=True)

    def test_candidate_audit_preserves_role_and_adapter_blockers(self):
        from lpf.phase2_models.candidate_audit import audit_candidate
        circuit = SimpleNamespace(policy_id='RF-T005', policy_fingerprint='test',
            validate_components=lambda x: {'component_policy_pass': False,
                                           'promotion_blockers': ('custom_blocker',)},
            connection_role_audit=lambda: {'all_declared_roles_supported_by_l_tree': False})
        report = audit_candidate(circuit, None)
        self.assertIn('component_policy_failed', report['promotion_blockers'])
        self.assertIn('declared_role_not_proven_by_l_tree', report['promotion_blockers'])
        self.assertIn('custom_blocker', report['promotion_blockers'])
        self.assertFalse(report['eligible_for_owner_review'])
        with patch.object(circuit, 'validate_components', side_effect=ValueError('invalid')):
            with self.assertRaisesRegex(ValueError, 'invalid'):
                audit_candidate(circuit, None)

    def test_candidate_audit_recomputes_bound_limited_evidence(self):
        from lpf.phase2_models.candidate_audit import audit_candidate
        _, x = exp042.policy_and_seed()
        config = definition(exp042.C_EDGES[:4], exp042.C_EDGES[4:],
                            ('GJM01','GJM01','GJM01','PCB_PATTERN_C'),
                            ('shunt_to_ground','shunt_to_ground','bridge'))
        circuit = build_nominal_circuit(load_constraint('RF-T005', allow_trial=True), config)
        report = audit_candidate(circuit, x, limited_points_per_interval=2)
        self.assertEqual(report['independent_mna_state'], 'passed_limited')
        self.assertEqual(report['power_accounting_state'], 'passed_limited')
        evidence = report['limited_evidence']
        self.assertEqual(len(evidence['grid']), 56)
        self.assertEqual(len(evidence['segments']), 28)
        self.assertEqual(evidence['coverage'], 'canonical')
        self.assertEqual(evidence['identity']['constraint_fingerprint'], circuit.policy_fingerprint)
        self.assertEqual(len(evidence['identity']['git_head']), 40)
        self.assertEqual(len(evidence['identity']['input_sha256']), 3)
        self.assertLess(evidence['max_abs_power_residual_w'], 1e-12)
        self.assertLess(evidence['max_forward_il_error_db'], 1e-9)
        self.assertIn('UL', evidence['threshold_observations'])
        self.assertFalse(report['rf_dense_evaluation_completed'])
        self.assertEqual(report['dense_rf_state'], 'not_checked')
        self.assertFalse(report['rf_compliance_certified'])
        self.assertTrue(report['candidate_promotion_blocked'])
        self.assertFalse(report['eligible_for_owner_review'])
        changed = list(x)
        changed[-1] += 0.001
        second = audit_candidate(circuit, changed, limited_points_per_interval=2)
        self.assertEqual(second['independent_mna_state'], 'passed_limited')
        self.assertNotEqual(evidence['identity']['vector_fingerprint'],
                            second['limited_evidence']['identity']['vector_fingerprint'])
        self.assertEqual(audit_candidate(circuit, x, limited_points_per_interval=4)
                         ['independent_mna_state'], 'failed')

    def test_prior_evidence_requires_recomputation_and_exact_match(self):
        from copy import deepcopy
        from lpf.phase2_models.candidate_audit import audit_candidate
        from lpf.phase2_models.limited_candidate_evidence import compare_recomputed_evidence, EvidenceFailure
        _, x = exp042.policy_and_seed()
        config = definition(exp042.C_EDGES[:4], exp042.C_EDGES[4:],
                            ('GJM01','GJM01','GJM01','PCB_PATTERN_C'),
                            ('shunt_to_ground','shunt_to_ground','bridge'))
        circuit = build_nominal_circuit(load_constraint('RF-T005', allow_trial=True), config)
        prior = audit_candidate(circuit, x, limited_points_per_interval=2)['limited_evidence']
        rerun = audit_candidate(circuit, x, limited_points_per_interval=2, prior_evidence=prior)
        self.assertEqual(rerun['independent_mna_state'], 'passed_limited')
        self.assertEqual(audit_candidate(circuit, x, prior_evidence=prior)['independent_mna_state'], 'failed')
        mutations = [
            (('identity', 'constraint_fingerprint'), 'bad', 'policy_mismatch'),
            (('identity', 'vector_fingerprint'), 'bad', 'vector_mismatch'),
            (('identity', 'definition_fingerprint'), 'bad', 'circuit_definition_mismatch'),
            (('identity', 'git_head'), 'bad', 'source_mismatch'),
            (('identity', 'input_sha256'), {}, 'input_mismatch'),
            (('coverage',), 'cross', 'grid_or_coverage_mismatch'),
            (('points_per_interval',), 1001, 'grid_or_coverage_mismatch'),
            (('grid',), prior['grid'][:-1], 'grid_or_coverage_mismatch'),
            (('max_abs_power_residual_w',), 0.0, 'observation_mismatch'),
        ]
        for path, value, reason in mutations:
            bad = deepcopy(prior)
            obj = bad
            for key in path[:-1]:
                obj = obj[key]
            obj[path[-1]] = value
            with self.subTest(reason=reason), self.assertRaisesRegex(EvidenceFailure, reason):
                compare_recomputed_evidence(bad, prior)
        for key, value in (('subband', 'wrong'), ('case', 'B8'), ('setting', 5)):
            bad = deepcopy(prior)
            bad['segments'][0][key] = value
            with self.subTest(key=key), self.assertRaisesRegex(EvidenceFailure, 'grid_or_coverage_mismatch'):
                compare_recomputed_evidence(bad, prior)
        report = audit_candidate(circuit, x, limited_points_per_interval=2, prior_evidence=bad)
        self.assertEqual(report['limited_evidence_failure_reason'], 'grid_or_coverage_mismatch')
        self.assertIsNone(report['limited_evidence'])
        self.assertTrue(report['candidate_promotion_blocked'])

    def test_candidate_evidence_rejects_definition_and_policy_mismatch(self):
        from dataclasses import replace
        from lpf.phase2_models.limited_candidate_evidence import _identity, EvidenceFailure
        _, x = exp042.policy_and_seed()
        config = definition(exp042.C_EDGES[:4], exp042.C_EDGES[4:],
                            ('GJM01','GJM01','GJM01','PCB_PATTERN_C'),
                            ('shunt_to_ground','shunt_to_ground','bridge'))
        circuit = build_nominal_circuit(load_constraint('RF-T005', allow_trial=True), config)
        forged = replace(circuit, definition=replace(config, physical_order=tuple(reversed(config.physical_order))))
        with self.assertRaisesRegex(EvidenceFailure, 'circuit_definition_mismatch'):
            _identity(forged, x)
        forged = replace(circuit, _adapter=replace(circuit._adapter, policy_fingerprint='0' * 64))
        with self.assertRaisesRegex(EvidenceFailure, 'policy_mismatch'):
            _identity(forged, x)

    def test_candidate_audit_rejects_bad_power_samples(self):
        from lpf.phase2_models.candidate_audit import audit_candidate
        _, x = exp042.policy_and_seed()
        config = definition(exp042.C_EDGES[:4], exp042.C_EDGES[4:],
                            ('GJM01','GJM01','GJM01','PCB_PATTERN_C'),
                            ('shunt_to_ground','shunt_to_ground','bridge'))
        circuit = build_nominal_circuit(load_constraint('RF-T005', allow_trial=True), config)
        for key, value, reason in (('input_s2p_loss_w', -1.0, 'non_passive_power'),
                                   ('power_residual_w', 1e-6, 'power_balance_failed'),
                                   ('gain', float('nan'), 'sample_nonfinite')):
            def corrupt(*args, **kwargs):
                result = evaluate_independent_sample(*args, **kwargs)
                result[key] = value
                return result
            with self.subTest(reason=reason), patch(
                    'lpf.phase2_models.independent_scan.evaluate_independent_sample', side_effect=corrupt):
                report = audit_candidate(circuit, x, limited_points_per_interval=2)
            self.assertEqual(report['independent_mna_state'], 'failed')
            self.assertEqual(report['limited_evidence_failure_reason'], reason)
            self.assertIsNone(report['limited_evidence'])
            self.assertTrue(report['candidate_promotion_blocked'])

    def test_scan_coverage_and_refinement(self):
        policy = load_constraint('RF-T005', allow_trial=True)
        circuit = SimpleNamespace(_adapter=SimpleNamespace(policy=policy), policy_id='RF-T005',
                                  policy_fingerprint='synthetic',
                                  validate_components=lambda x: {'component_policy_pass': True})
        # Smooth synthetic maximum in the first UL segment, resolved by the
        # midpoint but underestimated by the endpoints and by the midpoint itself.
        from lpf.phase2_models._grid import ROOT
        import csv
        with (ROOT / 'data/bands.csv').open(newline='', encoding='utf-8') as f:
            rows = list(csv.DictReader(f))
        low, high = float(rows[0]['low_mhz'])*1e6, float(rows[0]['high_mhz'])*1e6
        peak = low + .4*(high-low)
        def fake(c, v, f, setting):
            return {'il_db': (32.0 + 3.0 * (1.0 - ((f-peak)/(high-low))**2)
                              if low <= f <= high else 32.5)}
        with patch('lpf.phase2_models.independent_scan.evaluate_independent_sample', side_effect=fake):
            report = scan_independent_rf(circuit, None, points_per_interval=3, coverage='cross', refine=True)
            canonical = scan_independent_rf(circuit, None, points_per_interval=2)
        self.assertEqual(len(report['segments']), 168)
        self.assertEqual(len(canonical['segments']), 28)
        self.assertEqual(report['coverage'], 'cross')
        self.assertEqual(canonical['coverage'], 'canonical')
        self.assertEqual(report['summary']['grid_worst']['pass_il']['setting'], 0)
        self.assertEqual(report['summary']['grid_worst']['pass_il']['segment'], 0)
        self.assertEqual(report['summary']['refined_worst']['H2']['region'], 'H2')
        self.assertEqual(report['summary']['refined_worst']['H3']['region'], 'H3')
        for summary in canonical['summary'].values():
            for item in summary.values():
                self.assertEqual(item['setting'], item['canonical_setting'])
        self.assertTrue(report['component_policy_pass'])
        self.assertFalse(report['forward_sampled_checked'])
        self.assertEqual({r['subband'] for r in report['segments'] if r['case'] == 'B13+B14'}, {'B13', 'B14'})
        self.assertEqual({(r['segment'], r['setting']) for r in report['segments']},
                         {(s, k) for s in range(28) for k in range(6)})
        first = report['segments'][0]
        self.assertGreater(first['refined_worst']['il_db'], first['grid_worst']['il_db'])
        self.assertAlmostEqual(first['refined_worst']['frequency_hz'], peak, delta=2)
        self.assertGreater(first['additional_evaluations'], 0)
        stop = next(r for r in report['segments'] if r['region'] == 'H2' and 30 <= r['refined_worst']['il_db'] < 35)
        self.assertTrue(stop['mandatory_stop_pass'])
        self.assertFalse(stop['nominal_goal_pass'])
        self.assertFalse(report['rf_compliance_certified'])
        self.assertTrue(report['candidate_promotion_blocked'])

    def test_scan_threshold_boundaries_are_observations_not_certification(self):
        policy = load_constraint('RF-T005', allow_trial=True)
        circuit = SimpleNamespace(_adapter=SimpleNamespace(policy=policy), policy_id='RF-T005',
                                  policy_fingerprint='synthetic',
                                  validate_components=lambda x: {'component_policy_pass': True})
        for value in (0.3, 30.0, 35.0):
            with self.subTest(value=value), patch(
                    'lpf.phase2_models.independent_scan.evaluate_independent_sample',
                    return_value={'il_db': value}):
                report = scan_independent_rf(circuit, None, points_per_interval=2)
            obs = report['threshold_observations']
            self.assertEqual(obs['UL']['status'],
                             'sampled_numeric_observation' if value <= 0.3 else 'failed')
            self.assertEqual(obs['DL']['status'], obs['UL']['status'])
            for region in ('H2', 'H3'):
                self.assertEqual(obs[region]['mandatory']['status'],
                                 'sampled_numeric_observation' if value >= 30 else 'failed')
                self.assertEqual(obs[region]['nominal']['status'],
                                 'sampled_numeric_observation' if value >= 35 else 'failed')
            self.assertEqual(report['threshold_policy_scope'], 'full_lpf')
            self.assertEqual(report['threshold_evidence_scope'], 'finite_grid')
            self.assertFalse(report['rf_compliance_certified'])
            self.assertFalse(report['rf_dense_evaluation_completed'])
            self.assertTrue(report['candidate_promotion_blocked'])

    def test_scan_failure_and_stop_refinement(self):
        policy = load_constraint('RF-T005', allow_trial=True)
        circuit = SimpleNamespace(_adapter=SimpleNamespace(policy=policy), policy_id='RF-T005',
                                  policy_fingerprint='synthetic',
                                  validate_components=lambda x: {'component_policy_pass': False})
        for kwargs in ({'points_per_interval': 1}, {'points_per_interval': 2, 'refine': True},
                       {'points_per_interval': 3, 'coverage': 'bad'}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                scan_independent_rf(circuit, None, **kwargs)
        with patch('lpf.phase2_models.independent_scan.evaluate_independent_sample', return_value={'il_db': float('nan')}):
            with self.assertRaisesRegex(ValueError, 'Non-finite'):
                scan_independent_rf(circuit, None, points_per_interval=3)
        for reason in ('non-SPD', 'non-passive'):
            with patch('lpf.phase2_models.independent_scan.evaluate_independent_sample', side_effect=ValueError(reason)):
                with self.assertRaisesRegex(ValueError, reason):
                    scan_independent_rf(circuit, None, points_per_interval=3)
        from lpf.phase2_models._grid import ROOT
        import csv
        with (ROOT / 'data/bands.csv').open(newline='', encoding='utf-8') as f:
            row = next(r for r in csv.DictReader(f) if r['region'] == 'H2')
        low, high = float(row['low_mhz'])*1e6, float(row['high_mhz'])*1e6
        center = low + .4*(high-low)
        def fake(c, v, f, s):
            return {'il_db': 31 + ((f-center)/(high-low))**2 if low <= f <= high else 32}
        with patch('lpf.phase2_models.independent_scan.evaluate_independent_sample', side_effect=fake):
            report = scan_independent_rf(circuit, None, points_per_interval=3, refine=True)
            h2 = next(r for r in report['segments'] if r['case'] == row['case'] and r['region'] == 'H2' and r['subband'] == row['note'])
            self.assertLess(h2['refined_worst']['il_db'], h2['grid_worst']['il_db'])
            self.assertAlmostEqual(h2['refined_worst']['frequency_hz'], center, delta=2)
            self.assertFalse(report['component_policy_pass'])
            for result in (SimpleNamespace(success=False, fun=0), SimpleNamespace(success=True, fun=float('nan'))):
                with patch('lpf.phase2_models.independent_scan.minimize_scalar', return_value=result):
                    with self.assertRaisesRegex(ValueError, 'refinement failed'):
                        scan_independent_rf(circuit, None, points_per_interval=3, refine=True)

    def test_small_real_cross_scan(self):
        _, x = exp042.policy_and_seed()
        config = definition(exp042.C_EDGES[:4], exp042.C_EDGES[4:],
                            ('GJM01','GJM01','GJM01','PCB_PATTERN_C'),
                            ('shunt_to_ground','shunt_to_ground','bridge'))
        circuit = build_nominal_circuit(load_constraint('RF-T005', allow_trial=True), config)
        report = scan_independent_rf(circuit, x, points_per_interval=2, coverage='cross')
        self.assertEqual(len(report['segments']), 168)
        self.assertFalse(report['continuous_band_proven'])
        self.assertFalse(report['rf_dense_evaluation_completed'])
        for row in report['segments']:
            self.assertIn(row['grid_worst']['frequency_hz'], (row['low_hz'], row['high_hz']))

    def test_frozen_external_parity_and_power(self):
        _, x42 = exp042.policy_and_seed()
        x55 = json.loads((RUNS / 'EXP-055/checkpoints/cv1_input_tip_best.json').read_text())['vector']
        x58 = json.loads((SNAP / 'rf_t008_exp058_area4p667_20261020.json').read_text())['best']['vector']
        caps = exp055.capacitor_edges('cv1_input_tip')
        cases = [
            ('RF-T005', definition(exp042.C_EDGES[:4], exp042.C_EDGES[4:],
             ('GJM01','GJM01','GJM01','PCB_PATTERN_C'), ('shunt_to_ground','shunt_to_ground','bridge')), x42),
            ('RF-T007', definition(caps[:4], caps[4:7],
             ('GJM01','GJM01','PCB_PATTERN_C','PCB_PATTERN_C'), ('shunt_to_ground','bridge','bridge')), x55),
            ('RF-T008', definition(exp058_area4l_gjm.ALL_FIXED, exp058_area4l_gjm.DTC['input_output'],
             ('GJM01','PCB_PATTERN_C','PCB_PATTERN_C','PCB_PATTERN_C'), ('bridge','bridge'), paired=True), x58),
        ]
        archive = RUNS / 'EXP-043'
        spec = importlib.util.spec_from_file_location('frozen_043_b2', archive / 'search_3l.py')
        source = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(source)
        for name in ('zero_gjm_double', 'two_gjm_bridge'):
            row = json.loads((archive / 'checkpoints' / (name + '.json')).read_text())
            self.assertEqual(row['experiment'], 'EXP-043')
            self.assertEqual(row['variant'], name)
            types, edges = source.CONFIGS[name]
            config = CircuitDefinition(
                inductor_tree=InductorTree(4, source.L_EDGES),
                inductor_types=('LQP02HV',)*3, physical_order=(0,2,1),
                coupling_pairs=((0,2),(2,1)),
                capacitor_placement=CapacitorPlacement(4, source.CF_EDGES, edges),
                fixed_c_types=tuple('GJM01' if t == 'GJM' else 'PCB_PATTERN_C' for t in types),
                variable_roles=tuple('shunt_to_ground' if -1 in e else 'bridge' for e in edges))
            cases.append(('RF-T005', config, row['vector']))
        maxima = {'il': (-1, None), 'power': (-1, None)}
        labels = ['EXP-042/preliminary_js_5pt', 'EXP-055/cv1_input_tip_best',
                  'EXP-058/area4p667', 'EXP-043/zero_gjm_double', 'EXP-043/two_gjm_bridge']
        for label, (trial, config, x) in zip(labels, cases):
            c = build_nominal_circuit(load_constraint(trial, allow_trial=True), config)
            component = c.validate_components(x)
            self.assertTrue(component['component_policy_pass'], label)
            self.assertEqual(component['constraint_id'], trial)
            self.assertEqual(component['constraint_fingerprint'], c.policy_fingerprint)
            self.assertEqual(len(c.decode(x).capacitors_pf_by_setting), 6)
            forward = c.forward_evaluator(3)
            reference = forward.il(x)
            self.assertEqual(len(reference), 84)
            for i, expected in enumerate(reference):
                frequency_mhz, setting = float(forward.f[i]), int(forward.setting[i])
                with self.subTest(trial=trial, frequency_mhz=frequency_mhz,
                                  setting=setting, segment=int(forward.segment[i])):
                    with patch.object(CoupledLCTopology, 'node_admittance', side_effect=AssertionError('forward called')), \
                         patch.object(CoupledLCTopology, 'matrices', side_effect=AssertionError('forward called')):
                        result = evaluate_independent_sample(c, x, frequency_mhz*1e6, setting)
                    location = (label, trial, setting, int(forward.segment[i]), frequency_mhz, c.policy_fingerprint)
                    for key, value in (('il', abs(result['il_db'] - expected)),
                                       ('power', abs(result['power_residual_w']))):
                        if value > maxima[key][0]:
                            maxima[key] = (value, location)
                    self.assertLess(abs(result['il_db'] - expected), 1e-9)
                    self.assertLess(abs(result['power_residual_w']), 1e-12)
                    for key in ('inductor_loss_w','capacitor_loss_w','input_s2p_loss_w','output_s2p_loss_w','load_power_w'):
                        self.assertGreaterEqual(result[key], -1e-12, key)
                    self.assertFalse(result['rf_compliance_certified'])
                    self.assertTrue(result['candidate_promotion_blocked'])
        print('B2 parity maxima:', maxima)

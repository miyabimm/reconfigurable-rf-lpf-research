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
    def test_scan_coverage_and_refinement(self):
        policy = load_constraint('RF-T005', allow_trial=True)
        circuit = SimpleNamespace(_adapter=SimpleNamespace(policy=policy), policy_id='RF-T005')
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
        for trial, config, x in cases:
            c = build_nominal_circuit(load_constraint(trial, allow_trial=True), config)
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
                    self.assertLess(abs(result['il_db'] - expected), 1e-9)
                    self.assertLess(abs(result['power_residual_w']), 1e-12)
                    for key in ('inductor_loss_w','capacitor_loss_w','input_s2p_loss_w','output_s2p_loss_w','load_power_w'):
                        self.assertGreaterEqual(result[key], -1e-12, key)
                    self.assertFalse(result['rf_compliance_certified'])
                    self.assertTrue(result['candidate_promotion_blocked'])

"""Limited fixed-vector parity and power evidence; not a dense RF run."""
import json
import unittest
from unittest.mock import patch

from test_phase2_public_circuit_api import (definition, RUNS, SNAP, exp042,
                                            exp055, exp058_area4l_gjm)
from lpf.constraint_versions import load_constraint
from lpf.phase2_models.api import build_nominal_circuit
from lpf.phase2_models.coupled_lc import CoupledLCTopology
from lpf.phase2_models.independent_rf import evaluate_independent_sample


class IndependentRFTests(unittest.TestCase):
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
        for trial, config, x in cases:
            c = build_nominal_circuit(load_constraint(trial, allow_trial=True), config)
            forward = c.forward_evaluator(2)
            reference = forward.il(x)
            self.assertEqual(len(reference), 56)
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

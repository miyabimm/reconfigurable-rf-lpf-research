"""Owner-approved 2026-10-11 PCB patterned fixed-capacitor constraints."""
import sys
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))

from lpf.constraints import (check_counts, chip_area, load_policy,
                             validate_pcb_pattern_caps)
from lpf.circuit import solve
from lpf.evaluate import CASES
from lpf.legacy_graph_builder import check_graph, build_grounded_settings


class PCBPatternCPolicyTests(unittest.TestCase):
    def test_canonical_policy_values(self):
        p=load_policy()
        c=p['components']['PCB_PATTERN_C']
        self.assertEqual(c['q'],40)
        self.assertAlmostEqual(c['bounds']['min'],0.02)
        self.assertEqual(c['area_units'],0)
        self.assertEqual(c['max_count'],3)
        self.assertAlmostEqual(c['bounds']['max'],0.2)
        self.assertTrue(c['common_across_settings'])

    def test_zero_chip_cost_and_max_three(self):
        self.assertEqual(chip_area(4,0,0,3,3),6)
        self.assertTrue(check_counts(n_lqp02=4,n_gjm01=3,n_pcb_pattern_c=3))
        self.assertFalse(check_counts(n_lqp02=4,n_gjm01=3,n_pcb_pattern_c=4))
        self.assertFalse(check_counts(n_pcb_pattern_c=-1))

    def test_minimum_maximum_and_q(self):
        self.assertTrue(validate_pcb_pattern_caps([0.02,0.05,0.2],[40,40,40]))
        self.assertTrue(validate_pcb_pattern_caps([0.2],[40]))  # upper boundary
        for values, qs in (([0.01999],[40]),([0.200001],[40]),([0.02]*4,[40]*4),([0.02],[80])):
            with self.assertRaises(ValueError):
                validate_pcb_pattern_caps(values,qs)

    def test_grounded_graph_treats_pcb_c_as_fixed_capacitor(self):
        # Graph: one series chip L, grounded PCB C. N=3 (GND/IN/OUT).
        graph=(3,((1,2,'LQP02'),(2,0,'PCB_PATTERN_C')))
        self.assertEqual(check_graph(graph),1.0)
        setting=build_grounded_settings(graph,values=[2e-9,0.02e-12])
        self.assertEqual(set(setting),set(CASES))
        cap=setting['B71']['capacitors'][0]
        self.assertEqual(cap.q,40)
        self.assertAlmostEqual(cap.value,0.02e-12)
        self.assertEqual(len(setting['B71']['inductors']),1)
        self.assertEqual(setting['B8']['capacitors'][0],cap)
        r=solve(700e6,**setting['B71'])
        self.assertTrue(r['gain']>0)
        self.assertLess(abs(r['power_residual']),1e-10)

    def test_graph_rejects_excess_and_below_min(self):
        excess=(3,((1,2,'LQP02'),)+((2,0,'PCB_PATTERN_C'),)*4)
        with self.assertRaises(ValueError):
            check_graph(excess)
        with self.assertRaises(ValueError):
            build_grounded_settings((3,((1,2,'LQP02'),(2,0,'PCB_PATTERN_C'))),
                                    values=[2e-9,0.019e-12])
        with self.assertRaises(ValueError):
            build_grounded_settings((3,((1,2,'LQP02'),(2,0,'PCB_PATTERN_C'))),
                                    values=[2e-9,0.201e-12])

    def test_fixed_across_settings(self):
        graph=(3,((1,2,'LQP02'),(2,0,'PCB_PATTERN_C')))
        settings=build_grounded_settings(graph,values=[2e-9,0.1e-12])
        from lpf.configuration import validate_six_settings
        settings['B8']['capacitors']=tuple(
            [type(settings['B8']['capacitors'][0])(2,0,0.2e-12,40)]
            +list(settings['B8']['capacitors'][1:]))
        with self.assertRaises(ValueError):
            validate_six_settings(settings,(1,2))


if __name__=='__main__':
    unittest.main()

"""RF-T008 grounded versus hot-hot fixed PCB-C nominal policy regression."""
import math
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from lpf.constraint_versions import (
    constraint_fingerprint,
    load_constraint,
    validate_registry,
)
from lpf.trial_pcb_pattern_c import (
    validate_trial_pcb_pattern_c_branches,
    pcb_pattern_c_branch_admittance,
)
from lpf.trial_shunt_dtc import (
    shunt_dtc_parasitic_branches,
    single_parasitic_admittance,
)


class RFT008Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.trial = load_constraint("RF-T008", allow_trial=True)
        cls.formal = load_constraint("RF-F003")
        cls.t007 = load_constraint("RF-T007", allow_trial=True)

    def test_registered_and_frozen_inheritance(self):
        registry = validate_registry()
        self.assertEqual(registry["active_formal_id"], "RF-F003")
        self.assertEqual(registry["trial"]["RF-T008"]["state"], "study_authorized")
        self.assertEqual(self.trial["trial_base_constraint_id"], "RF-F003")
        self.assertEqual(self.trial["components"]["IC_VARIABLE_C"]["max_branches_principle"], 3)
        self.assertEqual(self.trial["components"]["IC_VARIABLE_C"]["q"], 35)
        self.assertEqual(self.trial["components"]["IC_VARIABLE_C"]["max_total_variable_pf_per_branch"], 3)
        # The formal default stays 0.2pF/Q40. The trial exception is per-connection.
        self.assertEqual(self.trial["components"]["PCB_PATTERN_C"]["max_pf_per_component"], 0.2)
        self.assertEqual(self.trial["components"]["PCB_PATTERN_C"]["q"], 40)
        self.assertEqual(self.formal["components"]["PCB_PATTERN_C"]["max_pf_per_component"], 0.2)
        self.assertEqual(self.trial["external_port_parasitics"], self.formal["external_port_parasitics"])
        self.assertNotIn("trial_pcb_pattern_c_by_connection", self.t007)
        self.assertNotEqual(constraint_fingerprint(self.trial),
                            constraint_fingerprint(self.t007))

    def test_only_grounded_fixed_pcb_c_extended(self):
        caps = [
            {"a": 1, "b": 2, "capacitance_pf": 0.2, "q": 40},
            {"a": 3, "b": 4, "capacitance_pf": 0.02, "q": 40},
            {"a": 3, "b": 0, "capacitance_pf": 1.0, "q": 60},
        ]
        self.assertTrue(validate_trial_pcb_pattern_c_branches(self.trial, caps))
        self.assertTrue(validate_trial_pcb_pattern_c_branches(
            self.trial, [{"a": 0, "b": 3, "capacitance_pf": 0.3770198105, "q": 60}]))
        for bad in [
            [{"a": 3, "b": 0, "capacitance_pf": 1.0000001, "q": 60}],
            [{"a": 3, "b": 0, "capacitance_pf": 0.377, "q": 40}],
            [{"a": 3, "b": 0, "capacitance_pf": 0.0199, "q": 60}],
            [{"a": 1, "b": 2, "capacitance_pf": 0.2000001, "q": 40}],
            [{"a": 1, "b": 2, "capacitance_pf": 0.2, "q": 60}],
            [{"a": 1, "b": 1, "capacitance_pf": 0.1, "q": 40}],
            [{"a": -1, "b": 3, "capacitance_pf": 0.377, "q": 60}],
            [{"a": True, "b": 3, "capacitance_pf": 0.377, "q": 60}],
            caps[0:2] + caps[2:] + caps[:1],
        ]:
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                validate_trial_pcb_pattern_c_branches(self.trial, bad)

    def test_q_60_admittance_is_not_q_40(self):
        branch = {"a": 3, "b": 0, "capacitance_pf": 0.3770198105, "q": 60}
        freq = 800_000_000
        actual = pcb_pattern_c_branch_admittance(self.trial, branch, freq)
        expected = 2 * math.pi * freq * branch["capacitance_pf"] * 1e-12 / (1 / 60 - 1j)
        self.assertAlmostEqual(abs(actual - expected), 0, places=16)
        self.assertGreater(actual.real, 0)
        wrong = 2 * math.pi * freq * branch["capacitance_pf"] * 1e-12 / (1 / 40 - 1j)
        self.assertGreater(abs(actual - wrong), 1e-5)
        with self.assertRaises(ValueError):
            pcb_pattern_c_branch_admittance(self.trial, branch, float("nan"))
        with self.assertRaises(ValueError):
            validate_trial_pcb_pattern_c_branches(self.t007, [branch])

    def test_shunt_dtc_parasitic_is_still_separate_q40(self):
        branches = [
            {"a": 4, "b": 0, "role": "shunt_to_ground"},
            {"a": 2, "b": 3, "role": "bridge"},
        ]
        result = shunt_dtc_parasitic_branches(self.trial, branches)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["capacitance_pf"], 0.5)
        self.assertEqual(result[0]["q"], 40)
        f = 800_000_000
        self.assertAlmostEqual(
            abs(single_parasitic_admittance(self.trial, f)
                - 2 * math.pi * f * 0.5e-12 / (1/40 - 1j)),
            0, places=16)

    def test_explicit_trial_opt_in_and_no_wide_stopband_merging(self):
        with self.assertRaises(ValueError):
            load_constraint("RF-T008")
        self.assertNotIn("trial_additional_stopband", self.trial)


if __name__ == "__main__":
    unittest.main()

"""RF-T007 trial-spec and nominal 0.5pF/Q40 per-grounded-branch tests."""
import math
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from lpf.constraint_versions import load_constraint, validate_registry
from lpf.trial_shunt_dtc import (
    shunt_dtc_parasitic_branches,
    single_parasitic_admittance,
)


class RFt007Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.policy = load_constraint("RF-T007", allow_trial=True)

    def test_registry_and_inheritance(self):
        registry = validate_registry()
        self.assertEqual(registry["active_formal_id"], "RF-F003")
        self.assertEqual(self.policy["trial_base_constraint_id"], "RF-F003")
        self.assertEqual(self.policy["components"]["IC_VARIABLE_C"]["max_branches_principle"], 3)
        self.assertEqual(self.policy["components"]["IC_VARIABLE_C"]["q"], 35)
        self.assertEqual(self.policy["components"]["IC_VARIABLE_C"]["max_total_variable_pf_per_branch"], 3)
        self.assertEqual(self.policy["components"]["PCB_PATTERN_C"]["max_count"], 3)
        self.assertEqual(self.policy["components"]["PCB_PATTERN_C"]["max_pf_per_component"], 0.2)
        self.assertEqual(self.policy["trial_shunt_dtc_parasitic"]["fixed_capacitance_pf"], 0.5)
        self.assertEqual(self.policy["trial_shunt_dtc_parasitic"]["q"], 40)

    def test_each_ground_shunt_and_no_bridge(self):
        # Existing EXP-042 labels: Cv0 node4-GND, Cv1 node5-GND, Cv2 node2-node3.
        branches = [
            {"a": 4, "b": 0, "role": "shunt_to_ground"},
            {"a": 5, "b": 0, "role": "shunt_to_ground"},
            {"a": 2, "b": 3, "role": "bridge"},
        ]
        result = shunt_dtc_parasitic_branches(self.policy, branches)
        self.assertEqual(len(result), 2)
        self.assertEqual([p["node"] for p in result], [4, 5])
        self.assertEqual([p["variable_branch_index"] for p in result], [0, 1])
        self.assertEqual([p["capacitance_pf"] for p in result], [0.5, 0.5])
        self.assertEqual(shunt_dtc_parasitic_branches(
            self.policy, [{"a": 2, "b": 3, "role": "bridge"}]), ())

    def test_non_ground_series_unaffected(self):
        self.assertEqual(shunt_dtc_parasitic_branches(
            self.policy, [{"a": 1, "b": 2, "role": "series"}]), ())

    def test_y_and_unchanged_zero_state(self):
        # Parasitic stamp is unchanged even when programmed Cvar=0.
        f = 1_000_000_000
        actual = single_parasitic_admittance(self.policy, f)
        expected = 2 * math.pi * f * 0.5e-12 / (1 / 40 - 1j)
        self.assertAlmostEqual(abs(actual - expected), 0, places=16)
        self.assertGreater(actual.real, 0)
        self.assertGreater(actual.imag, 0)
        self.assertNotEqual(actual, 0)

    def test_explicit_opt_in(self):
        with self.assertRaises(ValueError):
            load_constraint("RF-T007")
        with self.assertRaises(ValueError):
            shunt_dtc_parasitic_branches(load_constraint("RF-T005", allow_trial=True), [])
        with self.assertRaises(ValueError):
            single_parasitic_admittance(self.policy, -1)


if __name__ == "__main__":
    unittest.main()

"""RF-T008 rev3 max-two IC variable+fixed composite branches, not RF-T007."""
import math
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from lpf.constraint_versions import (
    constraint_fingerprint,
    load_constraint,
    validate_variable_c_connections,
)
from lpf.trial_ic_fixed_c import (
    ic_fixed_c_branches,
    ic_c_pair_admittances,
    validate_ic_fixed_c_settings,
)
from lpf.trial_shunt_dtc import shunt_dtc_parasitic_branches


class RFT008ICFixedCTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.p = load_constraint("RF-T008", allow_trial=True)
        cls.old = load_constraint("RF-T007", allow_trial=True)
        cls.bridge = {"a": 2, "b": 3, "role": "bridge"}
        cls.series = {"a": 4, "b": 5, "role": "series"}
        cls.ground = {"a": 6, "b": 0, "role": "shunt_to_ground"}

    def test_policy_independent_limits_and_old_T007_unchanged(self):
        p = self.p
        c = p["trial_ic_fixed_c_by_connection"]
        self.assertEqual(c["fixed_c_q"], 60)
        self.assertEqual(c["variable_c_q"], 35)
        self.assertEqual(c["non_ground"], {"min_pf_per_branch": 0.2,
                                            "max_pf_per_branch": 3})
        self.assertEqual(c["grounded"], {"min_pf_per_branch": 0.5,
                                        "max_pf_per_branch": 3})
        self.assertEqual(c["variable_capacitance_pf_range"], [0, 3])
        self.assertEqual(c["max_composite_branches"], 2)
        self.assertEqual(p["components"]["IC_VARIABLE_C"]["max_branches_principle"], 2)
        self.assertEqual(p["trial_variable_c_layout"]["branch_count"], 2)
        self.assertEqual(p["trial_base_constraint_id"], "RF-F003")
        self.assertEqual(self.old["trial_shunt_dtc_parasitic"]["q"], 40)
        self.assertEqual(self.old["trial_shunt_dtc_parasitic"]["fixed_capacitance_pf"], 0.5)
        self.assertNotIn("trial_shunt_dtc_parasitic", p)
        self.assertNotIn("trial_ic_fixed_c_by_connection", self.old)
        self.assertNotEqual(constraint_fingerprint(p), constraint_fingerprint(self.old))

    def test_mandatory_pair_for_each_hot_hot_and_grounded(self):
        fixed = ic_fixed_c_branches(self.p, [self.bridge, self.ground], [0.2, 0.5])
        self.assertEqual(len(fixed), 2)
        self.assertEqual([(e["a"], e["b"]) for e in fixed], [(2, 3), (6, 0)])
        self.assertEqual([e["q"] for e in fixed], [60, 60])
        self.assertEqual([e["variable_branch_index"] for e in fixed], [0, 1])
        self.assertTrue(all(e["setting_invariant"] for e in fixed))
        # A hot-hot series can still be installed in lieu of either branch.
        series = ic_fixed_c_branches(self.p, [self.series], [3])
        self.assertEqual((series[0]["a"], series[0]["b"]), (4, 5))

    def test_composite_max_total_6pF(self):
        for branch, fix in [(self.bridge, 3), (self.ground, 3)]:
            ys = ic_c_pair_admittances(self.p, branch, fix, 3, 900_000_000)
            w = 2 * math.pi * 900_000_000
            expectf = w * 3e-12 / (1 / 60 - 1j)
            expectv = w * 3e-12 / (1 / 35 - 1j)
            self.assertAlmostEqual(abs(ys["fixed"] - expectf), 0, places=16)
            self.assertAlmostEqual(abs(ys["variable"] - expectv), 0, places=16)
            self.assertAlmostEqual(abs(ys["total"] - expectf - expectv), 0, places=16)
            self.assertGreater(ys["total"].real, 0)

    def test_zero_var_never_opens_hot_hot_series(self):
        for branch, fix in [(self.bridge, 0.2), (self.series, 0.2),
                            (self.ground, 0.5)]:
            y = ic_c_pair_admittances(self.p, branch, fix, 0, 700_000_000)
            self.assertEqual(y["variable"], 0)
            self.assertNotEqual(y["fixed"], 0)
            self.assertEqual(y["fixed"], y["total"])

    def test_capacity_bounds_reject_missing_fixed_or_wrong_ground(self):
        branches = [self.bridge, self.ground]
        for invalid in [[0.199999, 0.5], [0.2, 0.499999], [3.000001, 0.5],
                        [0.2, 3.000001], [0.2], [0.2, 0.5, 0.6], [None, 0.5],
                        [True, 0.5], [float("nan"), 0.5]]:
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                ic_fixed_c_branches(self.p, branches, invalid)
        for bad_variable in [-1e-5, 3.001, True, float("inf")]:
            with self.subTest(bad_variable=bad_variable), self.assertRaises(ValueError):
                ic_c_pair_admittances(self.p, self.bridge, 0.2, bad_variable, 900_000_000)
        for bad_freq in [-1, float("nan"), None]:
            with self.subTest(bad_freq=bad_freq), self.assertRaises(ValueError):
                ic_c_pair_admittances(self.p, self.bridge, 0.2, 0, bad_freq)

    def test_six_setting_common_fixed_C(self):
        branches = [self.bridge, self.ground]
        var = {
            "B71": [0, 3], "B12": [0.1, 2], "B28": [1.0, 0],
            "B13+B14": [2.0, 0.7], "B26": [2.7, 0.2], "B8": [3.0, 1.1],
        }
        self.assertTrue(validate_ic_fixed_c_settings(self.p, branches, [0.2, 0.5], var))
        bad = dict(var)
        del bad["B8"]
        with self.assertRaises(ValueError):
            validate_ic_fixed_c_settings(self.p, branches, [0.2, 0.5], bad)
        bad = dict(var)
        bad["B8"] = [1.0]
        with self.assertRaises(ValueError):
            validate_ic_fixed_c_settings(self.p, branches, [0.2, 0.5], bad)
        bad = dict(var)
        bad["B8"] = [1.0, 3.1]
        with self.assertRaises(ValueError):
            validate_ic_fixed_c_settings(self.p, branches, [0.2, 0.5], bad)

    def test_t007_old_function_forbidden_on_t008(self):
        with self.assertRaises(ValueError):
            shunt_dtc_parasitic_branches(self.p, [self.ground])
        with self.assertRaises(ValueError):
            ic_fixed_c_branches(self.old, [self.ground], [0.5])

    def test_no_IC_fixed_without_DTC_and_no_duplicate_dimensions(self):
        self.assertEqual(ic_fixed_c_branches(self.p, [], []), ())
        with self.assertRaises(ValueError):
            ic_fixed_c_branches(self.p, [], [0.5])
        with self.assertRaises(ValueError):
            ic_fixed_c_branches(self.p, [self.bridge, self.series, self.ground],
                                 [0.2, 0.2, 0.5])
        with self.assertRaises(ValueError):
            validate_variable_c_connections(
                [self.bridge, self.series, self.ground], self.p)
        # Old T007 3-branch experiment stays available only under T007.
        self.assertTrue(validate_variable_c_connections(
            [self.bridge, self.series, self.ground], self.old))

    def test_PCB_ground_still_Q60_and_hot_hot_Q40(self):
        spec = self.p["trial_pcb_pattern_c_by_connection"]
        self.assertEqual(spec["grounded"], {"min_pf_per_component": 0.02,
                                            "max_pf_per_component": 1, "q": 60})
        self.assertEqual(spec["non_ground"], {"min_pf_per_component": 0.02,
                                             "max_pf_per_component": 0.2, "q": 40})
        self.assertEqual(spec["max_count"], 3)


if __name__ == "__main__":
    unittest.main()

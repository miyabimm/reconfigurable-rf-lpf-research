"""RF-F002 formal adoption and RF-T004 unrestricted up-to-three-C trial."""
import json
import unittest
from pathlib import Path
from src.lpf.constraint_versions import (
    constraint_fingerprint, load_constraint, validate_registry,
    validate_variable_c_connections,
)
from src.lpf.constraints import check_counts

ROOT = Path(__file__).resolve().parents[1]

class RevisedRFConstraintsTests(unittest.TestCase):
    def test_formal_identity_hash_and_components(self):
        reg = validate_registry()
        self.assertIn("RF-F003", reg["formal"])
        current = load_constraint("RF-F002")
        self.assertEqual(load_constraint("RF-F003"), json.loads(
            (ROOT/"rf/constraints/formal/RF-F003.json").read_text()))
        self.assertEqual(reg["formal"]["RF-F002"]["effective_constraint_sha256"],
                         constraint_fingerprint(current))
        self.assertEqual(current["components"]["IC_VARIABLE_C"]["q"], 50)
        self.assertEqual(current["components"]["IC_VARIABLE_C"]["max_total_variable_pf_per_branch"], 1.5)
        self.assertEqual(current["components"]["IC_VARIABLE_C"]["max_branches_principle"], 2)
        self.assertEqual(current["components"]["IC_VARIABLE_C"]["positions_allowed_by_default"],
                         ["shunt_to_ground", "non_ground_bridge", "series"])
        self.assertFalse(current["components"]["IC_VARIABLE_C"]["series_requires_separate_approval"])
        self.assertEqual(current["components"]["LQW04"]["q"], 33)
        self.assertEqual(current["components"]["PCB_L"]["max_inductance_nh"], 2)
        limits = current["coupling_limits"]
        for name, expected in (
            ("chip_chip_strong_adjacent_abs_k_max", .15),
            ("chip_chip_nonstrong_abs_k_max", .03),
            ("chip_chip_nonstrong_nominal_k", 0),
            ("pcb_pcb_abs_k_max_default", .15),
            ("chip_pcb_abs_k_max", 0)
        ):
            self.assertEqual(limits[name], expected)
        self.assertTrue(check_counts(n_var=2, resolved_policy=current))
        self.assertFalse(check_counts(n_var=3, resolved_policy=current))

    def test_legacy_f001_is_intact(self):
        old = load_constraint("RF-F001")
        self.assertEqual(old["coupling_limits"]["chip_chip_strong_adjacent_abs_k_max"], .4)
        self.assertEqual(old["components"]["IC_VARIABLE_C"]["q"], 80)
        self.assertEqual(old["components"]["IC_VARIABLE_C"]["max_total_variable_pf_per_branch"], 4)
        self.assertEqual(old["components"]["IC_VARIABLE_C"]["positions_allowed_by_default"],
                         ["shunt_to_ground"])

    def test_connections_formal_and_trial(self):
        formal = load_constraint("RF-F002")
        with self.assertRaises(ValueError):
            load_constraint("RF-T004")
        trial = load_constraint("RF-T004", allow_trial=True)
        self.assertEqual(trial["trial_base_constraint_id"], "RF-F002")
        self.assertEqual(trial["trial_variable_c_layout"],
                         {"branch_count":3,"count_policy":"up_to","connection_policy":"any_allowed"})
        self.assertEqual(trial["components"]["IC_VARIABLE_C"]["max_branches_principle"], 3)
        self.assertEqual(trial["components"]["IC_VARIABLE_C"]["q"], 50)
        # RF-F002 count validation remains fixed; trial opt-in allows 3.
        self.assertFalse(check_counts(n_var=3, resolved_policy=formal))
        self.assertTrue(check_counts(n_var=3, resolved_policy=trial))
        self.assertFalse(check_counts(n_var=4, resolved_policy=trial))
        shunt = {"a":1,"b":0}
        bridge = {"a":1,"b":2,"role":"bridge"}
        series = {"a":2,"b":3,"role":"series"}
        for branches in ([shunt, bridge], [shunt, series], [bridge, series]):
            self.assertTrue(validate_variable_c_connections(branches, formal))
            self.assertTrue(validate_variable_c_connections(branches, trial))
        for branches in ([shunt, bridge, series], [series,series,series]):
            self.assertTrue(validate_variable_c_connections(branches, trial))
            with self.assertRaises(ValueError):
                validate_variable_c_connections(branches, formal)
        with self.assertRaises(ValueError):
            validate_variable_c_connections([{"a":1,"b":2}], trial)
        with self.assertRaises(ValueError):
            validate_variable_c_connections([shunt]*4, trial)
        with self.assertRaises(ValueError):
            validate_variable_c_connections([series], load_constraint("RF-F001"))

if __name__ == "__main__":
    unittest.main()

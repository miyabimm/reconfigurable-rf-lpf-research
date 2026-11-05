"""Rule regression for LQP02HV (Q25, <=27 nH) and HQ (Q20, <=56 nH)."""
import json
import unittest
from pathlib import Path

from src.lpf.lqp02_series import audit_saved_candidate, load_policy, select_series


class Lqp02SeriesPolicyTest(unittest.TestCase):
    def test_rules_match_machine_readable_constraints(self):
        p = load_policy()
        self.assertIsNone(p["q"])
        self.assertEqual(p["preferred_series"], "LQP02HV")
        self.assertEqual(p["series"]["LQP02HV"]["q"], 25)
        self.assertEqual(p["series"]["LQP02HQ"]["q"], 20)
        self.assertEqual(p['series']['LQP02HV']['bounds']['max'], 27)
        self.assertEqual(p['series']['LQP02HQ']['bounds']['max'], 56)
        self.assertEqual(p["series"]["LQP02HV"]["area_units"], 1)
        self.assertEqual(p["series"]["LQP02HQ"]["area_units"], 1)

    def test_auto_series_and_Q_boundary(self):
        self.assertEqual(select_series(3.4)["series"], "LQP02HV")
        self.assertEqual(select_series(27)["Q"], 25)
        self.assertEqual(select_series(27.00001)["series"], "LQP02HQ")
        self.assertEqual(select_series(27.00001)["Q"], 20)
        self.assertEqual(select_series(56)["Q"], 20)
        self.assertEqual(select_series(15, series="LQP02HQ")["Q"], 20)
        with self.assertRaises(ValueError):
            select_series(28, series="LQP02HV")
        with self.assertRaises(ValueError):
            select_series(56.001)
        with self.assertRaises(ValueError):
            select_series(float("nan"))

    def test_legacy_Q25_56nH_must_not_pass(self):
        d = {"id": "legacy", "components": {"LQP02": {"count": 2, "Q": 25}},
             "topology": {"inductors": [
                 {"id": "L0", "L_nH": 3.4, "Q": 25},
                 {"id": "L1", "L_nH": 56, "Q": 25}
             ]}}
        result = audit_saved_candidate(d)
        self.assertFalse(result["new_policy_validated"])
        self.assertTrue(result["needs_reoptimization"])
        self.assertEqual(result["inductors"][1]["expected_Q"], 20)
        self.assertEqual(result["inductors"][1]["status"], "old_Q_incompatible")

    def test_legacy_Q25_below_27_requires_explicit_label(self):
        d = {"candidate_id": "historical", "components": {"LQP02": {"Q": 25}},
             "topology": {"inductors": [{"id": "L0", "L_nH": 8}]}}
        result = audit_saved_candidate(d)
        self.assertFalse(result["new_policy_validated"])
        self.assertFalse(result["needs_reoptimization"])
        self.assertTrue(result["needs_series_annotation"])

    def test_explicit_series_Q_cannot_cross_assign(self):
        d = {"topology": {"inductors": [
            {"id": "L0", "series": "LQP02HV", "L_nH": 15, "Q": 25},
            {"id": "L1", "series": "LQP02HQ", "L_nH": 29, "Q": 20}
        ]}}
        result = audit_saved_candidate(d)
        self.assertTrue(result["new_policy_validated"])
        self.assertFalse(result["srf_or_implementation_validated"])
        d["topology"]["inductors"][1]["Q"] = 25
        self.assertTrue(audit_saved_candidate(d)["needs_reoptimization"])


if __name__ == "__main__":
    unittest.main()

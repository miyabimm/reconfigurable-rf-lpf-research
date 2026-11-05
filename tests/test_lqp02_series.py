"""Regression for owner-approved LQP02HV Q25 <=27 nH and LQP02HQ Q20 <=56 nH."""
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.lpf.lqp02_series import load_policy, select_series, audit_saved_candidate


class TestLQP02Series(unittest.TestCase):
    def test_policy_and_limits(self):
        p = load_policy()
        self.assertIsNone(p["q"], "New designs must not assume universal LQP02 Q25")
        self.assertEqual(p["legacy_baseline_q"], 25)
        self.assertEqual(p["series"]["LQP02HV"]["q"], 25)
        self.assertEqual(p["series"]["LQP02HQ"]["q"], 20)
        self.assertEqual(p['series']['LQP02HV']['bounds']['max'], 27)
        self.assertEqual(p['series']['LQP02HQ']['bounds']['max'], 56)
        self.assertEqual(select_series(25)["series"], "LQP02HV")
        self.assertEqual(select_series(30)["Q"], 20)
        self.assertEqual(select_series(5, series="LQP02HQ")["Q"], 20)
        with self.assertRaises(ValueError):
            select_series(28, series="LQP02HV")
        with self.assertRaises(ValueError):
            select_series(56.1)

    def test_historical_Q25_56_nh_not_migrated_silently(self):
        old = {"id": "legacy-checkpoint",
               "components": {"LQP02": {"Q": 25}},
               "topology": {"inductors": [{"id": "L1", "L_nH": 56.0, "Q": 25}]}}
        status = audit_saved_candidate(old)
        self.assertTrue(status["needs_reoptimization"])
        self.assertFalse(status["new_policy_validated"])
        self.assertEqual(status["inductors"][0]["expected_Q"], 20)


if __name__ == "__main__":
    unittest.main()

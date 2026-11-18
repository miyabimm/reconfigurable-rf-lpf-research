"""Historical LPF-007 baseline metadata guardrails (not a fresh RF replay)."""
import unittest
from copy import deepcopy

from scripts import verify_no_pcb_tunable_candidates as baseline


class BaselinePolicyGuardrails(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.policy = baseline.read_policy()
        cls.reference = baseline.read_candidate("LPF-007")

    def test_q_model_regression_is_rejected(self):
        candidate = deepcopy(self.reference)
        candidate["topology"]["inductors"][0]["Q"] = 26
        with self.assertRaisesRegex(AssertionError, "Q changed"):
            baseline.check_baseline_metadata(candidate, self.policy)

    def test_fixed_cap_q_regression_is_rejected(self):
        candidate = deepcopy(self.reference)
        candidate["topology"]["fixed_caps"][0]["Q"] = 81
        with self.assertRaisesRegex(AssertionError, "fixed capacitor Q"):
            baseline.check_baseline_metadata(candidate, self.policy)

    def test_variable_cap_connection_and_limit_are_rejected(self):
        candidate = deepcopy(self.reference)
        candidate["topology"]["variable_caps"][0]["b"] = 1
        with self.assertRaises(AssertionError):
            baseline.check_baseline_metadata(candidate, self.policy)
        candidate = deepcopy(self.reference)
        candidate["ic_variable_C_pf_by_setting"]["B8"][0] = 4.1
        with self.assertRaises(AssertionError):
            baseline.check_baseline_metadata(candidate, self.policy)

    def test_saved_performance_cannot_be_rebaselined_silently(self):
        candidate = deepcopy(self.reference)
        candidate["performance"]["worst_IL_db"] += 0.0001
        with self.assertRaisesRegex(AssertionError, "saved reference metric"):
            baseline.check_baseline_metadata(candidate, self.policy)


if __name__ == "__main__":
    unittest.main()

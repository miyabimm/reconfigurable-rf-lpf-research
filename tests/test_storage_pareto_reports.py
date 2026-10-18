"""Condition-isolated Pareto tests; historical storage-inventory tests retired."""
import unittest

from scripts.report_research_pareto import dominates, make_report


class ParetoRegressions(unittest.TestCase):
    def test_domination_requires_no_worse_area_and_il(self):
        a = {"chip_area_units": 6, "worst_il_db": 0.4}
        b = {"chip_area_units": 6, "worst_il_db": 0.5}
        c = {"chip_area_units": 8, "worst_il_db": 0.3}
        self.assertTrue(dominates(a, b))
        self.assertFalse(dominates(a, c))
        self.assertFalse(dominates(c, a))
        self.assertFalse(dominates(a, a))

    def test_register_groups_cannot_promote_trial_to_formal(self):
        view, summary = make_report()
        self.assertEqual(14, summary["candidate_count"])
        self.assertEqual(8, summary["comparison_group_count"])
        self.assertFalse(summary["formal_strict_rf_f002_il0p3_met"])
        by_id = {r["catalog_id"]: r for r in view}
        recovered = by_id["EXP017-LQW4-H30-NEAR"]
        self.assertEqual("formal", recovered["constraint_class"])
        self.assertEqual("RF-F002", recovered["constraint_id"])
        self.assertEqual("false", recovered["il_0p30_met_on_recorded_grid"])
        trial = by_id["EXP018-C13.667"]
        self.assertEqual("trial", trial["constraint_class"])
        self.assertEqual("RF-T004", trial["constraint_id"])
        self.assertEqual("true", trial["il_0p30_met_on_recorded_grid"])
        nominal = by_id["EXP-041-35DB-STAGE"]
        self.assertEqual("tolerance_only", nominal["threshold_classification"])
        self.assertEqual("false", nominal["il_0p30_met_on_recorded_grid"])
        same_group = [r for r in view if r["comparison_key"] ==
                      "RF-F002_full_lpf_35_strict_finite_grid"]
        self.assertEqual(2, len(same_group))
        self.assertTrue(all(r["pareto_within_group"] == "true" for r in same_group))
        old = [r for r in view if r["constraint_class"] == "historical"]
        self.assertEqual(1, sum(r["pareto_within_group"] == "true" for r in old))


if __name__ == "__main__":
    unittest.main()

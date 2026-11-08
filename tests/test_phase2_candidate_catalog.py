"""Step 3: validate derived data, trial/formal separation, and source evidence."""
from collections import Counter
import unittest
from unittest.mock import patch

from scripts import build_phase2_candidate_catalog as catalog
from scripts import report_research_pareto as pareto


class UnifiedCatalogTests(unittest.TestCase):
    def test_legacy_fourteen_preserved_and_new_ten_separate(self):
        records = catalog.build_catalog()
        self.assertEqual(24, len(records))
        self.assertEqual({"RF-F003": 4, "RF-T005": 6},
                         dict(Counter(r["constraint_id"] for r in records[14:])))
        original = catalog.rows_from_csv(catalog.ROOT, catalog.LEGACY)
        self.assertEqual(original, [{k: row[k] for k in catalog.BASE_COLUMNS}
                                    for row in records[:14]])
        self.assertEqual(24, len({r["catalog_id"] for r in records}))
        self.assertEqual(2, len({r["comparison_key"] for r in records[14:]}))
        self.assertEqual({"formal", "trial"}, {r["constraint_class"] for r in records[14:]})
        self.assertEqual(
            {"RF-F003": {"2"}, "RF-T005": {"3"}},
            {cid: {r["num_ic_variable_c"] for r in records[14:]
                   if r["constraint_id"] == cid}
             for cid in ("RF-F003", "RF-T005")},
        )

    def test_all_new_metrics_reproduce_snapshot(self):
        with patch.object(catalog, "evidence_blob_check",
                          wraps=catalog.evidence_blob_check) as checked:
            records = catalog.build_catalog()
        self.assertEqual(20, checked.call_count)
        snap = catalog.read_json(catalog.ROOT, catalog.SNAPSHOT)
        by_id = {r["catalog_id"]: r for r in records}
        for condition in snap["conditions"]:
            for candidate in condition["candidates"]:
                r = by_id[candidate["id"]]
                self.assertEqual(float(r["worst_il_db"]), candidate["metrics"]["worst_il_db"])
                self.assertEqual(float(r["min_h2_db"]), candidate["metrics"]["min_h2_db"])
                self.assertEqual(float(r["min_h3_db"]), candidate["metrics"]["min_h3_db"])
                self.assertEqual(int(r["mesh_points_per_interval"]),
                                 candidate["verification"]["points_per_interval"])
                self.assertEqual(int(r["independent_mna_probe_points"]), 84)
                self.assertEqual(r["original_metadata_discrepancy"],
                                 candidate.get("source_metadata_discrepancy", ""))
                self.assertEqual(r["experiment_execution_status"], "partial")

    def test_area_correction_and_unconverged_state_visible(self):
        records = catalog.build_catalog()
        by_id = {r["catalog_id"]: r for r in records}
        f = by_id["F003_4L_A6p667_EXP047"]
        self.assertAlmostEqual(6 + 2/3, float(f["chip_area_units"]))
        self.assertIn("誤記", f["original_metadata_discrepancy"])
        t = by_id["T005_4L_A6_EXP042"]
        self.assertIn("nonconverged", t["solver_convergence_status"])
        self.assertEqual("7001", t["mesh_points_per_interval"])
        self.assertEqual("84", t["independent_mna_probe_points"])
        self.assertEqual("EXP042-30m005", t["source_subcandidate_id"])
        self.assertEqual("", t["checkpoint_stage_index"])

    def test_source_blob_mismatch_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "Git blob mismatch"):
            catalog.evidence_blob_check(catalog.ROOT, {
                "path": catalog.SNAPSHOT,
                "blob_sha": "0" * 40,
            })
        with self.assertRaisesRegex(ValueError, "unsafe evidence path"):
            catalog.safe_evidence(catalog.ROOT, "../README.md")

    def test_formal_trial_swap_is_rejected(self):
        real = catalog.read_json
        def corrupted(root, rel):
            val = real(root, rel)
            if rel == catalog.SNAPSHOT:
                val["conditions"][0]["type"] = "formal_active"
            return val
        with patch.object(catalog, "read_json", side_effect=corrupted):
            with self.assertRaises(ValueError):
                catalog.build_catalog()

    def test_tampering_with_source_area_fails(self):
        real = catalog.read_json
        def corrupted(root, rel):
            val = real(root, rel)
            if rel == catalog.SNAPSHOT:
                val["conditions"][1]["candidates"][0]["chip_area_units"] = 123
            return val
        with patch.object(catalog, "read_json", side_effect=corrupted):
            with self.assertRaisesRegex(ValueError, "chip area formula mismatch"):
                catalog.build_catalog()

    def test_generated_files_identical_to_source(self):
        records = catalog.build_catalog()
        self.assertEqual((catalog.ROOT / catalog.OUTPUT_CSV).read_text(encoding="utf-8"),
                         catalog.as_csv(records))

    def test_opt_in_pareto_reports_24_with_old_default_unchanged(self):
        current_old, current_summary = pareto.make_report()
        archived_old, archived_summary = pareto.make_report(catalog_path=catalog.LEGACY)
        combined, newer = pareto.make_report(catalog_path=catalog.OUTPUT_CSV)
        # The default follows the evolving live source; the 2026-10-17
        # historical subset remains independently pinned to exactly 14 rows.
        self.assertEqual(len(current_old),
                         len(catalog.rows_from_csv(catalog.ROOT, "data/research_candidate_register.csv")))
        self.assertEqual(current_summary["candidate_count"], len(current_old))
        self.assertEqual(14, len(archived_old))
        self.assertEqual(14, archived_summary["candidate_count"])
        self.assertEqual(24, len(combined))
        self.assertEqual(24, newer["candidate_count"])
        self.assertEqual(archived_summary["comparison_group_count"] + 2,
                         newer["comparison_group_count"])
        for cid, expected in (("RF-T005", 6), ("RF-F003", 4)):
            matching = [r for r in combined if r["constraint_id"] == cid]
            self.assertEqual(expected, len(matching))
            self.assertTrue(all(r["pareto_within_group"] == "true" for r in matching))
            self.assertTrue(all(r["il_0p30_met_on_recorded_grid"] == "false"
                                for r in matching))
        self.assertFalse(newer["formal_strict_rf_f003_il0p3_met"])
        self.assertNotEqual({r["comparison_key"] for r in combined if
                             r["constraint_id"] == "RF-T005"},
                            {r["comparison_key"] for r in combined if
                             r["constraint_id"] == "RF-F003"})


if __name__ == "__main__":
    unittest.main()

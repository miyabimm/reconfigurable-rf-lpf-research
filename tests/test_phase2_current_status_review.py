"""Phase 2 status/provenance guardrails; reads historical evidence only.

Does not re-run RF optimization or rewrite old experiments.
"""
import csv
import json
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read_csv(relpath):
    with (ROOT / relpath).open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


class Phase2CurrentStatusTests(unittest.TestCase):
    def test_current_roadmap_identifies_active_development_gates(self):
        roadmap = (ROOT / "docs/roadmap.md").read_text(encoding="utf-8")
        self.assertIn("Stage 1", roadmap)
        self.assertIn("Stage 2", roadmap)
        self.assertIn("PR #164", roadmap)
        self.assertIn("Issue #163", roadmap)
        self.assertIn("IL≤0.30dB", roadmap)
        self.assertNotIn("Phase 3", roadmap)

    def test_retired_docs_remain_git_recoverable(self):
        """Documentation history lives in Git and Issue #170, not more live docs."""
        pinned_commit = "0bf0e3a41e2ed2a5ae4e734ccec71bc530c19a53"
        prior_sources = {
            "docs/archive/README.md": "f393c7313f1d26aa2b477469689f70466af7674c",
            "docs/experiment_manifests.md": "c8ffbc6a66cd5e3b46a70809ac03b266f1b5842b",
            "docs/experiment_number_reservation_policy_20261015.md": "6653a02c9fb4f41a64a703ec526210869551c059",
            "docs/experiment_result_storage_policy_proposal_20261015.md": "309727f788c47a3dd6fbc513accf09f50969e56c",
            "docs/historical_results.md": "9bed3f70a24594dd5e8839df1521489b7fa816c6",
            "docs/phase2_cleanup_w1_completion_20261017.md": "bf07eb4d950d203934fe5d68cad5c2516ce7e443",
            "docs/phase2_cleanup_w3_document_review_20261017.md": "dbe9eb89ab45d6a54d564b5782dff85747f3a460",
            "docs/phase2_issue93_reference_consumer_audit_20261018.md": "d81674754527af7b04523ea45d134e6ee0f09ca6",
            "docs/phase2_repository_step4_review_20261017.md": "f2eaf31ffb67b2ab6dc0473d531f7949ea7c2c58",
            "docs/phase2_repository_step5_final_verification_20261017.md": "b548f4bb36d23c65b1b6fbc840f921c6f58c7326",
            "docs/maintenance/branch_cleanup_20261014.md": "ecc0ed6a874329c376b3211f1d166eb9a0d0bba3",
            "docs/phase2_issue93_pr91_canonical_reconciliation_20261018.md": "e4cfc796b11f1748e91044b005451f77824aa69b",
            "docs/phase2_issue93_pr92_retirement_20261018.md": "dafe9b9e0f8dceba2e4ea073bdb8aa4c44cb29bd",
        }
        previous_head = "26a5d4aff7d197754f17991123acc44e8b356b83"
        original_entrypoints = (
            "docs/current/phase2_status.md",
            "docs/current/open_research_questions.md",
            "docs/governance/README.md",
            "docs/phase2_repository_cleanup_and_deletion_plan_20261017.md",
            "docs/phase2_stepA_smoke_and_on_demand_checks_20261018.md",
            "docs/phase2_stepB_workflow_retirement_20261018.md",
            "docs/phase2_first_wave_workflow_parity_review_20261018.md",
            "docs/phase2_stepC_dated_audit_retirement_20261018.md",
        )
        for path, expected_blob in prior_sources.items():
            with self.subTest(path=path):
                self.assertFalse((ROOT / path).exists())
                actual_blob = subprocess.check_output(
                    ["git", "rev-parse", pinned_commit + ":" + path],
                    cwd=ROOT, text=True).strip()
                self.assertEqual(expected_blob, actual_blob)
        for path in original_entrypoints:
            with self.subTest(path=path):
                self.assertFalse((ROOT / path).exists())
                subprocess.check_output(
                    ["git", "cat-file", "-e", pinned_commit + ":" + path],
                    cwd=ROOT)
        self.assertFalse((ROOT / "docs/archive/maintenance_notes_20261027.md").exists())
        subprocess.check_output(
            ["git", "cat-file", "-e",
             previous_head + ":docs/archive/maintenance_notes_20261027.md"],
            cwd=ROOT)
        self.assertIn("issues/170",
                      (ROOT / "docs/README.md").read_text(encoding="utf-8"))
        results = (ROOT / "docs/results.md").read_text(encoding="utf-8")
        self.assertIn("EXP-048", results)
        self.assertIn("EXP-049", results)

    def test_exp017_near_0301_is_recovered_without_changing_original_sources(self):
        source = (ROOT / "experiments/chatgpt_topology_search/runs/EXP-017/README.md").read_text(encoding="utf-8")
        self.assertIn("30dB必須条件での近接値", source)
        self.assertIn("0.301248245", source)
        issues = {x["issue_id"]: x for x in read_csv("data/research_review_issues.csv")}
        self.assertTrue(issues["RG-001"]["status"].startswith("resolved_"))
        self.assertEqual("EXP-017", issues["RG-001"]["affected_experiments"])
        self.assertIn("ZIP", issues["RG-001"]["problem"])
        curated = read_csv("data/research_candidate_register.csv")
        near = [x for x in curated if x["catalog_id"] == "EXP017-LQW4-H30-NEAR"]
        self.assertEqual(1, len(near))
        self.assertEqual("formal", near[0]["constraint_class"])
        self.assertEqual("RF-F002", near[0]["constraint_id"])
        self.assertGreater(float(near[0]["worst_il_db"]), 0.30)
        older = json.loads((ROOT / "data/validation/exp017_20261012/checkpoints.json").read_text(encoding="utf-8"))
        self.assertEqual("RF-F001", older["candidate"]["formal_constraint_reference"])
        self.assertEqual("NONCANONICAL_UNAPPROVED", older["candidate"]["constraint_status"])

    def test_trial_zip_not_misidentified_as_missing_formal_exp017(self):
        notes = (ROOT / "docs/phase2_exp017_checkpoint_provenance_review_20261015.md").read_text(encoding="utf-8")
        self.assertIn("RF-T004-EXP017-bundle.zip", notes)
        self.assertIn("48175d3579d3814e5d3740858ee3959b88e9731b835cb2cd306ce6b0093ae640", notes)
        self.assertIn("0.2999624819232782", notes)
        self.assertIn("0.301248245", notes)
        self.assertIn("RF-F002", notes)
        self.assertIn("RF-T004", notes)
        self.assertIn("14,001", notes)
        issues = {x["issue_id"]: x for x in read_csv("data/research_review_issues.csv")}
        self.assertTrue(issues["RG-001"]["status"].startswith("resolved_"))
        self.assertIn("RF-F002", issues["RG-001"]["problem"])

    def test_review_gates_are_traceable_without_fabricating_missing_metadata(self):
        issues = {x["issue_id"]: x for x in read_csv("data/research_review_issues.csv")}
        self.assertEqual(10, len(issues))
        self.assertIn("RG-009", issues)
        self.assertIn("RG-010", issues)
        inventory = read_csv("data/experiment_evidence_inventory.csv")
        legacy = [x for x in inventory if int(x["experiment_id"][4:]) <= 41]
        self.assertEqual(39, len(legacy))
        self.assertEqual(25, sum(x["seed_recorded"] == "false" for x in legacy))
        self.assertEqual(15, sum(x["execution_sha_recorded"] == "false" for x in legacy))
        self.assertEqual(16, sum(x["environment_recorded"] == "false" for x in legacy))
        self.assertEqual(6, sum(x["registered_evidence_count"] == "0" for x in legacy))


if __name__ == "__main__":
    unittest.main()

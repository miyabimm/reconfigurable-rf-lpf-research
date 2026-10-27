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

    def test_retired_navigation_is_pinned_and_sources_stay_separate(self):
        for path in ("docs/current/phase2_status.md",
                     "docs/current/open_research_questions.md",
                     "docs/governance/README.md"):
            self.assertFalse((ROOT / path).exists())
        docs_index = (ROOT / "docs/README.md").read_text(encoding="utf-8")
        for path in ("docs/current/phase2_status.md",
                     "docs/current/open_research_questions.md",
                     "docs/governance/README.md"):
            self.assertIn("https://github.com/miyabimm/reconfigurable-rf-lpf-research/blob/0bf0e3a41e2ed2a5ae4e734ccec71bc530c19a53/docs/" + path.removeprefix("docs/"), docs_index)
        results = (ROOT / "docs/results.md").read_text(encoding="utf-8")
        self.assertIn("EXP-048", results)
        self.assertIn("EXP-049", results)

    def test_retired_process_documents_are_recoverable_from_git(self):
        pinned_commit = "0bf0e3a41e2ed2a5ae4e734ccec71bc530c19a53"
        old_blobs = {
            "docs/phase2_repository_cleanup_and_deletion_plan_20261017.md": "88cb034aab4d231c927de3605ded758f5d27153d",
            "docs/phase2_stepA_smoke_and_on_demand_checks_20261018.md": "3c70c0af0d8d7103521a7135443189d6b10bb570",
            "docs/phase2_stepB_workflow_retirement_20261018.md": "d90f00f1b61b6a145ae6f015649e3e9117de58be",
            "docs/phase2_first_wave_workflow_parity_review_20261018.md": "a2f741bfac38cd54d0d0270575b8a7835c2cbf9b",
            "docs/phase2_stepC_dated_audit_retirement_20261018.md": "95c15a54b0b17e7ae6911410b3f43aa893c32513",
        }
        index = (ROOT / "docs/archive/maintenance_notes_20261027.md").read_text(
            encoding="utf-8")
        for path, expected_blob in old_blobs.items():
            with self.subTest(path=path):
                self.assertFalse((ROOT / path).exists())
                self.assertIn(pinned_commit + "/" + path, index)
                self.assertIn(expected_blob, index)
                actual_blob = subprocess.check_output(
                    ["git", "rev-parse", pinned_commit + ":" + path],
                    cwd=ROOT, text=True).strip()
                self.assertEqual(expected_blob, actual_blob)

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

"""Focused gates for the EXP-048+ Git-only storage policy (no RF simulations)."""
import hashlib
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.audit_new_experiment_storage import (
    CASES, validate_checkpoint, validate_run, validate_selection, validate_summary,
)

SCRIPT = "scripts.audit_new_experiment_storage"


def dump(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return hashlib.sha256(path.read_bytes()).hexdigest()


class StoragePolicyGateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.run = self.root / "experiments/chatgpt_topology_search/runs/EXP-048"
        self.run.mkdir(parents=True)
        dump(self.root / "data/phase2_git_storage_budget.json", {
            "thresholds": {
                "individual_new_file_hard_bytes": 1048576,
                "new_experiment_curated_soft_bytes": 524288,
            }
        })
        self.base = self.run.relative_to(self.root).as_posix()
        self.selection = {
            "top_k": 2,
            "retain": ["best", "pareto", "representative_failure"],
            "rule": "retain Pareto points and one diagnostic failure",
            "estimated_curated_bytes": 2000,
        }
        self.manifest = {
            "experiment_id": "EXP-048",
            "constraints": {"constraint_id": "RF-F003"},
            "execution": {"status": "planned"},
            "validation": {"numerical": "not_run", "independent": "not_run"},
            "evidence": [],
        }
        self.record = {
            "schema_version": 1,
            "policy": "phase2-git-only-v1",
            "experiment_id": "EXP-048",
            "phase": "Phase 2",
            "stage": "planned",
            "selection": self.selection,
            "summary": None, "checkpoints": [], "validation_overlays": [],
            "git_readback": "not_run", "size_exception": None, "limitations": [],
        }

    def validate(self, mode):
        with patch(SCRIPT + ".validate_manifest"), patch(
            SCRIPT + ".reservation_on_main", return_value={"constraint_id": "RF-F003"}
        ):
            return validate_run(self.root, "EXP-048", mode=mode)

    def save(self):
        dump(self.run / "manifest.json", self.manifest)
        dump(self.run / "storage_record.json", self.record)

    def test_preflight_valid_requires_selection_and_planned_manifest(self):
        self.save()
        self.assertEqual("planned", self.validate("preflight")["stage"])
        self.record["selection"]["rule"] = ""
        self.save()
        with self.assertRaisesRegex(ValueError, "selection rule"):
            self.validate("preflight")
        self.record["selection"]["rule"] = "retain Pareto"
        self.manifest["execution"]["status"] = "completed"
        self.save()
        with self.assertRaisesRegex(ValueError, "preflight execution"):
            self.validate("preflight")

    def test_six_settings_are_mandatory_not_claim_of_rf_correctness(self):
        obj = self.checkpoint()
        validate_checkpoint(obj, "C1")
        del obj["ic_variable_C_pf_by_setting"]["B8"]
        with self.assertRaisesRegex(ValueError, "all 6"):
            validate_checkpoint(obj, "C1")
        obj = self.checkpoint()
        obj["ic_variable_C_pf_by_setting"]["B8"] = [3.1]
        with self.assertRaisesRegex(ValueError, "arrays/value"):
            validate_checkpoint(obj, "C1")

    def checkpoint(self):
        return {
            "candidate_id": "C1",
            "topology": {"nodes": ["input", "output"], "branches": [{"a": "input", "b": "output"}]},
            "components": [{"id": "L1", "L_nH": 2, "Q": 25, "series": "LQP02HV", "terminals": [1, 2]}],
            "couplings": [],
            "chip_row": ["L1"],
            "fixed_values": {"L1_nH": 2},
            "ic_variable_C_pf_by_setting": {k: [1.0] for k in CASES},
        }

    def complete(self):
        self.manifest["execution"]["status"] = "completed"
        candidate = self.base + "/checkpoints/C1.json"
        summary = self.base + "/run_summary.json"
        sha_candidate = dump(self.root / candidate, self.checkpoint())
        sha_summary = dump(self.root / summary, {
            "experiment_id": "EXP-048",
            "attempts": {"planned": 2, "attempted": 2, "converged": 1,
                         "nonconverged": 1, "failed": 0, "not_started": 0},
            "selected_candidate_count": 1,
            "best_found": ["C1"],
            "limitations": ["no independent MNA or physical verification"],
        })
        self.manifest["evidence"] = [
            {"path": candidate, "sha256": sha_candidate},
            {"path": summary, "sha256": sha_summary},
        ]
        self.record.update({
            "stage": "complete", "git_readback": "passed",
            "checkpoints": [{
                "candidate_id": "C1", "selection_reason": "best",
                "path": candidate, "sha256": sha_candidate,
            }],
            "summary": {"path": summary, "sha256": sha_summary},
        })
        self.save()
        subprocess.run(["git", "init", "-q"], cwd=self.root, check=True)
        subprocess.run(["git", "add", "."], cwd=self.root, check=True)
        subprocess.run(["git", "-c", "user.name=test", "-c", "user.email=test@example.invalid",
                        "commit", "-qm", "test evidence"], cwd=self.root, check=True)
        return candidate

    def test_finalized_committed_checkpoint_and_summary(self):
        self.complete()
        report = self.validate("finalize")
        self.assertEqual(1, report["checkpoints"])
        self.assertTrue(report["committed_readback"])
        self.assertEqual("not_run", report["independent_validation"])

    def test_commit_readback_detects_post_commit_mutation(self):
        filename = self.complete()
        (self.root / filename).write_text('{"changed":true}', encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "differs from committed"):
            self.validate("finalize")

    def test_checksum_and_summary_counts_cannot_be_faked(self):
        self.complete()
        self.record["checkpoints"][0]["sha256"] = "0" * 64
        self.save()
        with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
            self.validate("finalize")

    def test_summary_count_rule(self):
        summary = {
            "experiment_id": "EXP-048",
            "attempts": {"planned": 4, "attempted": 3, "converged": 1,
                         "nonconverged": 1, "failed": 1, "not_started": 1},
            "selected_candidate_count": 0,
            "no_candidate_reason": "none passed",
            "limitations": [],
        }
        validate_summary(summary, "EXP-048", 0)
        summary["attempts"]["failed"] = 2
        with self.assertRaisesRegex(ValueError, "outcomes do not sum"):
            validate_summary(summary, "EXP-048", 0)

    def test_bad_storage_selection(self):
        validate_selection(self.selection)
        self.selection["retain"] = ["pareto", "pareto"]
        with self.assertRaises(ValueError):
            validate_selection(self.selection)


if __name__ == "__main__":
    unittest.main()

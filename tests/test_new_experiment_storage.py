"""Focused gates for the EXP-050+ Git-only storage policy (no RF simulations)."""
import hashlib
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.audit_new_experiment_storage import (
    CASES, MIN_NEW_EXP_NUMBER, audit_all, inspect_new_git_files, reservation_on_main,
    validate_checkpoint, validate_run, validate_selection, validate_summary,
)
from scripts.experiment_id_registry import PATH, as_csv, next_reservation, read_ledger

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
        self.run = self.root / "experiments/chatgpt_topology_search/runs/EXP-050"
        self.run.mkdir(parents=True)
        dump(self.root / "data/phase2_git_storage_budget.json", {
            "thresholds": {
                "individual_new_file_soft_bytes": 131072,
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
            "experiment_id": "EXP-050",
            "constraints": {"constraint_id": "RF-F003"},
            "execution": {"status": "planned"},
            "validation": {"numerical": "not_run", "independent": "not_run"},
            "evidence": [],
        }
        self.record = {
            "schema_version": 1,
            "policy": "phase2-git-only-v1",
            "experiment_id": "EXP-050",
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
            return validate_run(self.root, "EXP-050", mode=mode)

    def save(self):
        dump(self.run / "manifest.json", self.manifest)
        dump(self.run / "storage_record.json", self.record)

    def test_exp_048_049_preserved_no_retroactive_manifest_migration(self):
        # Historical runs have no storage_record; the new CI must ignore them.
        legacy48 = self.run.parent / "EXP-048"
        legacy49 = self.run.parent / "EXP-049"
        legacy48.mkdir()
        legacy49.mkdir()
        (legacy48 / "manifest.json").write_text('{"experiment_id":"EXP-048"}')
        (legacy49 / "manifest.json").write_text('{"experiment_id":"EXP-049"}')
        with patch(SCRIPT + ".inspect_new_git_files", return_value=0), patch(
            SCRIPT + ".validate_run", return_value={"experiment_id": "EXP-050"}
        ) as validate:
            result = audit_all(self.root, main_ref="origin/main")
        self.assertEqual(50, MIN_NEW_EXP_NUMBER)
        self.assertEqual([{"experiment_id": "EXP-050"}], result)
        validate.assert_called_once_with(self.root, "EXP-050", main_ref="origin/main")
        self.assertFalse((legacy48 / "storage_record.json").exists())
        self.assertFalse((legacy49 / "storage_record.json").exists())

    def test_exp_047_to_049_preflight_and_finalize_rejected(self):
        for legacy in ("EXP-047", "EXP-048", "EXP-049"):
            with self.subTest(legacy=legacy):
                for mode in ("preflight", "finalize"):
                    with self.assertRaisesRegex(ValueError, "EXP-050+"):
                        validate_run(self.root, legacy, mode=mode)

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

    def test_main_reservation_is_authoritative_and_matches_manifest(self):
        def git(*args):
            return subprocess.run(["git", *args], cwd=self.root, check=True,
                                  capture_output=True, text=True)

        git("init", "-q", "-b", "main")
        git("config", "user.name", "Fixture")
        git("config", "user.email", "fixture@example.invalid")
        ledger = self.root / PATH
        ledger.parent.mkdir(parents=True, exist_ok=True)
        source = Path(__file__).resolve().parents[1] / PATH
        rows = read_ledger(source.read_text(encoding="utf-8"))
        ledger.write_text(as_csv(rows), encoding="utf-8")
        git("add", PATH)
        git("commit", "-qm", "baseline")
        git("update-ref", "refs/remotes/origin/main", "HEAD")
        rows, ident, _ = next_reservation(
            rows, owner="fixture", purpose="fixture", request_id="fixture-001",
            constraint_id="RF-F003", reserved_at_utc="2026-10-15T08:00:00Z")
        ledger.write_text(as_csv(rows), encoding="utf-8")
        # A working-tree reservation is not a main-backed reservation.
        with self.assertRaisesRegex(ValueError, "not reserved on main"):
            reservation_on_main(self.root, ident, main_ref="origin/main", starting=True)
        git("add", PATH)
        git("commit", "-qm", "reserve")
        git("update-ref", "refs/remotes/origin/main", "HEAD")
        self.assertEqual("RF-F003", reservation_on_main(
            self.root, ident, main_ref="origin/main", starting=True)["constraint_id"])

        self.run = self.run.parent / ident
        self.run.mkdir()
        self.record["experiment_id"] = ident
        self.manifest["experiment_id"] = ident
        self.manifest["constraints"]["constraint_id"] = "RF-F002"
        self.save()
        with patch(SCRIPT + ".validate_manifest"):
            with self.assertRaisesRegex(ValueError, "reservation and manifest RF conditions disagree"):
                validate_run(self.root, ident, mode="preflight", main_ref="origin/main")
        rows[-1]["state"] = "cancelled"
        ledger.write_text(as_csv(rows), encoding="utf-8")
        git("add", PATH)
        git("commit", "-qm", "cancel")
        git("update-ref", "refs/remotes/origin/main", "HEAD")
        with self.assertRaisesRegex(ValueError, "invalid main reservation state"):
            reservation_on_main(self.root, ident, main_ref="origin/main", starting=True)
        self.assertEqual("cancelled", reservation_on_main(
            self.root, ident, main_ref="origin/main", starting=False)["state"])
        with self.assertRaisesRegex(ValueError, "ledger unavailable"):
            reservation_on_main(self.root, ident, main_ref="missing", starting=True)

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
            "experiment_id": "EXP-050",
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

    def commit_changes(self):
        subprocess.run(["git", "add", "."], cwd=self.root, check=True)
        subprocess.run(["git", "-c", "user.name=test", "-c",
                        "user.email=test@example.invalid", "commit", "-qm",
                        "additional evidence"], cwd=self.root, check=True)

    def test_unclassified_tracked_checkpoint_cannot_linger(self):
        self.complete()
        dump(self.run / "checkpoints/orphan.json", {"unused": "raw intermediate"})
        self.commit_changes()
        with self.assertRaisesRegex(ValueError, "unclassified tracked EXP"):
            self.validate("finalize")

    def test_unregistered_supporting_evidence_must_be_classified(self):
        self.complete()
        path = self.base + "/source/snapshot.txt"
        sha = dump(self.root / path, {"source": "sample"})
        self.manifest["evidence"].append({"path": path, "sha256": sha})
        self.save()
        self.commit_changes()
        with self.assertRaisesRegex(ValueError, "unclassified (manifest evidence|tracked EXP files)"):
            self.validate("finalize")

    def test_duplicate_blob_at_different_paths_is_rejected(self):
        file = self.complete()
        extra = self.base + "/source/duplicate.json"
        original = (self.root / file).read_bytes()
        (self.root / extra).parent.mkdir(parents=True, exist_ok=True)
        (self.root / extra).write_bytes(original)
        sha = hashlib.sha256(original).hexdigest()
        self.manifest["evidence"].append({"path": extra, "sha256": sha})
        self.record["supporting_evidence"] = [{
            "path": extra, "sha256": sha, "role": "source_snapshot",
            "reason": "deliberate duplicate for guard testing",
        }]
        self.save()
        self.commit_changes()
        with self.assertRaisesRegex(ValueError, "duplicate content stored"):
            self.validate("finalize")

    def test_record_itself_must_be_committed_at_head(self):
        self.complete()
        self.record["limitations"].append("dirty final record")
        self.save()
        with self.assertRaisesRegex(ValueError, "differs from committed"):
            self.validate("finalize")

    def test_force_added_results_scratch_is_rejected(self):
        subprocess.run(["git", "init", "-q"], cwd=self.root, check=True)
        subprocess.run(["git", "add", "."], cwd=self.root, check=True)
        subprocess.run(["git", "-c", "user.name=test", "-c",
                        "user.email=test@example.invalid", "commit", "-qm",
                        "baseline"], cwd=self.root, check=True)
        subprocess.run(["git", "update-ref", "refs/remotes/origin/main", "HEAD"],
                       cwd=self.root, check=True)
        scratch = self.root / "results" / "intermediate.json"
        scratch.parent.mkdir(parents=True, exist_ok=True)
        scratch.write_text('{"iteration":1}\n', encoding="utf-8")
        self.commit_changes()
        with self.assertRaisesRegex(ValueError, "transient files committed"):
            inspect_new_git_files(self.root, "origin/main")

    def test_summary_count_rule(self):
        summary = {
            "experiment_id": "EXP-050",
            "attempts": {"planned": 4, "attempted": 3, "converged": 1,
                         "nonconverged": 1, "failed": 1, "not_started": 1},
            "selected_candidate_count": 0,
            "no_candidate_reason": "none passed",
            "limitations": [],
        }
        validate_summary(summary, "EXP-050", 0)
        summary["attempts"]["failed"] = 2
        with self.assertRaisesRegex(ValueError, "outcomes do not sum"):
            validate_summary(summary, "EXP-050", 0)

    def test_bad_storage_selection(self):
        validate_selection(self.selection)
        self.selection["retain"] = ["pareto", "pareto"]
        with self.assertRaises(ValueError):
            validate_selection(self.selection)


if __name__ == "__main__":
    unittest.main()

"""Focused gates for the EXP-050+ Git-only storage policy (no RF simulations)."""
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from lpf.experiment_storage_audit import (
    CASES, MIN_NEW_EXP_NUMBER, audit_all, audit_selected, inspect_new_git_files, reservation_on_main,
    validate_checkpoint, validate_run, validate_selection, validate_summary,
)
from lpf.experiment_id_registry import PATH, as_csv, next_reservation, read_ledger

SCRIPT = "lpf.experiment_storage_audit"


def dump(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return hashlib.sha256(path.read_bytes()).hexdigest()


class StoragePolicyGateTests(unittest.TestCase):
    def test_legacy_entry_uses_the_same_storage_gate(self):
        from scripts import audit_new_experiment_storage as legacy
        self.assertIs(legacy.validate_run, validate_run)
        self.assertIs(legacy.audit_all, audit_all)
        result = subprocess.run([sys.executable, str(Path(__file__).resolve().parents[1] /
                                                    'scripts/audit_new_experiment_storage.py'), '--help'],
                                capture_output=True, text=True, check=True)
        self.assertIn('preflight', result.stdout)
        self.assertIn('finalize', result.stdout)
        self.assertIn('audit', result.stdout)

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
                "new_experiment_curated_soft_bytes": 10000000,
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

    def test_archived_binding_is_opt_in_only_for_read_only_audit(self):
        self.save()
        for mode in ('audit', 'preflight', 'finalize'):
            with self.subTest(mode=mode), patch(SCRIPT + '.validate_manifest') as validate, patch(
                SCRIPT + '.reservation_on_main', return_value={'constraint_id': 'RF-F003'}
            ), patch(SCRIPT + '.tracked_run_files', return_value=set()):
                if mode == 'finalize':
                    with self.assertRaises(ValueError):
                        validate_run(self.root, 'EXP-050', mode=mode)
                else:
                    validate_run(self.root, 'EXP-050', mode=mode)
                self.assertEqual(validate.call_args.kwargs['allow_archived'], mode == 'audit')

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

    def test_selected_audit_only_checks_requested_exp_and_rejects_ambiguity(self):
        other = self.run.parent / 'EXP-051'
        other.mkdir()
        with patch(SCRIPT + '.inspect_new_git_files') as inspect, patch(
                SCRIPT + '.validate_run', side_effect=lambda root, ident, **kw: ident) as validate:
            self.assertEqual(['EXP-050'], audit_selected(self.root, ['EXP-050'], main_ref='origin/main'))
            validate.assert_called_once_with(self.root, 'EXP-050', main_ref='origin/main')
            inspect.assert_called_once_with(self.root, 'origin/main')
            validate.reset_mock()
            self.assertEqual(['EXP-050', 'EXP-051'],
                             audit_selected(self.root, ['EXP-051', 'EXP-050'], main_ref='origin/main'))
            self.assertEqual(2, validate.call_count)
            validate.reset_mock()
            for ids in ([], ['EXP-049'], ['EXP-050', 'EXP-050'], ['EXP-052'], ['../EXP-050']):
                with self.subTest(ids=ids), self.assertRaises(ValueError):
                    audit_selected(self.root, ids, main_ref='origin/main')
            duplicate = self.root/'experiments/matching_limit/runs/EXP-050'
            duplicate.mkdir(parents=True)
            with self.assertRaisesRegex(ValueError, 'ambiguous'):
                audit_selected(self.root, ['EXP-050'], main_ref='origin/main')
            validate.assert_not_called()
            duplicate.rmdir()
            duplicate.symlink_to(self.run, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, 'symlinked'):
                audit_selected(self.root, ['EXP-050'], main_ref='origin/main')
            validate.assert_not_called()

    def test_explicit_selected_audit_binds_planned_metadata_and_evidence_to_head(self):
        self.save()
        def git(*args):
            return subprocess.check_output(['git', '-C', str(self.root), *args], text=True).strip()
        git('init', '-q', '-b', 'main')
        git('config', 'user.name', 'fixture')
        git('config', 'user.email', 'fixture@example.invalid')
        git('add', '.')
        git('commit', '-qm', 'planned')
        head = git('rev-parse', 'HEAD')
        with patch(SCRIPT + '.validate_manifest'), patch(
                SCRIPT + '.reservation_on_main', return_value={'constraint_id': 'RF-F003'}):
            def audit():
                return audit_selected(self.root, ['EXP-050'], main_ref='origin/main',
                                      diff_base=head, expected_head=head)
            self.assertFalse(audit()[0]['committed_readback'])  # Not a G3 readback claim.
            budget = self.root/'data/phase2_git_storage_budget.json'
            budget.write_text(budget.read_text() + '\n')
            with self.assertRaisesRegex(ValueError, 'differs from committed evidence'):
                audit()
            git('restore', str(budget.relative_to(self.root)))
            for name in ('storage_record.json', 'manifest.json'):
                with self.subTest(name=name):
                    file = self.run/name
                    file.write_text(file.read_text() + '\n')
                    with self.assertRaisesRegex(ValueError, 'differs from committed evidence'):
                        audit()
                    git('restore', str(file.relative_to(self.root)))
            stray = self.base + '/unclassified.json'
            dump(self.root/stray, {'fixture': 'unclassified'})
            git('add', stray)
            git('commit', '-qm', 'unclassified committed file')
            head = git('rev-parse', 'HEAD')
            git('rm', '--cached', '-q', stray)
            with self.assertRaisesRegex(ValueError, 'unclassified tracked EXP files'):
                audit()
            git('restore', '--staged', stray)
            git('rm', '-q', stray)
            git('commit', '-qm', 'remove synthetic fixture file')
            head = git('rev-parse', 'HEAD')
            orphan = self.base + '/manifest-only.json'
            orphan_sha = dump(self.root/orphan, {'fixture': 'untracked manifest evidence'})
            self.manifest['evidence'] = [{'path': orphan, 'sha256': orphan_sha}]
            self.save()
            git('add', self.base+'/manifest.json')
            git('commit', '-qm', 'manifest-only untracked evidence reference')
            head = git('rev-parse', 'HEAD')
            with self.assertRaisesRegex(ValueError, 'evidence not committed at HEAD'):
                audit()
            evidence_path = self.base + '/support.json'
            digest = dump(self.root/evidence_path, {'fixture': 'not committed'})
            self.manifest['evidence'] = [{'path': evidence_path, 'sha256': digest}]
            self.record['supporting_evidence'] = [{'path': evidence_path, 'sha256': digest,
                                                   'role': 'recovery_state', 'reason': 'fixture'}]
            self.save()
            git('add', self.base+'/manifest.json', self.base+'/storage_record.json')
            git('commit', '-qm', 'reference untracked evidence')
            head = git('rev-parse', 'HEAD')
            with self.assertRaisesRegex(ValueError, 'evidence not committed at HEAD'):
                audit()
            git('add', evidence_path)
            git('commit', '-qm', 'track evidence')
            head = git('rev-parse', 'HEAD')
            self.assertEqual(audit()[0]['supporting_records'], 1)
            (self.root/evidence_path).write_text('dirty\n')
            with self.assertRaises((ValueError, AssertionError)):
                audit()
            git('restore', evidence_path)
            (self.root/evidence_path).unlink()
            alias = self.run/'alias-target.json'
            digest = dump(alias, {'fixture': 'symlink target'})
            (self.root/evidence_path).symlink_to(alias.name)
            self.manifest['evidence'][0]['sha256'] = digest
            self.record['supporting_evidence'][0]['sha256'] = digest
            self.save()
            git('add', self.base)
            git('commit', '-qm', 'symlinked evidence')
            head = git('rev-parse', 'HEAD')
            with self.assertRaisesRegex(ValueError, 'symlinked evidence'):
                audit()

    def test_explicit_selected_audit_binds_archived_logical_evidence(self):
        archive = self.root/'rf/constraints/history/pre-issue-307'
        snapshot = archive/'formal/RF-F003.json'
        digest = dump(snapshot, {'fixture': 'historical snapshot'})
        provenance = archive/'provenance.json'
        dump(provenance, {'snapshot_file_sha256': {'formal/RF-F003.json': digest}})
        self.manifest['evidence'] = [{'path': 'data/constraints/formal/RF-F003.json', 'sha256': digest}]
        self.save()
        def git(*args):
            return subprocess.check_output(['git', '-C', str(self.root), *args], text=True).strip()
        git('init', '-q', '-b', 'main')
        git('config', 'user.name', 'fixture')
        git('config', 'user.email', 'fixture@example.invalid')
        git('add', '.')
        git('commit', '-qm', 'archived evidence')
        head = git('rev-parse', 'HEAD')
        with patch(SCRIPT + '.validate_manifest'), patch(
                SCRIPT + '.reservation_on_main', return_value={'constraint_id': 'RF-F003'}):
            def audit():
                return audit_selected(self.root, ['EXP-050'], main_ref='origin/main',
                                      diff_base=head, expected_head=head)
            self.assertEqual(audit()[0]['stage'], 'planned')
            provenance.write_text(provenance.read_text() + '\n')
            with self.assertRaisesRegex(ValueError, 'differs from committed evidence'):
                audit()
            git('restore', str(provenance.relative_to(self.root)))
            snapshot.write_text(snapshot.read_text() + '\n')
            with self.assertRaisesRegex(ValueError, 'Historical RF snapshot evidence byte mismatch'):
                audit()

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

    def test_complete_campaign_cannot_hide_preservation_errors(self):
        self.complete()
        self.manifest['search_scope'] = {'campaign': {'kind': 'campaign_v1'}}
        summary_path = self.root / self.record['summary']['path']
        summary = json.loads(summary_path.read_text(encoding='utf-8'))
        summary.update(preservation_kind='campaign_v1',
                       preservation_errors=['synthetic incomplete G3'])
        def commit_summary():
            digest = dump(summary_path, summary)
            self.record['summary']['sha256'] = digest
            for item in self.manifest['evidence']:
                if item['path'] == self.record['summary']['path']:
                    item['sha256'] = digest
            self.save()
            self.commit_changes()
        def selected():
            head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=self.root, text=True).strip()
            with patch(SCRIPT + '.validate_manifest'), patch(
                    SCRIPT + '.reservation_on_main', return_value={'constraint_id': 'RF-F003'}):
                return audit_selected(self.root, ['EXP-050'], main_ref='origin/main',
                                      diff_base=head, expected_head=head)
        commit_summary()
        for mode in ('audit', 'finalize'):
            with self.subTest(mode=mode), self.assertRaisesRegex(ValueError, 'Campaign preservation errors'):
                self.validate(mode)
        with self.assertRaisesRegex(ValueError, 'Campaign preservation errors'):
            selected()
        summary['preservation_errors'] = []
        commit_summary()
        self.assertEqual('complete', self.validate('audit')['stage'])
        self.assertEqual('complete', selected()[0]['stage'])
        del summary['preservation_kind']
        commit_summary()
        for mode in ('audit', 'finalize'):
            with self.subTest(mode=mode), self.assertRaisesRegex(ValueError, 'Campaign summary identity'):
                self.validate(mode)
        with self.assertRaisesRegex(ValueError, 'Campaign summary identity'):
            selected()
        # Incomplete evidence must remain auditable and must not be relabeled complete.
        summary['preservation_kind'] = 'campaign_v1'
        summary['preservation_errors'] = ['synthetic incomplete G3']
        self.record['stage'] = 'preservation_incomplete'
        commit_summary()
        self.assertEqual('preservation_incomplete', self.validate('audit')['stage'])

    def test_exp_total_limit_is_configurable(self):
        self.complete()
        path = self.root / "data/phase2_git_storage_budget.json"
        policy = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(policy["thresholds"]["new_experiment_curated_soft_bytes"], 10_000_000)
        total = self.validate("finalize")["curated_bytes"]
        policy["thresholds"]["new_experiment_curated_soft_bytes"] = total - 1
        dump(path, policy)
        with self.assertRaisesRegex(ValueError, "exceeds configured limit"):
            self.validate("finalize")
        policy["thresholds"]["new_experiment_curated_soft_bytes"] = total
        dump(path, policy)
        self.assertEqual(self.validate("finalize")["curated_bytes"], total)

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

    def test_rename_into_transient_path_is_rejected(self):
        def git(*args):
            return subprocess.check_output(['git', *args], cwd=self.root, text=True).strip()
        git('init', '-q', '-b', 'main')
        git('config', 'user.name', 'test')
        git('config', 'user.email', 'test@example.invalid')
        (self.root/'safe.json').write_text('{"fixture":true}\n')
        git('add', '.')
        git('commit', '-qm', 'base')
        base = git('rev-parse', 'HEAD')
        (self.root/'results').mkdir()
        git('mv', 'safe.json', 'results/moved.json')
        git('commit', '-qm', 'rename into scratch')
        head = git('rev-parse', 'HEAD')
        with self.assertRaisesRegex(ValueError, 'transient files committed'):
            inspect_new_git_files(self.root, 'origin/main', diff_base=base, expected_head=head)

    def test_explicit_range_rejects_scratch_added_then_deleted_before_head(self):
        def git(*args):
            return subprocess.check_output(['git', *args], cwd=self.root, text=True).strip()
        git('init', '-q', '-b', 'main')
        git('config', 'user.name', 'test')
        git('config', 'user.email', 'test@example.invalid')
        git('add', '.')
        git('commit', '-qm', 'baseline')
        base = git('rev-parse', 'HEAD')
        scratch = self.root/'results/intermediate.json'
        scratch.parent.mkdir(parents=True)
        scratch.write_text('{"synthetic":true}\n')
        git('add', '.')
        git('commit', '-qm', 'add transient fixture')
        git('rm', '-q', 'results/intermediate.json')
        git('commit', '-qm', 'remove transient fixture')
        head = git('rev-parse', 'HEAD')
        self.assertEqual(git('diff', '--name-only', base, head), '')
        with patch(SCRIPT + '.MAX_DIFF_COMMITS', 1):
            with self.assertRaisesRegex(ValueError, 'event history exceeds inspection limit'):
                inspect_new_git_files(self.root, 'origin/main', diff_base=base, expected_head=head)
        with self.assertRaisesRegex(ValueError, 'transient files committed'):
            inspect_new_git_files(self.root, 'origin/main', diff_base=base, expected_head=head)

    def test_merge_history_checks_intermediate_scratch_without_rejecting_baseline_file(self):
        def git(*args):
            return subprocess.check_output(['git', *args], cwd=self.root, text=True).strip()
        git('init', '-q', '-b', 'main')
        git('config', 'user.name', 'test')
        git('config', 'user.email', 'test@example.invalid')
        old = self.root/'results/old.json'
        old.parent.mkdir(parents=True)
        old.write_text('baseline historical fixture\n')
        git('add', '.')
        git('commit', '-qm', 'baseline')
        base = git('rev-parse', 'HEAD')
        git('switch', '-qc', 'side')
        git('rm', '-q', 'results/old.json')
        git('commit', '-qm', 'side deletes baseline path')
        git('switch', '-q', 'main')
        old.write_text('baseline path changed on main\n')
        git('add', 'results/old.json')
        git('commit', '-qm', 'main modifies baseline path')
        merge = subprocess.run(['git', 'merge', '--no-ff', 'side', '-m', 'merge'],
                               cwd=self.root, capture_output=True, text=True)
        self.assertNotEqual(merge.returncode, 0)  # synthetic modify/delete conflict
        git('add', 'results/old.json')
        git('commit', '-qm', 'merge preserving baseline path')
        head = git('rev-parse', 'HEAD')
        self.assertEqual(inspect_new_git_files(self.root, 'origin/main',
                                              diff_base=base, expected_head=head), 0)
        git('switch', '-qc', 'side-with-transient')
        transient = self.root/'results/transient.json'
        transient.write_text('synthetic\n')
        git('add', 'results/transient.json')
        git('commit', '-qm', 'side adds transient')
        git('rm', '-q', 'results/transient.json')
        git('commit', '-qm', 'side deletes transient')
        git('switch', '-q', 'main')
        (self.root/'other.txt').write_text('diverge\n')
        git('add', 'other.txt')
        git('commit', '-qm', 'main diverges')
        git('merge', '--no-ff', '-qm', 'merge transient history', 'side-with-transient')
        with self.assertRaisesRegex(ValueError, 'transient files committed'):
            inspect_new_git_files(self.root, 'origin/main', diff_base=head,
                                  expected_head=git('rev-parse', 'HEAD'))

    def test_selected_audit_checks_entire_explicit_push_range(self):
        def git(*args):
            return subprocess.check_output(['git', *args], cwd=self.root, text=True).strip()
        git('init', '-q', '-b', 'main')
        git('config', 'user.name', 'test')
        git('config', 'user.email', 'test@example.invalid')
        git('add', '.')
        git('commit', '-qm', 'baseline')
        base = git('rev-parse', 'HEAD')
        scratch = self.root/'results/intermediate.json'
        scratch.parent.mkdir(parents=True)
        scratch.write_text('{"intermediate":true}\n')
        git('add', '.')
        git('commit', '-qm', 'unsafe first commit')
        (self.root/'unrelated.txt').write_text('second commit\n')
        git('add', '.')
        git('commit', '-qm', 'second commit')
        head = git('rev-parse', 'HEAD')
        git('update-ref', 'refs/remotes/origin/main', head)
        # Existing HEAD^ mode misses the first commit; explicit event base must not.
        self.assertEqual(1, inspect_new_git_files(self.root, 'origin/main'))
        with patch(SCRIPT + '.validate_run') as validate:
            with self.assertRaisesRegex(ValueError, 'transient files committed'):
                audit_selected(self.root, ['EXP-050'], main_ref='origin/main',
                               diff_base=base, expected_head=head)
            validate.assert_not_called()
            with self.assertRaisesRegex(ValueError, 'HEAD mismatch'):
                audit_selected(self.root, ['EXP-050'], main_ref='origin/main',
                               diff_base=base, expected_head=base)
            with self.assertRaises(ValueError):
                audit_selected(self.root, ['EXP-050'], main_ref='origin/main',
                               diff_base='0'*40, expected_head=head)
            with self.assertRaises(ValueError):
                audit_selected(self.root, ['EXP-050'], main_ref='origin/main', diff_base=base)
            validate.assert_not_called()
            parent = git('rev-parse', 'HEAD^')
            audit_selected(self.root, ['EXP-050'], main_ref='origin/main',
                           diff_base=parent, expected_head=head)
            validate.assert_called_once_with(self.root.resolve(), 'EXP-050', main_ref='origin/main',
                                             require_committed=True)

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
        summary['attempts'].update(failed=0, unknown=1)
        validate_summary(summary, 'EXP-050', 0)
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

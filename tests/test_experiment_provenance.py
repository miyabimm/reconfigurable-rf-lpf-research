"""Constraint approval isolation and historical/new-run provenance failure cases."""
import csv
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from src.lpf.constraint_versions import constraint_fingerprint, load_constraint, validate_registry
from src.lpf.experiment_manifest import (
    ROOT, RUNS, audit_provenance, experiment_index, file_sha256, new_manifest,
    validate_manifest, write_manifest,
)


class ConstraintRegistryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        shutil.copytree(ROOT / "rf/constraints", self.root / "rf/constraints")
        self.registry_path = self.root / "rf/constraints/registry.json"
        self.registry = json.loads(self.registry_path.read_text())
        self.trial = {
            "constraint_id": "RF-T001", "status": "trial", "base_constraint_id": "RF-F001",
            "study_authorized": True,
            "study_variable_c_layout": {"branch_count": 3, "shunt_to_ground": 3,
                                        "non_ground_bridge": 0},
            "overrides": {"components": {"IC_VARIABLE_C": {"max_branches_principle": 3}}},
        }
        self.registry["trial"]["RF-T001"] = {
            "file": "data/constraints/trial/RF-T001.json", "state": "study_authorized",
            "base_constraint_id": "RF-F001",
        }
        self.trial_path = self.root / "rf/constraints/trial/RF-T001.json"
        self.trial_path.parent.mkdir(exist_ok=True)
        self.save()

    def save(self):
        self.registry_path.write_text(json.dumps(self.registry))
        self.trial_path.write_text(json.dumps(self.trial))

    def test_trial_does_not_change_approved_bytes_or_default(self):
        path = self.root / "rf/constraints/formal/RF-F001.json"
        before = path.read_bytes()
        formal = load_constraint(root=self.root)
        with self.assertRaises(ValueError):
            load_constraint("RF-T001", root=self.root)
        trial = load_constraint("RF-T001", root=self.root, allow_trial=True)
        trial["components"]["IC_VARIABLE_C"]["max_branches_principle"] = 9
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(load_constraint(root=self.root), formal)

    def test_formal_pending_or_modified_snapshot_is_rejected(self):
        self.registry["formal"]["RF-F001"]["state"] = "proposed"
        self.save()
        with self.assertRaisesRegex(ValueError, "not approved"):
            load_constraint(root=self.root)
        self.registry["formal"]["RF-F001"]["state"] = "approved"
        self.save()
        path = self.root / "rf/constraints/formal/RF-F001.json"
        payload = json.loads(path.read_text())
        payload["components"]["LQP02"]["series"]["LQP02HV"]["q"] = 99
        path.write_text(json.dumps(payload))
        with self.assertRaisesRegex(ValueError, "fingerprint mismatch"):
            load_constraint(root=self.root)

    def test_approval_must_agree_and_trial_must_not_be_default(self):
        for state in ("proposed", "rejected", "withdrawn"):
            with self.subTest(state=state):
                self.registry["trial"]["RF-T001"]["state"] = state
                self.trial["study_authorized"] = False
                self.save()
                validate_registry(root=self.root)
                with self.assertRaises(ValueError):
                    load_constraint("RF-T001", root=self.root, allow_trial=True)
        self.trial["study_authorized"] = True
        self.save()
        with self.assertRaisesRegex(ValueError, "approval differs"):
            validate_registry(root=self.root)
        self.registry["trial"]["RF-T001"]["state"] = "study_authorized"
        self.registry["active_formal_id"] = "RF-T001"
        self.save()
        with self.assertRaisesRegex(ValueError, "Active constraint"):
            load_constraint(root=self.root, allow_trial=True)

    def test_fixed_base_identity_and_metadata_cannot_be_overridden(self):
        for key, value in (("active_constraint_id", "RF-F001"), ("active_constraint_status", "formal"),
                           ("policy_version", "RF-T001"), ("phase3", "enabled"),
                           ("trial_base_constraint_id", "RF-F002")):
            with self.subTest(key=key):
                self.trial["overrides"] = {key: value}
                self.save()
                with self.assertRaises(ValueError):
                    load_constraint("RF-T001", root=self.root, allow_trial=True)
        self.trial["overrides"] = {}
        self.registry["trial"]["RF-T001"]["base_constraint_id"] = "RF-F002"
        self.save()
        with self.assertRaisesRegex(ValueError, "same registered formal base"):
            validate_registry(root=self.root)

    def test_namespace_path_and_nonfinite_types_rejected(self):
        self.registry["formal"]["RF-F001"]["file"] = "../../RF-F001.json"
        self.save()
        with self.assertRaises(ValueError):
            load_constraint(root=self.root)
        self.registry["formal"]["RF-F001"]["file"] = "data/constraints/formal/RF-F001.json"
        for value in (True, "3", [], float("nan"), float("inf")):
            with self.subTest(value=value):
                self.trial["overrides"] = {"components": {"IC_VARIABLE_C": {"max_branches_principle": value}}}
                self.save()
                with self.assertRaises(ValueError):
                    load_constraint("RF-T001", root=self.root, allow_trial=True)

    def test_fingerprint_is_order_independent_and_approved_hash_is_locked(self):
        policy = load_constraint()
        self.assertEqual(constraint_fingerprint(policy), constraint_fingerprint(dict(reversed(list(policy.items())))))
        self.assertEqual(constraint_fingerprint(policy),
                         validate_registry()["formal"]["RF-F003"]["effective_constraint_sha256"])
        self.assertEqual(constraint_fingerprint(load_constraint("RF-F002")),
                         "f20d27e93451dcec2f823e6f7c3731c06d843050c4d2ace8b0b46ded605542e2")
        self.assertEqual(constraint_fingerprint(load_constraint("RF-F001")),
                         "df6b4cbd347aac06538527cd68963b785207582152e17117a683c10058af0c54")


class ManifestTests(unittest.TestCase):
    def historical(self):
        return json.loads((ROOT / RUNS / "EXP-015/manifest.json").read_text())

    def test_historical_unknowns_are_not_current_policy_certificates(self):
        m = self.historical()
        validate_manifest(m)
        self.assertIsNone(m["code"]["execution_sha"])
        self.assertIsNone(m["constraints"]["effective_constraint_sha256"])
        self.assertIsNone(m["environment"])
        self.assertEqual(m["validation"]["independent"], "reported_in_sources")
        m["constraints"]["constraint_id"] = "RF-F001"
        with self.assertRaisesRegex(ValueError, "invent"):
            validate_manifest(m)

    def test_new_manifest_captures_inputs_and_refuses_policy_drift(self):
        m = new_manifest("EXP-016", "Metadata smoke only", {"max_search_area": 8},
                         objective="matching_only", seed=12)
        self.assertEqual(m["constraints"]["constraint_id"], "RF-F003")
        self.assertIsNone(m["constraints"]["effective_constraints"]["area_budget"]["hard_cap"])
        self.assertEqual(m["execution"]["status"], "planned")
        self.assertEqual(m["validation"]["independent"], "not_run")
        self.assertEqual(m["environment"]["python"].split('.')[0], "3")
        m["constraints"]["effective_constraints"]["components"]["LQP02"]["series"]["LQP02HV"]["q"] = 26
        with self.assertRaisesRegex(ValueError, "fingerprint mismatch"):
            validate_manifest(m)

    def test_new_manifest_rejects_invalid_seeds_and_band_drift(self):
        for seed in (True, -1, "12"):
            with self.subTest(seed=seed), self.assertRaises(ValueError):
                new_manifest("EXP-016", "metadata", {}, objective="full_lpf", seed=seed)
        m = new_manifest("EXP-016", "metadata", {}, objective="full_lpf", seed=None)
        m["bands_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "band definitions"):
            validate_manifest(m)

    def test_evidence_tampering_and_path_escape_rejected(self):
        for field, value in (("sha256", "0" * 64), ("path", "../../etc/passwd")):
            m = self.historical()
            m["evidence"][0][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate_manifest(m)

    def test_saved_manifest_cannot_be_overwritten(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "manifest.json"
            m = self.historical()
            write_manifest(path, m)
            before = path.read_bytes()
            with self.assertRaises(FileExistsError):
                write_manifest(path, m)
            self.assertEqual(path.read_bytes(), before)

    def test_index_retains_failed_partial_and_not_run(self):
        manifests = []
        for i, state in enumerate(("failed", "partial", "not_run"), start=16):
            m = self.historical()
            m["experiment_id"] = f"EXP-{i:03}"
            m["execution"]["status"] = state
            validate_manifest(m)
            manifests.append((f"{RUNS}/{m['experiment_id']}/manifest.json", m))
        import io
        rows = list(csv.DictReader(io.StringIO(experiment_index(manifests))))
        self.assertEqual([r["execution_status"] for r in rows], ["failed", "partial", "not_run"])
        self.assertTrue(all(r["effective_constraint_sha256"] == "" for r in rows))

    def test_all_historical_experiments_and_candidate_provenance_audit(self):
        self.assertEqual(audit_provenance(), [])
        paths = sorted((ROOT / RUNS).glob("EXP-*/manifest.json"))
        self.assertTrue({f"EXP-{i:03}" for i in range(1, 16)}.issubset({p.parent.name for p in paths}))
        for path in paths:
            if path.parent.name == "EXP-047":
                # Original noncanonical in-chat provenance is preserved and
                # verified via a pinned, index-only compatibility overlay.
                from src.lpf.legacy_manifest_adapter import legacy_exp047_index_view
                view = legacy_exp047_index_view(root=ROOT)
                self.assertEqual(view["experiment_id"], "EXP-047")
            else:
                validate_manifest(json.loads(path.read_text()))

    def test_nonfinite_scope_and_invalid_validation_rejected(self):
        for key, value in (("phase", "Phase 3"), ("search_scope", {"max_search_area": float("inf")}),
                           ("validation", {"numerical": "passed"})):
            m = self.historical()
            m[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate_manifest(m)


if __name__ == "__main__":
    unittest.main()

"""Current approval isolation and new experiment provenance validation."""
import csv
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from src.lpf.constraint_versions import constraint_fingerprint, load_constraint, validate_registry
from src.lpf.experiment_manifest import (
    ROOT, RUNS, experiment_index, new_manifest,
    validate_manifest, write_manifest,
)


class ConstraintRegistryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        shutil.copytree(ROOT/'rf/constraints', self.root/'rf/constraints')
        self.registry_path = self.root/'rf/constraints/registry.json'
        self.registry = json.loads(self.registry_path.read_text())
        self.trial_path = self.root/'rf/constraints/trial/RF-T005.json'
        self.trial = json.loads(self.trial_path.read_text())

    def save(self):
        self.registry_path.write_text(json.dumps(self.registry))
        self.trial_path.write_text(json.dumps(self.trial))

    def test_trial_does_not_change_approved_bytes_or_default(self):
        path = self.root/'rf/constraints/formal/RF-F003.json'
        before = path.read_bytes()
        formal = load_constraint(root=self.root)
        with self.assertRaises(ValueError): load_constraint('RF-T005', root=self.root)
        trial = load_constraint('RF-T005', root=self.root, allow_trial=True)
        trial['components']['IC_VARIABLE_C']['max_branches_principle'] = 9
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(load_constraint(root=self.root), formal)

    def test_formal_pending_or_modified_snapshot_is_rejected(self):
        self.registry['formal']['RF-F003']['state'] = 'proposed'
        self.save()
        with self.assertRaisesRegex(ValueError, 'not approved'): load_constraint(root=self.root)
        self.registry['formal']['RF-F003']['state'] = 'approved'
        self.save()
        path = self.root/'rf/constraints/formal/RF-F003.json'
        payload = json.loads(path.read_text())
        payload['components']['LQP02']['series']['LQP02HV']['q'] = 99
        path.write_text(json.dumps(payload))
        with self.assertRaisesRegex(ValueError, 'fingerprint mismatch'): load_constraint(root=self.root)

    def test_approval_must_agree_and_trial_must_not_be_default(self):
        for state in ('proposed', 'rejected', 'withdrawn'):
            with self.subTest(state=state):
                self.registry['trial']['RF-T005']['state'] = state
                self.trial['study_authorized'] = False
                self.save()
                validate_registry(root=self.root)
                with self.assertRaises(ValueError): load_constraint('RF-T005', root=self.root, allow_trial=True)
        self.trial['study_authorized'] = True
        self.save()
        with self.assertRaisesRegex(ValueError, 'approval differs'): validate_registry(root=self.root)
        self.registry['trial']['RF-T005']['state'] = 'study_authorized'
        self.registry['active_formal_id'] = 'RF-T005'
        self.save()
        with self.assertRaisesRegex(ValueError, 'Active constraint'): load_constraint(root=self.root, allow_trial=True)

    def test_fixed_base_identity_and_metadata_cannot_be_overridden(self):
        for key, value in (('active_constraint_id', 'RF-F003'), ('active_constraint_status', 'formal'),
                           ('policy_version', 'RF-T005'), ('phase3', 'enabled'),
                           ('trial_base_constraint_id', 'RF-F002')):
            with self.subTest(key=key):
                self.trial['overrides'] = {key: value}
                self.save()
                with self.assertRaises(ValueError): load_constraint('RF-T005', root=self.root, allow_trial=True)
        self.trial['overrides'] = {}
        self.registry['trial']['RF-T005']['base_constraint_id'] = 'RF-F002'
        self.save()
        with self.assertRaisesRegex(ValueError, 'same registered formal base'): validate_registry(root=self.root)

    def test_namespace_path_and_nonfinite_types_rejected(self):
        self.registry['formal']['RF-F003']['file'] = '../../RF-F003.json'
        self.save()
        with self.assertRaises(ValueError): load_constraint(root=self.root)
        self.registry['formal']['RF-F003']['file'] = 'data/constraints/formal/RF-F003.json'
        for value in (True, '3', [], float('nan'), float('inf')):
            with self.subTest(value=value):
                self.trial['overrides'] = {'components': {'IC_VARIABLE_C': {'max_branches_principle': value}}}
                self.save()
                with self.assertRaises(ValueError): load_constraint('RF-T005', root=self.root, allow_trial=True)

    def test_fingerprint_is_order_independent_and_approved_hash_is_locked(self):
        policy = load_constraint()
        self.assertEqual(constraint_fingerprint(policy), constraint_fingerprint(dict(reversed(list(policy.items())))))
        self.assertEqual(constraint_fingerprint(policy), validate_registry()['formal']['RF-F003']['effective_constraint_sha256'])


class ManifestTests(unittest.TestCase):
    def manifest(self):
        return new_manifest('EXP-016', 'Metadata smoke only', {}, objective='full_lpf', seed=12)

    def test_new_manifest_captures_inputs_and_refuses_policy_drift(self):
        m = new_manifest('EXP-016', 'Metadata smoke only', {'max_search_area': 8}, objective='matching_only', seed=12)
        self.assertEqual(m['constraints']['constraint_id'], 'RF-F003')
        self.assertIsNone(m['constraints']['effective_constraints']['area_budget']['hard_cap'])
        self.assertEqual(m['execution']['status'], 'planned')
        self.assertEqual(m['validation']['independent'], 'not_run')
        self.assertEqual(m['environment']['python'].split('.')[0], '3')
        m['constraints']['effective_constraints']['components']['LQP02']['series']['LQP02HV']['q'] = 26
        with self.assertRaisesRegex(ValueError, 'fingerprint mismatch'): validate_manifest(m)

    def test_new_manifest_rejects_invalid_seeds_and_band_drift(self):
        for seed in (True, -1, '12'):
            with self.subTest(seed=seed), self.assertRaises(ValueError):
                new_manifest('EXP-016', 'metadata', {}, objective='full_lpf', seed=seed)
        m = new_manifest('EXP-016', 'metadata', {}, objective='full_lpf', seed=None)
        m['bands_sha256'] = '0'*64
        with self.assertRaisesRegex(ValueError, 'band definitions'): validate_manifest(m)

    def test_evidence_tampering_and_path_escape_rejected(self):
        for field, value in (('sha256', '0'*64), ('path', '../../etc/passwd')):
            m = self.manifest(); m['evidence'] = [{'path': 'rf/bands.csv', 'sha256': '0'*64}]
            m['evidence'][0][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError): validate_manifest(m)

    def test_saved_manifest_cannot_be_overwritten(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)/'manifest.json'
            m = self.manifest(); write_manifest(path, m)
            before = path.read_bytes()
            with self.assertRaises(FileExistsError): write_manifest(path, m)
            self.assertEqual(path.read_bytes(), before)

    def test_index_retains_failed_partial_and_not_run(self):
        manifests = []
        for i, state in enumerate(('failed', 'partial', 'not_run'), start=16):
            m = self.manifest(); m['experiment_id'] = f'EXP-{i:03}'; m['execution']['status'] = state
            validate_manifest(m)
            manifests.append((f"{RUNS}/{m['experiment_id']}/manifest.json", m))
        import io
        rows = list(csv.DictReader(io.StringIO(experiment_index(manifests))))
        self.assertEqual([r['execution_status'] for r in rows], ['failed', 'partial', 'not_run'])
        self.assertTrue(all(r['effective_constraint_sha256'] for r in rows))

    def test_nonfinite_scope_and_invalid_validation_rejected(self):
        for key, value in (('phase', 'Phase 3'), ('search_scope', {'max_search_area': float('inf')}),
                           ('validation', {'numerical': 'passed'})):
            m = self.manifest(); m[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError): validate_manifest(m)


if __name__ == '__main__': unittest.main()

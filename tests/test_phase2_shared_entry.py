"""Shared entry tests: isolated mock diagnostics and temporary Git evidence only."""
import hashlib
import json
import shutil
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from lpf.checkpoint_io import canonical_config_hash
from lpf.experiment_manifest import new_manifest
from scripts.experiment_id_registry import PATH, as_csv, next_reservation, read_ledger
from scripts.run_phase2_shared import exp_preflight, manifest_preview, storage_audit


class SharedEntryTests(unittest.TestCase):
    def test_explicit_mock_entry(self):
        script = str(ROOT / 'scripts/run_phase2_shared.py')
        env = {**os.environ, 'OPENBLAS_NUM_THREADS': '1'}
        missing = subprocess.run([sys.executable, script, 'synthetic', '--policy', 'RF-T005',
                                  '--inductors', '3'], env=env, capture_output=True)
        self.assertNotEqual(missing.returncode, 0)
        for policy in ('RF-T005', 'RF-T007', 'RF-T008'):
            for n in (3, 4):
                cmd = [sys.executable, script, 'synthetic', '--mock', '--policy', policy, '--inductors', str(n)]
                result = json.loads(subprocess.check_output(cmd, env=env))
                self.assertEqual(result['mode'], 'synthetic_mock')
                self.assertEqual(result['policy_id'], policy)
                self.assertTrue(result['candidate_promotion_blocked'])
                self.assertFalse(result['rf_compliance_certified'])
                self.assertEqual(result['run_summary']['attempts'], {
                    'planned': 1, 'attempted': 1, 'converged': 1,
                    'nonconverged': 0, 'failed': 0, 'not_started': 0})
                self.assertEqual(len(result['pareto']['candidates']), 1)
                self.assertEqual(result['run_summary']['experiment_id'], None)
                self.assertEqual(result['git_readback'], 'not_run')
                candidate = result['result']['completed'][0]
                self.assertEqual(candidate['numerical']['state'], 'converged')
                self.assertEqual(candidate['validation']['independent_mna'], 'not_run')
                again = json.loads(subprocess.check_output(cmd, env=env))
                self.assertEqual(result['plan_fingerprint'], again['plan_fingerprint'])

    def test_preview_is_only_in_memory(self):
        result = manifest_preview(ROOT, 'EXP-999', 'fixture only', {}, policy_id='RF-T005', seed=1, allow_trial=True)
        self.assertEqual(result['manifest']['execution']['status'], 'planned')
        self.assertFalse(result['execution_allowed'])
        with self.assertRaises(ValueError):
            manifest_preview(ROOT, 'EXP-999', 'fixture', {}, policy_id='RF-F003', seed=1, allow_trial=True)

    def test_temporary_full_checkout_preflight_and_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo, remote = Path(tmp) / 'repo', Path(tmp) / 'remote.git'
            def git(*args, cwd=repo):
                return subprocess.check_output(['git', *map(str, args)], cwd=cwd, stderr=subprocess.PIPE, text=True).strip()
            repo.mkdir()
            git('init', '-q', '-b', 'main')
            git('config', 'user.name', 'Fixture')
            git('config', 'user.email', 'fixture@example.invalid')
            git('init', '--bare', '-q', remote, cwd=tmp)
            git('remote', 'add', 'origin', remote)
            shutil.copytree(ROOT / 'rf', repo / 'rf')
            (repo / 'experiments').mkdir()
            (repo / 'experiments/README').write_text('isolated fixture')
            ledger = repo / PATH
            ledger.parent.mkdir(parents=True, exist_ok=True)
            rows = [{'experiment_id': f'EXP-{n:03}',
                     'state': 'legacy_gap_retired' if n in (18, 19) else 'legacy_recorded',
                     'owner': '', 'request_id': '', 'purpose': '', 'constraint_id': '',
                     'reserved_at_utc': '', 'origin': ''} for n in range(1, 50)]
            rows, ident, _ = next_reservation(rows, owner='fixture', purpose='fixture only',
                request_id='fixture-194', constraint_id='RF-T005', reserved_at_utc='2026-10-28T00:00:00Z')
            ledger.write_text(as_csv(rows))
            (repo / 'data/phase2_git_storage_budget.json').write_text(json.dumps({'thresholds': {
                'individual_new_file_soft_bytes': 131072, 'individual_new_file_hard_bytes': 1048576,
                'new_experiment_curated_soft_bytes': 524288}}))
            git('add', '.')
            git('commit', '-qm', 'fixture reservation')
            git('push', '-q', '-u', 'origin', 'main')
            source = git('rev-parse', 'HEAD')
            input_source = {'fixture': 'synthetic-only'}
            input_sha = canonical_config_hash(input_source)
            scope = {'input_source': input_source, 'input_source_sha256': input_sha}
            manifest = new_manifest(ident, 'fixture only', scope, objective='full_lpf', seed=1,
                                    root=repo, constraint_id='RF-T005', allow_trial=True)
            run = repo / 'experiments/chatgpt_topology_search/runs' / ident
            run.mkdir(parents=True)
            record = {'schema_version': 1, 'policy': 'phase2-git-only-v1', 'experiment_id': ident,
                      'phase': 'Phase 2', 'stage': 'planned',
                      'selection': {'top_k': 1, 'retain': ['best'], 'rule': 'best and representative failure',
                                    'estimated_curated_bytes': 1000},
                      'summary': None, 'checkpoints': [], 'validation_overlays': [],
                      'git_readback': 'not_run', 'size_exception': None, 'limitations': []}
            (run / 'manifest.json').write_text(json.dumps(manifest))
            (run / 'storage_record.json').write_text(json.dumps(record))
            git('add', str(run.relative_to(repo)))
            git('commit', '-qm', 'fixture planned evidence')
            git('push', '-q', 'origin', 'main')
            args = dict(owner='fixture', request_id='fixture-194', policy_id='RF-T005',
                        policy_sha256=manifest['constraints']['effective_constraint_sha256'],
                        source_sha=source, bands_sha256=manifest['bands_sha256'],
                        input_sha256=input_sha, allow_trial=True)
            result = exp_preflight(repo, ident, **args)
            self.assertEqual(result['owner_approval'], 'not_verified')
            self.assertFalse(result['execution_allowed'])
            for change in ({'owner': 'wrong'}, {'request_id': 'wrong'}, {'policy_id': 'RF-T007'},
                           {'policy_id': 'RF-F003'}, {'allow_trial': False},
                           {'policy_sha256': '0' * 64}, {'bands_sha256': '0' * 64},
                           {'input_sha256': '0' * 64}, {'source_sha': '0' * 40}):
                with self.subTest(change=change), self.assertRaises((ValueError, subprocess.CalledProcessError)):
                    exp_preflight(repo, ident, **(args | change))
            with self.assertRaises(ValueError):
                exp_preflight(repo, 'EXP-999', **args)
            with self.assertRaises(ValueError):
                storage_audit(repo, 'finalize', ident)
            git('config', 'core.sparseCheckout', 'true')
            with self.assertRaisesRegex(ValueError, 'sparse'):
                exp_preflight(repo, ident, **args)
            git('config', 'core.sparseCheckout', 'false')
            git('update-ref', 'refs/remotes/origin/main', source)
            with self.assertRaisesRegex(ValueError, 'stale'):
                exp_preflight(repo, ident, **args)
            git('fetch', '-q', 'origin', 'main')
            # Complete preservation in this throw-away fixture, then verify actual HEAD readback.
            summary_path = run / 'run_summary.json'
            summary = {'experiment_id': ident, 'attempts': {'planned': 1, 'attempted': 1,
                'converged': 0, 'nonconverged': 0, 'failed': 1, 'not_started': 0},
                'selected_candidate_count': 0, 'no_candidate_reason': 'fixture failed', 'limitations': ['fixture']}
            summary_path.write_text(json.dumps(summary))
            summary_ref = {'path': str(summary_path.relative_to(repo)),
                           'sha256': hashlib.sha256(summary_path.read_bytes()).hexdigest()}
            manifest['execution']['status'] = 'failed'
            manifest['evidence'] = [summary_ref]
            record.update(stage='complete', summary=summary_ref, git_readback='passed')
            (run / 'manifest.json').write_text(json.dumps(manifest))
            (run / 'storage_record.json').write_text(json.dumps(record))
            git('add', str(run.relative_to(repo)))
            git('commit', '-qm', 'fixture preserved')
            git('push', '-q', 'origin', 'main')
            preserved = storage_audit(repo, 'finalize', ident)
            self.assertTrue(preserved['result']['committed_readback'])
            self.assertEqual(preserved['result']['independent_validation'], 'not_run')
            summary_path.write_text('tampered')
            with self.assertRaises(ValueError):
                storage_audit(repo, 'finalize', ident)


if __name__ == '__main__':
    unittest.main()

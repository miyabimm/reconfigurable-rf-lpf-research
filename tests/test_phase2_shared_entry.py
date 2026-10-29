"""Shared entry tests: isolated mock diagnostics and temporary Git evidence only."""
import hashlib
from dataclasses import asdict
import json
import shutil
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from lpf.checkpoint_io import canonical_config_hash
from lpf.experiment_manifest import new_manifest
from scripts.experiment_id_registry import PATH, as_csv, next_reservation, read_ledger
from scripts.run_phase2_shared import exp_preflight, manifest_preview, one_start_gate, prepare_one_start, storage_audit
from lpf.phase2_models.problem_seed import vector_fingerprint
from lpf.slsqp_budget import STANDARD_SLSQP_BUDGET, TERMINATION_AWARE_POLICY_ID
from test_phase2_problem_seed import make
from test_phase2_staged_optimization import status


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
            # Copy exactly the executing tracked inputs into the isolated source commit.
            names = subprocess.check_output(['git', 'ls-files', '-z', '--', 'src', 'scripts',
                'project', 'rf', 'pyproject.toml', 'uv.lock'], cwd=ROOT).split(b'\0')
            for name in filter(None, names):
                path = Path(name.decode())
                (repo / path).parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT / path, repo / path)
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
            problem, vector = make('RF-T005', 3)
            vector[6] = 0.
            vector = vector.tolist()
            budget = {**STANDARD_SLSQP_BUDGET.as_dict(), 'policy_id': TERMINATION_AWARE_POLICY_ID}
            start_args = {'circuit': problem.circuit, 'vector': vector, 'seed': 23,
                          'jitter_fraction': 0.0, 'coarse_points': 1, 'fine_points': 2,
                          'budget': budget}
            input_source = json.loads(json.dumps({'definition': asdict(problem.circuit.definition),
                'vector': vector, 'vector_sha256': vector_fingerprint(vector), 'seed': 23,
                'jitter_fraction': 0.0, 'grids': {'coarse_points': 1, 'fine_points': 2},
                'budget': budget}))
            input_sha = canonical_config_hash(input_source)
            scope = {'input_source': input_source, 'input_source_sha256': input_sha}
            manifest = new_manifest(ident, 'fixture only', scope, objective='full_lpf', seed=23,
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
            with patch('lpf.phase2_models.staged_optimization.minimize',
                       side_effect=AssertionError('solver must not run')) as minimize:
                gate = one_start_gate(repo, ident, **args, **start_args)
                self.assertEqual(gate['rejection'], 'owner_approval_not_verified')
                self.assertEqual(gate['execution'], 'not_run')
                self.assertFalse(gate['execution_allowed'])
                minimize.assert_not_called()
            # A fixture-only adapter links the *same* checked manifest input to
            # the existing C1/C2 and #207 classifier. It is not a production entry.
            from lpf.phase2_models.staged_optimization import run_c1_staged
            from lpf.phase2_models.candidate_records import record_candidate
            from lpf.phase2_models.synthetic_runner import checked_one_start_selection, diagnostic_selection
            from lpf.phase2_models.synthetic_plan import _source
            from scripts.audit_new_experiment_storage import validate_selection, validate_summary
            def fixture_preview(params, callback, *, stopped=False, preflight_args=args):
                prepared = prepare_one_start(repo, ident, **preflight_args, **params)
                self.assertFalse(prepared['execution_allowed'])
                selection = diagnostic_selection()
                result = {'completed': [], 'not_started': int(stopped)}
                if not stopped:
                    local_source = _source()
                    provenance = {'kind': 'synthetic', 'optimizer_kind': 'synthetic_callback',
                        'git_head': local_source['git_head'],
                        'dirty_patch_sha256': local_source['dirty_patch_sha256'],
                        'input_source_sha256': canonical_config_hash(prepared['input_source'])}
                    staged = run_c1_staged(params['circuit'], prepared['seed_record'],
                        coarse_points=params['coarse_points'], fine_points=params['fine_points'],
                        optimize_stage=callback, source_provenance=provenance)
                    final = (prepared['seed_record']['vector'][:-1] if staged['numerical_state'] == 'failed'
                             else staged['stage_calls'][-1]['output_vector'][:-1])
                    result['completed'].append(record_candidate('fixture', params['circuit'], final,
                        staged_record=staged, source_provenance=provenance).as_dict())
                preview = checked_one_start_selection(result)
                self.assertEqual(selection, preview['selection'])
                validate_selection(selection)
                validate_summary(preview['run_summary'], None, len(preview['selected']))
                return {**preview, 'mode': 'isolated_fixture_mock_non_exp',
                        'reservation': 'fixture_only', 'owner_approval': 'not_verified',
                        'execution_allowed': False, 'experiment_execution': 'not_run',
                        'finite_grid_rf': 'synthetic_observation_not_certified',
                        'independent_mna': 'not_run', 'dense_rf': 'not_run',
                        'git_readback': 'not_run', 'candidate_promotion_blocked': True}

            harmonic_failure = [False]
            def fake_il(evaluator, vector):
                il = np.where(evaluator.role == 0, .25, 36.)
                if harmonic_failure[0]:
                    il[evaluator.role == 1] = 29.
                return il
            with patch('lpf.phase2_models.coupled_lc.CoupledLCEvaluator.il', fake_il), \
                 patch('lpf.phase2_models.staged_optimization.minimize',
                       side_effect=AssertionError('solver forbidden')) as minimize:
                for codes, state, reason in (((0, 0), 'converged', None),
                    ((4, 9), 'nonconverged', 'numerical_not_converged'),
                    ((8, 9), 'nonconverged', 'numerical_not_converged'),
                    ((9, 0, 0, 0), 'converged', None),
                    (('error',), 'failed', 'numerical_failed'),
                    ((), 'not_started', None)):
                    with self.subTest(codes=codes):
                        calls = []
                        def callback(p, x, maxiter, target):
                            code = codes[len(calls)]
                            calls.append(maxiter)
                            if code == 'error':
                                raise RuntimeError('fixture failure')
                            x[-1] = .5
                            return x, status(code)
                        preview = fixture_preview(start_args, callback, stopped=not codes)
                        self.assertEqual(preview['run_summary']['attempts'][state], 1)
                        self.assertEqual(preview['owner_approval'], 'not_verified')
                        self.assertFalse(preview['execution_allowed'])
                        for field in ('experiment_execution', 'independent_mna', 'dense_rf', 'git_readback'):
                            self.assertEqual(preview[field], 'not_run')
                        self.assertEqual(len(calls), len(codes))
                        if codes:
                            row = preview['pareto']['candidates'][0]
                            if reason:
                                self.assertIn(reason, row['reasons'])
                            else:
                                self.assertEqual(row['reasons'], [])
                                self.assertTrue(row['pareto_within_group'])
                            self.assertTrue(row['candidate_promotion_blocked'])
                        else:
                            self.assertEqual(preview['selected'], [])
                harmonic_failure[0] = True
                def success(p, x, budget, target):
                    x[-1] = .5
                    return x, status(0)
                infeasible = fixture_preview(start_args, success)
                self.assertEqual(infeasible['run_summary']['attempts']['converged'], 1)
                self.assertIn('mandatory_harmonics_failed_on_grid',
                              infeasible['pareto']['candidates'][0]['reasons'])
                self.assertEqual(infeasible['run_summary']['selected_candidate_count'], 0)
                harmonic_failure[0] = False
                calls = []
                def interrupted(*args):
                    calls.append(1)
                    raise KeyboardInterrupt()
                with self.assertRaises(KeyboardInterrupt):
                    fixture_preview(start_args, interrupted)
                self.assertEqual(calls, [1])  # no automatic retry or invented outcome
                bad_circuit = make('RF-T007', 3)[0].circuit
                other_definition = make('RF-T005', 4)[0].circuit
                for change in ({'circuit': bad_circuit}, {'circuit': other_definition}, {'vector': vector[:-1]},
                               {'vector': [2.1] + vector[1:]}, {'seed': 24},
                               {'jitter_fraction': .01}, {'coarse_points': 2},
                               {'fine_points': 3}, {'budget': budget | {'policy_id': 'invalid'}}):
                    with self.subTest(change=change), self.assertRaises((ValueError, TypeError)):
                        fixture_preview(start_args | change, lambda *a: self.fail('callback called'))
                with patch('lpf.experiment_manifest._environment', return_value={}):
                    with self.assertRaisesRegex(ValueError, 'environment'):
                        fixture_preview(start_args, lambda *a: self.fail('callback called'))
                from lpf.experiment_manifest import file_sha256
                def wrong_source(path):
                    return '0' * 64 if path == ROOT / 'scripts/run_phase2_shared.py' else file_sha256(path)
                with patch('lpf.experiment_manifest.file_sha256', side_effect=wrong_source):
                    with self.assertRaisesRegex(ValueError, 'source/input files'):
                        fixture_preview(start_args, lambda *a: self.fail('callback called'))
                for change in ({'owner': 'wrong'}, {'request_id': 'wrong'},
                               {'allow_trial': False}, {'source_sha': '0' * 40},
                               {'policy_sha256': '0' * 64}, {'bands_sha256': '0' * 64},
                               {'input_sha256': '0' * 64}):
                    with self.subTest(preflight=change), self.assertRaises((ValueError, subprocess.CalledProcessError)):
                        fixture_preview(start_args, lambda *a: self.fail('callback called'),
                                        preflight_args=args | change)
                minimize.assert_not_called()

            for change in ({'owner': 'wrong'}, {'request_id': 'wrong'}, {'policy_id': 'RF-T007'},
                           {'policy_id': 'RF-F003'}, {'allow_trial': False},
                           {'policy_sha256': '0' * 64}, {'bands_sha256': '0' * 64},
                           {'input_sha256': '0' * 64}, {'source_sha': '0' * 40}):
                with self.subTest(change=change), self.assertRaises((ValueError, subprocess.CalledProcessError)):
                    one_start_gate(repo, ident, **(args | change), **start_args)
            with self.assertRaises(ValueError):
                one_start_gate(repo, 'EXP-999', **args, **start_args)
            with self.assertRaises(ValueError):
                storage_audit(repo, 'finalize', ident)
            git('config', 'core.sparseCheckout', 'true')
            with self.assertRaisesRegex(ValueError, 'sparse'):
                one_start_gate(repo, ident, **args, **start_args)
            git('config', 'core.sparseCheckout', 'false')
            evidence = repo / 'experiments/README'
            evidence.unlink()
            with self.assertRaisesRegex(ValueError, 'missing tracked evidence'):
                one_start_gate(repo, ident, **args, **start_args)
            git('restore', 'experiments/README')
            git('update-ref', 'refs/remotes/origin/main', source)
            with self.assertRaisesRegex(ValueError, 'stale'):
                one_start_gate(repo, ident, **args, **start_args)
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

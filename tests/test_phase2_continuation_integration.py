"""Isolated Git G0-G4 continuation integration; RF and optimizer are synthetic.

Never accesses a production remote or creates a real experiment. The local bare
remote and all evidence are temporary. Synthetic validation is NOT RF evidence.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

import numpy as np
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))

from lpf.checkpoint_io import atomic_write_json
from lpf.experiment_manifest import experiment_index, new_manifest
from lpf.phase2_models.experiment_config import load_plan
from lpf.phase2_models.experiment_post_search import (prepare_post_search,
    run_post_search_candidate, package_post_search)
from lpf.phase2_models.experiment_run import CONTINUATION_RETENTION_RULE, run_plan
from scripts.audit_new_experiment_storage import validate_run
from scripts.experiment_id_registry import PATH, as_csv, next_reservation
from scripts.run_phase2_one_start import finalize_experiment
from scripts.run_phase2_shared import prepare_continuation_plan


class ContinuationIntegrationTests(unittest.TestCase):
    @unittest.skipUnless((ROOT / 'experiments/chatgpt_topology_search/runs/EXP-062/checkpoints/a6_best.json').is_file(),
                         'full evidence checkout required for topology-reference fixture')
    def test_temporary_remote_full_lifecycle(self):
        with tempfile.TemporaryDirectory() as tmp, ExitStack() as stack:
            repo, remote = Path(tmp) / 'repo', Path(tmp) / 'remote.git'
            repo.mkdir()
            def git(*args):
                return subprocess.check_output(['git', *map(str, args)], cwd=repo,
                                               stderr=subprocess.PIPE, text=True).strip()
            git('init', '-q', '-b', 'main')
            git('config', 'user.name', 'Fixture')
            git('config', 'user.email', 'fixture@example.invalid')
            git('init', '--bare', '-q', remote)
            git('remote', 'add', 'origin', remote)
            names = subprocess.check_output(['git', 'ls-files', '-z', '--', 'src', 'scripts',
                'project', 'rf', 'pyproject.toml', 'uv.lock'], cwd=ROOT).split(b'\0')
            historical = 'experiments/chatgpt_topology_search/runs/EXP-062/checkpoints/a6_best.json'
            for name in (n.decode() for n in names if n):
                path = repo / name
                path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT / name, path)
            reference = repo / 'fixture-inputs/topology.json'
            reference.parent.mkdir()
            shutil.copyfile(ROOT / historical, reference)
            config_path = repo / 'project/experiments/issue270.yaml'
            config = yaml.safe_load(config_path.read_text())
            config['topology_reference']['path'] = 'fixture-inputs/topology.json'
            config_path.write_text(yaml.safe_dump(config, sort_keys=False))
            (repo / '.gitignore').write_text('results/\n__pycache__/\n*.pyc\n')
            (repo / 'experiments').mkdir()
            (repo / 'experiments/README.md').write_text('Synthetic fixture only.\n')
            ledger = repo / PATH
            ledger.parent.mkdir(parents=True, exist_ok=True)
            rows = [dict(experiment_id=f'EXP-{n:03}', state='legacy_gap_retired' if n in (18, 19)
                         else 'legacy_recorded', owner='', request_id='', purpose='', constraint_id='',
                         reserved_at_utc='', origin='') for n in range(1, 50)]
            rows, ident, _ = next_reservation(rows, owner='fixture', purpose='synthetic test only',
                request_id='fixture-continuation', constraint_id='RF-T008', reserved_at_utc='2026-11-03T00:00:00Z')
            ledger.write_text(as_csv(rows))
            (repo / 'data/phase2_git_storage_budget.json').write_text(json.dumps({'thresholds': {
                'individual_new_file_soft_bytes': 131072, 'individual_new_file_hard_bytes': 1048576,
                'new_experiment_curated_soft_bytes': 10000000}}))
            git('add', '.')
            git('commit', '-qm', 'fixture source and mock G0')
            git('push', '-qu', 'origin', 'main')
            stack.enter_context(patch.dict(os.environ, {'OPENBLAS_NUM_THREADS': '1',
                'OMP_NUM_THREADS': '1', 'MKL_NUM_THREADS': '1'}))
            for module in ('scripts.run_phase2_shared', 'lpf.phase2_models.limited_candidate_evidence',
                           'lpf.phase2_models.post_search_validation'):
                stack.enter_context(patch(module + '.ROOT', repo))
            from lpf.phase2_models.coupled_lc import CoupledLCEvaluator
            eligible = []
            def fake_forward(ev, x):
                passed = not eligible or np.array_equal(np.asarray(x)[:len(eligible[0])], eligible[0])
                return np.where(ev.role == 0, .25, 36. if passed else 29.)
            stack.enter_context(patch.object(CoupledLCEvaluator, 'il', fake_forward))
            prep = prepare_continuation_plan(repo, config_path, ident)
            self.assertEqual(prep['initialization_cost']['frequency_samples_requested'], 112)
            config = yaml.safe_load(config_path.read_text())
            config['plan']['sha256'] = prep['plan_sha256']
            config_path.write_text(yaml.safe_dump(config, sort_keys=False))
            git('add', str(config_path.relative_to(repo)))
            git('commit', '-qm', 'fixture frozen plan')
            git('push', '-q', 'origin', 'main')
            loaded = load_plan(repo, config_path)
            post = dict(schema='post-search-g1-1', selection_rule='all eight mock anchors', search_guard=True,
                        max_selected=8, separate17=3808, dense1001=224224,
                        independent_forward84=672, independent_mna84=672)
            scope = dict(input_source=loaded['input_source'], input_source_sha256=loaded['input_source_sha256'],
                         post_search_validation=post)
            manifest = new_manifest(ident, 'synthetic fixture only', scope, objective='full_lpf',
                                    seed=23, root=repo, constraint_id='RF-T008', allow_trial=True)
            run = repo / 'experiments/chatgpt_topology_search/runs' / ident
            run.mkdir(parents=True)
            storage = dict(schema_version=1, policy='phase2-git-only-v1', experiment_id=ident,
                phase='Phase 2', stage='planned', git_readback='not_run',
                selection=dict(top_k=2, retain=['other'], rule=CONTINUATION_RETENTION_RULE,
                               estimated_curated_bytes=8000000),
                summary=None, checkpoints=[], validation_overlays=[], supporting_evidence=[],
                size_exception=None, limitations=[])
            atomic_write_json(run / 'manifest.json', manifest, compact=True)
            atomic_write_json(run / 'storage_record.json', storage, compact=True)
            rel = lambda p: p.relative_to(repo).as_posix()
            (repo / 'data/experiment_index.csv').write_text(experiment_index([(rel(run / 'manifest.json'), manifest)]))
            git('add', '.')
            git('commit', '-qm', 'fixture G1')
            git('push', '-q', 'origin', 'main')

            # Isolate each interruption from the successful fixture and from
            # every other attempt. These are local-only disposable remotes.
            import lpf.phase2_models.experiment_run as runner
            from lpf.phase2_models.evaluation_cost import SampleBudgetCost
            for failure in ('exception', 'timeout', 'interrupt', 'storage', 'budget'):
                with self.subTest(failure=failure):
                    clone = Path(tmp) / ('failure-' + failure)
                    git('clone', '-q', '--branch', 'main', remote, clone)
                    clone_config = clone / 'project/experiments/issue270.yaml'
                    def bad_solver(problem, vector, maxiter, target, *, coordinates):
                        if failure == 'exception':
                            raise ValueError('synthetic stage exception')
                        if failure == 'timeout':
                            raise TimeoutError('synthetic timeout')
                        if failure == 'interrupt':
                            raise KeyboardInterrupt('synthetic interrupt')
                        return vector, dict(success=True, status=0, message='mock', nit=0, nfev=0)
                    original_save = runner._save
                    snapshots = []
                    def failing_save(path, state):
                        if state.get('continuation_record') is not None:
                            snapshots.append(1)
                            if len(snapshots) == 2:
                                raise OSError('synthetic disk failure')
                        return original_save(path, state)
                    original_meter = SampleBudgetCost
                    meters = []
                    class LimitedMeter(original_meter):
                        def __init__(self, maximum, **kwargs):
                            meters.append(1)
                            super().__init__(56 if len(meters) == 1 else maximum, **kwargs)
                    with patch('scripts.run_phase2_shared.ROOT', clone), ExitStack() as injection:
                        if failure == 'storage':
                            injection.enter_context(patch.object(runner, '_save', side_effect=failing_save))
                        if failure == 'budget':
                            injection.enter_context(patch.object(runner, 'SampleBudgetCost', LimitedMeter))
                            pilot_failure = run_plan(clone, clone_config, ident, 'pilot', optimize_stage=bad_solver)
                            self.assertEqual(len(pilot_failure['completed']), 4)
                            first_failure = pilot_failure['completed']['nominal-A']['continuation']
                            self.assertEqual(first_failure['state'], 'budget_exhausted')
                            self.assertEqual(first_failure['evaluation_cost']['frequency_samples_requested'], 56)
                            self.assertFalse(any(k.startswith('sobol-') for k in pilot_failure['completed']))
                            self.assertIsNone(pilot_failure['in_progress'])
                            raw = clone / 'results' / ident / 'run.json'
                            before = raw.read_bytes()
                            repeated = run_plan(clone, clone_config, ident, 'pilot', optimize_stage=bad_solver)
                            self.assertEqual(repeated, json.loads(json.dumps(pilot_failure)))
                            self.assertEqual(raw.read_bytes(), before)
                            failure_run = clone / 'experiments/chatgpt_topology_search/runs' / ident
                            summary = json.loads((failure_run / 'run_summary.json').read_text())
                            self.assertEqual(summary['attempts']['not_started'], 4)
                            preserved = {p: p.read_bytes() for p in failure_run.rglob('*') if p.is_file()}
                            with patch.object(CoupledLCEvaluator, 'il', side_effect=AssertionError('remaining must not evaluate RF')):
                                with self.assertRaisesRegex(ValueError, 'Pilot.*STOP.*budget_exhausted'):
                                    run_plan(clone, clone_config, ident, 'remaining', optimize_stage=bad_solver)
                            self.assertEqual(raw.read_bytes(), before)
                            self.assertEqual(preserved, {p: p.read_bytes() for p in preserved})
                        else:
                            expected = {'exception': RuntimeError, 'timeout': RuntimeError,
                                        'interrupt': KeyboardInterrupt, 'storage': Exception}[failure]
                            with self.assertRaises(expected) as caught:
                                run_plan(clone, clone_config, ident, 'pilot', optimize_stage=bad_solver)
                            if failure == 'storage':
                                self.assertIsInstance(caught.exception.__cause__, OSError)
                            raw = clone / 'results' / ident / 'run.json'
                            saved = json.loads(raw.read_text())['body']
                            self.assertEqual(saved['in_progress'], 'nominal-A')
                            self.assertEqual(saved['completed'], {})
                            self.assertIsNotNone(saved['continuation_record'])
                            if failure in ('exception', 'timeout'):
                                self.assertEqual(saved['continuation_record']['state'], 'failed')
                                self.assertEqual(saved['continuation_record']['exception']['type'], 'FrequencyExchangeError')
                                stage_exception = saved['continuation_record']['final_stage']['exception']
                                self.assertEqual(stage_exception['type'], 'ValueError' if failure == 'exception' else 'TimeoutError')
                                self.assertIn('synthetic stage exception' if failure == 'exception' else 'synthetic timeout',
                                              stage_exception['message'])
                            else:
                                self.assertEqual(saved['continuation_record']['state'], 'running')
                            self.assertEqual(sum(k.startswith('sobol-') for k in saved['completed']), 0)
                            before = raw.read_bytes()
                            with self.assertRaisesRegex(ValueError, 'automatic retry prohibited'):
                                run_plan(clone, clone_config, ident, 'remaining', optimize_stage=bad_solver)
                            self.assertEqual(raw.read_bytes(), before)
                        audit = validate_run(clone, ident, mode='audit')
                        self.assertNotEqual(audit['numerical_validation'], 'passed')
                        self.assertNotEqual(audit['independent_validation'], 'passed')
            calls = []
            def optimizer(problem, vector, maxiter, target, *, coordinates):
                calls.append(1)
                output = vector.copy()
                if len(calls) == 1:
                    output[0] += .0001
                return output, dict(success=True, status=0, message='synthetic mock', nit=0, nfev=0)
            with patch('lpf.phase2_models.staged_optimization.minimize', side_effect=AssertionError('no SciPy')):
                pilot = run_plan(repo, config_path, ident, 'pilot', optimize_stage=optimizer)
                self.assertEqual(set(pilot['completed']), {f'nominal-{m}' for m in 'ABCD'})
                final = run_plan(repo, config_path, ident, 'remaining', optimize_stage=optimizer)
            self.assertEqual(set(final['completed']), {f'{start}-{m}' for start in ('nominal', 'sobol') for m in 'ABCD'})
            summary = json.loads((run / 'run_summary.json').read_text())
            self.assertEqual(summary['costs']['allocated_initialization']['frequency_samples_requested'], 672)
            self.assertEqual(summary['costs']['initialization_actual']['frequency_samples_requested'], 112)
            first = next(iter(final['completed']))
            eligible.append(np.asarray(final['completed'][first]['continuation']['last_valid_vector'][:-1]))
            evaluator = loaded['circuit'].forward_evaluator(3)
            def fake_mna(circuit, vector, frequency, setting):
                match = np.flatnonzero((evaluator.setting == setting) &
                    np.isclose(evaluator.f * 1e6, frequency, rtol=0, atol=1e-6))
                if not len(match):
                    raise AssertionError('synthetic frequency outside grid')
                il = .25 if evaluator.role[match[0]] == 0 else 36.
                gain = 10 ** (-il / 10)
                return dict(gain=gain, il_db=il, power_residual_w=0., inductor_loss_w=1-gain,
                            capacitor_loss_w=0., input_s2p_loss_w=0., output_s2p_loss_w=0.,
                            load_power_w=gain, input_power_w=1.)
            stack.enter_context(patch('lpf.phase2_models.post_search_validation.evaluate_independent_sample', fake_mna))
            budgets = dict(separate17=476, dense1001=28028, independent_forward84=84, independent_mna84=84)
            selections = [dict(candidate_id=k, vector=v['continuation']['last_valid_vector'][:-1],
                               budgets=budgets, run_dense=True, run_independent=True)
                          for k, v in final['completed'].items()]
            prepare_post_search(repo, config_path, ident, selections)
            reports = []
            for row in selections:
                reports.append(run_post_search_candidate(repo, config_path, ident, **row))
            self.assertEqual(sum(r['separate17']['state'] == 'pass' for r in reports), 1)
            self.assertEqual(sum(r['dense1001']['state'] == 'pass' for r in reports), 1)
            self.assertEqual(sum(r['independent84']['state'] == 'pass' for r in reports), 1)
            for report in reports:
                if report['separate17']['state'] != 'pass':
                    self.assertEqual(report['separate17']['state'], 'fail')
                    self.assertEqual(report['dense1001']['state'], 'not_run')
                    self.assertEqual(report['independent84']['state'], 'not_run')
            package_post_search(repo, config_path, ident)
            validate_run(repo, ident, mode='audit')
            result = finalize_experiment(repo, ident)
            self.assertEqual(result['stage'], 'complete')
            git('push', '-q', 'origin', 'main')
            self.assertEqual(validate_run(repo, ident, mode='finalize', main_ref='origin/main')['stage'], 'complete')
            files = [p for base in (run, repo / 'results' / ident) for p in base.rglob('*') if p.is_file()]
            files.append(repo / 'data/experiment_index.csv')
            for path in [p for p in files if p.is_relative_to(run)] + [repo / 'data/experiment_index.csv']:
                self.assertEqual(subprocess.check_output(['git', 'show', 'origin/main:' + rel(path)], cwd=repo), path.read_bytes())
            self.assertTrue(all(p.stat().st_size <= 1048576 for p in run.rglob('*') if p.is_file()))
            self.assertLess(sum(p.stat().st_size for p in run.rglob('*') if p.is_file()), 10000000)
            print('SYNTHETIC SIZE AUDIT', json.dumps({rel(p): p.stat().st_size for p in files}, sort_keys=True))


if __name__ == '__main__':
    unittest.main()

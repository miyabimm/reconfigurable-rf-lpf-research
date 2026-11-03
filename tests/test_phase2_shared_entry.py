"""Shared entry tests: isolated mock diagnostics and temporary Git evidence only."""
import hashlib
from copy import deepcopy
from dataclasses import asdict
from functools import partial
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
from scripts.experiment_id_registry import PATH, as_csv, next_reservation
from scripts.run_phase2_shared import exp_preflight, manifest_preview, one_start_gate, prepare_one_start, storage_audit
from lpf.phase2_models.problem_seed import vector_fingerprint
from lpf.phase2_models._grid import CASES
from lpf.slsqp_budget import STANDARD_SLSQP_BUDGET, TERMINATION_AWARE_POLICY_ID
from test_phase2_problem_seed import make
from test_phase2_staged_optimization import status


from scripts.run_phase2_one_start import (
    candidate_checkpoint as fixture_checkpoint, run_one_start, finalize_one_start,
    _optimizer_provenance, scipy_slsqp_stage)


class SharedEntryTests(unittest.TestCase):
    def _check_components(self, circuit, vector, checkpoint):
        d, s, t = circuit.definition, circuit.schema, circuit.topology
        values = circuit.decode(vector)
        parts = checkpoint['components']
        self.assertEqual(checkpoint['candidate_record']['vector'], vector)
        self.assertEqual(checkpoint['candidate_record']['policy_id'], circuit.policy_id)
        self.assertEqual(checkpoint['chip_row'], [f'L{i}' for i in d.physical_order])
        self.assertEqual(checkpoint['couplings'][0]['signed_k'], -.02)
        self.assertEqual(len(parts), s.n_inductors + len(t.capacitor_edges))
        for i, part in enumerate(parts[:s.n_inductors]):
            self.assertEqual((part['series'], part['Q'], part['terminals'], part['L_nH']),
                (d.inductor_types[i], t.inductor_q[i], list(d.inductor_tree.edges[i]),
                 values.inductances_nh[i]))
        caps = parts[s.n_inductors:]
        for i, part in enumerate(caps):
            self.assertEqual(part['terminals'], list(t.capacitor_edges[i]))
            self.assertEqual(part['Q'], t.capacitor_q[i])
            self.assertEqual(part['C_pf_by_setting'],
                {case: values.capacitors_pf_by_setting[j][i] for j, case in enumerate(CASES)})
        self.assertEqual(checkpoint['ic_variable_C_pf_by_setting'],
            {case: list(row[s.n_fixed:s.n_fixed + s.n_variable])
             for case, row in zip(CASES, values.capacitors_pf_by_setting)})
        if circuit.policy_id == 'RF-T008':
            self.assertEqual([p['Q'] for p in caps[1:3]], [60., 40.])
            self.assertEqual(s.n_ic_fixed, 2)
            for i, fixed in enumerate(caps[s.n_fixed + s.n_variable:]):
                variable = caps[s.n_fixed + i]
                self.assertEqual((fixed['series'], fixed['Q']), ('IC_FIXED_C', 60.))
                self.assertEqual((variable['series'], variable['Q']), ('IC_VARIABLE_C', 35.))
                self.assertEqual(fixed['terminals'], variable['terminals'])
                self.assertEqual(fixed['parallel_variable_component_id'], variable['id'])
                self.assertEqual(set(fixed['C_pf_by_setting'].values()), {fixed['C_pf']})
                self.assertGreater(fixed['C_pf'], 0.)
            self.assertEqual(caps[s.n_fixed]['C_pf_by_setting'][CASES[0]], 0.)
            self.assertEqual(checkpoint['fixed_values']['ic_fixed_capacitors_pf'],
                             [caps[-2]['C_pf'], caps[-1]['C_pf']])

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

    def test_scipy_opt_in_provenance_not_synthetic(self):
        for coordinates in ('physical', 'normalized'):
            callback = partial(scipy_slsqp_stage, coordinates=coordinates,
                               finite_difference_eps=None)
            result = _optimizer_provenance(callback)
            self.assertEqual(result['execution_kind'], 'scipy_slsqp')
            self.assertEqual(result['optimizer_kind'], 'reported_slsqp')
            self.assertEqual(result['coordinate_configuration'], {
                'coordinates': coordinates, 'finite_difference_eps': None})
        for callback in (lambda *args: None, partial(lambda *args: None),
                         partial(scipy_slsqp_stage, object()),
                         partial(scipy_slsqp_stage, unknown=True)):
            self.assertEqual(_optimizer_provenance(callback)['execution_kind'],
                             'injected_callback')
        self.assertEqual(_optimizer_provenance(scipy_slsqp_stage), {
            'execution_kind': 'scipy_slsqp', 'optimizer_kind': 'reported_slsqp'})

    def test_preview_is_only_in_memory(self):
        result = manifest_preview(ROOT, 'EXP-999', 'fixture only', {}, policy_id='RF-T005', seed=1, allow_trial=True)
        self.assertEqual(result['manifest']['execution']['status'], 'planned')
        self.assertEqual(result['execution'], 'not_run')
        self.assertNotIn('owner_approval', result)
        self.assertFalse(result['execution_allowed'])
        with self.assertRaises(ValueError):
            manifest_preview(ROOT, 'EXP-999', 'fixture', {}, policy_id='RF-F003', seed=1, allow_trial=True)

    def test_temporary_full_checkout_preflight_and_fail_closed(self):
        self._checkout_driver('RF-T005', 3, enumerated=False)

    def test_driver_unsupported_policies_never_preflight_or_dispatch(self):
        from types import SimpleNamespace
        with patch('scripts.run_phase2_one_start.prepare_one_start') as prepare:
            for policy in ('RF-T007', 'RF-T006', 'RF-F003', 'RF-T999'):
                with self.subTest(policy=policy), self.assertRaisesRegex(ValueError, 'Only RF-T005'):
                    run_one_start(ROOT, 'EXP-999', circuit=SimpleNamespace(policy_id=policy),
                                  optimize_stage=lambda *a: self.fail('solver called'))
            prepare.assert_not_called()

    def test_enumerated_multi_topology_driver_and_checkpoint(self):
        for policy in ('RF-T005', 'RF-T008'):
            for n in (3, 4):
                with self.subTest(policy=policy, inductors=n):
                    self._checkout_driver(policy, n, enumerated=True)

    def _checkout_driver(self, policy, n, *, enumerated):
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
            (repo / '.gitignore').write_text('results/\n__pycache__/\n*.pyc\n')
            (repo / 'experiments').mkdir()
            (repo / 'experiments/README').write_text('isolated fixture')
            ledger = repo / PATH
            ledger.parent.mkdir(parents=True, exist_ok=True)
            rows = [{'experiment_id': f'EXP-{n:03}',
                     'state': 'legacy_gap_retired' if n in (18, 19) else 'legacy_recorded',
                     'owner': '', 'request_id': '', 'purpose': '', 'constraint_id': '',
                     'reserved_at_utc': '', 'origin': ''} for n in range(1, 50)]
            rows, ident, _ = next_reservation(rows, owner='fixture', purpose='fixture only',
                request_id='fixture-194', constraint_id=policy, reserved_at_utc='2026-10-28T00:00:00Z')
            ledger.write_text(as_csv(rows))
            (repo / 'data/phase2_git_storage_budget.json').write_text(json.dumps({'thresholds': {
                'individual_new_file_soft_bytes': 131072, 'individual_new_file_hard_bytes': 1048576,
                'new_experiment_curated_soft_bytes': 524288}}))
            git('add', '.')
            git('commit', '-qm', 'fixture reservation')
            git('push', '-q', '-u', 'origin', 'main')
            source = git('rev-parse', 'HEAD')
            if enumerated:
                from lpf.constraint_versions import load_constraint
                from lpf.phase2_models.api import build_nominal_circuit
                from lpf.phase2_models.circuit_layout import InductorTree
                from lpf.phase2_models.topology_enumeration import TopologySpace, enumerate_topologies
                from lpf.phase2_models.sampled_epigraph import SampledEpigraph
                space = TopologySpace(
                    trees=(InductorTree(n + 1, tuple((0, i) for i in range(1, n + 1))),),
                    inductor_assignments=(('LQP02HQ',) + ('LQP02HV',) * (n - 2) + ('PCB_L',),),
                    fixed_layouts=((((0, 1), 'GJM01'), ((1, -1), 'PCB_PATTERN_C'),
                                    ((0, 2), 'PCB_PATTERN_C')),),
                    variable_layouts=((((3, -1), 'shunt_to_ground'), ((0, 2), 'bridge')),),
                    coupling_slot_counts=(1,), physical_order_limit=1, max_candidates=1)
                approved = load_constraint(policy, allow_trial=True)
                rows = enumerate_topologies(approved, space)['candidates']
                self.assertEqual(len(rows), 1)
                circuit = build_nominal_circuit(approved, rows[0]['definition'])
                problem = SampledEpigraph(circuit, 1)
                vector = np.array(rows[0]['representative_vector'])
                vector[n + 3] = -.02  # signed adjacent-chip k
            else:
                problem, vector = make(policy, n)
                vector[6] = 0.
            # Distinct six-setting values catch accidental row reuse/reordering.
            vector[-12:] = [0., 3., .2, 2.8, .4, 2.6, .6, 2.4, .8, 2.2, 1., 2.]
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
                                    root=repo, constraint_id=policy, allow_trial=True)
            run = repo / 'experiments/chatgpt_topology_search/runs' / ident
            run.mkdir(parents=True)
            record = {'schema_version': 1, 'policy': 'phase2-git-only-v1', 'experiment_id': ident,
                      'phase': 'Phase 2', 'stage': 'planned',
                      'selection': {'top_k': 0, 'retain': ['pareto'],
                                    'rule': 'Fixture only: retain checked Pareto checkpoints; preserve '
                                            'all exclusions and mock attempt diagnostics in summary.',
                                    'estimated_curated_bytes': 200000},
                      'summary': None, 'checkpoints': [], 'validation_overlays': [],
                      'git_readback': 'not_run', 'size_exception': None, 'limitations': []}
            (run / 'manifest.json').write_text(json.dumps(manifest))
            (run / 'storage_record.json').write_text(json.dumps(record))
            git('add', str(run.relative_to(repo)))
            git('commit', '-qm', 'fixture planned evidence')
            git('push', '-q', 'origin', 'main')
            args = dict(owner='fixture', request_id='fixture-194', policy_id=policy,
                        policy_sha256=manifest['constraints']['effective_constraint_sha256'],
                        source_sha=source, bands_sha256=manifest['bands_sha256'],
                        input_sha256=input_sha, allow_trial=True)
            with patch('lpf.phase2_models.staged_optimization.minimize',
                       side_effect=AssertionError('solver must not run')) as minimize, \
                 patch('lpf.phase2_models.staged_optimization.run_c1_staged',
                       side_effect=AssertionError('staged driver must not run')) as staged:
                result = exp_preflight(repo, ident, **args)
                prepared = prepare_one_start(repo, ident, **args, **start_args)
                gate = one_start_gate(repo, ident, **args, **start_args)
                for report in (result, prepared, gate):
                    self.assertEqual(report['status'], 'preflight_ready')
                    self.assertEqual(report['execution'], 'not_run')
                    # False describes this read-only API, not missing owner authentication.
                    self.assertFalse(report['execution_allowed'])
                    self.assertNotIn('owner_approval', report)
                    self.assertNotIn('rejection', report)
                self.assertEqual(result['reservation']['owner'], 'fixture')
                self.assertEqual(prepared['preflight'], result)
                self.assertEqual(gate['preflight'], result)
                for field in ('finite_grid_rf', 'independent_mna', 'dense_rf', 'git_readback'):
                    self.assertEqual(gate[field], 'not_run')
                self.assertTrue(gate['candidate_promotion_blocked'])
                minimize.assert_not_called()
                staged.assert_not_called()
            # Exercise the actual explicit driver, with real isolated commits.
            planned_head = git('rev-parse', 'HEAD')
            def forward(evaluator, x):
                return np.where(evaluator.role == 0, .25,
                                np.where(evaluator.role == 1, 29. if h2_bad[0] else 36., 36.))
            h2_bad = [False]
            with patch('lpf.phase2_models.coupled_lc.CoupledLCEvaluator.il', forward), \
                 patch('lpf.phase2_models.staged_optimization.minimize',
                       side_effect=AssertionError('real SciPy forbidden')) as minimize:
                scenarios = (((0, 0), 'converged'),) if enumerated else (
                    ((0, 0), 'converged'), ((4, 9), 'nonconverged'),
                    ((8, 9), 'nonconverged'), ((4, 0, 0, 0), 'converged'),
                    ((9, 0, 0, 0), 'converged'), ((0, 9, 0), 'converged'),
                    ((0, 'error'), 'failed'), ((0, 'interrupt'), 'failed'),
                    ((0, 'timeout'), 'failed'), ((0, 'stop'), 'failed'),
                    ((0, 'source'), 'failed'),
                    ((0, 'parts'), 'converged'), ((0, 'h2'), 'converged'),
                    ((), 'not_started'))
                for codes, expected in scenarios:
                    with self.subTest(driver=codes):
                        calls = []
                        h2_bad[0] = bool(codes and codes[-1] == 'h2')
                        def solver(p, x, maxiter, target):
                            self.assertTrue((repo / 'results' / ident / 'run.json').is_file())
                            code = codes[len(calls)]
                            calls.append(maxiter)
                            if code == 'error':
                                raise RuntimeError('fixture exception')
                            if code == 'interrupt':
                                raise KeyboardInterrupt('fixture interruption')
                            if code == 'timeout':
                                raise TimeoutError('fixture timeout')
                            if code == 'stop':
                                (repo / 'results' / ident / 'STOP').touch()
                            if code == 'source':
                                (repo / 'rf/bands.csv').write_text('changed during execution')
                            if code == 'parts':
                                x[3] = 0.  # excluded GJM boundary, status0 is not RF PASS
                            x[-1] = .5
                            return x, status(0 if isinstance(code, str) else code)
                        if not codes:
                            # Stop after preflight, before any dispatch.
                            with patch('scripts.run_phase2_one_start.time.monotonic',
                                       side_effect=[0., 2., 3.]):
                                outcome = run_one_start(repo, ident, **args, **start_args,
                                    optimize_stage=solver, timeout_seconds=1.)
                        else:
                            outcome = run_one_start(repo, ident, **args, **start_args,
                                                    optimize_stage=solver)
                        self.assertEqual(len(calls), len(codes))
                        saved = json.loads((run / 'run_summary.json').read_text())
                        self.assertEqual(saved['attempts'][expected], 1)
                        if enumerated:
                            self.assertEqual(saved['selected_candidate_count'], 1)
                            checkpoint = fixture_checkpoint(problem.circuit,
                                outcome['result']['completed'][0])
                            self._check_components(problem.circuit, vector, checkpoint)
                            for field, value in (('policy_sha256', '0' * 64),
                                    ('vector', vector[:-1]), ('definition', {})):
                                bad = deepcopy(outcome['result']['completed'][0])
                                bad[field] = value
                                with self.assertRaises((ValueError, TypeError, KeyError)):
                                    fixture_checkpoint(problem.circuit, bad)
                            for other_policy, other_n in (('RF-T007', n),
                                    ('RF-T008' if policy == 'RF-T005' else 'RF-T005', n),
                                    (policy, 4 if n == 3 else 3)):
                                with self.assertRaises(ValueError):
                                    fixture_checkpoint(make(other_policy, other_n)[0].circuit,
                                        outcome['result']['completed'][0])
                        self.assertEqual(saved['selection_before_run'], record['selection'])
                        self.assertEqual(saved['source_provenance']['kind'], 'recorded')
                        self.assertEqual(saved['source_provenance']['execution_kind'], 'injected_callback')
                        self.assertFalse(outcome['rf_compliance_certified'])
                        self.assertEqual(outcome['preservation'],
                            'awaiting_git_readback' if codes and codes[-1] != 'source'
                            else 'preservation_incomplete')
                        if codes:
                            staged = outcome['staged_record']
                            self.assertEqual(len(staged['stage_calls']), len(codes))
                            self.assertEqual(staged['stage_calls'][0]['input_vector'],
                                             list(outcome['seed_record']['vector']))
                            self.assertIn('grid_sha256', staged['grids']['fine'])
                            self.assertGreaterEqual(staged['elapsed_seconds'], 0)
                            if codes[-1] == 'interrupt':
                                self.assertEqual(saved['termination']['type'], 'KeyboardInterrupt')
                            if codes[-1] in ('parts', 'h2'):
                                self.assertEqual(saved['selected_candidate_count'], 0)
                            if codes == (0, 'stop'):
                                self.assertEqual(saved['termination']['type'], '_Stopped')
                                self.assertEqual(len(saved['callback_returns']), 2)
                            if codes == (0, 0):
                                with patch('scripts.run_phase2_one_start.tracked_file',
                                           side_effect=ValueError('fixture readback failure')):
                                    with self.assertRaisesRegex(ValueError, 'readback failure'):
                                        finalize_one_start(repo, ident)
                                incomplete = json.loads((run / 'storage_record.json').read_text())
                                self.assertEqual(incomplete['stage'], 'preservation_incomplete')
                                self.assertEqual(incomplete['git_readback'], 'not_run')
                                self.assertTrue((repo / 'results' / ident / 'run.json').exists())
                            if codes[-1] == 'source':
                                self.assertEqual(saved['attempts']['not_started'], 0)
                                self.assertIsNotNone(saved['partial_staged_record'])
                                with self.assertRaises(ValueError):
                                    finalize_one_start(repo, ident)
                            else:
                                report = finalize_one_start(repo, ident)
                                self.assertTrue(report['committed_readback'])
                                self.assertEqual(report['independent_validation'], 'not_run')
                                if enumerated:
                                    stored = json.loads((run / 'storage_record.json').read_text())
                                    self.assertEqual(len(stored['checkpoints']), 1)
                                    cp = stored['checkpoints'][0]
                                    self.assertEqual(json.loads(subprocess.check_output(
                                        ['git', 'show', 'HEAD:' + cp['path']], cwd=repo)), checkpoint)
                                final_head = git('rev-parse', 'HEAD')
                                self.assertEqual(finalize_one_start(repo, ident), report)
                                self.assertEqual(git('rev-parse', 'HEAD'), final_head)
                            for ref in json.loads((run / 'manifest.json').read_text())['evidence']:
                                if codes[-1] != 'source':
                                    self.assertEqual(subprocess.check_output(['git', 'show', 'HEAD:' + ref['path']],
                                        cwd=repo), (repo / ref['path']).read_bytes())
                        else:
                            with self.assertRaises(ValueError):
                                finalize_one_start(repo, ident)
                        self.assertTrue((repo / 'results' / ident / 'run.json').exists())
                        with self.assertRaises(ValueError):
                            run_one_start(repo, ident, **args, **start_args, optimize_stage=solver)
                        git('reset', '--hard', planned_head)
                        # Only disposable TemporaryDirectory fixture outputs are removed.
                        shutil.rmtree(repo / 'results')
                        git('clean', '-fd', '--', str(run.relative_to(repo)))
                        h2_bad[0] = False
                for change in ({'seed': 24}, {'vector': vector[:-1]}, {'fine_points': 3},
                               {'budget': budget | {'policy_id': 'bad'}}, {'owner': 'wrong'},
                               {'source_sha': '0' * 40}, {'input_sha256': '0' * 64},
                               {'policy_sha256': '0' * 64},
                               {'circuit': make('RF-T008' if policy == 'RF-T005' else 'RF-T005', n)[0].circuit},
                               {'circuit': make(policy, 4 if n == 3 else 3)[0].circuit}):
                    with self.subTest(driver_rejection=change), self.assertRaises((ValueError, subprocess.CalledProcessError)):
                        run_one_start(repo, ident, **(args | start_args | change),
                                      optimize_stage=lambda *a: self.fail('solver called'))
                minimize.assert_not_called()
            if enumerated:
                return  # The legacy fixture below owns the exhaustive stop/failure regressions.
            # A fixture-only adapter links the *same* checked manifest input to
            # the existing C1/C2 and #207 classifier. It is not a production entry.
            from lpf.phase2_models.staged_optimization import run_c1_staged
            from lpf.phase2_models.candidate_records import record_candidate
            from lpf.phase2_models.synthetic_runner import checked_one_start_selection, diagnostic_selection
            from lpf.phase2_models.synthetic_plan import _source
            from scripts.audit_new_experiment_storage import validate_selection, validate_summary
            def fixture_preview(params, callback, *, stopped=False, preflight_args=args):
                prepared = prepare_one_start(repo, ident, **preflight_args, **params)
                self.assertEqual(prepared['status'], 'preflight_ready')
                self.assertEqual(prepared['execution'], 'not_run')
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
                return {**preview, 'result': result, 'mode': 'isolated_fixture_mock_non_exp',
                        'reservation': 'fixture_only',
                        'execution_allowed': False, 'experiment_execution': 'not_run',
                        'finite_grid_rf': 'synthetic_observation_not_certified',
                        'independent_mna': 'not_run', 'dense_rf': 'not_run',
                        'git_readback': 'not_run', 'candidate_promotion_blocked': True}

            previews = []
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
                        previews.append(preview)
                        self.assertEqual(preview['run_summary']['attempts'][state], 1)
                        self.assertNotIn('owner_approval', preview)
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
                previews.append(infeasible)
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
                           {'policy_id': 'RF-F003'}, {'policy_id': 'RF-T006'}, {'allow_trial': False},
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
            # Connect the SAME preflight-bound mock results, not handmade outcomes.
            # This adapter writes only inside TemporaryDirectory; no production exporter.
            from scripts.audit_new_experiment_storage import tracked_file, validate_run
            def package(preview):
                actual = checked_one_start_selection(preview['result'])
                if any(preview[k] != actual[k] for k in actual):
                    raise ValueError('Contradictory selection/counts/diagnostics')
                rows = {r['candidate_id']: r for r in preview['result']['completed']}
                for row in rows.values():
                    if (row['seed_record']['input_vector'] != input_source['vector'] or
                            row['seed_record']['seed'] != manifest['random_seed'] or
                            row['source_provenance']['value']['input_source_sha256'] != input_sha or
                            row['policy_id'] != manifest['constraints']['constraint_id'] or
                            row['policy_sha256'] != args['policy_sha256']):
                        raise ValueError('Candidate differs from bound manifest input/source/RF')
                checkpoints = [(item, fixture_checkpoint(problem.circuit, rows[item['candidate_id']]))
                               for item in actual['selected']]
                summary = deepcopy(actual['run_summary'])
                summary.update(experiment_id=ident, pareto=actual['pareto'], selected=actual['selected'],
                    excluded_records=[r for cid, r in rows.items()
                                      if cid not in actual['run_summary']['best_found']])
                summary['limitations'] = [
                    'Temporary isolated Git fixture only; not a real EXP.',
                    'Mock finite-grid observations, not RF certification or real SciPy execution.',
                    'Independent MNA/power/dense RF/continuous frequency/physical validation not_run.']
                validate_summary(summary, ident, len(checkpoints))
                m, storage = deepcopy(manifest), deepcopy(record)
                counts = summary['attempts']
                m['execution']['status'] = ('not_run' if counts['not_started'] else
                    'failed' if counts['failed'] else 'completed')
                # Existing policy cannot finalize an unexecuted run. Preserve the
                # unstarted summary as incomplete instead of inventing execution.
                storage['stage'] = 'preservation_incomplete' if counts['not_started'] else 'running'
                m['limitations'] = storage['limitations'] = summary['limitations']
                self.assertEqual(m['validation']['independent'], 'not_run')
                self.assertEqual(m['validation']['numerical'], 'not_run')
                def save(path, body):
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text(json.dumps(body, sort_keys=True, allow_nan=False))
                    return {'path': str(path.relative_to(repo)),
                            'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
                # Previous subcases are isolated alternative outcomes of one fixture.
                for old in (run / 'checkpoints').glob('*.json'):
                    old.unlink()
                storage['checkpoints'] = [item | save(run / 'checkpoints' / (item['candidate_id'] + '.json'), body)
                                          for item, body in checkpoints]
                storage['summary'] = save(run / 'run_summary.json', summary)
                m['evidence'] = [storage['summary']] + [
                    {k: cp[k] for k in ('path', 'sha256')} for cp in storage['checkpoints']]
                save(run / 'manifest.json', m)
                save(run / 'storage_record.json', storage)
                git('add', '-A', str(run.relative_to(repo)))
                git('commit', '-qm', 'fixture mock evidence bytes')
                # Real readback of ALL evidence/core bytes precedes any passed flag.
                for ref in m['evidence'] + [{'path': str((run / name).relative_to(repo))}
                                           for name in ('manifest.json', 'storage_record.json')]:
                    tracked_file(repo, ref['path'], committed=True)
                if not counts['not_started']:
                    storage.update(stage='complete', git_readback='passed')
                    save(run / 'storage_record.json', storage)
                    git('add', str(run.relative_to(repo)))
                    git('commit', '-qm', 'fixture verified preservation state')
                git('push', '-q', 'origin', 'main')
                return m, storage, summary

            with patch('lpf.phase2_models.coupled_lc.CoupledLCEvaluator.il', fake_il), \
                 patch('lpf.phase2_models.staged_optimization.minimize',
                       side_effect=AssertionError('solver forbidden')) as minimize:
                # Reject contradictions BEFORE writing, not by correcting the preview.
                for field, change in (
                    ('selected', [{'candidate_id': 'missing', 'selection_reason': 'pareto'}]),
                    ('selected', [{'candidate_id': 'fixture', 'selection_reason': 'best'}]),
                    ('run_summary', previews[0]['run_summary'] | {'selected_candidate_count': 0})):
                    with self.subTest(inconsistent=field), self.assertRaises(ValueError):
                        package(previews[0] | {field: change})
                for mutation in ('settings', 'rf', 'source', 'sha', 'missing'):
                    bad = deepcopy(previews[0])
                    row = bad['result']['completed'][0]
                    if mutation == 'settings':
                        row['values']['capacitors_pf_by_setting'].pop()
                    elif mutation == 'rf':
                        row['policy_sha256'] = '0' * 64
                    elif mutation == 'source':
                        row['source_provenance']['value']['input_source_sha256'] = '0' * 64
                    elif mutation == 'sha':
                        row['vector_sha256'] = '0' * 64
                    else:
                        bad['result']['completed'] = []
                    with self.subTest(candidate=mutation), self.assertRaises(ValueError):
                        package(bad)
                for index, preview in enumerate(previews[1:] + previews[:1]):
                    harmonic_failure[0] = preview is infeasible
                    with self.subTest(preserved=index):
                        m, storage, summary = package(preview)
                        self.assertGreater(storage['selection']['estimated_curated_bytes'], 0)
                        self.assertEqual(storage['selection'], record['selection'])
                        self.assertEqual(summary['attempts'], preview['run_summary']['attempts'])
                        self.assertEqual(summary['pareto'], preview['pareto'])
                        self.assertEqual(summary['selected_candidate_count'], len(storage['checkpoints']))
                        self.assertEqual(summary['experiment_id'], ident)
                        mode = 'audit' if summary['attempts']['not_started'] else 'finalize'
                        preserved = storage_audit(repo, mode, ident if mode == 'finalize' else None)
                        report = (preserved['result'] if mode == 'finalize' else preserved['result'][0])
                        self.assertEqual(report['independent_validation'], 'not_run')
                        self.assertEqual(report['numerical_validation'], 'not_run')
                        if mode == 'finalize':
                            self.assertTrue(report['committed_readback'])
                            self.assertGreater(report['curated_bytes'], 0)
                            self.assertLessEqual(report['curated_bytes'], 524288)
                        else:
                            self.assertEqual(storage['git_readback'], 'not_run')
                            with self.assertRaises(ValueError):
                                storage_audit(repo, 'finalize', ident)
                        for ref in m['evidence']:
                            self.assertEqual(git('show', 'HEAD:' + ref['path']),
                                             (repo / ref['path']).read_text())
                        for cp in storage['checkpoints']:
                            payload = json.loads(git('show', 'HEAD:' + cp['path']))
                            original = preview['result']['completed'][0]
                            self.assertEqual(payload, fixture_checkpoint(problem.circuit, original))
                            self.assertEqual(payload['ic_variable_C_pf_by_setting'],
                                {case: row[2:] for case, row in zip(CASES,
                                    original['values']['capacitors_pf_by_setting'])})
                        saved_summary = json.loads(git('show', 'HEAD:' + storage['summary']['path']))
                        self.assertEqual(saved_summary, summary)
                minimize.assert_not_called()

            # Existing audit must reject real committed-package damage; raw is never deleted.
            baseline = git('rev-parse', 'HEAD')
            summary_path = run / 'run_summary.json'
            for damage in ('missing', 'tampered', 'sha', 'count', 'settings', 'id',
                           'unclassified', 'duplicate'):
                with self.subTest(damage=damage):
                    if damage == 'missing':
                        summary_path.unlink()
                    elif damage == 'tampered':
                        summary_path.write_text('tampered')
                    elif damage == 'sha':
                        storage['summary']['sha256'] = '0' * 64
                        (run / 'storage_record.json').write_text(json.dumps(storage))
                    elif damage == 'count':
                        summary['selected_candidate_count'] = 0
                        summary_path.write_text(json.dumps(summary))
                        ref = {'path': storage['summary']['path'],
                               'sha256': hashlib.sha256(summary_path.read_bytes()).hexdigest()}
                        storage['summary'] = ref
                        m['evidence'] = [ref] + m['evidence'][1:]
                        (run / 'manifest.json').write_text(json.dumps(m))
                        (run / 'storage_record.json').write_text(json.dumps(storage))
                    elif damage in ('settings', 'id'):
                        cp = storage['checkpoints'][0]
                        path = repo / cp['path']
                        payload = json.loads(path.read_text())
                        if damage == 'settings':
                            del payload['ic_variable_C_pf_by_setting']['B8']
                        else:
                            payload['candidate_id'] = 'wrong'
                        path.write_text(json.dumps(payload))
                        cp['sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
                        m['evidence'][1] = {k: cp[k] for k in ('path', 'sha256')}
                        (run / 'manifest.json').write_text(json.dumps(m))
                        (run / 'storage_record.json').write_text(json.dumps(storage))
                    else:
                        orphan = run / 'orphan.json'
                        orphan.write_bytes(summary_path.read_bytes() if damage == 'duplicate' else b'{}')
                        if damage == 'duplicate':
                            ref = {'path': str(orphan.relative_to(repo)),
                                   'sha256': hashlib.sha256(orphan.read_bytes()).hexdigest()}
                            m['evidence'].append(ref)
                            storage['supporting_evidence'] = [ref | {
                                'role': 'method_note', 'reason': 'deliberate duplicate negative'}]
                            (run / 'manifest.json').write_text(json.dumps(m))
                            (run / 'storage_record.json').write_text(json.dumps(storage))
                    if damage not in ('missing', 'tampered'):
                        git('add', '-A', str(run.relative_to(repo)))
                        git('commit', '-qm', 'fixture deliberate damage')
                    with self.assertRaises(ValueError):
                        validate_run(repo, ident, mode='finalize')
                    git('reset', '--hard', baseline)
                    m = json.loads((run / 'manifest.json').read_text())
                    storage = json.loads((run / 'storage_record.json').read_text())
                    summary = json.loads(summary_path.read_text())


class FrozenConfigTests(unittest.TestCase):
    """Reusable YAML/dispatch contracts, never real SciPy or a scientific EXP."""

    def fixture(self, root):
        import yaml
        from lpf.phase2_models.sampled_epigraph import SampledEpigraph
        from lpf.phase2_models.problem_seed import definition_fingerprint
        from lpf.phase2_models.experiment_config import stable_identity
        from lpf.checkpoint_io import atomic_write_json
        p, x = make('RF-T008', 4)
        p = SampledEpigraph(p.circuit, 2)
        circuit = p.circuit
        actual, logical = [], []
        for i, seed in enumerate((23, 24, 25)):
            vector = x.copy()
            vector[0] += i * .1
            sha = vector_fingerprint(vector)
            record = p.seed(vector, policy_id=circuit.policy_id,
                policy_fingerprint=circuit.policy_fingerprint,
                definition_sha256=definition_fingerprint(circuit.definition), input_sha256=sha,
                seed=seed, jitter_fraction=0)
            record = json.loads(json.dumps(record))
            actual.append(dict(id=f's{i}', start=dict(vector=vector.tolist(), vector_sha256=sha,
                seed_record=record, policy_id=circuit.policy_id, policy_sha256=circuit.policy_fingerprint,
                definition_sha256=definition_fingerprint(circuit.definition),
                schema_sha256=canonical_config_hash(asdict(circuit.schema)), jitter_fraction=0)))
            logical.append(dict(id=f'logical-{i}', method='M', seed=seed,
                                actual_start_id=f's{i}', vector_sha256=sha))
        # One shared nominal reference, with no additional actual computation.
        logical.append(dict(id='common', method='common', seed=None,
            actual_start_id='s0', vector_sha256=actual[0]['start']['vector_sha256']))
        config = dict(schema_version=1, rf=dict(id=circuit.policy_id,
            effective_sha256=circuit.policy_fingerprint, allow_trial=True), objective='full_lpf',
            definition_sha256=definition_fingerprint(circuit.definition),
            plan=dict(path='results/plan.json', sha256='0' * 64), iteration_policy_id='slsqp-staged-v2',
            grids=dict(coarse_points=2, fine_points=3), samples_per_start=1_500_000,
            seeds=[23, 24, 25], methods=['M'], pilot_seeds=[23, 24],
            selection=dict(intermediate_points=17, dense_points=1001, independent_points=3, top_k_per_method=5),
            budgets=dict(logical_starts=4, actual_starts=3, stages=16, optimization_samples=6_000_000,
                screen_forwards=1, screen_samples=56, intermediate_samples=1904, dense_samples=28028))
        limits = dict(max_starts=4, max_stages=16, max_samples_per_start=1_500_000,
            max_optimization_samples=6_000_000, max_screen_forwards=1, max_screen_samples=56,
            max_intermediate_samples=1904, max_dense_samples=28028, top_k_per_method=5,
            coarse_points=2, fine_points=3, coarse_maxiter=240, fine_maxiter=120,
            rescue_coarse_maxiter=500, rescue_fine_maxiter=280, max_stages_per_start=4,
            iteration_policy_id='slsqp-staged-v2')
        source = dict(policy_id=circuit.policy_id, policy_sha256=circuit.policy_fingerprint,
            objective='full_lpf', definition=asdict(circuit.definition), definition_sha256=config['definition_sha256'],
            seeds=[23, 24, 25], pilot_seeds=[23, 24], actual_starts=actual, logical_starts=logical,
            limits=limits, screen_cost=dict(RF_forward_calls=0, frequency_samples_requested=0,
                                           wall_seconds=1, cpu_seconds=2))
        digest = canonical_config_hash(stable_identity(json.loads(json.dumps(source))))
        config['plan']['sha256'] = digest
        atomic_write_json(root / 'results/plan.json', dict(input_source=source, input_source_sha256=digest))
        path = root / 'results/config.yaml'
        path.write_text(yaml.safe_dump(config))
        return path, config, circuit

    def explicit_fixture(self, root):
        import yaml
        from lpf.phase2_models.experiment_config import stable_identity
        path, config, circuit = self.fixture(root)
        plan_path = root / config['plan']['path']
        envelope = json.loads(plan_path.read_text())
        source = envelope['input_source']
        actual, logical = [], []
        for row, seed in zip(source['actual_starts'][:2], (23, 24)):
            ref_path = root / f'source-{seed}.json'
            ref_path.write_text(json.dumps({k: row['start'][k] for k in ('vector', 'vector_sha256')}))
            ref = dict(path=ref_path.name, sha256=hashlib.sha256(ref_path.read_bytes()).hexdigest(),
                       vector_sha256=row['start']['vector_sha256'])
            for mode in ('physical', 'normalized'):
                ident = f'{seed}-{mode}'
                actual.append(dict(id=ident, start=deepcopy(row['start']), coordinates=mode, source_ref=ref))
                logical.append(dict(id=ident, seed=seed, method=mode,
                    vector_sha256=ref['vector_sha256'], actual_start_id=ident))
        config.update(schema_version=2, seeds=[23, 24], pilot_seeds=[23], methods=['physical', 'normalized'])
        config['budgets']['actual_starts'] = 4
        source.update(seeds=[23, 24], pilot_seeds=[23], actual_starts=actual, logical_starts=logical)
        def save():
            digest = canonical_config_hash(stable_identity(source))
            envelope['input_source_sha256'] = config['plan']['sha256'] = digest
            plan_path.write_text(json.dumps(envelope))
            path.write_text(yaml.safe_dump(config))
        save()
        return path, config, circuit, source, save

    def exchange_fixture(self, root):
        path, config, circuit, source, save = self.explicit_fixture(root)
        raw_source = {'executable_plan': {'actual_starts': []}}
        for seed, row in zip((23, 24), source['actual_starts'][::2]):
            raw_source['executable_plan']['actual_starts'].append(
                dict(id=str(seed), seed_record=row['start']['seed_record']))
        body = {'input_source': raw_source, 'completed': {}}
        summary = {'actual_results': {}}
        for seed, row in zip((23, 24), source['actual_starts'][::2]):
            final = row['start']['seed_record']['vector']
            body['completed'][str(seed)] = {'staged_record': {'stage_calls': [{'output_vector': final}]}}
            summary['actual_results'][str(seed)] = dict(
                seed_ref=dict(actual_start_id=str(seed), input_source_sha256=canonical_config_hash(raw_source),
                              seed_record_sha256=canonical_config_hash(row['start']['seed_record'])),
                stage_calls=[dict(output_vector=final)])
        raw_path, summary_path = root / 'raw.json', root / 'summary.json'
        raw_path.write_text(json.dumps(dict(body=body, sha256=canonical_config_hash(body))))
        summary_path.write_text(json.dumps(summary))
        for i, row in enumerate(source['actual_starts']):
            seed = (23, 24)[i // 2]
            row['method'] = ('baseline', 'exchange')[i % 2]
            row['coordinates'] = 'physical'
            row['source_ref'].update(raw_path='raw.json', raw_sha256=hashlib.sha256(raw_path.read_bytes()).hexdigest(),
                summary_path='summary.json', summary_sha256=hashlib.sha256(summary_path.read_bytes()).hexdigest(),
                actual_id=str(seed))
        for i, row in enumerate(source['logical_starts']):
            row['method'] = ('baseline', 'exchange')[i % 2]
        config.update(schema_version=3, methods=['baseline', 'exchange'],
            frequency_exchange=dict(mode='opt_in', scan_points=17, max_additions=4, max_rounds=3))
        config['budgets']['stages'] = source['limits']['max_stages'] = 32
        source['limits']['max_stages_per_start'] = 12
        save()
        return path, config, circuit, source, save

    def test_preparation_requires_reviewed_main_before_any_forward(self):
        from scripts.run_phase2_shared import prepare_continuation_plan
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            subprocess.check_call(['git', 'init', '-q', '-b', 'main', root])
            subprocess.check_call(['git', 'config', 'user.name', 'Fixture'], cwd=root)
            subprocess.check_call(['git', 'config', 'user.email', 'fixture@example.invalid'], cwd=root)
            (root / 'README').write_text('fixture')
            subprocess.check_call(['git', 'add', 'README'], cwd=root)
            subprocess.check_call(['git', 'commit', '-qm', 'fixture'], cwd=root)
            with patch('scripts.run_phase2_shared._complete_checkout'), \
                 patch('scripts.run_phase2_shared._fresh_main', return_value='0' * 40), \
                 patch('lpf.phase2_models.multistart.generate_starts', side_effect=AssertionError('forward')):
                with self.assertRaisesRegex(ValueError, 'reviewed origin/main'):
                    prepare_continuation_plan(root, 'missing.yaml', 'EXP-999')

    def test_preparation_marker_and_no_retry_in_temporary_checkout(self):
        from scripts.run_phase2_shared import prepare_continuation_plan
        from lpf.phase2_models.experiment_config import ContinuationPreparationError
        ref = ROOT / 'experiments/chatgpt_topology_search/runs/EXP-062/checkpoints/a6_best.json'
        if not ref.exists():
            self.skipTest('Complete historical evidence checkout required')
        for fails in (False, True):
            with self.subTest(fails=fails), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                subprocess.check_call(['git', 'init', '-q', '-b', 'main', root])
                subprocess.check_call(['git', 'config', 'user.name', 'Fixture'], cwd=root)
                subprocess.check_call(['git', 'config', 'user.email', 'fixture@example.invalid'], cwd=root)
                (root / '.gitignore').write_text('results/\n')
                for name in ('project/experiments/issue270.yaml', 'project/experiments/issue270-definition.json',
                             'experiments/chatgpt_topology_search/runs/EXP-062/checkpoints/a6_best.json'):
                    target = root / name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(ROOT / name, target)
                (root / 'src').mkdir()
                (root / 'src/mock.py').write_text('# fixture\n')
                subprocess.check_call(['git', 'add', '.'], cwd=root)
                subprocess.check_call(['git', 'commit', '-qm', 'fixture'], cwd=root)
                head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip()
                subprocess.check_call(['git', 'update-ref', 'refs/remotes/origin/main', head], cwd=root)
                fake = dict(input_source=dict(screen_cost={'frequency_samples_requested': 112},
                    initialization_timing=dict(elapsed_wall_s=1., elapsed_cpu_s=1.)))
                failure = ContinuationPreparationError(ValueError('no start'), {'frequency_samples_requested': 56},
                                                        {'elapsed_wall_s': 1., 'elapsed_cpu_s': 1.})
                with patch('scripts.run_phase2_shared._complete_checkout'), \
                     patch('scripts.run_phase2_shared._fresh_main', return_value=head), \
                     patch('scripts.experiment_id_registry.is_reserved_on_main', return_value={'constraint_id': 'RF-T008'}), \
                     patch('lpf.phase2_models.experiment_config.prepare_continuation_starts',
                           side_effect=failure if fails else None, return_value=deepcopy(fake)), \
                     patch.dict(os.environ, {k: '1' for k in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS')}):
                    if fails:
                        with self.assertRaises(ContinuationPreparationError):
                            prepare_continuation_plan(root, 'project/experiments/issue270.yaml', 'EXP-999')
                    else:
                        result = prepare_continuation_plan(root, 'project/experiments/issue270.yaml', 'EXP-999')
                        self.assertEqual(result['execution'], 'not_run')
                    saved = json.loads((root / 'results/issue270/starts.json').read_text())
                    if fails:
                        self.assertEqual(saved['state'], 'failed')
                        self.assertEqual(saved['initialization_cost']['frequency_samples_requested'], 56)
                    else:
                        self.assertEqual(saved['input_source']['preparation_source']['git_head'], head)
                    with self.assertRaisesRegex(ValueError, 'never overwrite'):
                        prepare_continuation_plan(root, 'project/experiments/issue270.yaml', 'EXP-999')

    def test_continuation_reference_definition_matches_historical_structure_only(self):
        import yaml
        from lpf.phase2_models.experiment_config import _check_continuation_reference
        from scripts.prepare_issue250_comparison import comparison_circuit
        config = yaml.safe_load((ROOT / 'project/experiments/issue270.yaml').read_text())
        if not (ROOT / config['topology_reference']['path']).exists():
            self.skipTest('Complete historical evidence checkout required')
        with patch('lpf.phase2_models.coupled_lc.CoupledLCEvaluator.il', side_effect=AssertionError('RF')):
            _check_continuation_reference(ROOT, config, comparison_circuit())
        config['topology_reference']['sha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'path/SHA'):
            _check_continuation_reference(ROOT, config, comparison_circuit())

    def test_continuation_plan_mock_dispatch_and_fail_closed(self):
        import yaml
        from lpf.phase2_models.experiment_config import load_plan, stable_identity
        from lpf.phase2_models.experiment_run import run_plan
        from lpf.phase2_models.multistart import generate_starts
        from lpf.phase2_models.sampled_epigraph import SampledEpigraph
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            subprocess.check_call(['git', 'init', '-q', root])
            (root / '.gitignore').write_text('results/\n')
            path, config, circuit = self.fixture(root)
            plan_path = root / config['plan']['path']
            envelope = json.loads(plan_path.read_text())
            source = envelope['input_source']
            from lpf.phase2_models.problem_seed import circuit_box
            nominal = np.asarray(circuit_box(circuit).bounds[:-1], float).mean(axis=1)
            starts = generate_starts(SampledEpigraph(circuit, 2), nominal, seed=23, count=2)['starts']
            actual, logical = [], []
            for i, start in enumerate(starts):
                kind = ('nominal', 'sobol')[i]
                count = i + 1
                ref = dict(kind=kind, seed=23, sobol_index=start['sobol_index'],
                    vector_sha256=start['vector_sha256'], initialization_cost=dict(
                        RF_forward_calls=count, frequency_samples_requested=count * 56,
                        frequency_samples_completed=count * 56))
                for method in ('A', 'B', 'C', 'D'):
                    key = f'{kind}-{method}'
                    actual.append(dict(id=key, start=start, method=method,
                                       coordinates='physical', source_ref=ref))
                    logical.append(dict(id=key, method=method, seed=(0 if i == 0 else 23),
                                        actual_start_id=key, vector_sha256=start['vector_sha256']))
            definition_path = root / 'definition.json'
            definition_path.write_text(json.dumps(asdict(circuit.definition)))
            d = circuit.definition
            reference_path = root / 'reference.json'
            reference_path.write_text(json.dumps(dict(topology=dict(
                L_edges=d.inductor_tree.edges,
                fixed_GJM_edges=[e for e, kind in zip(d.capacitor_placement.fixed_edges, d.fixed_c_types) if kind == 'GJM01'],
                PCB_C_edges=[e for e, kind in zip(d.capacitor_placement.fixed_edges, d.fixed_c_types) if kind == 'PCB_PATTERN_C'],
                variable_C_edges=d.capacitor_placement.variable_edges,
                IC_fixed_C_parallel_edges=d.capacitor_placement.ic_fixed_edges),
                components=[{'type': kind} for kind in d.inductor_types],
                chip_row=[f'L{i}' for i in d.physical_order],
                couplings=[{'pair': [f'L{a}', f'L{b}']} for a, b in d.coupling_pairs])))
            config.update(schema_version=4, methods=['A', 'B', 'C', 'D'], seeds=[0, 23], pilot_seeds=[0],
                definition_source=dict(path='definition.json', sha256=hashlib.sha256(definition_path.read_bytes()).hexdigest()),
                topology_reference=dict(path='reference.json', sha256=hashlib.sha256(reference_path.read_bytes()).hexdigest()),
                continuation=dict(mode='opt_in', il_only_bands=['B8', 'B8+B71', 'all'],
                    thresholds_db=[10, 20, 25, 28], final_guard_db=30.005,
                    scan_points=17, max_additions=4, max_rounds=3))
            config['selection']['top_k_per_method'] = 2
            config['budgets'].update(logical_starts=8, actual_starts=8, stages=296,
                optimization_samples=12_000_000, screen_forwards=2, screen_samples=112,
                intermediate_samples=3808, dense_samples=224224)
            from lpf.phase2_models.evaluation_cost import EvaluationCost
            screen_cost = EvaluationCost().snapshot()
            screen_cost.update(RF_forward_calls=2, frequency_samples_requested=112,
                               frequency_samples_completed=112)
            source.update(seeds=[0, 23], pilot_seeds=[0], actual_starts=actual, logical_starts=logical,
                          screen_cost=screen_cost, initialization_timing=dict(elapsed_wall_s=0.1, elapsed_cpu_s=0.1),
                          preparation_source=dict(git_head='a' * 40, experiment_id='EXP-999', program_sha256='b' * 64,
                              definition_source=config['definition_source'], topology_reference=config['topology_reference']))
            source['limits'].update(max_starts=8, max_stages=296, max_stages_per_start=60,
                top_k_per_method=2, max_optimization_samples=12_000_000, max_screen_forwards=2, max_screen_samples=112,
                max_intermediate_samples=3808, max_dense_samples=224224)
            from lpf.phase2_models.experiment_config import prepare_continuation_starts
            prepared = prepare_continuation_starts(circuit, config)
            self.assertEqual([r['start']['vector_sha256'] for r in prepared['input_source']['actual_starts']],
                             [r['start']['vector_sha256'] for r in actual])
            self.assertEqual(prepared['input_source']['screen_cost']['frequency_samples_requested'], 112)
            self.assertFalse(prepared['rf_compliance_certified'])
            preparation_source = source['preparation_source']
            source.clear()
            source.update(prepared['input_source'])
            source['preparation_source'] = preparation_source
            def save():
                digest = canonical_config_hash(stable_identity(source))
                envelope['input_source_sha256'] = config['plan']['sha256'] = digest
                plan_path.write_text(json.dumps(envelope))
                path.write_text(yaml.safe_dump(config))
            save()
            with patch('lpf.phase2_models.coupled_lc.CoupledLCEvaluator.il', side_effect=AssertionError('RF')):
                loaded = load_plan(root, path)
                frozen = json.loads(json.dumps(loaded['input_source']))
                self.assertEqual(load_plan(root, path, frozen_input=frozen)['input_source'], frozen)
            self.assertEqual(len(loaded['actual']), 8)
            import lpf.phase2_models.experiment_run as runner
            from lpf.experiment_manifest import _environment, file_sha256
            from lpf.constraint_versions import rf_input_file
            shutil.copytree(ROOT / 'rf', root / 'rf')
            g1_run = root / 'g1-fixture'
            g1_run.mkdir()
            post = dict(schema='post-search-g1-1', selection_rule='all anchors', search_guard=True,
                        max_selected=8, separate17=3808, dense1001=224224,
                        independent_forward84=672, independent_mna84=672)
            manifest = dict(execution={'status': 'planned'}, objective='full_lpf',
                search_scope=dict(input_source=loaded['input_source'], input_source_sha256=loaded['input_source_sha256'],
                                  post_search_validation=post),
                constraints=dict(constraint_id='RF-T008', effective_constraint_sha256=circuit.policy_fingerprint),
                environment=_environment(), random_seed=23,
                code=dict(execution_sha='a' * 40, working_tree_dirty=False),
                bands_sha256=file_sha256(rf_input_file(root, circuit.resolved_policy['bands_file'])))
            storage = dict(stage='planned', selection=dict(top_k=2, retain=['other'],
                rule=runner.CONTINUATION_RETENTION_RULE, estimated_curated_bytes=8_000_000))
            def g1_git(repo, *args):
                if args[:1] == ('show',):
                    body = manifest if args[1].endswith('/manifest.json') else storage
                    return json.dumps(body).encode()
                return b''
            def sync_g1():
                (g1_run / 'manifest.json').write_text(json.dumps(manifest))
                (g1_run / 'storage_record.json').write_text(json.dumps(storage))
            sync_g1()
            from types import SimpleNamespace
            with patch('scripts.run_phase2_shared._complete_checkout'), \
                 patch('scripts.run_phase2_shared._fresh_main', return_value='a' * 40), \
                 patch('scripts.run_phase2_shared.exp_preflight'), \
                 patch('scripts.experiment_id_registry.is_reserved_on_main', return_value={'owner': 'fixture', 'request_id': 'fixture'}), \
                 patch('scripts.audit_new_experiment_storage.find_run', return_value=g1_run), \
                 patch('lpf.phase2_models.experiment_config.continuation_program_sha256', return_value='b' * 64), \
                 patch.object(runner, '_git', side_effect=g1_git), \
                 patch.object(runner.subprocess, 'run', return_value=SimpleNamespace(returncode=0)):
                runner._gate(root, 'EXP-999', loaded, resuming=False)
                manifest['random_seed'] = 0
                sync_g1()
                with self.assertRaisesRegex(ValueError, 'G1 frozen'):
                    runner._gate(root, 'EXP-999', loaded, resuming=False)
                manifest['random_seed'] = 23
                storage['selection']['rule'] = 'not the all-anchor rule'
                sync_g1()
                with self.assertRaisesRegex(ValueError, 'all-anchor retention'):
                    runner._gate(root, 'EXP-999', loaded, resuming=False)
                storage['selection']['rule'] = runner.CONTINUATION_RETENTION_RULE
                post['separate17'] = 1
                sync_g1()
                with self.assertRaisesRegex(ValueError, 'cover all eight'):
                    runner._gate(root, 'EXP-999', loaded, resuming=False)
            gate = dict(run=root / 'experiments/EXP-999', source_sha='a' * 40,
                        g1_sha256='b' * 64, manifest={}, storage={})
            def optimizer(problem, vector, maxiter, target, *, coordinates):
                return vector, dict(success=True, status=0, message='mock', nit=1, nfev=1)
            raw = root / 'results/EXP-999/run.json'
            actual_package = runner._package
            def mock_continuation(circuit, seed_record, *, method, cost_meter,
                                  source_provenance, optimize_stage, record_sink):
                numerical = 'not_converged' if method == 'C' else 'converged'
                staged = dict(seed=seed_record, numerical_state=numerical, exception=None,
                    controller=None, stage_calls=[], source_provenance=dict(state='provided', value=source_provenance),
                    definition_sha256=config['definition_sha256'], policy_fingerprint=circuit.policy_fingerprint)
                trace = dict(method=method, state='not_converged' if method == 'C' else 'completed', stages=[], final_stage=staged,
                    final_exchange=None, last_valid_vector=list(seed_record['vector']),
                    evaluation_cost=cost_meter.snapshot(), rf_compliance_certified=False)
                record_sink(trace)
                return trace
            with patch.object(runner, '_load_g1_plan', return_value=loaded), \
                 patch.object(runner, '_gate', return_value=gate), \
                 patch.object(runner, '_package'), patch.object(runner, '_candidate', return_value=None), \
                 patch.object(runner, 'run_c1_continuation', side_effect=mock_continuation):
                pilot = run_plan(root, path, 'EXP-999', 'pilot', optimize_stage=optimizer)
                self.assertEqual(len(pilot['completed']), 4)
                self.assertEqual(pilot['completed']['nominal-C']['staged_record']['numerical_state'], 'not_converged')
                final = run_plan(root, path, 'EXP-999', 'remaining', optimize_stage=optimizer)
                self.assertEqual(len(final['completed']), 8)
                for key, item in final['completed'].items():
                    self.assertEqual(item['continuation']['state'],
                                     'not_converged' if loaded['actual'][key]['method'] == 'C' else 'completed')
                    allocation = loaded['actual'][key]['source_ref']['initialization_cost']
                    self.assertGreaterEqual(item['staged_record']['evaluation_cost']['frequency_samples_requested'],
                                            allocation['frequency_samples_requested'])
                    curated = runner._curated_result(item, actual_start_id=key,
                                                     input_source=loaded['input_source'])
                    self.assertEqual(runner.restore_curated_result(curated, loaded['input_source']),
                                     runner._curated_result(item))
                before = raw.read_bytes()
                with patch('lpf.phase2_models.coupled_lc.CoupledLCEvaluator.il', side_effect=AssertionError('no-op')):
                    run_plan(root, path, 'EXP-999', 'remaining', optimize_stage=optimizer)
                self.assertEqual(raw.read_bytes(), before)
                gate['run'].mkdir(parents=True)
                gate['manifest'] = {'execution': {}}
                gate['storage'] = {'checkpoints': [], 'validation_overlays': []}
                with patch('scripts.audit_new_experiment_storage.validate_run'):
                    actual_package(root, gate, loaded, final, EvaluationCost())
                summary = json.loads((gate['run'] / 'run_summary.json').read_text())
                storage = json.loads((gate['run'] / 'storage_record.json').read_text())
                self.assertEqual(summary['attempts']['attempted'], 8)
                self.assertEqual(len(storage['checkpoints']), 8)
                self.assertTrue(all(item['selection_reason'] == 'other' for item in storage['checkpoints']))
                self.assertTrue(all('continuation' in row for row in summary['actual_results'].values()))
                costs = summary['costs']
                self.assertEqual(costs['allocated_initialization']['frequency_samples_requested'], 672)
                self.assertEqual(costs['initialization_actual']['frequency_samples_requested'], 112)
                self.assertEqual(costs['optimization_actual_excluding_initialization']['frequency_samples_requested'], 0)
                self.assertAlmostEqual(costs['allocated_initialization']['cpu_seconds'],
                    8 * costs['initialization_actual_timing']['elapsed_cpu_s'])
            def exhausted(circuit, seed_record, *, method, cost_meter, source_provenance,
                          optimize_stage, record_sink):
                trace = dict(method=method, state='budget_exhausted', stages=[], final_stage=None,
                    final_exchange=None, last_valid_vector=list(seed_record['vector']),
                    evaluation_cost=cost_meter.snapshot(), exception={'type': 'SampleBudgetExceeded', 'message': 'limit'},
                    rf_compliance_certified=False)
                record_sink(trace)
                return trace
            with patch.object(runner, '_load_g1_plan', return_value=loaded), \
                 patch.object(runner, '_gate', return_value=gate), patch.object(runner, '_package'), \
                 patch.object(runner, 'run_c1_continuation', side_effect=exhausted):
                raw_limited = root / 'results/EXP-998/run.json'
                limited = run_plan(root, path, 'EXP-998', 'pilot', optimize_stage=optimizer)
                self.assertEqual(len(limited['completed']), 4)
                for item in limited['completed'].values():
                    self.assertEqual(item['staged_record']['numerical_state'], 'budget_exhausted')
                    self.assertEqual(item['validation_anchor']['numerical']['state'], 'not_run')
                    self.assertIsNone(item['candidate'])
                before = raw_limited.read_bytes()
                with patch.object(runner, 'run_c1_continuation', side_effect=AssertionError('no dispatch')):
                    with self.assertRaisesRegex(ValueError, 'Pilot.*STOP.*budget_exhausted'):
                        run_plan(root, path, 'EXP-998', 'remaining', optimize_stage=optimizer)
                self.assertEqual(raw_limited.read_bytes(), before)
            def failed(*args, **kwargs):
                trace = exhausted(*args, **kwargs)
                trace.update(state='failed', exception=None)
                return trace
            with patch.object(runner, '_load_g1_plan', return_value=loaded), \
                 patch.object(runner, '_gate', return_value=gate), patch.object(runner, '_package'), \
                 patch.object(runner, 'run_c1_continuation', side_effect=failed):
                raw_failure = root / 'results/EXP-996/run.json'
                run_plan(root, path, 'EXP-996', 'pilot', optimize_stage=optimizer)
                before = raw_failure.read_bytes()
                with patch.object(runner, 'run_c1_continuation', side_effect=AssertionError('no dispatch')):
                    with self.assertRaisesRegex(ValueError, 'Pilot.*STOP.*failed'):
                        run_plan(root, path, 'EXP-996', 'remaining', optimize_stage=optimizer)
                self.assertEqual(raw_failure.read_bytes(), before)
            with patch.object(runner, '_load_g1_plan', return_value=loaded), \
                 patch.object(runner, '_gate', return_value=gate), patch.object(runner, '_package'), \
                 patch.object(runner, 'run_c1_continuation', side_effect=OSError('lost storage')):
                raw_failed = root / 'results/EXP-997/run.json'
                with self.assertRaises(OSError):
                    run_plan(root, path, 'EXP-997', 'pilot', optimize_stage=optimizer)
                self.assertIsNotNone(json.loads(raw_failed.read_text())['body']['in_progress'])
                with self.assertRaisesRegex(ValueError, 'Unknown in-progress'):
                    run_plan(root, path, 'EXP-997', 'pilot', optimize_stage=optimizer)
            source['actual_starts'][4]['source_ref']['sobol_index'] += 1
            save()
            with self.assertRaises(ValueError):
                load_plan(root, path)

    def test_exchange_plan_and_mock_dispatch(self):
        from lpf.phase2_models.experiment_config import load_plan
        from lpf.phase2_models.experiment_run import run_plan, _curated_result, restore_curated_result
        import lpf.phase2_models.experiment_run as runner
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            subprocess.check_call(['git', 'init', '-q', root])
            (root / '.gitignore').write_text('results/\n')
            path, config, _, source, save = self.exchange_fixture(root)
            loaded = load_plan(root, path)
            frozen = json.loads(json.dumps(loaded['input_source']))
            self.assertEqual(load_plan(root, path, frozen_input=frozen)['input_source'], frozen)
            calls = []
            def mock(p, x, budget, target, *, coordinates):
                calls.append((coordinates, p.points_per_interval))
                return x, dict(success=True, status=0, message='mock', nit=1, nfev=1)
            gate = dict(run=root / 'experiments/EXP-999', source_sha='a' * 40,
                        g1_sha256='b' * 64, manifest={}, storage={})
            actual_package = runner._package
            with patch.object(runner, '_gate', return_value=gate), \
                 patch.object(runner, '_load_g1_plan', return_value=loaded), \
                 patch.object(runner, '_package'):
                pilot = run_plan(root, path, 'EXP-999', 'pilot', optimize_stage=mock)
                self.assertEqual(len(pilot['completed']), 2)
                final = run_plan(root, path, 'EXP-999', 'remaining', optimize_stage=mock)
                self.assertEqual(len(final['completed']), 4)
                for key, result in final['completed'].items():
                    exchange = result['frequency_exchange']
                    self.assertLessEqual(len(exchange['rounds']), 1 if loaded['actual'][key]['method'] == 'baseline' else 3)
                    self.assertEqual(exchange['evaluation_cost'], result['staged_record']['evaluation_cost'])
                    curated = _curated_result(result, actual_start_id=key, input_source=loaded['input_source'])
                    self.assertEqual(restore_curated_result(curated, loaded['input_source']), _curated_result(result))
                self.assertTrue(all(c[0] == 'physical' for c in calls))
                from lpf.phase2_models.evaluation_cost import EvaluationCost
                gate['run'].mkdir(parents=True)
                gate['manifest'] = {'execution': {}}
                gate['storage'] = {'checkpoints': [], 'validation_overlays': []}
                with patch('scripts.audit_new_experiment_storage.validate_run'):
                    actual_package(root, gate, loaded, final, EvaluationCost())
                saved_summary = json.loads((gate['run'] / 'run_summary.json').read_text())
                self.assertEqual(saved_summary['attempts']['attempted'], 4)
                self.assertTrue(all('frequency_exchange' in v for v in saved_summary['actual_results'].values()))
                raw = root / 'results/EXP-999/run.json'
                before = raw.read_bytes()
                with patch('lpf.phase2_models.coupled_lc.CoupledLCEvaluator.il', side_effect=AssertionError('no-op')):
                    run_plan(root, path, 'EXP-999', 'remaining', optimize_stage=mock)
                self.assertEqual(raw.read_bytes(), before)
                def failed(*args, **kwargs):
                    raise ValueError('mock stage failure')
                with self.assertRaisesRegex(RuntimeError, 'Inner optimizer'):
                    run_plan(root, path, 'EXP-998', 'pilot', optimize_stage=failed)
                failed_raw = json.loads((root / 'results/EXP-998/run.json').read_text())['body']
                self.assertIsNotNone(failed_raw['in_progress'])
                self.assertEqual(failed_raw['exchange_record']['stop_reason'], 'failed')
                self.assertEqual(failed_raw['completed'], {})
                with self.assertRaisesRegex(ValueError, 'Unknown in-progress'):
                    run_plan(root, path, 'EXP-998', 'pilot', optimize_stage=mock)
                loaded['config']['samples_per_start'] = 476
                limited = run_plan(root, path, 'EXP-997', 'pilot', optimize_stage=mock)
                for item in limited['completed'].values():
                    self.assertEqual(item['staged_record']['numerical_state'], 'budget_exhausted')
                    self.assertEqual(item['frequency_exchange']['stop_reason'], 'budget_exhausted')
                    self.assertIsNone(item['candidate'])
                    self.assertEqual(item['staged_record']['evaluation_cost']['frequency_samples_requested'], 476)
                run_plan(root, path, 'EXP-997', 'pilot', optimize_stage=mock)
            source['actual_starts'][0]['source_ref']['raw_sha256'] = '0' * 64
            source['actual_starts'][1]['source_ref']['raw_sha256'] = '0' * 64
            save()
            with self.assertRaisesRegex(ValueError, 'raw/curated'):
                load_plan(root, path)
            raw_path = root / 'raw.json'
            raw = json.loads(raw_path.read_text())
            raw['body']['completed']['23']['staged_record']['stage_calls'][-1]['output_vector'][0] += 0.1
            raw['sha256'] = canonical_config_hash(raw['body'])
            raw_path.write_text(json.dumps(raw))
            for row in source['actual_starts'][:2]:
                row['source_ref']['raw_sha256'] = hashlib.sha256(raw_path.read_bytes()).hexdigest()
            save()
            with self.assertRaisesRegex(ValueError, 'raw/curated final vector'):
                load_plan(root, path)

    def test_explicit_coordinate_pairs_portability_and_rejections(self):
        from lpf.phase2_models.experiment_config import load_plan
        from lpf.phase2_models.experiment_run import phase_ids
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path, config, _, source, save = self.explicit_fixture(root)
            loaded = load_plan(root, path)
            self.assertEqual(phase_ids(loaded, 'pilot'), ['23-physical', '23-normalized'])
            self.assertEqual(phase_ids(loaded, 'remaining'), ['24-physical', '24-normalized'])
            frozen = json.loads(json.dumps(loaded['input_source']))
            plan = root / config['plan']['path']
            before = plan.read_bytes()
            plan.unlink()
            with patch('lpf.phase2_models.coupled_lc.CoupledLCEvaluator.il', side_effect=AssertionError('static only')):
                self.assertEqual(load_plan(root, path, frozen_input=frozen)['input_source'], frozen)
            plan.write_bytes(before)
            for field, value in [('coordinates', 'physical'), ('coordinates', 'unknown')]:
                old = source['actual_starts'][1][field]
                source['actual_starts'][1][field] = value
                save()
                with self.assertRaises(ValueError):
                    load_plan(root, path)
                source['actual_starts'][1][field] = old
            save()
            (root / 'source-23.json').write_text('{}')
            with self.assertRaisesRegex(ValueError, 'source reference SHA'):
                load_plan(root, path, frozen_input=frozen)

    def test_explicit_mock_dispatch_preserves_four_arms_and_noop(self):
        from lpf.phase2_models.experiment_config import load_plan
        from lpf.phase2_models.experiment_run import run_plan, _curated_result, restore_curated_result
        import lpf.phase2_models.experiment_run as runner
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            subprocess.check_call(['git', 'init', '-q', root])
            (root / '.gitignore').write_text('results/\n')
            path, _, _, _, _ = self.explicit_fixture(root)
            loaded = load_plan(root, path)
            calls = []
            def mock(p, x, budget, target, *, coordinates):
                calls.append(coordinates)
                return x, dict(success=False, status=8, message='mock', nit=1, nfev=1)
            gate = dict(run=root / 'experiments/EXP-999', source_sha='a' * 40,
                        g1_sha256='b' * 64, manifest={}, storage={})
            with patch.object(runner, '_gate', return_value=gate), \
                 patch.object(runner, '_load_g1_plan', return_value=loaded), patch.object(runner, '_package'):
                run_plan(root, path, 'EXP-999', 'pilot', optimize_stage=mock)
                final = run_plan(root, path, 'EXP-999', 'remaining', optimize_stage=mock)
                self.assertEqual(calls, ['physical'] * 2 + ['normalized'] * 2 + ['physical'] * 2 + ['normalized'] * 2)
                self.assertEqual(len(final['completed']), 4)
                for key, result in final['completed'].items():
                    curated = _curated_result(result, actual_start_id=key, input_source=loaded['input_source'])
                    self.assertEqual(curated['coordinates'], loaded['actual'][key]['coordinates'])
                    self.assertEqual(restore_curated_result(curated, loaded['input_source']), _curated_result(result))
                raw = root / 'results/EXP-999/run.json'
                before = raw.read_bytes()
                with patch('lpf.phase2_models.coupled_lc.CoupledLCEvaluator.il', side_effect=AssertionError('no-op')):
                    run_plan(root, path, 'EXP-999', 'remaining', optimize_stage=mock)
                self.assertEqual(raw.read_bytes(), before)
                self.assertEqual(len(calls), 8)
                def failing(*args, **kwargs):
                    raise ValueError('explicit-arm exception')
                with self.assertRaisesRegex(RuntimeError, 'retain marker'):
                    run_plan(root, path, 'EXP-998', 'pilot', optimize_stage=failing)
                stopped = root / 'results/EXP-998/run.json'
                body = json.loads(stopped.read_text())['body']
                self.assertEqual(body['in_progress'], '23-physical')
                self.assertEqual(body['completed'], {})
                with self.assertRaisesRegex(ValueError, 'Unknown in-progress'):
                    run_plan(root, path, 'EXP-998', 'pilot', optimize_stage=mock)

    def test_yaml_read_only_hash_stability_and_invalid_inputs(self):
        import yaml
        from lpf.phase2_models.experiment_config import load_plan, plan_preview
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path, config, circuit = self.fixture(root)
            before = {p: p.read_bytes() for p in root.rglob('*') if p.is_file()}
            preview = plan_preview(root, path)
            self.assertEqual(before, {p: p.read_bytes() for p in root.rglob('*') if p.is_file()})
            self.assertEqual(preview['execution'], 'not_run')
            loaded = load_plan(root, path)
            self.assertEqual(len(loaded['actual']), 3)
            plan = root / 'results/plan.json'
            value = json.loads(plan.read_text())
            value['input_source']['screen_cost']['wall_seconds'] = 9999
            plan.write_text(json.dumps(value))
            self.assertEqual(loaded['input_source_sha256'], load_plan(root, path)['input_source_sha256'])
            for mutation in (
                lambda c: c.update(unknown=1), lambda c: c.update(schema_version=2),
                lambda c: c.update(seeds=[23, 23]), lambda c: c.update(samples_per_start=float('nan')),
                lambda c: c['rf'].update(id='RF-F003'), lambda c: c['plan'].update(sha256='a' * 64),
                lambda c: c['selection'].update(dense_points=-1)):
                bad = deepcopy(config)
                mutation(bad)
                path.write_text(yaml.safe_dump(bad))
                with self.assertRaises((ValueError, TypeError)):
                    load_plan(root, path)
            # Even a newly matching plan SHA cannot bless an illegal vector.
            from lpf.phase2_models.experiment_config import stable_identity
            bad_plan = deepcopy(value)
            start = bad_plan['input_source']['actual_starts'][0]['start']
            start['vector'][0] = -1.
            start['vector_sha256'] = vector_fingerprint(start['vector'])
            new_sha = canonical_config_hash(stable_identity(bad_plan['input_source']))
            bad_plan['input_source_sha256'] = new_sha
            bad_config = deepcopy(config)
            bad_config['plan']['sha256'] = new_sha
            plan.write_text(json.dumps(bad_plan))
            path.write_text(yaml.safe_dump(bad_config))
            with self.assertRaisesRegex(ValueError, 'outside policy box'):
                load_plan(root, path)
            path.write_text(yaml.safe_dump(config) + '\nschema_version: 1\n')
            with self.assertRaisesRegex(ValueError, 'Duplicate'):
                load_plan(root, path)

    def test_g1_complete_seed_input_without_preparation_or_rf(self):
        from lpf.phase2_models.experiment_config import load_plan
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path, config, _ = self.fixture(root)
            original = load_plan(root, path)
            frozen = json.loads(json.dumps(original['input_source']))
            (root / config['plan']['path']).unlink()
            with patch('lpf.phase2_models.coupled_lc.CoupledLCEvaluator.il',
                       side_effect=AssertionError('G1 static load must not evaluate RF')):
                portable = load_plan(root, path, frozen_input=frozen)
                self.assertEqual(portable['input_source_sha256'], original['input_source_sha256'])
                for key in original['actual']:
                    self.assertEqual(portable['actual'][key]['seed_record'], original['actual'][key]['seed_record'])
                corrupt = deepcopy(frozen)
                corrupt['executable_plan']['actual_starts'][0]['seed_record']['vector'][-1] += .1
                with self.assertRaisesRegex(ValueError, 'C1 seed record SHA mismatch'):
                    load_plan(root, path, frozen_input=corrupt)
                changed = deepcopy(frozen)
                changed['config_sha256'] = '0' * 64
                with self.assertRaisesRegex(ValueError, 'G1 config/plan SHA mismatch'):
                    load_plan(root, path, frozen_input=changed)

    def test_mock_phases_shared_mapping_restart_and_atomic_stop(self):
        from lpf.phase2_models.experiment_run import run_plan, phase_ids
        from lpf.phase2_models.experiment_config import load_plan
        import lpf.phase2_models.experiment_run as runner
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            subprocess.check_call(['git', 'init', '-q', root])
            (root / '.gitignore').write_text('results/\n')
            path, config, circuit = self.fixture(root)
            loaded = load_plan(root, path)
            self.assertEqual(phase_ids(loaded, 'pilot'), ['s0', 's1'])
            self.assertEqual(phase_ids(loaded, 'remaining'), ['s2'])
            calls = []
            def mock(p, x, budget, target):
                calls.append(budget)
                # Status4/8 is a result, not a global STOP or budget extension.
                return x, dict(success=False, status=4 if len(calls) % 2 else 8,
                               message='mock', nit=1, nfev=1)
            gate = dict(run=root / 'experiments/EXP-999', source_sha='a' * 40,
                        g1_sha256='b' * 64, manifest={}, storage={})
            with patch.object(runner, '_gate', return_value=gate), \
                 patch.object(runner, '_load_g1_plan', return_value=loaded), \
                 patch.object(runner, '_package') as package:
                with self.assertRaisesRegex(ValueError, 'Pilot'):
                    run_plan(root, path, 'EXP-999', 'remaining', optimize_stage=mock)
                pilot = run_plan(root, path, 'EXP-999', 'pilot', optimize_stage=mock)
                self.assertTrue(pilot['pilot_complete'])
                self.assertEqual(len(calls), 4)
                self.assertEqual(len(pilot['completed']), 2)
                raw = root / 'results/EXP-999/run.json'
                before = raw.read_bytes()
                package_count = package.call_count
                with patch('lpf.phase2_models.coupled_lc.CoupledLCEvaluator.il',
                           side_effect=AssertionError('completed phase must not evaluate RF')):
                    repeated = run_plan(root, path, 'EXP-999', 'pilot', optimize_stage=mock)
                self.assertEqual(json.loads(json.dumps(pilot)), repeated)
                self.assertEqual(raw.read_bytes(), before)
                self.assertEqual(package.call_count, package_count)
                self.assertEqual(len(calls), 4)  # completed results never dispatched twice
                final = run_plan(root, path, 'EXP-999', 'remaining', optimize_stage=mock)
                self.assertEqual(len(final['completed']), 3)
                self.assertEqual(len(calls), 6)
                self.assertTrue(package.called)
                for result in final['completed'].values():
                    self.assertEqual(result['staged_record']['numerical_state'], 'not_converged')
                    self.assertLessEqual(result['staged_record']['evaluation_cost']['frequency_samples_requested'], 1_500_000)
                # Simulate external termination after dispatch, with durable marker.
                raw = root / 'results/EXP-999/run.json'
                from lpf.phase2_models.experiment_run import _save
                final['in_progress'] = 's2'
                _save(raw, final)
                before = raw.read_bytes()
                with self.assertRaisesRegex(ValueError, 'Unknown in-progress'):
                    run_plan(root, path, 'EXP-999', 'remaining', optimize_stage=mock)
                self.assertEqual(raw.read_bytes(), before)
                self.assertEqual(len(calls), 6)

    def test_g1_opt_in_dispatch_and_curated_guard(self):
        from lpf.phase2_models.experiment_run import run_plan, _curated_result, restore_curated_result
        from lpf.phase2_models.experiment_config import load_plan
        import lpf.phase2_models.experiment_run as runner
        for enabled in (False, True):
            with self.subTest(enabled=enabled), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                subprocess.check_call(['git', 'init', '-q', root])
                (root / '.gitignore').write_text('results/\n')
                path, _, circuit = self.fixture(root)
                loaded = load_plan(root, path)
                scope = {'post_search_validation': {'search_guard': True}} if enabled else {}
                gate = dict(run=root / 'experiments/EXP-999', source_sha='a' * 40,
                            g1_sha256='b' * 64, manifest={'search_scope': scope}, storage={})
                observed = []
                def mock(problem, vector, budget, target):
                    observed.append((problem.mandatory_stop_db, problem.search_stop_db))
                    return vector, dict(success=True, status=0, message='mock', nit=0, nfev=0)
                with patch.object(runner, '_gate', return_value=gate), \
                     patch.object(runner, '_load_g1_plan', return_value=loaded), \
                     patch.object(runner, '_package'):
                    result = run_plan(root, path, 'EXP-999', 'pilot', optimize_stage=mock)
                self.assertTrue(observed)
                for mandatory, target in observed:
                    self.assertEqual(target, mandatory + (.005 if enabled else 0.))
                for key, row in result['completed'].items():
                    curated = _curated_result(row, actual_start_id=key, input_source=loaded['input_source'])
                    self.assertEqual('search_guard' in curated, enabled)
                    restored = restore_curated_result(curated, loaded['input_source'])
                    self.assertEqual(restored, _curated_result(row))

    def test_budget_exhaustion_partial_failure_and_interrupt_are_distinct(self):
        from lpf.phase2_models.experiment_run import run_plan
        from lpf.phase2_models.experiment_config import load_plan
        from lpf.phase2_models.evaluation_cost import SampleBudgetCost
        import lpf.phase2_models.experiment_run as runner
        for mode in ('budget', 'exception', 'interrupt', 'stop', 'storage'):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp)
                subprocess.check_call(['git', 'init', '-q', root])
                (root / '.gitignore').write_text('results/\n')
                path, _, _ = self.fixture(root)
                loaded = load_plan(root, path)
                gate = dict(run=root / 'experiments/EXP-999', source_sha='a' * 40,
                            g1_sha256='b' * 64, manifest={}, storage={})
                calls = []
                original_write = runner.atomic_write_json
                def write_snapshot(destination, payload):
                    if mode == 'storage' and payload['body']['staged_record'] is not None:
                        raise OSError('mock atomic storage failure')
                    return original_write(destination, payload)
                def solver(p, x, budget, target):
                    calls.append(budget)
                    if mode == 'budget':
                        p.residuals(x)
                    elif mode == 'exception':
                        raise RuntimeError('mock numerical exception')
                    elif mode == 'interrupt':
                        raise KeyboardInterrupt('external interruption')
                    else:
                        # A STOP arriving during the solver is a global stop.
                        (root / 'results/EXP-999/STOP').touch()
                    return x, dict(success=True, status=0, message='mock', nit=0, nfev=0)
                with patch.object(runner, '_gate', return_value=gate), patch.object(runner, '_package'), \
                     patch.object(runner, '_load_g1_plan', return_value=loaded), \
                     patch.object(runner, 'SampleBudgetCost', side_effect=lambda n: SampleBudgetCost(196)), \
                     patch.object(runner, 'atomic_write_json', side_effect=write_snapshot):
                    if mode in ('interrupt', 'stop', 'storage'):
                        with self.assertRaises((KeyboardInterrupt, ValueError, OSError)):
                            run_plan(root, path, 'EXP-999', 'pilot', optimize_stage=solver)
                        saved = json.loads((root / 'results/EXP-999/run.json').read_text())['body']
                        self.assertEqual(saved['in_progress'], 's0')
                        self.assertFalse(saved['completed'])
                        with self.assertRaisesRegex(ValueError, 'Unknown in-progress'):
                            run_plan(root, path, 'EXP-999', 'pilot', optimize_stage=solver)
                    else:
                        saved = run_plan(root, path, 'EXP-999', 'pilot', optimize_stage=solver)
                        self.assertEqual(len(saved['completed']), 2)
                        for result in saved['completed'].values():
                            staged = result['staged_record']
                            self.assertEqual(staged['numerical_state'],
                                             'budget_exhausted' if mode == 'budget' else 'failed')
                            self.assertIsNone(result['candidate'])
                            self.assertLessEqual(staged['evaluation_cost']['frequency_samples_requested'], 196)

    @patch('lpf.phase2_models.coupled_lc.CoupledLCEvaluator.il',
           lambda ev, x: np.where(ev.role == 0, .25, 36.))
    def test_multistart_real_remote_gate_storage_and_finalize(self):
        from lpf.phase2_models.experiment_config import load_plan
        from lpf.phase2_models.experiment_run import run_plan, _gate
        with tempfile.TemporaryDirectory() as tmp:
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
            for name in filter(None, names):
                p = Path(name.decode())
                (repo / p).parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT / p, repo / p)
            (repo / '.gitignore').write_text('results/\n__pycache__/\n*.pyc\n')
            path, config, circuit = self.fixture(repo)
            loaded = load_plan(repo, path)
            ledger = repo / PATH
            ledger.parent.mkdir(parents=True, exist_ok=True)
            rows = [dict(experiment_id=f'EXP-{n:03}', state='legacy_gap_retired' if n in (18, 19)
                         else 'legacy_recorded', owner='', request_id='', purpose='', constraint_id='',
                         reserved_at_utc='', origin='') for n in range(1, 50)]
            rows, ident, _ = next_reservation(rows, owner='fixture', purpose='mock only',
                request_id='fixture-multi', constraint_id='RF-T008', reserved_at_utc='2026-11-02T00:00:00Z')
            ledger.write_text(as_csv(rows))
            (repo / 'data/phase2_git_storage_budget.json').write_text(json.dumps(dict(thresholds=dict(
                individual_new_file_soft_bytes=131072, individual_new_file_hard_bytes=1048576,
                new_experiment_curated_soft_bytes=524288))))
            run = repo / 'experiments/chatgpt_topology_search/runs' / ident
            run.mkdir(parents=True)
            git('add', '.')
            git('commit', '-qm', 'fixture source and G0')
            git('push', '-qu', 'origin', 'main')
            manifest = new_manifest(ident, 'fixture multi mock only', dict(
                input_source=loaded['input_source'], input_source_sha256=loaded['input_source_sha256']),
                objective='full_lpf', seed=23, root=repo, constraint_id='RF-T008', allow_trial=True)
            storage = dict(schema_version=1, policy='phase2-git-only-v1', experiment_id=ident,
                phase='Phase 2', stage='planned', selection=dict(top_k=5, retain=['pareto'],
                    rule='Retain checked Pareto and all start status/vector diagnostics; mock only.',
                    estimated_curated_bytes=200000), summary=None, checkpoints=[], validation_overlays=[],
                git_readback='not_run', size_exception=None, limitations=[])
            (run / 'manifest.json').write_text(json.dumps(manifest))
            (run / 'storage_record.json').write_text(json.dumps(storage))
            git('add', '.')
            git('commit', '-qm', 'fixture G1')
            # Local planned evidence is insufficient before actual remote readback.
            with self.assertRaises((ValueError, subprocess.CalledProcessError)):
                _gate(repo, ident, loaded, resuming=False)
            git('push', '-q', 'origin', 'main')
            # Start from another complete checkout containing only remote G1
            # evidence and YAML: no ignored preparation plan or result files.
            portable_config = repo / 'fixture.yaml'
            shutil.copyfile(path, portable_config)
            git('add', 'fixture.yaml')
            git('commit', '-qm', 'fixture portable config')
            git('push', '-q', 'origin', 'main')
            fresh = Path(tmp) / 'fresh'
            git('clone', '-q', '--branch', 'main', remote, fresh)
            repo = fresh
            path = repo / 'fixture.yaml'
            run = repo / 'experiments/chatgpt_topology_search/runs' / ident
            self.assertFalse((repo / config['plan']['path']).exists())
            git('config', 'user.name', 'Fixture')
            git('config', 'user.email', 'fixture@example.invalid')
            checked = _gate(repo, ident, loaded, resuming=False)
            self.assertEqual(checked['source_sha'], manifest['code']['execution_sha'])
            calls = []
            def solver(p, x, budget, target):
                calls.append(budget)
                return x, dict(success=True, status=0, message='mock', nit=1, nfev=1)
            with patch('lpf.phase2_models.staged_optimization.minimize', side_effect=AssertionError('no SciPy')):
                pilot = run_plan(repo, path, ident, 'pilot', optimize_stage=solver)
                self.assertTrue(pilot['pilot_complete'])
                self.assertEqual(json.loads((run / 'manifest.json').read_text())['execution']['status'], 'running')
                # A repeated completed phase must be a byte-identical no-op,
                # including raw/summary/checkpoints/manifest/storage and costs.
                before = {p.relative_to(repo): p.read_bytes() for p in run.rglob('*') if p.is_file()}
                raw = repo / 'results' / ident / 'run.json'
                before[raw.relative_to(repo)] = raw.read_bytes()
                with patch('lpf.phase2_models.coupled_lc.CoupledLCEvaluator.il',
                           side_effect=AssertionError('no-op must not evaluate RF')):
                    repeated = run_plan(repo, path, ident, 'pilot', optimize_stage=solver)
                self.assertEqual(json.loads(json.dumps(pilot)), repeated)
                self.assertEqual(before, {p: (repo / p).read_bytes() for p in before})
                self.assertEqual(len(calls), 4)
                with self.assertRaisesRegex(ValueError, 'unfinalized preservation state'):
                    finalize_one_start(repo, ident)
                final = run_plan(repo, path, ident, 'remaining', optimize_stage=solver)
                self.assertEqual(len(final['completed']), 3)
                self.assertEqual(len(calls), 6)
                summary = json.loads((run / 'run_summary.json').read_text())
                self.assertEqual(summary['attempts'], dict(planned=3, attempted=3, converged=3,
                    nonconverged=0, failed=0, not_started=0))
                self.assertEqual(summary['selected_candidate_count'], 3)
                self.assertGreater(summary['costs']['recheck']['RF_forward_calls'], 0)
                preserved = {p.relative_to(repo): p.read_bytes() for p in run.rglob('*') if p.is_file()}
                preserved[raw.relative_to(repo)] = raw.read_bytes()
                for phase in ('remaining', 'pilot'):
                    with patch('lpf.phase2_models.coupled_lc.CoupledLCEvaluator.il',
                               side_effect=AssertionError('completed phase must not evaluate RF')):
                        repeated = run_plan(repo, path, ident, phase, optimize_stage=solver)
                    self.assertEqual(json.loads(json.dumps(final)), repeated)
                    self.assertEqual(preserved, {p: (repo / p).read_bytes() for p in preserved})
                    self.assertEqual(len(calls), 6)
                result = finalize_one_start(repo, ident)
                self.assertIsNotNone(result)
                self.assertEqual(json.loads((run / 'storage_record.json').read_text())['git_readback'], 'passed')
                preserved = (run / 'storage_record.json').read_bytes()
                with self.assertRaisesRegex(ValueError, 'Finalized evidence'):
                    run_plan(repo, path, ident, 'remaining', optimize_stage=solver)
                self.assertEqual(preserved, (run / 'storage_record.json').read_bytes())
                self.assertEqual(len(calls), 6)

    def test_curated_lossless_vectors_and_fail_closed_references(self):
        from lpf.phase2_models.experiment_config import load_plan
        from lpf.phase2_models.experiment_run import _curated_result, restore_curated_result
        from lpf.phase2_models.staged_optimization import run_c1_staged
        from lpf.checkpoint_io import atomic_write_json
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path, _, circuit = self.fixture(root)
            loaded = load_plan(root, path)
            seed = loaded['actual']['s0']['seed_record']
            for mode in ('normal', 'recovery', 'failure', 'exception', 'budget'):
                calls = []
                def solver(p, x, budget, target):
                    calls.append(budget)
                    if mode == 'exception':
                        raise RuntimeError('mock failure')
                    if mode == 'budget':
                        p.residuals(x)
                    # Exercise both a changed output and an exact warm reference.
                    y = x.copy()
                    y[0] += .001
                    code = 9 if mode == 'recovery' and len(calls) == 1 else (8 if mode == 'failure' else 0)
                    return y, dict(status=code, success=code == 0, message=mode, nit=1, nfev=2)
                from lpf.phase2_models.evaluation_cost import SampleBudgetCost
                staged = run_c1_staged(circuit, seed, coarse_points=2, fine_points=3,
                                       optimize_stage=solver,
                                       cost_meter=SampleBudgetCost(196 if mode == 'budget' else 1_500_000))
                result = dict(seed_record=seed, staged_record=staged)
                old = _curated_result(result)
                new = _curated_result(result, actual_start_id='s0', input_source=loaded['input_source'])
                self.assertEqual(old, restore_curated_result(new, loaded['input_source']))
                if mode == 'budget':
                    self.assertEqual(old['numerical_state'], 'budget_exhausted')
                corrupt = deepcopy(new)
                corrupt['stage_calls'][0]['input_vector']['sha256'] = '0' * 64
                with self.assertRaisesRegex(ValueError, 'vector reference/SHA'):
                    restore_curated_result(corrupt, loaded['input_source'])
                atomic_write_json(root / 'compact.json', new, compact=True)
                self.assertEqual(json.loads((root / 'compact.json').read_text()), new)
                bad = deepcopy(loaded['input_source'])
                bad['config_sha256'] = '0' * 64
                with self.assertRaisesRegex(ValueError, 'G1 input SHA'):
                    restore_curated_result(new, bad)
                bad = deepcopy(new)
                bad['stage_calls'][0]['input_vector']['vector_ref'] = '0'
                with self.assertRaisesRegex(ValueError, 'vector reference'):
                    restore_curated_result(bad, loaded['input_source'])
            atomic_write_json(root / 'legacy.json', {'日本語': [1., 2.]})
            self.assertIn('\n  ', (root / 'legacy.json').read_text())
            before = (root / 'compact.json').read_bytes()
            with self.assertRaises(ValueError):
                atomic_write_json(root / 'compact.json', {'bad': float('nan')}, compact=True)
            self.assertEqual(before, (root / 'compact.json').read_bytes())

    def test_gate_rejects_sparse_before_dispatch(self):
        from lpf.phase2_models.experiment_run import _gate
        with patch('scripts.run_phase2_shared._complete_checkout', side_effect=ValueError('Full checkout required')):
            with self.assertRaisesRegex(ValueError, 'Full checkout'):
                _gate(ROOT, 'EXP-999', {}, resuming=False)


if __name__ == '__main__':
    unittest.main()

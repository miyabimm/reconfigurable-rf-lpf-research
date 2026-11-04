"""Issue 299 mock-only API wiring; no scientific forward or EXP."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
import subprocess
import sys

import numpy as np
import yaml

from test_phase2_problem_seed import make
from lpf.phase2_models.comparison_mock_preflight import run_mock_arm, _GridBudget
from lpf.phase2_models.comparison_readiness import comparison_readiness, _required
from lpf.phase2_models.experiment_config import load_comparison_preflight, load_plan
from lpf.phase2_models.problem_seed import definition_fingerprint, vector_fingerprint
from lpf.phase2_models.api import CircuitDefinition, build_nominal_circuit
from lpf.phase2_models.circuit_layout import InductorTree, CapacitorPlacement
from lpf.phase2_models.sampled_epigraph import SampledEpigraph
from lpf.phase2_models.rf_pipeline_adapter import RFPipelineAdapter
from lpf.phase2_models.comparison_mock_preflight import sobol_start
from lpf.constraint_versions import load_constraint

ROOT = Path(__file__).resolve().parents[1]


class ComparisonMockPreflightTests(unittest.TestCase):
    def setUp(self):
        self.problem, _ = make('RF-T008', 4)
        self.circuit = self.problem.circuit
        self.mock = Mock(side_effect=lambda evaluator, x: np.where(evaluator.role == 0, .4, 30.))

    def test_four_arms_share_pipeline_sobol_and_c1_replays(self):
        with tempfile.TemporaryDirectory() as directory:
            rows = [run_mock_arm(self.circuit, arm, 23, mock_forward=self.mock,
                     output=Path(directory) / (arm + '.json')) for arm in 'ABCD']
            for row in rows:
                self.assertEqual(row['state'], 'returned_unverified', row)
                self.assertEqual(row['start'], rows[0]['start'])
                self.assertEqual(row['production_g0_g1_g2'], 'not_run')
                self.assertEqual(row['anytime'], 'mock_four_arm')
                self.assertIsNotNone(row['last_observation'])
                self.assertEqual(row['scans'][-1]['milestone'], 'terminal')
                self.assertEqual(json.loads((Path(directory) / (row['arm'] + '.json')).read_text()), row)
            a = rows[0]
            self.assertEqual(a['result']['seed']['vector'][:-1], a['start']['x'])
            # Initial C1 seed and deterministic replay are separate forward calls.
            self.assertGreaterEqual(a['cost']['frequency_samples_requested'], 112)
            self.assertEqual(rows[1]['cost']['frequency_samples_requested'], 56 + 476)
            self.assertEqual(rows[2]['cost']['frequency_samples_requested'], 168 + 476)
            self.assertGreaterEqual(rows[3]['cost']['frequency_samples_requested'], 224 + 476)
            d = rows[3]
            counts = d['result']['counts']
            self.assertGreater(sum(counts['selection'].values()), 0)
            self.assertEqual(d['cost_by_stage']['pipeline_selection_errors']['84']['calls'],
                             counts['selection']['errors'])
            self.assertEqual(d['cost_by_stage']['pipeline_selection_constraints']['84']['calls'],
                             counts['selection']['constraints'])
            self.assertEqual(d['cost_by_grid_samples']['84']['calls'],
                             sum(counts['selection'].values()) + sum(counts['slp'].values()))
            self.assertNotEqual(d['result']['nfev'], d['cost']['frequency_samples_requested'])

    def test_budget_and_forward_failure_are_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory)
            row = run_mock_arm(self.circuit, 'C', 23, mock_forward=self.mock,
                               output=p / 'budget.json', max_samples=560)
            self.assertEqual(row['state'], 'budget_exhausted')
            self.assertEqual(row['cost']['frequency_samples_requested'], 560)
            self.assertEqual(row['scans'][-1]['milestone'], 'terminal')
            self.assertEqual(row['cost_by_grid_samples']['84']['requested'], 84)
            self.assertEqual(row['cost_by_grid_samples']['476']['requested'], 476)
            self.assertIsNotNone(row['last_observation'])
            fail = Mock(side_effect=RuntimeError('forward failed'))
            row = run_mock_arm(self.circuit, 'B', 23, mock_forward=fail, output=p / 'fail.json')
            self.assertEqual(row['state'], 'failed')
            self.assertEqual(row['cost']['frequency_samples_requested'], 56)
            self.assertEqual(row['cost']['frequency_samples_completed'], 0)
            self.assertEqual(row['cost']['forward_failures'], 1)
            self.assertIsNone(row['last_observation'])
            self.assertEqual(json.loads((p / 'fail.json').read_text()), row)

    def test_c1_anytime_seed_replay_and_budget_abort(self):
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory)
            row = run_mock_arm(self.circuit, 'A', 23, mock_forward=self.mock,
                output=p / 'a.json', max_samples=1400, milestones=(56,))
            self.assertEqual(row['state'], 'returned_unverified', row)
            self.assertEqual([s['milestone'] for s in row['scans']], [56, 'terminal'])
            self.assertEqual(row['scans'][0]['x_sha256'], row['start']['sha256'])
            self.assertEqual(row['scans'][0]['samples_at_completion'], 532)
            self.assertEqual(row['last_observation']['sha256'], row['start']['sha256'])
            self.assertEqual(row['cost_by_stage']['seed']['56']['requested'], 56)
            self.assertEqual(row['cost_by_stage']['seed_replay']['56']['requested'], 56)
            stopped = run_mock_arm(self.circuit, 'A', 23, mock_forward=self.mock,
                output=p / 'stop.json', max_samples=588)
            self.assertEqual(stopped['state'], 'budget_exhausted', stopped)
            self.assertEqual(stopped['result']['numerical_state'], 'budget_exhausted')
            self.assertEqual(stopped['scans'][-1]['milestone'], 'terminal')
            self.assertEqual(stopped['cost']['frequency_samples_requested'], 588)
            self.assertEqual(stopped['last_observation']['sha256'], stopped['start']['sha256'])
            calls = 0
            def fail_stage(evaluator, vector):
                nonlocal calls
                calls += 1
                if calls == 3:
                    raise RuntimeError('C1 stage forward failure')
                return np.where(evaluator.role == 0, .4, 30.)
            failed = run_mock_arm(self.circuit, 'A', 23, mock_forward=Mock(side_effect=fail_stage),
                                 output=p / 'stage-failure.json')
            self.assertEqual(failed['state'], 'failed')
            self.assertEqual(failed['result']['numerical_state'], 'failed')
            self.assertEqual(failed['scans'], [])
            self.assertEqual(failed['cost']['forward_failures'], 1)
            self.assertEqual(failed['last_observation']['sha256'], failed['start']['sha256'])
            self.assertEqual(json.loads((p / 'stage-failure.json').read_text()), failed)

    def test_mock_v2_warm_restart_is_observed_and_separately_charged(self):
        outcomes = iter((4, 0, 0, 0))
        def stage(problem, vector, maxiter, target):
            problem.residuals(vector)
            status = next(outcomes)
            return vector, dict(success=(status == 0), status=status, message='fixture', nit=1, nfev=1)
        with tempfile.TemporaryDirectory() as directory:
            row = run_mock_arm(self.circuit, 'A', 23, mock_forward=self.mock,
                output=Path(directory) / 'warm.json', max_samples=3000,
                mock_stage_override=Mock(side_effect=stage))
            self.assertEqual(row['state'], 'returned_unverified', row)
            self.assertEqual(len(row['result']['stage_calls']), 4)
            for label, samples in (('c1_coarse_attempt_0', '56'), ('c1_fine_attempt_0', '84'),
                                   ('c1_coarse_attempt_1', '56'), ('c1_fine_attempt_1', '84')):
                self.assertEqual(row['cost_by_stage'][label][samples]['calls'], 2)
            self.assertEqual(row['terminal_scan'], 'observed')

    def test_real_scipy_mock_rf_observes_finite_differences_and_reserves_terminal(self):
        with tempfile.TemporaryDirectory() as directory:
            row = run_mock_arm(self.circuit, 'A', 23, mock_forward=self.mock,
                output=Path(directory) / 'scipy.json', max_samples=1700,
                milestones=(224,), scipy_stage=True)
            self.assertEqual(row['optimizer'], 'scipy')
            self.assertEqual(row['state'], 'budget_exhausted', row)
            self.assertEqual(row['terminal_scan'], 'observed')
            self.assertEqual(row['scans'][0]['milestone'], 224)
            self.assertEqual(row['cost_by_stage']['terminal_scan']['476']['requested'], 476)
            self.assertGreater(row['cost_by_stage']['c1_coarse_attempt_0']['56']['calls'], 2)
            self.assertGreater(row['cost']['solver_constraint_calls'], 1)
            self.assertLessEqual(row['cost']['frequency_samples_requested'], 1700)
            self.assertEqual(row['last_observation']['sha256'], row['scans'][-1]['x_sha256'])
            self.assertEqual(row['production_g0_g1_g2'], 'not_run')

    def test_milestone_scans_last_observation_and_keeps_terminal_reserve(self):
        with tempfile.TemporaryDirectory() as directory:
            row = run_mock_arm(self.circuit, 'B', 23, mock_forward=self.mock,
                output=Path(directory) / 'scan.json', max_samples=1008, milestones=(56,))
            self.assertEqual(row['state'], 'returned_unverified')
            self.assertEqual([s['milestone'] for s in row['scans']], [56, 'terminal'])
            self.assertEqual(row['scans'][0]['samples_at_completion'], 532)
            self.assertEqual(row['scans'][0]['x_sha256'], row['last_observation']['sha256'])
            self.assertTrue(row['scans'][0]['strict_finite_grid_feasible'])
            self.assertEqual(row['cost']['frequency_samples_requested'], 1008)
            self.assertEqual(row['cost_by_grid_samples']['476']['calls'], 2)

    def test_strict_threshold_and_nonfinite_forward(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            almost = Mock(side_effect=lambda e, x: np.where(e.role == 0, .4, np.nextafter(30., 0.)))
            row = run_mock_arm(self.circuit, 'B', 23, mock_forward=almost,
                               output=path / 'strict.json', max_samples=1008, milestones=(56,))
            self.assertFalse(row['scans'][0]['strict_finite_grid_feasible'])
            invalid = Mock(side_effect=lambda e, x: np.full(len(e.f), np.nan))
            row = run_mock_arm(self.circuit, 'B', 23, mock_forward=invalid, output=path / 'nan.json')
            self.assertEqual(row['state'], 'failed')
            self.assertEqual(row['cost']['frequency_samples_requested'], 56)
            # Forward returned; invalid data are rejected after completed samples.
            self.assertEqual(row['cost']['frequency_samples_completed'], 56)
            self.assertIsNone(row['last_observation'])

    def test_illegal_proposal_is_rejected_before_forward(self):
        meter = _GridBudget(1000)
        adapter = RFPipelineAdapter(self.circuit, 2, cost_meter=meter)
        meter.before_forward = lambda evaluator, vector: adapter.comparison.validate_vector(vector)
        bad = self.problem.box.bounds[4][0]
        vector = np.asarray(sobol_start(adapter, 23)).copy()
        vector[4] = bad  # excluded open lower endpoint for the fixture's GJM
        with patch.object(type(adapter.evaluator), 'il') as forward:
            with self.assertRaises(ValueError):
                meter.forward(adapter.evaluator, vector)
            forward.assert_not_called()
        self.assertEqual(meter.frequency_samples_requested, 0)
        self.assertEqual(meter.frequency_samples_completed, 0)

    def test_interrupt_is_not_saved_as_success(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'interrupt.json'
            with self.assertRaises(KeyboardInterrupt):
                run_mock_arm(self.circuit, 'B', 23,
                    mock_forward=Mock(side_effect=KeyboardInterrupt()), output=path)
            saved = json.loads(path.read_text())
            self.assertEqual(saved['state'], 'interrupted')
            self.assertEqual(saved['cost']['frequency_samples_requested'], 56)
            self.assertEqual(saved['cost']['frequency_samples_completed'], 0)

    def test_read_only_cli_opt_in_and_incomplete_g1(self):
        with patch.object(type(self.problem.evaluator), 'il', side_effect=AssertionError('RF forward')):
            with self.assertRaises(ValueError):
                comparison_readiness(ROOT, allow_trial=False)
            report = comparison_readiness(ROOT, allow_trial=True)
        self.assertEqual(report['production_readiness'], 'not_ready')
        self.assertEqual(report['g0_g1_g2'], 'not_run')
        self.assertEqual((report['rf']['settings'], report['rf']['intervals']), (6, 28))
        self.assertEqual(report['seed_vectors_grid_weights_budget_storage'], 'not_frozen')
        self.assertIn(report['checkpoint'], ('not_checked', 'local_file_sha_matches_only'))
        command = [sys.executable, str(ROOT / 'scripts/run_phase2_shared.py'), 'comparison-readiness']
        self.assertNotEqual(subprocess.run(command, capture_output=True).returncode, 0)
        output = subprocess.check_output(command + ['--allow-trial'], text=True)
        self.assertEqual(json.loads(output)['production_readiness'], 'not_ready')
        with tempfile.TemporaryDirectory() as directory:
            bad = Path(directory) / 'tampered'
            bad.write_bytes(b'tampered')
            with self.assertRaisesRegex(ValueError, 'SHA mismatch'):
                _required(bad, '0' * 64)

    def test_proposed_yaml_is_static_strict_and_never_enables_run(self):
        definition = json.loads((ROOT / 'project/experiments/issue270-definition.json').read_text())
        definition['inductor_tree'] = InductorTree(**definition['inductor_tree'])
        definition['capacitor_placement'] = CapacitorPlacement(**definition['capacitor_placement'])
        circuit = build_nominal_circuit(load_constraint('RF-T008', allow_trial=True), CircuitDefinition(**definition))
        adapter = RFPipelineAdapter(circuit, 2)
        problem = SampledEpigraph(circuit, 2)
        starts = []
        with patch.object(type(problem.evaluator), 'il',
                          new=lambda evaluator, vector: np.where(evaluator.role == 0, .4, 30.)):
            for seed in (23, 24):
                x = sobol_start(adapter, seed)
                sha = vector_fingerprint(x)
                record = problem.seed(x, policy_id=circuit.policy_id,
                    policy_fingerprint=circuit.policy_fingerprint,
                    definition_sha256=definition_fingerprint(circuit.definition),
                    input_sha256=sha, seed=seed, jitter_fraction=0.)
                starts.append(dict(seed=seed, vector=x.tolist(), vector_sha256=sha,
                                   seed_record=json.loads(json.dumps(record))))
        threads = {k: '1' for k in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS')}
        source = dict(git_head=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
                      uv_lock_sha256=__import__('hashlib').sha256((ROOT / 'uv.lock').read_bytes()).hexdigest(),
                      python=sys.version, thread_environment=threads)
        config = dict(schema_version=1, kind='four_arm_comparison_preflight',
            rf=dict(id='RF-T008', allow_trial=True, effective_sha256=circuit.policy_fingerprint),
            objective='full_lpf', definition_sha256=definition_fingerprint(circuit.definition),
            seeds=[23, 24], pilot_seeds=[23], starts=starts,
            grids=dict(coarse=2, fine=3, scan=17),
            weights=dict(hybrid='equal_1db', slp='signed_max', final='strict_policy'),
            solver=dict(a_policy='slsqp-staged-v2', hybrid_maxiter=240, hybrid_max_evaluations=6000,
                hybrid_max_restarts=0, restart_sigma=.1, slp_max_iterations=120, slp_max_evaluations=8000,
                constraint_tolerance=1e-7, pipeline_max_evaluations=14000, max_slp_candidates=1),
            budgets=dict(samples_per_arm=2000, total_samples=16000, milestones=[500], terminal_reserve=476),
            storage=dict(estimated_curated_bytes=1000, rule='fixture diagnostics'), source=source)
        with tempfile.TemporaryDirectory(dir=ROOT) as directory, patch.dict(os.environ, threads):
            path = Path(directory) / 'proposal.yaml'
            path.write_text(yaml.safe_dump(config))
            with patch.object(type(problem.evaluator), 'il', side_effect=AssertionError('RF forward')):
                report = load_comparison_preflight(ROOT, path)
            self.assertEqual(report['production_readiness'], 'not_ready')
            self.assertEqual(report['c1_forward_replay'], 'not_run')
            self.assertEqual(report['source_evidence']['remote_readback'], 'not_checked')
            self.assertIn(report['source_evidence']['checkpoint_topology'],
                          ('not_checked', 'local_structure_and_sha_match'))
            self.assertEqual(len(report['starts']), 2)
            with self.assertRaises(ValueError):
                load_plan(ROOT, path)
            command = [sys.executable, str(ROOT / 'scripts/run_phase2_shared.py'),
                       'comparison-readiness', '--allow-trial', '--config', str(path)]
            self.assertEqual(json.loads(subprocess.check_output(command, text=True))['proposed_plan'], report)
            original_vector = config['starts'][0]['vector'].copy()
            config['starts'][0]['vector'][0] += .001
            path.write_text(yaml.safe_dump(config))
            with self.assertRaisesRegex(ValueError, 'Sobol vector'):
                load_comparison_preflight(ROOT, path)
            config['starts'][0]['vector'] = original_vector
            config['budgets']['total_samples'] -= 1
            path.write_text(yaml.safe_dump(config))
            with self.assertRaisesRegex(ValueError, 'samples'):
                load_comparison_preflight(ROOT, path)

    def test_requires_mock_and_new_fixture(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'x.json'
            with self.assertRaises(TypeError):
                run_mock_arm(self.circuit, 'A', 23, mock_forward=lambda e, x: 0, output=path)
            path.touch()
            with self.assertRaises(ValueError):
                run_mock_arm(self.circuit, 'A', 23, mock_forward=self.mock, output=path)


if __name__ == '__main__':
    unittest.main()

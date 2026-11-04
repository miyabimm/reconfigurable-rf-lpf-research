"""New sequential boundary: synthetic solvers, cost/preservation, tiny RF wiring."""
import ast
from dataclasses import replace
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from lpf.search.plan import load
from lpf.search.problem import build, Problem
from lpf.search.starts import generate, physical_box, validate
from lpf.search.storage import canonical, sha, vector_sha
from lpf.search.evaluation import Evaluation, BudgetExceeded
from lpf.search.runner import run
from lpf.search.worker import JobSpec, execute_job
from lpf.search.validation import score, select, pending, dense_candidate, independent_sample
from lpf.optimizers.hybrid import HybridResult, LocalRun

CONFIG = ROOT / 'project/experiments/rf_search_fixture.yaml'


class SearchTests(unittest.TestCase):
    def setUp(self):
        self.plan = load(CONFIG)
        self.d = self.plan.data
        self.c = build(self.d['definition'], self.d['config']['rf'])
        self.start = generate(self.c, 23)
        self.x = self.start['vector']
        self.bounds, self.opened = physical_box(self.c)

    def meter(self, maximum=2000, **kwargs):
        return Evaluation(self.c, self.bounds, self.opened, maximum, backend='fixture', **kwargs)

    def spec(self, arm=0):
        source = {'test': 'synthetic'}
        return JobSpec('test', 'seed23', self.plan.sha256, sha(source), canonical({
            'plan': self.d, 'source': source, 'backend': 'fixture', 'arm_index': arm,
            'start': self.start}))

    def test_four_paths_same_complete_x_and_atomic_records(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = run(self.plan, Path(tmp) / 'run')
            self.assertEqual(state['status'], 'completed')
            self.assertEqual(len(state['jobs']), 4)
            for job in state['jobs']:
                raw = json.loads((Path(tmp) / 'run' / job['job_id'] / 'job.json').read_text())
                self.assertIn(raw['status'], ('converged', 'not_converged', 'budget_exhausted'))
                np.testing.assert_array_equal(raw['steps'][0]['input_vector'], self.x)
                self.assertEqual(raw['steps'][0]['input_vector_sha256'], vector_sha(self.x))
                self.assertEqual(len(raw['steps'][0]['input_vector']), self.c.schema.vector_length)
                self.assertEqual(raw['terminal17']['status'], 'completed')
                self.assertEqual(raw['cost']['terminal_reserved'], 0)
                self.assertLessEqual(raw['cost']['frequency_samples_requested'], 1800)
                self.assertEqual(raw['validation']['independent_mna'], 'not_run')
                ledger = raw['cost']['ledger']
                self.assertEqual(sum(r['requested'] for r in ledger), raw['cost']['frequency_samples_requested'])
                self.assertEqual(ledger[-1]['requested'], 476)
                self.assertTrue(raw['validation']['candidate_promotion_blocked'])
            self.assertEqual(len(state['ranking17']), 4)
            self.assertEqual(state['trials']['seed23']['frequency_samples_requested'],
                             sum(j['cost']['frequency_samples_requested'] for j in state['jobs']))
            with self.assertRaises(FileExistsError):
                run(self.plan, Path(tmp) / 'run')

    def test_residual_equations_and_strict_boundary(self):
        m = self.meter()
        p = Problem(m, 2, 'coarse', 30.)
        il = np.where(m.grid(2).role == 0, -.4, np.nextafter(30., 0.))
        with patch.object(m, 'forward', return_value=il):
            self.assertTrue(np.all(p.errors(self.x) == -.4))
            self.assertTrue(np.all(p.constraints(self.x) < 0))
            r = p.residuals(self.x)
            np.testing.assert_array_equal(r[:28], -.4 * np.ones(28))
            self.assertTrue(np.all(r[28:] > 0))
        self.assertFalse(score(il, m.grid(2).role, 30.)['strict_feasible'])
        self.assertTrue(score(np.where(m.grid(2).role == 0, .4, 30.), m.grid(2).role, 30.)['strict_feasible'])

    def test_budget_batch_reservation_stage_and_anytime(self):
        m = self.meter(532)
        m.forward(self.x, 2, 'initial')
        with self.assertRaises(BudgetExceeded):
            m.forward(self.x, 2, 'fd')
        self.assertEqual(m.requested, 56)
        m.forward(self.x, 17, 'terminal17', terminal=True)
        self.assertEqual(m.requested, 532)
        m = self.meter(1200, milestones=[56])
        m.begin_stage(600)
        m.forward(self.x, 2, 'initial')
        self.assertEqual(m.requested, 532)
        self.assertEqual(len(m.scans), 1)
        self.assertEqual(m.last['points_per_interval'], 17)
        m.begin_stage(55)
        with self.assertRaises(BudgetExceeded):
            m.forward(self.x, 2, 'fd')
        self.assertEqual(m.requested, 532)

    def test_anytime_charged_to_job_not_step(self):
        m = self.meter(1200, milestones=[56])
        m.begin_stage(200)
        m.forward(self.x, 2, 'solver')
        m.forward(self.x, 2, 'selection')
        self.assertEqual((m.requested, m.completed), (588, 588))
        self.assertEqual(m.snapshot()['stage_requested'], 112)
        with self.assertRaises(BudgetExceeded):
            m.forward(self.x, 4, 'selection')
        m.forward(self.x, 17, 'terminal17', terminal=True)
        self.assertEqual(m.requested, 1064)

    def test_selection_partial_checkpoints_budget_and_forward_error(self):
        vectors = [list(self.x) for _ in range(3)]
        for i, x in enumerate(vectors):
            x[0] += i * 1e-6
            validate(self.c, x, self.bounds, self.opened)
        expected = sorted(vector_sha(x) for x in vectors)[:2]
        runs = [LocalRun(x, None, x, None, True, 0, '', 0, 0) for x in vectors]
        out = HybridResult(runs, None, None, 0, 'mock', 23, 1, 2, 1, .1)
        original_forward = Evaluation.forward
        for failure in ('budget', 'forward'):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as tmp:
                data = json.loads(self.spec(1).frozen_json)
                data['plan']['config']['arms'][1]['steps'][0]['max_requested_samples'] = (
                    168 if failure == 'budget' else 560)
                spec = replace(self.spec(1), frozen_json=canonical(data), plan_sha256=sha(data['plan']))
                path = Path(tmp) / 'job'
                calls = []
                def forward(meter, vector, points, stage, **kwargs):
                    if stage.endswith(':selection'):
                        calls.append(1)
                        if len(calls) == 3:
                            saved = json.loads((path / 'step-0.json').read_text())
                            self.assertEqual(saved['selection_status'], 'partial')
                            self.assertEqual(sorted(r['vector_sha256'] for r in saved['selection']), expected)
                            if failure == 'forward':
                                raise ValueError('mock forward failure')
                    return original_forward(meter, vector, points, stage, **kwargs)
                with patch('lpf.search.worker.hybrid_minimize', return_value=out), \
                     patch.object(Evaluation, 'forward', forward):
                    result = execute_job(spec, path)
                self.assertEqual(result['status'], 'budget_exhausted' if failure == 'budget' else 'failed')
                raw = json.loads((path / 'step-0.json').read_text())
                self.assertEqual(raw['selection_status'], 'partial')
                self.assertEqual(sorted(r['vector_sha256'] for r in raw['selection']), expected)
                for row in raw['selection']:
                    self.assertEqual(vector_sha(row['vector']), row['vector_sha256'])
                    self.assertIn('strict_feasible', row['score'])

    def test_selection_checkpoint_before_anytime_budget_stop(self):
        runs = [LocalRun(self.x, None, self.x, None, True, 0, '', 0, 0)]
        out = HybridResult(runs, None, None, 0, 'mock', 23, 1, 0, 1, .1)
        data = json.loads(self.spec(1).frozen_json)
        data['plan']['config']['arms'][1]['max_requested_samples'] = 616
        data['plan']['config']['anytime_samples'] = [84]
        spec = replace(self.spec(1), frozen_json=canonical(data), plan_sha256=sha(data['plan']))
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'job'
            with patch('lpf.search.worker.hybrid_minimize', return_value=out):
                result = execute_job(spec, path)
            raw = json.loads((path / 'step-0.json').read_text())
            self.assertEqual(result['status'], 'budget_exhausted')
            self.assertEqual(raw['selection_status'], 'partial')
            self.assertEqual(raw['selection'][0]['vector_sha256'], vector_sha(self.x))
            self.assertIn('strict_feasible', raw['selection'][0]['score'])
            self.assertEqual(result['cost']['frequency_samples_requested'], 560)
            self.assertEqual(result['terminal17']['status'], 'completed')
            self.assertEqual(result['cost']['anytime17'][0]['status'], 'not_run')

    def test_illegal_nonfinite_open_role_and_spd_stop_without_forward(self):
        m = self.meter()
        for x in (self.x + [0.], [float('nan')] * len(self.x), [-1.] * len(self.x)):
            with self.assertRaises(ValueError):
                m.forward(x, 2, 'bad')
        x = list(self.x)
        x[4] = 0.  # GJM open endpoint
        with self.assertRaises(ValueError):
            m.forward(x, 2, 'open')
        for report in ({'component_policy_pass': False, 'connection_role_evidence_incomplete': False},
                       {'component_policy_pass': True, 'connection_role_evidence_incomplete': True}):
            with patch.object(type(self.c), 'validate_components', return_value=report):
                with self.assertRaises(ValueError):
                    m.forward(self.x, 2, 'component_or_role')
        with patch.object(type(self.c), 'validate_components', side_effect=ValueError('non-SPD')):
            with self.assertRaises(ValueError):
                m.forward(self.x, 2, 'spd')
        self.assertEqual(m.requested, 0)

    def test_failed_forward_counts_requested_not_completed_preserves_last(self):
        m = self.meter()
        m.backend = 'rf'
        e = m.grid(2)
        il = np.where(e.role == 0, .4, 30.)
        with patch.object(type(e), 'il', return_value=il):
            m.forward(self.x, 2, 'initial')
        last = m.last
        for error in (ValueError('callback'), KeyboardInterrupt()):
            with patch.object(type(e), 'il', side_effect=error):
                with self.assertRaises(type(error)):
                    m.forward(self.x, 2, 'fd')
        with patch.object(type(e), 'il', return_value=np.full(56, np.nan)):
            with self.assertRaises(ValueError):
                m.forward(self.x, 2, 'nonfinite')
        self.assertIs(m.last, last)
        self.assertEqual((m.requested, m.completed, m.failures), (224, 56, 3))

    def test_worker_interrupt_and_budget_partial_records(self):
        for exc, status in ((KeyboardInterrupt(), 'interrupted'),
                            (ValueError('solver callback'), 'failed'),
                            (BudgetExceeded('limit'), 'budget_exhausted')):
            def solver(callback, x, bounds, **kwargs):
                callback(x)
                raise exc
            with self.subTest(status=status), tempfile.TemporaryDirectory() as tmp:
                with patch('lpf.search.worker.slsqp_minimize', side_effect=solver):
                    result = execute_job(self.spec(), Path(tmp) / 'job')
                self.assertEqual(result['status'], status)
                self.assertEqual(result['cost']['last_legal_observation']['vector_sha256'], vector_sha(self.x))
                self.assertEqual(result['terminal17']['status'], 'completed' if status == 'budget_exhausted' else 'not_run')
                raw = json.loads((Path(tmp) / 'job/job.json').read_text())
                self.assertEqual(raw['status'], status)
                self.assertEqual(raw['steps'][0]['status'], 'unknown')
                self.assertTrue((Path(tmp) / 'job/job.json').is_file())

    def test_no_candidate_and_validation_connections_mock_only(self):
        m = self.meter()
        self.assertEqual(select(m, [], 3, 'selection'), [])
        self.assertEqual(dense_candidate(m, None)['status'], 'not_run')
        candidate = select(m, [self.x], 3, 'selection')[0]
        def dense_forward(vector, points, stage, *, on_completed):
            il = np.where(m.grid(points).role == 0, .4, 31.)
            on_completed(il)
            return il
        with patch.object(m, 'forward', side_effect=dense_forward) as f:
            result = dense_candidate(m, candidate)
            self.assertEqual(result['status'], 'completed')
            self.assertEqual(f.call_args.args[1], 1001)
        with patch('lpf.search.validation.evaluate_independent_sample', return_value={'raw': 'mock'}) as f:
            self.assertEqual(independent_sample(self.c, self.x, 700e6, 0), {'raw': 'mock'})
            f.assert_called_once()
        self.assertTrue(pending()['candidate_promotion_blocked'])

    def test_plan_rejects_bad_contract_before_start(self):
        original = yaml.safe_load(CONFIG.read_text())
        variants = []
        for mutate in (
            lambda d: d.update(unknown=True),
            lambda d: d['rf'].update(allow_trial=False),
            lambda d: d['definition'].update(source_sha256='0'*64),
            lambda d: d['arms'][0]['steps'][0].update(aggregation='signed_max'),
            lambda d: d['arms'][0].update(max_requested_samples=475),
            lambda d: d.update(max_trial_requested_samples=1),
            lambda d: d.update(seeds=[23, 23]),
        ):
            d = json.loads(json.dumps(original))
            mutate(d)
            variants.append(yaml.safe_dump(d))
        variants.append(CONFIG.read_text() + '\nseeds: [24]\n')
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'bad.yaml'
            for text in variants:
                p.write_text(text)
                with self.assertRaises(ValueError):
                    load(p)

    def test_production_stops_and_read_only_cli_preflight(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'production'
            with self.assertRaisesRegex(ValueError, 'not_ready'):
                run(self.plan, out, mode='production')
            self.assertFalse(out.exists())
            cmd = [sys.executable, str(ROOT / 'scripts/run_rf_search.py'), 'preflight', '--config', str(CONFIG)]
            proc = subprocess.run(cmd, capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertFalse(json.loads(proc.stdout)['execution_authorized'])
            proc = subprocess.run([*cmd[:2], 'run', '--config', str(CONFIG), '--output', str(out)],
                                  capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertEqual(json.loads((out / 'run.json').read_text())['status'], 'completed')

    def test_fixture_output_below_checkout_with_src_ancestor(self):
        # The checkout lives under ~/src on Pi. Only repository-relative
        # protected paths, not an ancestor directory named src, are forbidden.
        with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
            state = run(self.plan, Path(tmp) / 'run')
            self.assertEqual(state['status'], 'completed')

    def test_parent_stop_illegal_start_retains_attempt_and_not_started(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch('lpf.search.starts.validate', side_effect=ValueError('non-SPD')):
                state = run(self.plan, Path(tmp) / 'illegal')
            self.assertEqual(state['status'], 'failed')
            attempted = state['starts']['23']
            self.assertEqual(attempted['vector_sha256'], vector_sha(attempted['vector']))
            self.assertIn('non-SPD', attempted['reason'])
            self.assertTrue(all(j['status'] == 'not_started' for j in state['jobs']))
            self.assertEqual(state['ranking17'], [])
        with tempfile.TemporaryDirectory() as tmp:
            with patch('lpf.search.worker.slsqp_minimize', side_effect=KeyboardInterrupt):
                state = run(self.plan, Path(tmp) / 'interrupt')
            self.assertEqual(state['status'], 'interrupted')
            self.assertEqual([j['status'] for j in state['jobs']],
                             ['interrupted', 'not_started', 'not_started', 'not_started'])

    def test_spec_sha_and_storage_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = execute_job(replace(self.spec(), plan_sha256='0'*64), Path(tmp) / 'bad')
            self.assertEqual(result['status'], 'failed')
            self.assertIsNone(result['cost'])
            self.assertEqual(result['terminal17']['status'], 'not_run')
        def failed_sink(cost):
            raise OSError('disk full')
        m = self.meter(sink=failed_sink)
        e = m.grid(2)
        with patch.object(type(e), 'il') as forward:
            with self.assertRaises(OSError):
                m.forward(self.x, 2, 'initial')
            forward.assert_not_called()
        self.assertEqual(m.ledger[-1]['status'], 'unknown')
        self.assertIsNone(m.last)

    def test_development_mode_fixed_input_caps_and_invalid_fd_stop(self):
        plan = load(ROOT / 'project/experiments/rf_search_development_smoke.yaml')
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'dev'
            def solver(callback, x, bounds, **kwargs):
                callback(x)
                bad = list(x)
                bad[4] = 0.  # open GJM endpoint: never send to RF
                callback(bad)
            from lpf.phase2_models.coupled_lc import CoupledLCEvaluator
            def synthetic(e, x):
                return np.where(e.role == 0, .4, 31.)
            with patch('lpf.search.worker.slsqp_minimize', side_effect=solver), \
                 patch.object(CoupledLCEvaluator, 'il', synthetic):
                state = run(plan, out, mode='development_rf')
            self.assertEqual(state['kind'], 'development_rf_smoke_not_an_EXP')
            self.assertEqual(state['status'], 'failed')
            raw = json.loads((out / 'seed23_slsqp/job.json').read_text())
            self.assertIn('Illegal physical vector', raw['exit_reason'])
            self.assertEqual((raw['cost']['frequency_samples_requested'],
                              raw['cost']['frequency_samples_completed']), (56, 56))
            self.assertEqual(raw['cost']['backend'], 'rf')
            self.assertEqual(raw['terminal17']['status'], 'not_run')
            self.assertIsNotNone(raw['cost']['last_legal_observation'])
            self.assertTrue(raw['validation']['candidate_promotion_blocked'])
        from lpf.search.runner import check_development_plan
        data = plan.data
        data['config']['arms'][0]['max_requested_samples'] = 1601
        with self.assertRaisesRegex(ValueError, '1600'):
            check_development_plan(data)
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, 'fixed 4L'):
                run(self.plan, Path(tmp) / 'bad', mode='development_rf')

    def test_dependency_boundary(self):
        allowed = {'api', 'circuit_layout', 'nominal_inductors', 'independent_rf'}
        for path in (ROOT / 'src/lpf/search').glob('*.py'):
            for node in ast.walk(ast.parse(path.read_text())):
                if isinstance(node, ast.ImportFrom) and node.module and 'phase2_models' in node.module:
                    self.assertIn(node.module.split('.')[-1], allowed, str(path))
                if isinstance(node, ast.Import):
                    self.assertFalse(any('phase2_models' in alias.name for alias in node.names))

    def test_tiny_real_rf_forward_only_56_samples(self):
        # Known existing 4L fixture, NOT Sobol search, optimization or 17/1001 RF.
        from test_phase2_problem_seed import make
        p, x = make('RF-T008', 4)
        bounds, opened = physical_box(p.circuit)
        m = Evaluation(p.circuit, bounds, opened, 532)
        il = m.forward(x, 2, 'fixture_wiring')
        self.assertEqual(il.shape, (56,))
        self.assertEqual((m.requested, m.completed), (56, 56))
        self.assertEqual(set(m.grid(2).segment), set(range(28)))
        self.assertEqual(set(m.grid(2).setting), set(range(6)))
        self.assertEqual(m.last['vector_sha256'], vector_sha(x))


if __name__ == '__main__':
    unittest.main()

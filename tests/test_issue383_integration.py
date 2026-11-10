"""Bounded timing integration; RF forwards are mocked, not a research run."""
import copy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

import numpy as np
import test_issue315_fixed_stage as stage_tests
import test_issue317_fixed_worker as worker_tests
from lpf.rf_core.model import RFEvaluator, RFResponse
from lpf.search import runner
from lpf.search._window_evaluation import WindowJobEvaluation
from lpf.search.storage import vector_sha


class TimingIntegrationTests(unittest.TestCase):
    setUp = stage_tests.FixedStageTests.setUp
    setup_model = stage_tests.FixedStageTests.setup_model

    def test_window_raw_and_cost_unchanged_two_independent_jobs(self):
        def config(c):
            c['anytime_samples'] = []
            arm = copy.deepcopy(c['arms'][0])
            arm['name'] = 'other'
            c['arms'].append(arm)
            c['max_trial_requested_samples'] = 3000
        plan, definition, policy, vector = self.setup_model(mutate=config)
        starts = {23: dict(vector=vector.tolist(), vector_sha256=vector_sha(vector))}
        calls = []
        def fake_forward(evaluator, x):
            calls.append(x.tolist())
            n = len(evaluator.grid.frequency_hz)
            return RFResponse(evaluator.grid, evaluator.model.policy_id, evaluator.model.policy_fingerprint,
                              np.zeros((n, 2, 2), complex), *[np.zeros(n) for _ in range(4)])
        results = []
        diagnostics = []
        with patch.object(runner, '_validate_development_output'), \
             patch.object(WindowJobEvaluation, '_validate_checkpoint'), \
             patch.object(RFEvaluator, 'evaluate', autospec=True, side_effect=fake_forward), \
             patch('lpf.search.worker.slsqp_minimize', side_effect=worker_tests.FixedWorkerTests.fixture):
            for i in range(2):
                output = Path(self.raw.name) / f'timing-{i}'
                jobs = [] if i else None
                state = runner.run_development(plan, definition, policy, starts, output,
                                               solver_kind='fixture', storage_mode='window100', timing_jobs=jobs)
                self.assertEqual(state['status'], 'completed', state.get('exit_reason'))
                raw = [json.loads((output / row['raw_path']).read_text()) for row in state['jobs']]
                results.append(raw)
                if jobs is not None:
                    diagnostics = jobs
        self.assertEqual(results[0], results[1])
        self.assertEqual(calls[:8], calls[8:])
        self.assertEqual(len(diagnostics), 2)
        self.assertIsNot(diagnostics[0]['timer'], diagnostics[1]['timer'])
        for diagnostic in diagnostics:
            self.assertEqual(diagnostic['status'], 'not_converged')
            regions = diagnostic['timer'].snapshot()
            for name in ('job_worker', 'evaluation_initialization', 'solver:coarse:slsqp',
                         'evaluation', 'physical_validation', 'rf_forward', 'requirements',
                         'checkpoint', 'window_checkpoint_save', 'source_contract', 'solver_callback'):
                self.assertGreater(regions[name]['count'], 0, name)
            self.assertEqual(regions['rf_forward']['count'], 4)

    def test_hybrid_random_restarts_and_evaluations_unchanged(self):
        from dataclasses import asdict
        from lpf.optimizers.hybrid import hybrid_minimize
        from lpf.timing import TimerCollector
        def run(timer):
            calls = []
            def residual(x):
                calls.append(x.tolist())
                return [x[0] - .37, x[1] - .71]
            def event(e):
                if e['event'] in ('local_run_end', 'restart_start_generated'):
                    timer.add(e['event'], round(e['wall_s'] * 1e9))
            options = {} if timer is None else {'event_callback': event}
            result = hybrid_minimize(residual, [.8, .1], [(0, 1), (0, 1)], seed=12,
                                     maxiter=20, max_restarts=3, max_evaluations=200,
                                     restart_sigma=.2, **options)
            return asdict(result), calls
        timer = TimerCollector()
        self.assertEqual(run(None), run(timer))
        self.assertEqual(timer.snapshot()['local_run_end']['count'], 4)
        self.assertEqual(timer.snapshot()['restart_start_generated']['count'], 3)

    def test_hybrid_worker_mock_restart_and_raw_same(self):
        from lpf.search.worker import freeze_development_job, execute_development_job
        from lpf.timing import TimerCollector
        def config(c):
            c['anytime_samples'] = []
            c['arms'][0]['steps'][0].update(solver='hybrid', aggregation='sum', max_requested_samples=224,
                options=dict(maxiter=2, max_restarts=1, max_evaluations=2, restart_sigma=.1))
            slp = copy.deepcopy(c['arms'][0]['steps'][0])
            slp.update(name='fine', solver='slp', aggregation='signed_max',
                       options=dict(max_iterations=2, max_evaluations=2))
            c['arms'][0]['steps'].append(slp)
            c['max_trial_requested_samples'] = 3000
        plan, definition, policy, vector = self.setup_model(mutate=config)
        spec = freeze_development_job(plan, definition, policy, 'demo', 23, vector, storage_mode='window100')
        events = Path(self.raw.name) / 'forbidden-events.jsonl'
        observed = []
        def hybrid(callback, x, bounds, *, seed, **opts):
            random = np.random.default_rng(seed)
            draws = []
            for i in range(2):
                draws.append(random.normal())
                callback(x)
                if 'event_callback' in opts:
                    opts['event_callback'](dict(event='local_run_end', wall_s=.001, interrupted=False))
                    if i == 0:
                        opts['event_callback'](dict(event='restart_start_generated', wall_s=.002))
            observed.append(draws)
            return worker_tests.FixtureHybrid([worker_tests.FixtureRun(list(x))], list(x))
        def fake_forward(evaluator, x):
            n = len(evaluator.grid.frequency_hz)
            return RFResponse(evaluator.grid, evaluator.model.policy_id, evaluator.model.policy_fingerprint,
                              np.zeros((n, 2, 2), complex), *[np.zeros(n) for _ in range(4)])
        timer = TimerCollector()
        with patch.object(WindowJobEvaluation, '_validate_checkpoint'), \
             patch.object(RFEvaluator, 'evaluate', autospec=True, side_effect=fake_forward), \
             patch('lpf.search.worker.hybrid_minimize', side_effect=hybrid), \
             patch('lpf.search.worker.slp_minimize', side_effect=worker_tests.FixedWorkerTests.fixture):
            plain = execute_development_job(spec, Path(self.raw.name) / 'hybrid-off.json', solver_kind='fixture')
            with patch.dict('os.environ', {'LPF_DEVELOP_MONITOR_EVENTS': str(events)}):
                measured = execute_development_job(spec, Path(self.raw.name) / 'hybrid-on.json',
                                                   solver_kind='fixture', timer=timer)
        self.assertEqual(plain, measured)
        self.assertEqual(observed[0], observed[1])
        self.assertFalse(events.exists())
        regions = timer.snapshot()
        self.assertEqual(regions['solver:coarse:hybrid']['count'], 1)
        self.assertEqual(regions['hybrid_local_run:coarse']['count'], 2)
        self.assertEqual(regions['hybrid_restart_generation:coarse']['count'], 1)
        self.assertEqual(regions['solver:fine:slp']['count'], 1)
        self.assertEqual(regions['solver_callback']['count'], 4)

    def test_common_worker_timer_with_real_non_rf_slsqp_and_slp(self):
        from lpf.optimizers.slsqp import slsqp_minimize
        from lpf.optimizers.slp import slp_minimize
        from lpf.search.evaluation import raw_numbers
        from lpf.search.worker import _timed_solver
        from lpf.timing import TimerCollector
        for name, solver in (('slsqp', slsqp_minimize), ('slp', slp_minimize)):
            def run(timer):
                calls = []
                def callback(x):
                    calls.append(('objective', x.tolist()))
                    return [x[0] - .3]
                def constraints(x):
                    calls.append(('constraint', x.tolist()))
                    return [x[0] + 1.]
                result = _timed_solver(timer, name, solver, callback, [.8], [(0., 1.)],
                                       constraints=constraints, aggregation='sum',
                                       max_iterations=3, max_evaluations=25)
                return raw_numbers(result), calls
            timer = TimerCollector()
            self.assertEqual(run(None), run(timer), name)
            self.assertEqual(timer.snapshot()[name]['count'], 1)

    def test_cli_single_final_save_and_save_failure_does_not_change_exit(self):
        from scripts import run_rf_search as cli
        from types import SimpleNamespace
        from lpf.timing import TimerCollector
        with TemporaryDirectory(prefix='issue383-cli-') as tmp:
            path = Path(tmp) / 'timing.json'
            output = Path(tmp) / 'science'
            plan = SimpleNamespace(data={'config': {'definition': {'path': 'unused'},
                'rf': {'constraint_id': 'x', 'allow_trial': False}}})
            def fake_run(*args, timing_jobs, **kwargs):
                self.assertFalse(path.exists())
                t = TimerCollector()
                with t.measure('solver:mock:slp'):
                    pass
                timing_jobs.append(dict(job_id='mock', status='not_converged', timer=t))
                return {}
            summary = dict(exit_code=4, development_flow='completed', plan_sha256='plan', source_sha256='source')
            with patch.object(cli, 'load_preflight', return_value=plan), \
                 patch.object(Path, 'read_bytes', return_value=json.dumps(dict(inductor_tree={}, capacitor_placement={})).encode()), \
                 patch('lpf.topology_management.InductorTree'), patch('lpf.topology_management.CapacitorPlacement'), \
                 patch('lpf.topology_management.CircuitDefinition'), patch('lpf.constraint_versions.load_constraint'), \
                 patch.object(cli, 'load_explicit'), patch.object(cli, 'run_development', side_effect=fake_run), \
                 patch.object(cli, 'finalize_development', return_value=summary):
                args = ['develop', '--config', 'unused', '--starts', 'unused', '--output', str(output), '--timing-output', str(path)]
                self.assertEqual(cli.main(args), 4)
                report = json.loads(path.read_text())
                self.assertEqual(report['status'], 'completed')
                self.assertEqual(report['summary']['exit_code'], 4)
                self.assertEqual(report['jobs'][0]['regions']['solver:mock:slp']['count'], 1)
                path.unlink()
                with patch.object(Path, 'open', side_effect=OSError('diagnostic failure')):
                    self.assertEqual(cli.main(args), 4)
                self.assertFalse(path.exists())
                with patch.object(cli, 'run_development', side_effect=ValueError('synthetic stop')):
                    self.assertEqual(cli.main(args), 2)
                interrupted = json.loads(path.read_text())
                self.assertEqual(interrupted['status'], 'incomplete')
                self.assertIsNone(interrupted['summary'])
                original = path.read_bytes()
                self.assertEqual(cli.main(args), 2)
                self.assertEqual(path.read_bytes(), original)

    def test_timing_path_rejects_git_and_scientific_raw(self):
        from scripts.run_rf_search import _timing_path
        with TemporaryDirectory(prefix='issue383-path-') as tmp:
            raw = Path(tmp) / 'raw'
            raw.mkdir()
            with self.assertRaisesRegex(ValueError, 'separate'):
                _timing_path(raw / 'timing.json', raw)
            with self.assertRaisesRegex(ValueError, 'Git'):
                _timing_path(Path(__file__).resolve().parent / 'timing.json', raw)


if __name__ == '__main__':
    unittest.main()

"""Stage 4C-2: bounded real RF plus mock-only parent accounting fault injection."""
import copy
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import test_issue315_fixed_stage as stage_tests
import test_issue317_fixed_worker as worker_tests
from lpf.search import runner
from lpf.search.storage import atomic, canonical, plain, sha, vector_sha


class ParentRunnerTests(unittest.TestCase):
    setUp = stage_tests.FixedStageTests.setUp
    setup_model = stage_tests.FixedStageTests.setup_model

    def setup_parent(self, seeds=None, mutate=None):
        def config(c):
            c['seeds'] = seeds or [23]
            other = copy.deepcopy(c['arms'][0]); other['name'] = 'other'
            c['arms'].append(other)
            c['max_trial_requested_samples'] = 3000
            if mutate:
                mutate(c)
        plan, d, p, x = self.setup_model(mutate=config)
        starts = {seed: dict(vector=x.tolist(), vector_sha256=vector_sha(x)) for seed in plan.data['config']['seeds']}
        self.counter += 1
        output = Path(self.raw.name)/f'parent{self.counter}'
        return plan, d, p, starts, output

    @staticmethod
    def mock_result(spec, path, *, root=None, solver_kind='fixture'):
        """No forwards. One fully charged grid, deliberately no solver/RF claim."""
        d = spec.data; plan = d['plan']; arm = d['arm']
        stage = arm + '/' + plan['config']['arms'][0]['steps'][0]['name']
        n = plan['grids'][stage]['requested_samples_per_forward']
        job = plan['costs']['jobs'][arm]
        # Synthetic shape/identity evidence only, not an RF simulation/result.
        response = {key: [0.] * n for key in ('il_db', 'apl_db', 'in_rl_db', 'out_rl_db')}
        response.update({key: [[[0., 0.], [0., 0.]] for _ in range(n)]
                         for key in ('s_real', 's_imag')})
        assessment = dict(status='evaluated', policy_id=plan['config']['rf']['constraint_id'],
            policy_fingerprint=plan['requirements']['policy_fingerprint'], mode=plan['config']['objective'],
            requirements_fingerprint=plan['requirements']['fingerprint'],
            grid_fingerprint=plan['grids'][stage]['sha256'], strict_feasible=False,
            worst_il_db=0., max_violation_db=1., sum_violation_db=1.)
        result = dict(kind='stage4c1_development_only', spec=plain(spec),
            plan_sha256=spec.plan_sha256, policy_id=plan['config']['rf']['constraint_id'],
            policy_fingerprint=plan['requirements']['policy_fingerprint'],
            requirements_fingerprint=plan['requirements']['fingerprint'],
            definition_sha256=sha(d['definition']), rf_inputs=plan['rf_inputs'], grids=plan['grids'],
            gates=plan['gates'], rf_backend='rf_core', status='not_converged', exit_reason='mock_only',
            requested=n, completed=n, search_requested=n, evaluation_status='ready',
            remaining=dict(job=job['max_requested_samples']-n, trial=plan['costs']['max_trial_requested_samples']-n),
            allocations={}, active=None,
            reservations=dict(inactive=0, other_jobs=plan['costs']['trial_job_cap_reservation']-job['max_requested_samples'], dense=plan['costs']['dense']),
            steps=[dict(solver_result=dict(nfev=999))], terminal=dict(status='not_run'),
            anytime=[], dense=dict(status='not_run'),
            batches=[dict(stage=stage, allocation=stage, grid_sha256=plan['grids'][stage]['sha256'],
                requested=n, completed=n, status='completed', vector=d['start']['vector'],
                vector_sha256=d['start']['vector_sha256'], independent=dict(status='not_run'),
                response=response, assessment=assessment)])
        atomic(path, result)
        return result

    def test_real_f003_two_arms_tiny_fixture_and_readback(self):
        args = self.setup_parent(mutate=lambda c: c.update(anytime_samples=[56]))
        with patch('lpf.search.worker.slsqp_minimize', side_effect=worker_tests.FixedWorkerTests.fixture):
            state = runner.run_development(*args, solver_kind='fixture', spot_checks={'terminal': [0]})
        self.assertEqual(state['status'], 'completed', state.get('exit_reason'))
        self.assertEqual(len(state['jobs']), 2)
        self.assertEqual(state['campaign']['requested'], 2*392)  # each: 112 search + 84 anytime + 84 selection + 112 terminal
        self.assertEqual(state['campaign']['requested'], state['campaign']['completed'])
        self.assertEqual(state['campaign']['independent_completed'], 2)
        self.assertEqual(state['campaign']['reserved'], 0)
        for row in state['jobs']:
            raw = (args[-1]/row['raw_path']).read_bytes()
            result = json.loads(raw)
            self.assertEqual(row['raw_byte_sha256'], hashlib.sha256(raw).hexdigest())
            self.assertEqual(row['raw_content_sha256'], sha(result))
            self.assertNotEqual(row['raw_byte_sha256'], row['raw_content_sha256'])
            self.assertEqual(result['spec']['source_sha256'], state['source_sha256'])
            self.assertEqual(result['grids'], args[0].data['grids'])
            self.assertEqual(result['spec']['plan_sha256'], args[0].sha256)
            self.assertEqual(result['spec']['frozen_json'], row['spec']['frozen_json'])
            frozen = json.loads(result['spec']['frozen_json'])
            self.assertEqual(frozen['start'], args[3][23])
            self.assertEqual(result['policy_fingerprint'], args[0].data['requirements']['policy_fingerprint'])
            self.assertEqual([b['requested'] for b in result['batches']], [56, 84, 56, 84, 112])
            self.assertEqual(sum(b['completed'] for b in result['batches']), 392)
            self.assertEqual(row['worker_status'], 'not_converged')
            self.assertEqual(row['evidence']['anytime'][0]['status'], 'completed')
            self.assertEqual(row['evidence']['terminal']['status'], 'completed')
            for observed, batch in zip(row['evidence']['observations'], result['batches']):
                self.assertEqual(observed['assessment']['strict_feasible'], batch['assessment']['strict_feasible'])
            self.assertEqual(row['evidence']['independent'][-1]['status'], 'pass')
            self.assertEqual(row['evidence']['dense']['status'], 'not_run')
            self.assertEqual(row['solver_nfev'], [999])
            self.assertEqual(row['released'], row['cap']-row['requested'])
        self.assertEqual(json.loads((args[-1]/'run.json').read_text()), state)

    def test_window_parent_worker_readback_with_mock_rf(self):
        # No real RF forward: retain scientific grid/requirements accounting.
        import numpy as np
        from lpf.rf_core.model import RFEvaluator, RFResponse
        from lpf.search._window_evaluation import WindowJobEvaluation
        plan, d, p, x = self.setup_model(mutate=lambda c: c.update(anytime_samples=[]))
        starts = {23: dict(vector=x.tolist(), vector_sha256=vector_sha(x))}
        output = Path(self.raw.name)/'window-parent'
        def fake_forward(evaluator, vector):
            n = len(evaluator.grid.frequency_hz)
            return RFResponse(evaluator.grid, evaluator.model.policy_id, evaluator.model.policy_fingerprint,
                np.zeros((n, 2, 2), complex), *[np.zeros(n) for _ in range(4)])
        def fake_independent(*args, **kwargs):
            return dict(s=np.zeros((2, 2), complex), il_db=0., apl_db=0., in_rl_db=0., out_rl_db=0.)
        with patch.object(runner, '_validate_development_output'), \
             patch.object(WindowJobEvaluation, '_validate_checkpoint'), \
             patch.object(RFEvaluator, 'evaluate', autospec=True, side_effect=fake_forward) as forward, \
             patch('lpf.rf_core.independent.evaluate_independent_response', side_effect=fake_independent), \
             patch('lpf.search.worker.slsqp_minimize', side_effect=worker_tests.FixedWorkerTests.fixture):
            state = runner.run_development(plan, d, p, starts, output, solver_kind='fixture',
                                           storage_mode='window100', spot_checks={'terminal': [0]})
            self.assertEqual(state['status'], 'completed', state.get('exit_reason'))
            self.assertEqual(forward.call_count, 4)  # 2 search + selection + terminal
            raw = json.loads((output/state['jobs'][0]['raw_path']).read_bytes())
            self.assertEqual(raw['kind'], 'development_forward_window_v1')
            self.assertIsNone(raw['window'])
            self.assertEqual(raw['confirmed']['forwards'], 4)
            self.assertEqual([b['stage'] for b in raw['payload']['batches']], ['selection', 'terminal'])
            self.assertIn('response', raw['payload']['batches'][-1])
            summary = runner.finalize_development(state, output)
            self.assertEqual(summary['exit_code'], 4)
            self.assertEqual(summary['campaign']['requested'], 308)
            legacy_output = Path(self.raw.name)/'legacy-comparison'
            legacy = runner.run_development(plan, d, p, starts, legacy_output, solver_kind='fixture',
                                            spot_checks={'terminal': [0]})
            self.assertEqual(legacy['status'], 'completed', legacy.get('exit_reason'))
            legacy_raw = json.loads((legacy_output/legacy['jobs'][0]['raw_path']).read_bytes())
            self.assertEqual(legacy_raw['requested'], raw['payload']['requested'])
            self.assertEqual(legacy_raw['completed'], raw['payload']['completed'])
            self.assertEqual(legacy_raw['selection'], raw['payload']['selection'])
            self.assertEqual(legacy_raw['terminal'], raw['payload']['terminal'])
            self.assertEqual(raw['payload']['batches'][-1]['independent']['status'], 'pass')
            self.assertEqual(legacy_raw['batches'][-1]['independent'], raw['payload']['batches'][-1]['independent'])
            self.assertEqual(forward.call_count, 8)
            self.assertEqual(summary['io']['worker']['atomic_writes'], raw['checkpoint_number'])
            self.assertEqual(summary['io']['summary']['payload_bytes'], len((output/'summary.json').read_bytes()))
        from lpf.search.worker import JobSpec
        spec = JobSpec(**state['jobs'][0]['spec'])
        path = output/state['jobs'][0]['raw_path']
        corruptions = [
            lambda r: r.update(identity={}),
            lambda r: r['confirmed'].update(requested=0),
            lambda r: r['previous_confirmed'].update(forwards=9999),
            lambda r: r['previous_uncertain_upper'].update(requested=0),
            lambda r: r['payload']['progress_by_allocation']['demo/coarse'].update(forwards=1),
            lambda r: r['payload']['progress_by_allocation']['demo/coarse'].update(completed=0),
            lambda r: r['payload']['best_observed_by_stage']['demo/coarse']['assessment'].update(nominal_pass='yes'),
            lambda r: r['payload']['best_observed_by_stage']['demo/coarse']['physical_checks'].update(checked_settings=5),
            lambda r: r['payload']['best_observed_by_stage']['demo/coarse']['assessment']['rows'].pop(),
            lambda r: r['payload']['best_observed_by_stage']['demo/coarse']['assessment']['rows'][0].update(violation_db=1234),
            lambda r: r['payload']['batches'][-1]['independent'].update(power_balance='fail'),
            lambda r: r['payload']['batches'][-1]['independent']['samples'][0].update(il_db=100.),
            lambda r: r.update(window={'reserved_samples': 70}),
            lambda r: r['payload']['batches'][0]['assessment'].update(policy_id='wrong'),
            lambda r: r['payload']['batches'][-1].pop('response'),
            lambda r: r['payload']['best_observed_by_stage']['demo/coarse'].update(vector_sha256='0'*64),
            lambda r: r['payload']['selection']['ranked'][0].update(batch_index=0),
            lambda r: r['payload']['selection']['ranked'][0].update(rank_key=[0]),
            lambda r: r['payload']['terminal']['candidates'][0].update(vector_sha256='0'*64),
        ]
        for mutate in corruptions:
            broken = copy.deepcopy(raw)
            mutate(broken)
            atomic(path, broken)
            with self.assertRaises((ValueError, KeyError)):
                runner._window_development_readback(path, broken, spec)
        atomic(path, raw)
        with self.assertRaises((ValueError, KeyError)):
            runner._development_readback(path, raw, spec)

    def test_window_anytime_candidate_binding_mock(self):
        import numpy as np
        from lpf.rf_core.model import RFEvaluator, RFResponse
        from lpf.search._window_evaluation import WindowJobEvaluation
        from lpf.search.worker import JobSpec
        plan, d, p, x = self.setup_model(mutate=lambda c: c.update(anytime_samples=[56]))
        starts = {23: dict(vector=x.tolist(), vector_sha256=vector_sha(x))}
        output = Path(self.raw.name)/'window-anytime'
        def fake_forward(evaluator, vector):
            n = len(evaluator.grid.frequency_hz)
            return RFResponse(evaluator.grid, evaluator.model.policy_id, evaluator.model.policy_fingerprint,
                np.zeros((n, 2, 2), complex), *[np.zeros(n) for _ in range(4)])
        with patch.object(runner, '_validate_development_output'), \
             patch.object(WindowJobEvaluation, '_validate_checkpoint'), \
             patch.object(RFEvaluator, 'evaluate', autospec=True, side_effect=fake_forward), \
             patch('lpf.search.worker.slsqp_minimize', side_effect=worker_tests.FixedWorkerTests.fixture):
            state = runner.run_development(plan, d, p, starts, output, solver_kind='fixture', storage_mode='window100')
        self.assertEqual(state['status'], 'completed', state.get('exit_reason'))
        path = output/state['jobs'][0]['raw_path']
        raw = json.loads(path.read_bytes())
        scan = raw['payload']['anytime'][0]
        self.assertEqual(scan['observation_vector_sha256'], vector_sha(x))
        scan['observation_vector_sha256'] = '0'*64
        atomic(path, raw)
        with self.assertRaises(ValueError):
            runner._window_development_readback(path, raw, JobSpec(**state['jobs'][0]['spec']))

    def test_window_hybrid_scores_checkpoint_and_readback(self):
        # Fixed mock assessments have the same max/sum violation but different
        # squared sums; science rank ties while the Hybrid objective does not.
        import numpy as np
        from lpf.rf_core.model import RFEvaluator, RFResponse
        from lpf.search._window_evaluation import WindowJobEvaluation
        from lpf.search.performance import grid_fingerprint
        from lpf.search.worker import JobSpec
        def config(c):
            c['anytime_samples'] = []
            step = c['arms'][0]['steps'][0]
            step.update(solver='hybrid', aggregation='sum',
                options=dict(maxiter=2, max_restarts=0, max_evaluations=4, restart_sigma=0.1))
        plan, d, p, x = self.setup_model(mutate=config)
        starts = {23: dict(vector=x.tolist(), vector_sha256=vector_sha(x))}
        output = Path(self.raw.name)/'window-hybrid'
        def fake_forward(evaluator, vector):
            n = len(evaluator.grid.frequency_hz)
            return RFResponse(evaluator.grid, evaluator.model.policy_id, evaluator.model.policy_fingerprint,
                np.zeros((n, 2, 2), complex), *[np.zeros(n) for _ in range(4)])
        calls = []
        def fake_assessment(response, req, *, requested_grid):
            search = grid_fingerprint(requested_grid) == plan.data['grids']['demo/coarse']['sha256']
            if search: calls.append(1)
            g = [-3., -2., 0.] if not search or len(calls) == 1 else [-3., -1., -1.]
            return dict(status='evaluated', policy_id=req.policy_id, policy_fingerprint=req.policy_fingerprint,
                mode=req.mode, requirements_fingerprint=req.fingerprint, grid_fingerprint=grid_fingerprint(requested_grid),
                strict_feasible=False, worst_il_db=1., max_violation_db=3., sum_violation_db=5.,
                mandatory_g=g, rows=[])
        seen = []
        def solver(residuals, vector, bounds, **options):
            for _ in range(2):
                r = residuals(vector)
                seen.append(float(np.sum(r*r)))
            return worker_tests.FixtureHybrid([worker_tests.FixtureRun(list(vector))], list(vector))
        with patch.object(runner, '_validate_development_output'), \
             patch.object(WindowJobEvaluation, '_validate_checkpoint'), \
             patch.object(RFEvaluator, 'evaluate', autospec=True, side_effect=fake_forward), \
             patch('lpf.search._window_evaluation.evaluate_requirements', side_effect=fake_assessment), \
             patch('lpf.search.worker.hybrid_minimize', side_effect=solver):
            state = runner.run_development(plan, d, p, starts, output, solver_kind='fixture', storage_mode='window100',
                                           debug_forward_history=True)
        self.assertEqual(state['status'], 'completed', state.get('exit_reason'))
        self.assertEqual(seen, [14., 12.])
        raw_path = output/state['jobs'][0]['raw_path']
        raw = json.loads(raw_path.read_bytes())
        payload = raw['payload']
        self.assertEqual([r['assessment']['hybrid_objective']['value'] for r in payload['batches'][:2]], seen)
        self.assertEqual(payload['best_observed_by_stage']['demo/coarse']['batch_index'], 0)
        self.assertEqual(payload['best_hybrid_observed_by_stage']['demo/coarse']['batch_index'], 1)
        spec = JobSpec(**state['jobs'][0]['spec'])
        for mutate in (
            lambda r: r['payload']['batches'][0]['assessment']['hybrid_objective'].update(value=20.),
            lambda r: r['payload']['batches'][0]['assessment']['hybrid_objective'].update(aggregation='max'),
            lambda r: r['payload']['best_hybrid_observed_by_stage']['demo/coarse'].update(batch_index=0),
            lambda r: r['payload']['batches'][0]['assessment'].pop('hybrid_objective'),
        ):
            broken = copy.deepcopy(raw); mutate(broken); atomic(raw_path, broken)
            with self.assertRaises((ValueError, KeyError)):
                runner._window_development_readback(raw_path, broken, spec)

    def test_window_output_rejects_tmp_checkout_and_other_git_checkout(self):
        import tempfile
        root = Path.cwd().resolve()
        for output, source_root in ((Path(tempfile.gettempdir())/'window-output', root),
                                    (root/'window-output', root),
                                    (root/'window-output', Path('/nonexistent-other-root'))):
            with self.subTest(output=output, source_root=source_root), self.assertRaises(ValueError):
                runner._validate_development_output(output, source_root, 'window100')
        runner._validate_development_output(Path('/var')/'issue369-test-output', root, 'window100')

    def test_window_failure_keeps_parent_cap_and_prior_window(self):
        from lpf.rf_core.model import RFEvaluator
        from lpf.search._window_evaluation import WindowJobEvaluation
        plan, d, p, x = self.setup_model(mutate=lambda c: c.update(anytime_samples=[]))
        starts = {23: dict(vector=x.tolist(), vector_sha256=vector_sha(x))}
        output = Path(self.raw.name)/'window-failure'
        with patch.object(runner, '_validate_development_output'), \
             patch.object(WindowJobEvaluation, '_validate_checkpoint'), \
             patch.object(RFEvaluator, 'evaluate', side_effect=RuntimeError('fixture crash')), \
             patch('lpf.search.worker.slsqp_minimize', side_effect=worker_tests.FixedWorkerTests.fixture):
            state = runner.run_development(plan, d, p, starts, output, solver_kind='fixture', storage_mode='window100')
        self.assertEqual(state['status'], 'unknown')
        row = state['jobs'][0]
        self.assertEqual((row['requested'], row['reserved'], row['released']), (0, row['cap'], 0))
        raw = json.loads((output/row['raw_path']).read_bytes())
        self.assertEqual(raw['confirmed']['requested'], 0)
        self.assertGreater(raw['uncertain_upper']['requested'], 0)
        self.assertIsNotNone(raw['window'])

    def test_window_failure_after_three_forwards_keeps_confirmed_payload(self):
        import numpy as np
        from lpf.rf_core.model import RFEvaluator, RFResponse
        from lpf.search._window_evaluation import WindowJobEvaluation
        from lpf.search.worker import JobSpec
        plan, d, p, x = self.setup_model(mutate=lambda c: c.update(anytime_samples=[]))
        starts = {23: dict(vector=x.tolist(), vector_sha256=vector_sha(x))}
        output = Path(self.raw.name)/'window-partial-failure'
        calls = []
        def fake_forward(evaluator, vector):
            calls.append(1)
            if len(calls) == 4:
                raise RuntimeError('fourth mock forward failed')
            n = len(evaluator.grid.frequency_hz)
            return RFResponse(evaluator.grid, evaluator.model.policy_id, evaluator.model.policy_fingerprint,
                np.zeros((n, 2, 2), complex), *[np.zeros(n) for _ in range(4)])
        def solver(callback, vector, bounds, **kwargs):
            for _ in range(4): callback(vector)
            raise AssertionError('fourth forward must fail')
        with patch.object(runner, '_validate_development_output'), \
             patch.object(WindowJobEvaluation, '_validate_checkpoint'), \
             patch.object(RFEvaluator, 'evaluate', autospec=True, side_effect=fake_forward), \
             patch('lpf.search.worker.slsqp_minimize', side_effect=solver):
            state = runner.run_development(plan, d, p, starts, output, solver_kind='fixture', storage_mode='window100')
        self.assertEqual(len(calls), 4)
        self.assertEqual(state['status'], 'unknown')
        job = state['jobs'][0]
        self.assertEqual((job['requested'], job['reserved'], job['released']), (0, job['cap'], 0))
        path = output/job['raw_path']
        raw = json.loads(path.read_bytes())
        self.assertEqual(raw['termination']['status'], 'unknown')
        self.assertIn('fourth mock forward failed', raw['termination']['reason'])
        self.assertEqual(raw['confirmed'], dict(forwards=0, requested=0, completed=0))
        self.assertEqual((raw['payload']['requested'], raw['payload']['completed']), (0, 0))
        self.assertEqual(raw['payload']['batches'], [])
        self.assertGreaterEqual(raw['uncertain_upper']['requested'], 4*56)
        with self.assertRaisesRegex(ValueError, 'uncertain'):
            runner._window_development_readback(path, raw, JobSpec(**job['spec']))

    def test_window_budget_exhaustion_reconciles_without_extra_forward(self):
        import numpy as np
        from lpf.rf_core.model import RFEvaluator, RFResponse
        from lpf.search._window_evaluation import WindowJobEvaluation
        def config(c):
            c['anytime_samples'] = []
            c['arms'][0]['steps'][0]['max_requested_samples'] = 112
        plan, d, p, x = self.setup_model(mutate=config)
        starts = {23: dict(vector=x.tolist(), vector_sha256=vector_sha(x))}
        output = Path(self.raw.name)/'window-budget'
        def fake_forward(evaluator, vector):
            n = len(evaluator.grid.frequency_hz)
            return RFResponse(evaluator.grid, evaluator.model.policy_id, evaluator.model.policy_fingerprint,
                np.zeros((n, 2, 2), complex), *[np.zeros(n) for _ in range(4)])
        def solver(callback, vector, bounds, **kwargs):
            for _ in range(3): callback(vector)
            raise AssertionError('Must stop before third mock forward')
        with patch.object(runner, '_validate_development_output'), \
             patch.object(WindowJobEvaluation, '_validate_checkpoint'), \
             patch.object(RFEvaluator, 'evaluate', autospec=True, side_effect=fake_forward) as forward, \
             patch('lpf.search.worker.slsqp_minimize', side_effect=solver):
            state = runner.run_development(plan, d, p, starts, output, solver_kind='fixture', storage_mode='window100')
        self.assertEqual(forward.call_count, 2)
        self.assertEqual(state['status'], 'completed', state.get('exit_reason'))
        row = state['jobs'][0]
        self.assertEqual((row['worker_status'], row['requested'], row['completed']), ('budget_exhausted', 112, 112))
        self.assertEqual(row['reserved'], 0)
        self.assertTrue(row['safe_to_release'])

    def test_window_initial_save_failure_keeps_parent_unknown(self):
        from lpf.rf_core.model import RFEvaluator
        from lpf.search._window_evaluation import WindowJobEvaluation
        plan, d, p, x = self.setup_model(mutate=lambda c: c.update(anytime_samples=[]))
        starts = {23: dict(vector=x.tolist(), vector_sha256=vector_sha(x))}
        output = Path(self.raw.name)/'window-save-failure'
        with patch.object(runner, '_validate_development_output'), \
             patch.object(WindowJobEvaluation, '_validate_checkpoint'), \
             patch('lpf.search._forward_window.atomic_verified', side_effect=OSError('fixture disk failure')) as save, \
             patch.object(RFEvaluator, 'evaluate') as forward:
            state = runner.run_development(plan, d, p, starts, output, solver_kind='fixture', storage_mode='window100')
        self.assertEqual(save.call_count, 1)
        forward.assert_not_called()
        self.assertEqual(state['status'], 'unknown')
        self.assertEqual(state['jobs'][0]['reserved'], state['jobs'][0]['cap'])
        self.assertEqual(state['jobs'][0]['released'], 0)
        self.assertTrue((output/state['jobs'][0]['raw_path']).exists())

    def test_mock_two_seeds_are_separate_trials_and_fixed_order(self):
        args = self.setup_parent([23, 24])
        seen = []
        def worker(spec, path, **kw):
            durable = json.loads((path.parent/'run.json').read_text())
            row = durable['jobs'][len(seen)]
            self.assertEqual(row['status'], 'unknown')
            self.assertEqual(row['reserved'], row['cap'])
            self.assertTrue(all(j['status'] == 'completed' for j in durable['jobs'][:len(seen)]))
            self.assertTrue(all(j['status'] == 'not_started' for j in durable['jobs'][len(seen)+1:]))
            seen.append((spec.data['seed'], spec.data['arm']))
            return self.mock_result(spec, path, **kw)
        with patch.object(runner, 'execute_development_job', side_effect=worker):
            state = runner.run_development(*args, solver_kind='fixture')
        self.assertEqual(seen, [(23, 'demo'), (23, 'other'), (24, 'demo'), (24, 'other')])
        self.assertEqual([t['requested'] for t in state['trials'].values()], [112, 112])
        self.assertEqual(state['campaign']['requested'], 224)
        self.assertNotIn('cap', state['campaign'])

    def test_bad_starts_plan_caps_specs_and_output_stop_before_worker(self):
        args = self.setup_parent()
        bad_starts = [dict(args[3], **{'99': args[3][23]}), {},
                      {99: args[3][23]}, {23: dict(args[3][23], vector_sha256='0'*64)}]
        for starts in bad_starts:
            with patch.object(runner, 'execute_development_job') as worker:
                with self.assertRaises(ValueError): runner.run_development(*args[:3], starts, args[-1])
                worker.assert_not_called()
                self.assertFalse(args[-1].exists())
        for change in (lambda d: d['config'].update(max_trial_requested_samples=2999),
                       lambda d: d['costs'].update(trial_job_cap_reservation=1)):
            data = args[0].data; change(data)
            bad = replace(args[0], frozen_json=canonical(data), sha256=sha(data))
            with self.assertRaises(ValueError): runner.run_development(bad, *args[1:])
        real_freeze = runner.freeze_development_job
        for field, value in [('job_id', 'duplicate'), ('trial_id', 'seed23')]:
            def bad_freeze(*a, **kw): return replace(real_freeze(*a, **kw), **{field: value})
            with patch.object(runner, 'freeze_development_job', side_effect=bad_freeze):
                with self.assertRaises(ValueError): runner.run_development(*args)
        for output in (Path.cwd()/'results/parent', Path('/var/parent')):
            with self.assertRaises(ValueError): runner.run_development(*args[:-1], output)

    def test_unknown_exception_interrupt_and_missing_raw_hold_full_cap_stop_all(self):
        for failure in ('failed', 'interrupted', 'unknown', 'exception', 'interrupt', 'missing'):
            args = self.setup_parent([23, 24])
            def worker(spec, path, **kw):
                if failure == 'exception': raise RuntimeError('worker crash')
                if failure == 'interrupt': raise KeyboardInterrupt()
                result = self.mock_result(spec, path, **kw)
                if failure == 'missing': path.unlink()
                else:
                    result.update(status=failure, evaluation_status='unknown', completed=0)
                    result['batches'][0].update(status='unknown', completed=0)
                    atomic(path, result)
                return result
            with patch.object(runner, 'execute_development_job', side_effect=worker) as call:
                state = runner.run_development(*args, solver_kind='fixture')
            self.assertEqual(call.call_count, 1)
            self.assertEqual(state['status'], 'unknown')
            row = state['jobs'][0]
            self.assertEqual(row['status'], 'unknown')
            self.assertEqual(row['requested']+row['reserved'], row['cap'])
            self.assertEqual(row['released'], 0)
            self.assertTrue(all(j['status'] == 'not_started' for j in state['jobs'][1:]))
            with self.assertRaisesRegex(ValueError, 'Existing'): runner.run_development(*args)

    def test_raw_corruption_and_self_consistent_digest_do_not_bypass_contract(self):
        def mutations():
            yield lambda r: r.update(requested=-1)
            yield lambda r: r.update(completed=r['requested']+1)
            yield lambda r: r.update(requested=True)
            yield lambda r: r['batches'][0].update(requested=0)
            yield lambda r: r.update(plan_sha256='0'*64)
            yield lambda r: r['spec'].update(job_id='wrong')
            yield lambda r: r['spec'].update(source_sha256='0'*64)
            yield lambda r: r.update(policy_fingerprint='0'*64)
            yield lambda r: r['grids']['terminal'].update(sha256='0'*64)
            yield lambda r: r['reservations'].update(other_jobs=0)
            yield lambda r: r['batches'][0].update(grid_sha256='0'*64)
            yield lambda r: r['spec'].update(frozen_json='{}')
        for mutation in mutations():
            args = self.setup_parent()
            def worker(spec, path, **kw):
                result = self.mock_result(spec, path, **kw)
                mutation(result); atomic(path, result)
                return result  # same altered snapshot: semantic checks still required
            with patch.object(runner, 'execute_development_job', side_effect=worker) as call:
                state = runner.run_development(*args, solver_kind='fixture')
            self.assertEqual(call.call_count, 1)
            self.assertEqual(state['status'], 'unknown')
            self.assertEqual(state['jobs'][0]['reserved'], 1500)
        for corruption in ('whitespace', 'numeric', 'invalid_json'):
            args = self.setup_parent()
            def worker(spec, path, **kw):
                result = self.mock_result(spec, path, **kw)
                if corruption == 'whitespace': path.write_bytes(path.read_bytes()+b' ')
                elif corruption == 'invalid_json': path.write_text('{')
                else:
                    modified = copy.deepcopy(result); modified['requested'] += 1; atomic(path, modified)
                return result
            with patch.object(runner, 'execute_development_job', side_effect=worker):
                state = runner.run_development(*args, solver_kind='fixture')
            self.assertEqual(state['status'], 'unknown')

    def test_completed_batch_requires_response_and_bound_assessment(self):
        cases = [('missing_response', lambda b: b.pop('response')),
                 ('missing_assessment', lambda b: b.pop('assessment'))]
        for key in ('s_real', 's_imag', 'il_db', 'apl_db', 'in_rl_db', 'out_rl_db'):
            cases.append((f'missing_{key}', lambda b, key=key: b['response'].pop(key)))
            cases.append((f'short_{key}', lambda b, key=key: b['response'][key].pop()))
        # Correct outer sample count is insufficient for a malformed complex S.
        cases.append(('bad_s_shape', lambda b: b['response'].update(s_real=[0.] * b['requested'])))
        for key in ('status', 'policy_id', 'policy_fingerprint', 'mode',
                    'requirements_fingerprint', 'grid_fingerprint'):
            cases.append((f'wrong_{key}', lambda b, key=key: b['assessment'].update({key: 'wrong'})))
        for name, mutate in cases:
            with self.subTest(case=name):
                args = self.setup_parent()
                def worker(spec, path, **kw):
                    result = self.mock_result(spec, path, **kw)
                    mutate(result['batches'][0])
                    atomic(path, result)
                    # Both raw bytes and returned snapshot carry the same defect.
                    self.assertEqual(json.loads(path.read_text()), result)
                    return result
                with patch.object(runner, 'execute_development_job', side_effect=worker) as call:
                    state = runner.run_development(*args, solver_kind='fixture')
                self.assertEqual(call.call_count, 1)
                self.assertEqual(state['status'], 'unknown')
                row = state['jobs'][0]
                self.assertEqual((row['status'], row['requested'], row['reserved'], row['released']),
                                 ('unknown', 0, row['cap'], 0))
                self.assertEqual(state['jobs'][1]['status'], 'not_started')
                self.assertEqual(json.loads((args[-1]/'run.json').read_text()), state)

    def test_budget_is_accepted_but_not_rf_success(self):
        args = self.setup_parent()
        def worker(spec, path, **kw):
            result = self.mock_result(spec, path, **kw)
            result.update(status='budget_exhausted', evaluation_status='stopped')
            atomic(path, result); return result
        with patch.object(runner, 'execute_development_job', side_effect=worker):
            state = runner.run_development(*args, solver_kind='fixture')
        self.assertEqual(state['status'], 'completed')
        self.assertTrue(all(r['worker_status'] == 'budget_exhausted' for r in state['jobs']))
        self.assertTrue(all(r['evidence']['terminal']['status'] == 'not_run' for r in state['jobs']))

    def test_parent_save_failure_never_retries_or_commits_in_memory_success(self):
        for when in ('unknown_marker', 'import'):
            args = self.setup_parent()
            saves = 0
            def save(path, value):
                nonlocal saves
                saves += 1
                if (when == 'unknown_marker' and value['jobs'][0]['status'] == 'unknown' or
                        when == 'import' and value['jobs'][0]['status'] == 'completed'):
                    raise OSError('disk failure')
                return atomic(path, value)
            with patch.object(runner, 'execute_development_job', side_effect=self.mock_result) as worker, \
                 patch.object(runner, 'atomic', side_effect=save):
                with self.assertRaises(OSError): runner.run_development(*args, solver_kind='fixture')
            self.assertEqual(worker.call_count, 0 if when == 'unknown_marker' else 1)
            self.assertEqual(saves, 2 if when == 'unknown_marker' else 3)
            durable = json.loads((args[-1]/'run.json').read_text())
            self.assertEqual(durable['jobs'][0]['status'], 'not_started' if when == 'unknown_marker' else 'unknown')
            self.assertEqual(durable['jobs'][0]['reserved'], 1500)
            self.assertEqual(durable['jobs'][0]['requested'], 0)

    def test_uncaught_parent_exit_leaves_last_durable_unknown(self):
        args = self.setup_parent()
        with patch.object(runner, 'execute_development_job', side_effect=self.mock_result), \
             patch.object(runner, '_development_readback', side_effect=SystemExit('external stop')):
            with self.assertRaises(SystemExit): runner.run_development(*args, solver_kind='fixture')
        state = json.loads((args[-1]/'run.json').read_text())
        self.assertEqual(state['jobs'][0]['status'], 'unknown')
        self.assertEqual(state['jobs'][0]['reserved'], 1500)
        self.assertEqual(state['jobs'][1]['status'], 'not_started')
        self.assertTrue((args[-1]/state['jobs'][0]['raw_path']).exists())

    def test_stop_immediately_before_import_keeps_durable_unknown(self):
        args = self.setup_parent()
        with patch.object(runner, 'execute_development_job', side_effect=self.mock_result), \
             patch.object(runner, '_development_readback', side_effect=KeyboardInterrupt()):
            state = runner.run_development(*args, solver_kind='fixture')
        self.assertEqual(state['jobs'][0]['status'], 'unknown')
        self.assertEqual(state['jobs'][0]['reserved'], 1500)
        self.assertEqual(state['jobs'][1]['status'], 'not_started')


if __name__ == '__main__':
    unittest.main()

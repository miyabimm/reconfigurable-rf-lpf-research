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
                vector_sha256=d['start']['vector_sha256'], independent=dict(status='not_run'))])
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

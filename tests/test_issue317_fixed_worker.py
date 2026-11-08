"""Bounded development Worker tests, real tiny RF and explicitly fixture solvers."""
import copy
from dataclasses import dataclass, replace
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import numpy as np

import test_issue315_fixed_stage as stage_tests
from lpf.rf_core.model import RFEvaluator
from lpf.search.worker import freeze_development_job, execute_development_job
from lpf.search._job_evaluation import FixedJobEvaluation
from lpf.search.storage import canonical, sha, vector_sha
from lpf.search.plan import Plan


@dataclass
class FixtureOutput:
    x: np.ndarray
    success: bool = False
    nfev: int = 999  # deliberately unrelated to RF samples
    stop_reason: str = 'fixture_nonconvergence'


@dataclass
class FixtureRun:
    end_x: list | None
    success: bool = False


@dataclass
class FixtureHybrid:
    runs: list
    best_x: list | None
    reason: str = 'fixture_nonconvergence'


class FixedWorkerTests(unittest.TestCase):
    setUp = stage_tests.FixedStageTests.setUp
    setup_model = stage_tests.FixedStageTests.setup_model

    def job(self, mutate=None, cid='RF-F003', mode='full_lpf'):
        def config(c):
            first = c['arms'][0]['steps'][0]
            first['max_requested_samples'] = 224
            second = copy.deepcopy(first)
            second.update(name='fine', points_per_interval=2)
            c['arms'][0]['steps'].append(second)
            c['anytime_samples'] = [56, 168]
            if mutate:
                mutate(c)
        plan, definition, policy, x = self.setup_model(cid, mode, config)
        spec = freeze_development_job(plan, definition, policy, 'demo', 23, x)
        self.counter += 1
        path = Path(self.raw.name)/f'worker{self.counter}.json'
        return spec, path, plan, definition, policy, x

    @staticmethod
    def fixture(residuals, x, bounds, **options):
        residuals(x)
        options['constraints'](x)
        return FixtureOutput(np.array(x))

    def run_fixture(self, spec, path, solver=None):
        with patch('lpf.search.worker.slsqp_minimize', side_effect=solver or self.fixture):
            return execute_development_job(spec, path, solver_kind='fixture')

    def test_two_steps_real_rf_one_selection_shared_cost_and_audit(self):
        spec, path, plan, d, p, x = self.job()
        result = self.run_fixture(spec, path)
        self.assertEqual(result['status'], 'not_converged')
        self.assertEqual(result['requested'], 588)  # 4*56 + 2*84 + 84 + 112
        self.assertEqual(result['completed'], 588)
        self.assertEqual(result['search_requested'], 224)
        self.assertEqual([r['stage'] for r in result['batches']],
            ['demo/coarse', 'anytime', 'demo/coarse', 'demo/fine', 'anytime', 'demo/fine', 'selection', 'terminal'])
        self.assertEqual([s['status'] for s in result['anytime']], ['completed']*2)
        self.assertEqual(result['dense']['status'], 'not_run')
        self.assertEqual(result['steps'][1]['input_vector_sha256'], vector_sha(x))
        self.assertEqual(len(result['selection']['ranked']), 1)
        self.assertEqual(result['terminal']['status'], 'completed')
        self.assertEqual(result['solver_execution_kind'], 'fixture')
        for row in result['batches']:
            self.assertEqual(len(row['response']['s_real']), row['requested'])
            self.assertEqual(row['grid_sha256'], plan.data['grids'][row['stage']]['sha256'])
            self.assertEqual(row['independent']['status'], 'not_run')
        self.assertFalse(result['rf_compliance_certified'])
        self.assertEqual(json.loads(path.read_text()), result)
        with self.assertRaisesRegex(ValueError, 'Existing'):
            self.run_fixture(spec, path)
        # Existing audit API works on a named batch in an earlier step's grid.
        meter = FixedJobEvaluation(plan, d, p, 'demo', Path(self.raw.name)/'audit.json', spec, root=Path.cwd())
        meter.activate('demo/coarse', 'demo/coarse')
        meter.evaluate(x)
        meter.finish()
        meter.activate('demo/fine', 'demo/fine')
        self.assertEqual(meter.spot_check(0, [0, 55])['status'], 'pass')
        self.assertEqual(meter.rows[0]['independent']['completed'], 2)

    def test_window_meter_keeps_normal_mock_forwards_in_memory(self):
        # RF evaluator/requirements are fixtures: no RF forward is executed.
        from types import SimpleNamespace
        from lpf.search._window_evaluation import WindowJobEvaluation
        spec, path, plan, d, p, x = self.job(lambda c: c.update(anytime_samples=[]))
        spec = freeze_development_job(plan, d, p, 'demo', 23, x, storage_mode='window100')
        with patch.object(WindowJobEvaluation, '_validate_checkpoint'):
            meter = WindowJobEvaluation(plan, d, p, 'demo', path, spec, root=Path.cwd())
        meter.activate('demo/coarse', 'demo/coarse')
        before = path.read_bytes()
        n = len(meter.grid.frequency_hz)
        response = SimpleNamespace(s=np.zeros((n, 2, 2), complex),
            il_db=np.zeros(n), apl_db=np.zeros(n), in_rl_db=np.zeros(n), out_rl_db=np.zeros(n))
        assessment = dict(status='evaluated', policy_id=p['active_constraint_id'],
            policy_fingerprint=meter.model.policy_fingerprint, mode='full_lpf',
            requirements_fingerprint=meter.requirements.fingerprint, grid_fingerprint=plan.data['grids']['demo/coarse']['sha256'],
            strict_feasible=False, worst_il_db=1., max_violation_db=2., sum_violation_db=3., rows=[])
        with patch.object(RFEvaluator, 'evaluate', return_value=response) as forward, \
             patch('lpf.search._window_evaluation.evaluate_requirements', return_value=assessment), \
             patch.object(meter, '_contract', side_effect=AssertionError('per-forward contract')), \
             patch('builtins.open', side_effect=AssertionError('forward file open')), \
             patch.object(Path, 'open', side_effect=AssertionError('forward Path.open')):
            meter.evaluate(x)
            meter.evaluate(x)
        self.assertEqual(forward.call_count, 2)
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual((meter.requested, meter.completed), (2*n, 2*n))
        meter.finish()
        saved = json.loads(path.read_bytes())
        self.assertEqual(saved['confirmed']['requested'], 2*n)
        self.assertIsNone(saved['window'])
        self.assertNotIn('response', saved['payload']['batches'][0])
        self.assertEqual(saved['payload']['best_observed_by_stage']['demo/coarse']['vector_sha256'], vector_sha(x))

    def test_window_meter_99_100_101_with_mock_rf(self):
        from types import SimpleNamespace
        from lpf.search._window_evaluation import WindowJobEvaluation
        def configure(c):
            c['anytime_samples'] = []
            c['arms'][0]['steps'][0]['max_requested_samples'] = 102*56
            c['arms'][0]['max_requested_samples'] = 9000
            c['max_trial_requested_samples'] = 9000
        _, path, plan, d, p, x = self.job(configure)
        spec = freeze_development_job(plan, d, p, 'demo', 23, x, storage_mode='window100')
        with patch.object(WindowJobEvaluation, '_validate_checkpoint'):
            meter = WindowJobEvaluation(plan, d, p, 'demo', path, spec, root=Path.cwd())
        meter.activate('demo/coarse', 'demo/coarse')
        n = len(meter.grid.frequency_hz)
        response = SimpleNamespace(s=np.zeros((n, 2, 2), complex),
            il_db=np.zeros(n), apl_db=np.zeros(n), in_rl_db=np.zeros(n), out_rl_db=np.zeros(n))
        assessment = dict(status='evaluated', policy_id=p['active_constraint_id'],
            policy_fingerprint=meter.model.policy_fingerprint, mode='full_lpf',
            requirements_fingerprint=meter.requirements.fingerprint, grid_fingerprint=plan.data['grids']['demo/coarse']['sha256'],
            strict_feasible=False, worst_il_db=1., max_violation_db=2., sum_violation_db=3., rows=[])
        with patch.object(RFEvaluator, 'evaluate', return_value=response) as forward, \
             patch('lpf.search._window_evaluation.evaluate_requirements', return_value=assessment), \
             patch.object(meter.journal, 'validate_inputs', wraps=meter.journal.validate_inputs) as contract:
            for _ in range(99): meter.evaluate(x)
            self.assertEqual((meter.journal.write_calls, contract.call_count), (1, 0))
            self.assertEqual(json.loads(path.read_bytes())['confirmed']['forwards'], 0)
            meter.evaluate(x)
            boundary = json.loads(path.read_bytes())
            self.assertEqual((meter.journal.write_calls, contract.call_count), (2, 1))
            self.assertEqual((boundary['confirmed']['forwards'], boundary['window']['end_forward']), (100, 102))
            meter.evaluate(x)
            self.assertEqual((meter.journal.write_calls, contract.call_count), (2, 1))
            self.assertEqual(forward.call_count, 101)
        meter.finish()
        saved = json.loads(path.read_bytes())
        self.assertEqual((saved['confirmed']['forwards'], saved['confirmed']['requested']), (101, 101*n))
        self.assertIsNone(saved['window'])

    def test_frozen_model_validation_matches_legacy_and_rejects_bad_values(self):
        from lpf.search.component_constraints import validate_values
        from lpf.rf_core.model import build_rf_model
        _, _, _, d, p, x = self.job(lambda c: c.update(anytime_samples=[]))
        model = build_rf_model(d, p)
        self.assertEqual(validate_values(d, model.schema, x, p),
                         validate_values(d, model.schema, x, p, frozen_model=model))
        bad = x.copy(); bad[0] = -1
        with self.assertRaises(ValueError):
            validate_values(d, model.schema, bad, p, frozen_model=model)
        altered = copy.deepcopy(p); altered['source_ohms']['real'] += 1
        with self.assertRaisesRegex(ValueError, 'Frozen model'):
            validate_values(d, model.schema, x, altered, frozen_model=model)

    def test_window_boundary_detects_source_and_rf_changes_without_release(self):
        from lpf.search._window_evaluation import WindowJobEvaluation
        for changed in ('source', 'rf'):
            with self.subTest(changed=changed):
                _, path, plan, d, p, x = self.job(lambda c: c.update(anytime_samples=[]))
                spec = freeze_development_job(plan, d, p, 'demo', 23, x, storage_mode='window100')
                with patch.object(WindowJobEvaluation, '_validate_checkpoint'):
                    meter = WindowJobEvaluation(plan, d, p, 'demo', path, spec, root=Path.cwd())
                meter.activate('demo/coarse', 'demo/coarse')
                before = path.read_bytes()
                if changed == 'source':
                    change = patch('lpf.search._job_evaluation.source_identity', return_value={})
                else:
                    wrong = plan.data
                    wrong['rf_inputs']['bands']['sha256'] = '0'*64
                    change = patch('lpf.search.evaluation.freeze', return_value=wrong)
                with change, self.assertRaises(ValueError):
                    meter.finish()
                self.assertEqual(path.read_bytes(), before)
                self.assertIsNotNone(json.loads(before)['window'])
                self.assertEqual(meter.status, 'storage_failed')

    def test_frozen_independent_samples_in_worker(self):
        spec, path, plan, d, p, x = self.job()
        spec = freeze_development_job(plan, d, p, 'demo', 23, x,
                                      spot_checks={'terminal': [0, 111], 'anytime': [0]})
        result = self.run_fixture(spec, path)
        self.assertEqual(result['requested'], 588)
        self.assertEqual(result['batches'][-1]['independent']['status'], 'pass')
        self.assertEqual(result['batches'][-1]['independent']['completed'], 2)
        self.assertFalse(result['batches'][-1]['independent']['whole_band_checked'])
        for scan in (r for r in result['batches'] if r['stage'] == 'anytime'):
            self.assertEqual(scan['independent']['completed'], 1)
        with self.assertRaisesRegex(ValueError, 'spot-check'):
            freeze_development_job(plan, d, p, 'demo', 23, x, spot_checks={'terminal': [112]})

    def test_other_job_reservation_is_never_released(self):
        def change(c):
            other = copy.deepcopy(c['arms'][0]); other['name'] = 'other'
            c['arms'].append(other)
            c['max_trial_requested_samples'] = 3000
        spec, path, *_ = self.job(change)
        result = self.run_fixture(spec, path)
        self.assertEqual(result['requested'], 588)
        self.assertEqual(result['reservations']['other_jobs'], 1500)
        self.assertEqual(result['remaining']['trial'], 3000-588)

    def test_step_release_and_reservations_and_one_batch_short(self):
        spec, path, plan, d, p, x = self.job(lambda c: c.update(anytime_samples=[]))
        meter = FixedJobEvaluation(plan, d, p, 'demo', path, spec, root=Path.cwd())
        meter.activate('demo/coarse', 'demo/coarse')
        before = meter.snapshot()['reservations']['inactive']
        self.assertEqual(before, 224+168+112)
        meter.evaluate(x)
        meter.finish()
        self.assertNotIn('demo/coarse', meter.allocations)
        meter.activate('demo/fine', 'demo/fine')
        self.assertEqual(meter.requested, 56)
        self.assertEqual(meter.snapshot()['reservations']['inactive'], 168+112)
        meter.allocations[meter.active] = 55
        with patch.object(RFEvaluator, 'evaluate') as forward:
            with self.assertRaisesRegex(ValueError, 'full batch'): meter.evaluate(x)
            forward.assert_not_called()
        self.assertEqual(meter.requested, 56)
        self.assertEqual(json.loads(path.read_text())['evaluation_status'], 'stopped')

    def test_each_validation_slot_and_job_trial_caps(self):
        for allocation, grid in [('selection:0', 'selection'), ('terminal:0', 'terminal'), ('anytime:0', 'anytime')]:
            for cap in ('allocation', 'job', 'trial'):
                with self.subTest(allocation=allocation, cap=cap):
                    spec, path, plan, d, p, x = self.job()
                    meter = FixedJobEvaluation(plan, d, p, 'demo', path, spec, root=Path.cwd())
                    meter.activate(allocation, grid)
                    n = len(meter.grid.frequency_hz)
                    reserved = meter.snapshot()['reservations']['inactive']
                    if cap == 'allocation':
                        meter.allocations[allocation] = n-1
                    elif cap == 'job':
                        meter.job = dict(meter.job, max_requested_samples=reserved+n-1)
                    else:
                        meter.data['costs']['max_trial_requested_samples'] = reserved+meter.other_jobs+n-1
                        # Isolate runtime arithmetic with a reduced Trial balance;
                        # real contracts are immutable/recompiled before forward.
                        meter._contract = lambda: None
                    with patch.object(RFEvaluator, 'evaluate') as forward:
                        with self.assertRaisesRegex(ValueError, 'full batch'): meter.evaluate(x)
                        forward.assert_not_called()
                    self.assertEqual(meter.requested, 0)

    def test_audit_storage_failure_never_retries_save(self):
        from lpf.search.evaluation import atomic
        spec, path, plan, d, p, x = self.job(lambda c: c.update(anytime_samples=[]))
        meter = FixedJobEvaluation(plan, d, p, 'demo', path, spec, root=Path.cwd())
        meter.activate('demo/coarse', 'demo/coarse'); meter.evaluate(x)
        failures = 0
        def fail(path, value):
            nonlocal failures
            audit = value['batches'][0]['independent']
            if audit.get('completed', 0):
                failures += 1
                raise OSError('audit disk failure')
            return atomic(path, value)
        with patch('lpf.search.evaluation.atomic', side_effect=fail):
            with self.assertRaises(OSError): meter.spot_check(0, [0])
        self.assertEqual(failures, 1)
        self.assertEqual(meter.status, 'storage_failed')
        saved = json.loads(path.read_text())
        self.assertEqual(saved['batches'][0]['independent']['status'], 'unknown')
        self.assertEqual(saved['batches'][0]['independent']['completed'], 0)

    def test_unknown_failure_interrupt_and_no_retry(self):
        for failure in (RuntimeError('numerical failure'), KeyboardInterrupt()):
            spec, path, *_ = self.job()
            def fail(*args):
                saved = json.loads(path.read_text())
                self.assertEqual((saved['requested'], saved['completed'], saved['evaluation_status']), (56, 0, 'unknown'))
                raise failure
            with patch.object(RFEvaluator, 'evaluate', side_effect=fail):
                result = self.run_fixture(spec, path)
            self.assertEqual((result['requested'], result['completed']), (56, 0))
            self.assertEqual(result['status'], 'interrupted' if isinstance(failure, KeyboardInterrupt) else 'failed')
            self.assertIn('demo/coarse', result['allocations'])
            self.assertEqual(result['selection']['status'], 'not_run')
            with self.assertRaisesRegex(ValueError, 'Existing'): self.run_fixture(spec, path)

    def test_save_failure_preserves_durable_unknown(self):
        from lpf.search.evaluation import atomic
        for when in ('before_forward', 'after_forward'):
            spec, path, *_ = self.job()
            def fail(path, value):
                if (when == 'before_forward' and value['requested'] or
                        when == 'after_forward' and value['completed']):
                    raise OSError('disk failure')
                return atomic(path, value)
            with patch('lpf.search.evaluation.atomic', side_effect=fail):
                with self.assertRaises(OSError): self.run_fixture(spec, path)
            saved = json.loads(path.read_text())
            self.assertEqual(saved['completed'], 0)
            self.assertEqual(saved['requested'], 0 if when == 'before_forward' else 56)
            if when == 'after_forward':
                self.assertEqual(saved['batches'][0]['status'], 'unknown')

    def test_unreached_anytime_points_and_matching_mode(self):
        def change(c):
            c['anytime_samples'] = [400]
            c['anytime_points_per_interval'] = 5
            c['validation']['terminal_points'] = 6
        spec, path, *_ = self.job(change, 'RF-T006', 'matching_only')
        result = self.run_fixture(spec, path)
        self.assertEqual(result['search_requested'], 112)
        self.assertEqual(result['anytime'][0]['status'], 'not_run')
        terminal = result['batches'][-1]
        self.assertEqual(terminal['requested'], 84)
        self.assertEqual(terminal['assessment']['mode'], 'matching_only')
        self.assertFalse(result['rf_compliance_certified'])

    def test_candidate_cap_and_invalid_separation(self):
        def cap(c):
            c['selection'].update(max_candidates=1, top_k=1)
            c['anytime_samples'] = []
        spec, path, *_ = self.job(cap)
        def output(residuals, x, bounds, **opts):
            residuals(x)
            v = np.array(x); v[0] += .01
            return FixtureOutput(v)
        result = self.run_fixture(spec, path, output)
        self.assertEqual(len(result['selection']['ranked']), 1)
        self.assertEqual(result['selection']['excluded'][0]['status'], 'unrun')
        self.assertEqual(len(result['terminal']['candidates']), 1)

    def test_hybrid_slp_adapters_invalid_endpoint_and_top_k(self):
        def change(c):
            c['arms'][0]['steps'][0].update(solver='hybrid', aggregation='sum',
                options=dict(maxiter=1, max_restarts=0, max_evaluations=2, restart_sigma=.1))
            c['arms'][0]['steps'][1].update(solver='slp', aggregation='signed_max')
            c['selection']['top_k'] = 2
        spec, path, *_, x = self.job(change)
        def hybrid(callback, start, bounds, **opts):
            callback(start)
            end = list(start); end[0] += .01
            invalid = list(start); invalid[0] = -1
            return FixtureHybrid([FixtureRun(end), FixtureRun(invalid)], list(start))
        with patch('lpf.search.worker.hybrid_minimize', side_effect=hybrid), \
             patch('lpf.search.worker.slp_minimize', side_effect=self.fixture):
            result = execute_development_job(spec, path, solver_kind='fixture')
        self.assertEqual(result['status'], 'not_converged')
        self.assertEqual(result['requested'], 728)
        self.assertEqual(result['search_requested'], 168)
        self.assertEqual(result['steps'][1]['input_vector_sha256'], vector_sha(x))
        self.assertEqual(len(result['selection']['ranked']), 2)
        self.assertEqual(result['selection']['excluded'][0]['status'], 'invalid')
        self.assertEqual(len(result['terminal']['candidates']), 2)

    def test_empty_solver_no_observation_or_implicit_retry(self):
        def change(c):
            c['arms'][0]['steps'][0].update(solver='hybrid', aggregation='sum',
                options=dict(maxiter=1, max_restarts=0, max_evaluations=2, restart_sigma=.1))
        spec, path, *_ = self.job(change)
        with patch('lpf.search.worker.hybrid_minimize', return_value=FixtureHybrid([], None)):
            result = execute_development_job(spec, path, solver_kind='fixture')
        self.assertEqual(result['requested'], 0)
        self.assertEqual(result['steps'][0]['status'], 'no_candidate')
        self.assertEqual(result['steps'][1]['status'], 'not_started')
        self.assertEqual(result['selection']['status'], 'not_run')
        self.assertEqual(result['terminal']['status'], 'not_run')
        self.assertTrue(all(a['status'] == 'not_run' for a in result['anytime']))

    def test_second_step_budget_stop_preserves_first_step_charge(self):
        def change(c):
            c['arms'][0]['steps'][1]['max_requested_samples'] = 111
        spec, path, *_ = self.job(change)
        result = self.run_fixture(spec, path)
        self.assertEqual(result['status'], 'budget_exhausted')
        self.assertEqual(result['search_requested'], 168)
        self.assertEqual(result['requested'], 336)  # search + both triggered scans
        self.assertEqual(result['completed'], 336)
        self.assertNotIn('demo/coarse', result['allocations'])
        self.assertIn('demo/fine', result['allocations'])
        self.assertEqual(result['selection']['status'], 'not_run')

    def test_changed_anytime_and_terminal_points_are_executed(self):
        def change(c):
            c['anytime_points_per_interval'] = 5
            c['validation']['terminal_points'] = 6
        spec, path, *_ = self.job(change)
        result = self.run_fixture(spec, path)
        self.assertEqual(result['requested'], 756)
        self.assertEqual([r['requested'] for r in result['batches'] if r['stage'] == 'anytime'], [140, 140])
        self.assertEqual(result['batches'][-1]['requested'], 168)

    def test_validation_failure_and_audit_failure_are_not_pass(self):
        spec, path, plan, d, p, x = self.job(lambda c: c.update(anytime_samples=[]))
        real = RFEvaluator.evaluate
        calls = 0
        def fail_selection(evaluator, vector):
            nonlocal calls
            calls += 1
            if calls == 5: raise ValueError('selection numerical failure')
            return real(evaluator, vector)
        with patch.object(RFEvaluator, 'evaluate', new=fail_selection):
            result = self.run_fixture(spec, path)
        self.assertEqual((result['requested'], result['completed']), (308, 224))
        self.assertEqual(result['selection']['status'], 'failed')
        self.assertEqual(result['selection']['excluded'][0]['status'], 'not_evaluated')
        self.assertEqual(result['terminal']['status'], 'not_run')
        spec, path, plan, d, p, x = self.job(lambda c: c.update(anytime_samples=[]))
        meter = FixedJobEvaluation(plan, d, p, 'demo', path, spec, root=Path.cwd())
        meter.activate('demo/coarse', 'demo/coarse'); meter.evaluate(x)
        with patch('lpf.rf_core.independent.evaluate_independent_response', side_effect=ValueError('power balance')):
            with self.assertRaisesRegex(ValueError, 'power balance'): meter.spot_check(0, [0])
        self.assertEqual(meter.rows[0]['independent']['status'], 'failed')
        with self.assertRaises(RuntimeError): meter.evaluate(x)
        self.assertEqual((meter.requested, meter.completed), (56, 56))

    def test_frozen_spec_and_production_fail_closed(self):
        spec, path, plan, definition, policy, x = self.job()
        for key in ('solver_options', 'start', 'source'):
            d = spec.data
            if key == 'solver_options': d[key][0]['max_evaluations'] += 1
            elif key == 'start': d[key]['vector'][0] += .01
            else: d[key]['head'] = '0'*40
            with patch.object(RFEvaluator, 'evaluate') as forward:
                with self.assertRaises(ValueError): self.run_fixture(replace(spec, frozen_json=canonical(d)), path)
                forward.assert_not_called()
        with self.assertRaisesRegex(ValueError, 'not_ready'):
            execute_development_job(replace(spec, trial_id='EXP-NNN'), path)
        with self.assertRaisesRegex(ValueError, 'Seed'):
            freeze_development_job(plan, definition, policy, 'demo', 99, x)

    def test_tiny_actual_scipy_budget_is_not_nfev(self):
        def tiny(c):
            c['anytime_samples'] = []
            for step in c['arms'][0]['steps']:
                step['options'].update(max_iterations=1, max_evaluations=2)
        spec, path, *_ = self.job(tiny)
        result = execute_development_job(spec, path)
        self.assertEqual(result['solver_execution_kind'], 'scipy')
        self.assertEqual(result['status'], 'not_converged')
        self.assertEqual(result['search_requested'], 224)
        self.assertEqual([s['solver_result']['stop_reason'] for s in result['steps']], ['evaluation_budget_exhausted']*2)


if __name__ == '__main__':
    unittest.main()

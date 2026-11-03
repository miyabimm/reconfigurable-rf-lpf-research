"""Post-search dispatch and fail-closed checks; no production dense run."""
import sys
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace

import numpy as np
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from test_phase2_problem_seed import make, seed
from lpf.phase2_models.limited_candidate_evidence import _identity
from lpf.phase2_models.post_search_validation import validate_post_search, _forward, _independent
from lpf.phase2_models.post_search_journal import PostSearchJournal, candidate_binding, aggregate_selected
from lpf.checkpoint_io import canonical_config_hash
from lpf.phase2_models.post_search_evidence import verify_candidate_evidence
from lpf.phase2_models.api import NominalCircuit
from lpf.phase2_models.independent_rf import evaluate_independent_sample
from lpf.phase2_models.evaluation_cost import SampleBudgetCost, SampleBudgetExceeded
from lpf.phase2_models.staged_optimization import run_c1_staged


class PostSearchTests(unittest.TestCase):
    def setUp(self):
        p, self.x = make('RF-T008', 4)
        self.c = p.circuit
        ident = _identity(self.c, self.x)
        keys = ('git_head', 'source_tree_sha256', 'source_worktree_dirty', 'input_sha256', 'environment')
        self.source = {k: ident[k] for k in keys}
        def optimizer(problem, vector, maxiter, target):
            return vector, dict(success=True, status=0, message='mock', nit=0, nfev=0)
        self.raw = run_c1_staged(self.c, seed(p, self.x), coarse_points=1, fine_points=2,
            optimize_stage=optimizer, source_provenance=self.source,
            cost_meter=SampleBudgetCost(1000))
        self.budgets = dict(separate17=476, dense1001=28028,
                            independent_forward84=84, independent_mna84=84)

    def invoke(self, **kwargs):
        snapshots = []
        result = validate_post_search(self.c, self.x, optimization_record=self.raw,
            source_provenance=self.source, budgets=kwargs.pop('budgets', self.budgets),
            run_dense=kwargs.pop('run_dense', True), run_independent=kwargs.pop('run_independent', True),
            record_sink=snapshots.append, **kwargs)
        return result, snapshots

    def test_real_17_grid_and_budget_without_dense(self):
        result, snapshots = self.invoke(run_dense=False, run_independent=False)
        self.assertIn(result['separate17']['state'], ('pass', 'fail'))
        self.assertEqual(len(result['separate17']['segments']), 28)
        self.assertEqual(result['evaluation_cost']['separate17']['frequency_samples_requested'], 476)
        self.assertEqual(result['dense1001']['state'], 'not_run')
        self.assertEqual(snapshots[0]['optimization_record'], self.raw)
        self.assertEqual(snapshots[0]['separate17']['state'], 'not_run')
        self.assertEqual(snapshots[-1], result)
        budgets = dict(self.budgets, separate17=475)
        result, _ = self.invoke(budgets=budgets)
        self.assertEqual(result['separate17']['state'], 'budget_exhausted')
        self.assertEqual(result['evaluation_cost']['separate17']['frequency_samples_requested'], 0)
        self.assertEqual(result['dense1001']['state'], 'not_run')

    def test_raw_mandatory_and_guard_thresholds_are_distinct(self):
        base = self.c.forward_evaluator(17)
        for attenuation, state, guard in ((29.999999999, 'fail', False),
                                          (30.003, 'pass', False), (30.005, 'pass', True)):
            values = np.where(base.role == 0, 1., attenuation)
            fake = SimpleNamespace(f=base.f, role=base.role, setting=base.setting,
                                   segment=base.segment, il=lambda x: values)
            with patch.object(NominalCircuit, 'forward_evaluator', return_value=fake):
                result = _forward(self.c, self.x, 17, SampleBudgetCost(476), 30.)
            self.assertEqual(result['state'], state)
            self.assertEqual(result['guard_achieved'], guard)
            self.assertEqual(result['min_h2_db'], attenuation)

    def test_synthetic_dense_grid_and_budget(self):
        base = self.c.forward_evaluator(17)
        frequencies = np.concatenate([np.linspace(base.f[i * 17], base.f[i * 17 + 16], 1001)
                                      for i in range(28)])
        segment = np.repeat(np.arange(28), 1001)
        setting = np.repeat(base.setting[::17], 1001)
        role = np.repeat(base.role[::17], 1001)
        fake = SimpleNamespace(f=frequencies, role=role, setting=setting, segment=segment,
                               il=lambda x: np.where(role == 0, 1., 30.003))
        with patch.object(NominalCircuit, 'forward_evaluator', return_value=fake):
            meter = SampleBudgetCost(28028)
            result = _forward(self.c, self.x, 1001, meter, 30.)
            self.assertEqual(result['state'], 'pass')
            self.assertFalse(result['guard_achieved'])
            self.assertEqual(len(result['segments']), 28)
            self.assertEqual(sum(len(s['frequencies_mhz']) for s in result['segments']), 28028)
            self.assertEqual(meter.frequency_samples_requested, 28028)
            with self.assertRaises(SampleBudgetExceeded):
                _forward(self.c, self.x, 1001, SampleBudgetCost(28027), 30.)

    def test_real_independent_84_and_budget(self):
        forward, independent = SampleBudgetCost(84), SampleBudgetCost(84)
        result = _independent(self.c, self.x, forward, independent)
        self.assertEqual(result['state'], 'pass')
        self.assertEqual(len(result['samples']), 84)
        self.assertEqual(result['mna_dimension'], 9)
        self.assertEqual(forward.frequency_samples_requested, 84)
        self.assertEqual(independent.frequency_samples_requested, 84)
        partial = []
        with self.assertRaises(SampleBudgetExceeded):
            _independent(self.c, self.x, SampleBudgetCost(84), SampleBudgetCost(3), partial)
        self.assertEqual(len(partial), 3)
        for key, value in (('il_db', 1000.), ('gain', 1e-15),
                           ('power_residual_w', 1.), ('load_power_w', -1.)):
            def corrupt(*args):
                sample = evaluate_independent_sample(*args)
                sample[key] = value
                return sample
            with self.subTest(key=key), patch(
                    'lpf.phase2_models.post_search_validation.evaluate_independent_sample', side_effect=corrupt):
                failure_samples = []
                with self.assertRaises(ValueError):
                    _independent(self.c, self.x, SampleBudgetCost(84), SampleBudgetCost(84), failure_samples)
                self.assertEqual(len(failure_samples), 1)
                self.assertEqual(failure_samples[0][key], value)

    def test_explicit_dispatch_and_blocking(self):
        for state17, state1001, expect in [('fail', 'pass', []), ('pass', 'fail', []), ('pass', 'pass', [True])]:
            with self.subTest(state17=state17, state1001=state1001):
                called = []
                def fake_forward(c, x, points, meter, mandatory):
                    return {'state': state17 if points == 17 else state1001}
                def fake_independent(*args):
                    called.append(True)
                    return {'state': 'pass'}
                with patch('lpf.phase2_models.post_search_validation._forward', side_effect=fake_forward), \
                     patch('lpf.phase2_models.post_search_validation._independent', side_effect=fake_independent):
                    result, _ = self.invoke()
                self.assertEqual(called, expect)
                self.assertEqual(result['independent84']['state'], 'pass' if expect else 'not_run')
                self.assertFalse(result['rf_compliance_certified'])

    def test_terminal_failures_are_preserved_without_validation(self):
        for state in ('failed', 'budget_exhausted'):
            with self.subTest(state=state):
                self.raw['numerical_state'] = state
                self.raw['exception'] = {'type': 'test', 'message': state}
                result, snapshots = self.invoke()
                self.assertEqual(snapshots[0]['optimization_record'], self.raw)
                self.assertEqual(result['separate17'], {'state': 'not_run', 'reason': 'optimization_' + state})
                self.assertEqual(result['dense1001']['state'], 'not_run')
                self.assertEqual(result['independent84']['state'], 'not_run')
                self.assertEqual(result['evaluation_cost']['separate17']['frequency_samples_requested'], 0)

    def test_exchange_budget_before_any_stage_is_preserved(self):
        trace = {'stop_reason': 'budget_exhausted', 'rounds': [],
                 'evaluation_cost': SampleBudgetCost(0).snapshot()}
        snapshots = []
        result = validate_post_search(self.c, self.x, optimization_record=None,
            source_provenance=self.source, budgets=self.budgets, run_dense=True,
            run_independent=True, record_sink=snapshots.append, exchange_record=trace)
        self.assertIsNone(result['optimization_record'])
        self.assertEqual(result['exchange_record'], trace)
        self.assertEqual(result['separate17']['reason'], 'optimization_budget_exhausted')
        self.assertEqual(result['independent84']['state'], 'not_run')
        self.assertEqual(result['evaluation_cost']['separate17']['frequency_samples_requested'], 0)

    def test_exchange_stall_and_input_binding(self):
        trace = {'stop_reason': 'stalled_existing_constraint',
                 'final_vector': self.raw['stage_calls'][-1]['output_vector'],
                 'rounds': [{'inner': deepcopy(self.raw)}],
                 'evaluation_cost': self.raw['evaluation_cost']}
        snapshots = []
        result = validate_post_search(self.c, self.x, optimization_record=self.raw,
            source_provenance=self.source, budgets=self.budgets, run_dense=False,
            run_independent=False, record_sink=snapshots.append, exchange_record=trace)
        self.assertEqual(result['exchange_record']['stop_reason'], 'stalled_existing_constraint')
        self.assertEqual(result['dense1001']['reason'], 'not_selected')
        trace['rounds'][0]['inner']['numerical_state'] = 'failed'
        with self.assertRaisesRegex(ValueError, 'final staged record mismatch'):
            validate_post_search(self.c, self.x, optimization_record=self.raw,
                source_provenance=self.source, budgets=self.budgets, run_dense=False,
                run_independent=False, record_sink=snapshots.append, exchange_record=trace)

    def test_static_evidence_rejects_forged_pass_and_missing_coverage(self):
        original = NominalCircuit.forward_evaluator
        base = self.c.forward_evaluator(17)
        def synthetic(circuit, points, **kwargs):
            if points == 3:
                return original(circuit, points, **kwargs)
            frequencies = np.concatenate([np.linspace(base.f[i * 17], base.f[i * 17 + 16], points)
                                          for i in range(28)])
            roles = np.repeat(base.role[::17], points)
            return SimpleNamespace(f=frequencies, role=roles,
                setting=np.repeat(base.setting[::17], points), segment=np.repeat(np.arange(28), points),
                il=lambda x: np.where(roles == 0, 1., 30.003))
        kwargs = dict(optimization_record=self.raw, source_provenance=self.source,
                      budgets=self.budgets, run_dense=True, run_independent=True)
        binding = candidate_binding('a', self.c, self.x, **kwargs)
        snapshots = []
        with patch.object(NominalCircuit, 'forward_evaluator', synthetic):
            report = validate_post_search(self.c, self.x, record_sink=snapshots.append, **kwargs)
        self.assertEqual(report['dense1001']['state'], 'pass')
        self.assertFalse(report['dense1001']['guard_achieved'])
        self.assertEqual(report['independent84']['state'], 'pass')
        self.assertTrue(verify_candidate_evidence(self.c, binding, report))
        for mutate in (
            lambda r: r['dense1001']['segments'].pop(),
            lambda r: r['dense1001']['segments'][0].update(setting=99),
            lambda r: r['dense1001']['segments'][2].update(worst_il_db=29.),
            lambda r: r['independent84']['samples'].pop(),
            lambda r: r['independent84']['samples'][0].update(power_residual_w=1.),
            lambda r: r['evaluation_cost']['independent_mna84'].update(frequency_samples_completed=0),
        ):
            damaged = deepcopy(report)
            mutate(damaged)
            with self.subTest(mutate=mutate), self.assertRaises(ValueError):
                verify_candidate_evidence(self.c, binding, damaged)

    def test_frozen_set_aggregation_is_independent_and_not_vacuous(self):
        def report(component, scan, dense, mna):
            return {'schema': 'post-search-validation-1', 'component': {'state': component},
                    'separate17': {'state': scan}, 'dense1001': {'state': dense},
                    'independent84': {'state': mna}}
        good = report('pass', 'pass', 'pass', 'pass')
        fail17 = report('pass', 'fail', 'not_run', 'not_run')
        mna_fail = report('pass', 'pass', 'pass', 'fail')
        partial = report('pass', 'pass', 'budget_exhausted', 'not_run')
        self.assertEqual(aggregate_selected([], {})['validation'],
                         {'numerical': 'not_run', 'independent': 'not_run'})
        cases = [({'a': good, 'b': fail17}, ('failed', 'not_run')),
                 ({'a': good, 'b': mna_fail}, ('passed', 'failed')),
                 ({'a': good, 'b': partial}, ('not_run', 'not_run')),
                 ({'a': good, 'b': good}, ('passed', 'passed')),
                 ({'a': good}, ('not_run', 'not_run'))]
        for values, expected in cases:
            with self.subTest(expected=expected):
                actual = aggregate_selected(['a', 'b'], values)['validation']
                self.assertEqual((actual['numerical'], actual['independent']), expected)
        with self.assertRaises(ValueError):
            aggregate_selected(['a'], {'unselected': good})

    def test_selection_journal_freeze_and_interruption(self):
        kwargs = dict(optimization_record=self.raw, source_provenance=self.source,
                      budgets=self.budgets, run_dense=False, run_independent=False)
        binding = candidate_binding('a', self.c, self.x, **kwargs)
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'raw'
            journal = PostSearchJournal.create(path, [binding])
            with self.assertRaises(FileExistsError):
                PostSearchJournal.create(path, [binding])
            with self.assertRaisesRegex(ValueError, 'frozen selection'):
                journal.run_candidate('a', self.c, self.x, **(kwargs | {'run_dense': True}))
            self.assertIsNone(PostSearchJournal(path).state['in_progress'])
            with patch('lpf.phase2_models.post_search_validation._forward', side_effect=KeyboardInterrupt):
                with self.assertRaises(KeyboardInterrupt):
                    journal.run_candidate('a', self.c, self.x, **kwargs)
            saved = PostSearchJournal(path)
            self.assertEqual(saved.state['in_progress'], 'a')
            self.assertEqual(saved.state['candidates']['a']['state'], 'running')
            self.assertEqual(saved.summary()['validation'], {'numerical': 'not_run', 'independent': 'not_run'})
            with self.assertRaisesRegex(ValueError, 'automatic retry prohibited'):
                saved.run_candidate('a', self.c, self.x, **kwargs)

    def test_journal_success_is_bound_and_not_repeatable(self):
        kwargs = dict(optimization_record=self.raw, source_provenance=self.source,
                      budgets=self.budgets, run_dense=False, run_independent=False)
        binding = candidate_binding('a', self.c, self.x, **kwargs)
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'raw'
            journal = PostSearchJournal.create(path, [binding])
            result = journal.run_candidate('a', self.c, self.x, **kwargs)
            saved = PostSearchJournal(path)
            self.assertEqual(canonical_config_hash(saved.state['candidates']['a']['report']), canonical_config_hash(result))
            self.assertIsNone(saved.state['in_progress'])
            self.assertEqual(saved.summary()['validation']['independent'], 'not_run')
            with self.assertRaisesRegex(ValueError, 'already attempted'):
                saved.run_candidate('a', self.c, self.x, **kwargs)

    def test_journal_storage_failure_retains_marker_and_blocks_retry(self):
        kwargs = dict(optimization_record=self.raw, source_provenance=self.source,
                      budgets=self.budgets, run_dense=False, run_independent=False)
        binding = candidate_binding('a', self.c, self.x, **kwargs)
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'raw'
            journal = PostSearchJournal.create(path, [binding])
            from lpf.checkpoint_io import atomic_write_json
            count = 0
            def fail_second(*args, **kwargs):
                nonlocal count
                count += 1
                if count == 2:
                    raise OSError('synthetic storage failure')
                return atomic_write_json(*args, **kwargs)
            with patch('lpf.phase2_models.post_search_journal.atomic_write_json', side_effect=fail_second):
                with self.assertRaisesRegex(OSError, 'synthetic storage failure'):
                    journal.run_candidate('a', self.c, self.x, **kwargs)
            saved = PostSearchJournal(path)
            self.assertEqual(saved.state['in_progress'], 'a')
            self.assertEqual(saved.summary()['validation'], {'numerical': 'not_run', 'independent': 'not_run'})
            with self.assertRaisesRegex(ValueError, 'automatic retry prohibited'):
                saved.run_candidate('a', self.c, self.x, **kwargs)

    def test_provenance_and_sink_fail_closed(self):
        wrong = self.x.copy()
        wrong[0] += .01
        snapshots = []
        with self.assertRaisesRegex(ValueError, 'provenance mismatch'):
            validate_post_search(self.c, wrong, optimization_record=self.raw,
                source_provenance=self.source, budgets=self.budgets, run_dense=True,
                run_independent=True, record_sink=snapshots.append)
        self.assertEqual(snapshots[0]['optimization_record'], self.raw)
        self.assertEqual(snapshots[0]['separate17']['state'], 'not_run')
        with self.assertRaisesRegex(RuntimeError, 'sink'):
            validate_post_search(self.c, self.x, optimization_record=self.raw,
                source_provenance=self.source, budgets=self.budgets, run_dense=False,
                run_independent=False, record_sink=lambda _: (_ for _ in ()).throw(RuntimeError('sink')))


if __name__ == '__main__':
    unittest.main()

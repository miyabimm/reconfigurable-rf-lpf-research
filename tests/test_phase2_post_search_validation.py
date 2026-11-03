"""Post-search dispatch and fail-closed checks; no production dense run."""
import csv
import hashlib
import io
import json
import shutil
import subprocess
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
from lpf.checkpoint_io import canonical_config_hash, atomic_write_json
from lpf.experiment_manifest import INDEX_FIELDS, new_manifest, experiment_index
from lpf.phase2_models.experiment_post_search import _package as package_post_search_fixture
from scripts.run_phase2_one_start import _post_search_finalize_guard, candidate_checkpoint, finalize_experiment
from scripts.audit_new_experiment_storage import validate_run
from scripts.experiment_id_registry import PATH as LEDGER_PATH, as_csv, next_reservation
from lpf.phase2_models.candidate_records import record_candidate
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

    def test_terminal_anchor_validation_is_explicit_and_keeps_status(self):
        for state in ('not_converged', 'failed', 'budget_exhausted'):
            with self.subTest(state=state):
                raw = deepcopy(self.raw)
                raw['numerical_state'] = state
                if state != 'not_converged':
                    raw['exception'] = {'type': 'test', 'message': state}
                calls = []
                def fake_forward(c, x, points, meter, mandatory):
                    calls.append(points)
                    return {'state': 'pass'}
                def fake_independent(*args):
                    calls.append(84)
                    return {'state': 'pass'}
                with patch('lpf.phase2_models.post_search_validation._forward', side_effect=fake_forward), \
                     patch('lpf.phase2_models.post_search_validation._independent', side_effect=fake_independent):
                    result = validate_post_search(self.c, self.x, optimization_record=raw,
                        source_provenance=self.source, budgets=self.budgets, run_dense=True,
                        run_independent=True, record_sink=lambda _: None, validate_terminal_anchor=True)
                self.assertEqual(calls, [17, 1001, 84])
                self.assertEqual(result['validation_mode'], 'terminal_physical_anchor')
                self.assertEqual(result['optimization_record']['numerical_state'], state)
                self.assertTrue(result['candidate_promotion_blocked'])
                self.assertFalse(result['rf_compliance_certified'])

    def test_anchor_journal_binds_continuation_and_keeps_failed_status(self):
        raw = deepcopy(self.raw)
        raw['numerical_state'] = 'budget_exhausted'
        raw['exception'] = {'type': 'SampleBudgetExceeded', 'message': 'limit'}
        continuation = {'method': 'B', 'last_valid_vector': list(self.x) + [1.]}
        kwargs = dict(optimization_record=raw, source_provenance=self.source,
                      budgets=self.budgets, run_dense=False, run_independent=False,
                      validate_terminal_anchor=True, continuation_record=continuation)
        binding = candidate_binding('anchor', self.c, self.x, **kwargs)
        with tempfile.TemporaryDirectory() as tmp:
            journal = PostSearchJournal.create(Path(tmp) / 'journal', [binding])
            with self.assertRaisesRegex(ValueError, 'frozen selection'):
                journal.run_candidate('anchor', self.c, self.x,
                    **(kwargs | {'continuation_record': continuation | {'method': 'C'}}))
            report = journal.run_candidate('anchor', self.c, self.x, **kwargs)
            self.assertIn(report['separate17']['state'], ('pass', 'fail'))
            self.assertEqual(report['optimization_record']['numerical_state'], 'budget_exhausted')
            self.assertTrue(verify_candidate_evidence(self.c, binding, report))
            bad = dict(binding, validate_terminal_anchor=False)
            with self.assertRaisesRegex(ValueError, 'Validation mode'):
                verify_candidate_evidence(self.c, bad, report)

    def test_continuation_anchor_raw_binding_rejects_changed_evidence(self):
        from lpf.phase2_models.experiment_post_search import _check_bindings
        raw = deepcopy(self.raw)
        raw['numerical_state'] = 'budget_exhausted'
        continuation = {'method': 'B', 'last_valid_vector': list(self.x) + [1.]}
        source = dict(self.source, input_source_sha256='c' * 64)
        raw['source_provenance'] = {'state': 'provided', 'value': source}
        binding = candidate_binding('anchor', self.c, self.x, optimization_record=raw,
            source_provenance=source, budgets=self.budgets, run_dense=True, run_independent=True,
            validate_terminal_anchor=True, continuation_record=continuation)
        loaded = {'config': {'schema_version': 4, 'budgets': {
            'intermediate_samples': 3808, 'dense_samples': 224224}}, 'circuit': self.c,
            'input_source_sha256': source['input_source_sha256'],
            'actual': {'anchor': {'method': 'B', 'seed_record': raw['seed']}}}
        optimization = {'identity': {'source_provenance': source}, 'completed': {'anchor': {
            'staged_record': raw, 'continuation': continuation, 'validation_anchor': {
                'vector_sha256': binding['vector_sha256']}}}}
        plan = dict(schema='post-search-g1-1', selection_rule='all anchors', search_guard=True,
                    max_selected=8, separate17=3808, dense1001=224224,
                    independent_forward84=672, independent_mna84=672)
        _check_bindings([binding], optimization, loaded, plan, source['git_head'])
        optimization['completed']['anchor']['continuation']['method'] = 'C'
        with self.assertRaisesRegex(ValueError, 'last valid anchor'):
            _check_bindings([binding], optimization, loaded, plan, source['git_head'])

    def test_component_counterexample_and_missing_role_are_distinct(self):
        x = self.x.copy()
        x[0] = 1e6
        staged = deepcopy(self.raw)
        staged['stage_calls'][-1]['output_vector'][0] = x[0]
        result = validate_post_search(self.c, x, optimization_record=staged,
            source_provenance=self.source, budgets=self.budgets, run_dense=True,
            run_independent=True, record_sink=lambda _: None)
        self.assertEqual(result['component']['state'], 'fail')
        self.assertEqual(aggregate_selected(['a'], {'a': result})['validation'],
                         {'numerical': 'failed', 'independent': 'not_run'})
        real = self.c.validate_components(self.x)
        with patch.object(NominalCircuit, 'validate_components', return_value=real | {
                'connection_role_evidence_incomplete': True}):
            result, _ = self.invoke()
        self.assertEqual(result['separate17']['state'], 'failed')  # execution/evidence incomplete
        self.assertEqual(aggregate_selected(['a'], {'a': result})['validation'],
                         {'numerical': 'not_run', 'independent': 'not_run'})

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
        with patch.object(NominalCircuit, 'forward_evaluator', synthetic):
            report = validate_post_search(self.c, self.x, record_sink=lambda _: None, **kwargs)
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
            lambda r: r['independent84']['segments'][0]['grid_worst'].update(il_db=-999.),
            lambda r: r['independent84']['segments'][0]['grid_worst'].update(frequency_hz=1.),
            lambda r: r['independent84']['segments'][0].update(region='H2'),
            lambda r: r['independent84']['summary']['H2'].update(il_db=999.),
            lambda r: r['independent84']['summary']['pass_il'].update(frequency_hz=1.),
            lambda r: r['independent84']['summary']['H3'].update(case='invalid'),
            lambda r: r['evaluation_cost']['independent_mna84'].update(frequency_samples_completed=0),
        ):
            damaged = deepcopy(report)
            mutate(damaged)
            with self.subTest(mutate=mutate), self.assertRaises(ValueError):
                verify_candidate_evidence(self.c, binding, damaged)
        # Equal ILs must retain the earliest frequency and then CSV segment order.
        tied = deepcopy(report)
        independent = tied['independent84']
        for sample in independent['samples']:
            sample.update(il_db=10., forward_il_db=10., gain=.1)
        for i, row in enumerate(independent['segments']):
            row['grid_worst'] = {'frequency_hz': independent['samples'][i * 3]['frequency_hz'], 'il_db': 10.}
        fields = ('segment', 'case', 'region', 'subband', 'setting', 'canonical_setting')
        for role, index in (('pass_il', 0), ('UL', 0), ('DL', 1), ('H2', 2), ('H3', 3)):
            row = independent['segments'][index]
            independent['summary'][role] = {key: row[key] for key in fields} | row['grid_worst']
        self.assertTrue(verify_candidate_evidence(self.c, binding, tied))
        wrong_frequency = deepcopy(tied)
        wrong_frequency['independent84']['segments'][0]['grid_worst']['frequency_hz'] = independent['samples'][1]['frequency_hz']
        with self.assertRaisesRegex(ValueError, 'segment worst'):
            verify_candidate_evidence(self.c, binding, wrong_frequency)
        wrong_segment = deepcopy(tied)
        row = independent['segments'][4]
        wrong_segment['independent84']['summary']['UL'] = {key: row[key] for key in fields} | row['grid_worst']
        with self.assertRaisesRegex(ValueError, 'summary worst'):
            verify_candidate_evidence(self.c, binding, wrong_segment)

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

    def test_mna_interrupt_persists_completed_and_inflight_samples(self):
        kwargs = dict(optimization_record=self.raw, source_provenance=self.source,
                      budgets=self.budgets, run_dense=True, run_independent=True)
        binding = candidate_binding('a', self.c, self.x, **kwargs)
        original_forward = NominalCircuit.forward_evaluator
        base = self.c.forward_evaluator(17)
        def synthetic(circuit, points, **extra):
            if points == 3:
                return original_forward(circuit, points, **extra)
            frequencies = np.concatenate([np.linspace(base.f[i * 17], base.f[i * 17 + 16], points)
                                          for i in range(28)])
            roles = np.repeat(base.role[::17], points)
            return SimpleNamespace(f=frequencies, role=roles,
                setting=np.repeat(base.setting[::17], points), segment=np.repeat(np.arange(28), points),
                il=lambda x: np.where(roles == 0, 1., 30.003))
        count = 0
        def interrupted(*args):
            nonlocal count
            count += 1
            if count == 3:
                raise KeyboardInterrupt('synthetic MNA interruption')
            return evaluate_independent_sample(*args)
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'raw'
            journal = PostSearchJournal.create(path, [binding])
            with patch.object(NominalCircuit, 'forward_evaluator', synthetic), patch(
                    'lpf.phase2_models.post_search_validation.evaluate_independent_sample', side_effect=interrupted):
                with self.assertRaises(KeyboardInterrupt):
                    journal.run_candidate('a', self.c, self.x, **kwargs)
            saved = PostSearchJournal(path)
            report = saved.state['candidates']['a']['report']
            self.assertEqual(saved.state['in_progress'], 'a')
            self.assertEqual(report['independent84']['state'], 'running')
            self.assertEqual(len(report['independent84']['completed_samples']), 2)
            self.assertEqual(report['independent84']['last_attempt']['state'], 'dispatching')
            self.assertEqual(saved.summary()['validation']['independent'], 'not_run')
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

    def test_real_storage_audit_finalize_and_index_in_temporary_git(self):
        # A self-contained synthetic repository; never writes a real EXP.
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            def git(*args):
                return subprocess.check_output(['git', *args], cwd=root, stderr=subprocess.PIPE, text=True).strip()
            git('init', '-q', '-b', 'main')
            git('config', 'user.name', 'Fixture')
            git('config', 'user.email', 'fixture@example.invalid')
            (root / '.gitignore').write_text('results/\n')
            shutil.copytree(Path(__file__).resolve().parents[1] / 'rf', root / 'rf')
            (root / 'data').mkdir()
            (root / 'data/phase2_git_storage_budget.json').write_text(json.dumps({'thresholds': {
                'individual_new_file_soft_bytes': 131072, 'individual_new_file_hard_bytes': 1048576,
                'new_experiment_curated_soft_bytes': 10000000}}))
            ledger = root / LEDGER_PATH
            ledger.parent.mkdir(parents=True, exist_ok=True)
            rows = [{'experiment_id': f'EXP-{i:03}',
                     'state': 'legacy_gap_retired' if i in (18, 19) else 'legacy_recorded',
                     'owner': '', 'request_id': '', 'purpose': '', 'constraint_id': '',
                     'reserved_at_utc': '', 'origin': ''} for i in range(1, 50)]
            rows, expid, _ = next_reservation(rows, owner='fixture', purpose='fixture only',
                request_id='fixture-post', constraint_id='RF-T008', reserved_at_utc='2026-11-03T00:00:00Z')
            ledger.write_text(as_csv(rows))
            git('add', '.'); git('commit', '-qm', 'fixture reservation')
            plan = {'schema': 'post-search-g1-1', 'selection_rule': 'fixture fixed candidate', 'search_guard': True,
                    'max_selected': 1, 'separate17': 476, 'dense1001': 28028,
                    'independent_forward84': 84, 'independent_mna84': 84}
            source_input = {'fixture': 'synthetic'}
            input_sha = canonical_config_hash(source_input)
            scope = {'input_source': source_input, 'input_source_sha256': input_sha,
                     'post_search_validation': plan}
            g1 = new_manifest(expid, 'fixture only', scope, objective='full_lpf', seed=23,
                              root=root, constraint_id='RF-T008', allow_trial=True)
            # The fixture invokes the packager directly with a synthetic gate;
            # production's _gate additionally checks the actual source checkout.
            g1['code']['execution_sha'] = self.source['git_head']
            run = root / 'experiments/chatgpt_topology_search/runs' / expid
            run.mkdir(parents=True)
            storage = {'schema_version': 1, 'policy': 'phase2-git-only-v1', 'experiment_id': expid,
                       'phase': 'Phase 2', 'stage': 'planned', 'git_readback': 'not_run',
                       'selection': {'top_k': 0, 'retain': ['pareto'],
                                     'rule': 'fixture checked Pareto and retained diagnostics',
                                     'estimated_curated_bytes': 200000},
                       'summary': None, 'checkpoints': [], 'validation_overlays': [],
                       'supporting_evidence': [], 'size_exception': None, 'limitations': []}
            atomic_write_json(run / 'manifest.json', g1, compact=True)
            atomic_write_json(run / 'storage_record.json', storage, compact=True)
            rel = lambda p: p.relative_to(root).as_posix()
            (root / 'data/experiment_index.csv').write_text(experiment_index([(rel(run / 'manifest.json'), g1)]))
            git('add', '.'); git('commit', '-qm', 'fixture G1')
            git('update-ref', 'refs/remotes/origin/main', git('rev-parse', 'HEAD'))
            source = self.source | {'kind': 'synthetic', 'dirty_patch_sha256': hashlib.sha256(b'').hexdigest(),
                                    'input_source_sha256': input_sha}
            problem, vector = make('RF-T008', 4)
            def optimizer(p, x, maxiter, target):
                return x, {'success': True, 'status': 0, 'message': 'mock', 'nit': 0, 'nfev': 0}
            staged = run_c1_staged(problem.circuit, seed(problem, vector), coarse_points=1, fine_points=2,
                optimize_stage=optimizer, source_provenance=source, cost_meter=SampleBudgetCost(1000), search_guard=True)
            candidate = record_candidate('a', problem.circuit, vector, staged_record=staged,
                                         source_provenance=source).as_dict()
            checkpoint_path = run / 'checkpoints/a.json'
            atomic_write_json(checkpoint_path, candidate_checkpoint(problem.circuit, candidate), compact=True)
            ref = lambda p: {'path': rel(p), 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()}
            checkpoint_ref = {'candidate_id': 'a', 'selection_reason': 'pareto', **ref(checkpoint_path)}
            summary_path = run / 'run_summary.json'
            summary = {'experiment_id': expid, 'attempts': {'planned': 1, 'attempted': 1, 'converged': 1,
                        'nonconverged': 0, 'failed': 0, 'not_started': 0},
                       'selected_candidate_count': 1, 'best_found': ['a'], 'limitations': [], 'validation': {}}
            atomic_write_json(summary_path, summary, compact=True)
            manifest = deepcopy(g1)
            manifest['execution'].update(status='completed', elapsed_seconds=1., evaluation_count=0)
            manifest['evidence'] = [ref(summary_path), ref(checkpoint_path)]
            storage.update(stage='preservation_incomplete', summary=ref(summary_path), checkpoints=[checkpoint_ref])
            atomic_write_json(run / 'manifest.json', manifest, compact=True)
            atomic_write_json(run / 'storage_record.json', storage, compact=True)
            raw = root / 'results' / expid
            raw.mkdir(parents=True)
            optimization = {'identity': {'input_source_sha256': input_sha, 'source_provenance': source},
                            'input_source': source_input, 'in_progress': None,
                            'completed': {'a': {'staged_record': staged}}}
            atomic_write_json(raw / 'run.json', {'body': optimization, 'sha256': canonical_config_hash(optimization)}, compact=True)
            args = dict(optimization_record=staged, source_provenance=source,
                        budgets=self.budgets, run_dense=False, run_independent=False)
            binding = candidate_binding('a', problem.circuit, vector, **args)
            journal = PostSearchJournal.create(raw / 'post-search', [binding])
            journal.run_candidate('a', problem.circuit, vector, **args)
            loaded = {'actual': {'a': {'seed_record': staged['seed']}}, 'circuit': problem.circuit,
                      'input_source': source_input, 'input_source_sha256': input_sha,
                      'config': {'budgets': {'intermediate_samples': 476, 'dense_samples': 28028}}}
            validate_run(root, expid, mode='audit')
            package_post_search_fixture(root, expid, loaded, {'run': run, 'manifest': g1}, raw, journal, validate_run)
            before = validate_run(root, expid, mode='audit')
            self.assertEqual(before['stage'], 'preservation_incomplete')
            self.assertEqual(before['independent_validation'], 'not_run')
            result = finalize_experiment(root, expid)
            self.assertEqual(result['stage'], 'complete')
            self.assertTrue(result['committed_readback'])
            for path in (run / 'manifest.json', run / 'storage_record.json', root / 'data/experiment_index.csv'):
                self.assertEqual(subprocess.check_output(['git', 'show', 'HEAD:' + rel(path)], cwd=root), path.read_bytes())
            self.assertTrue((raw / 'run.json').exists())

    def test_supplemental_validation_identity_preserves_original_stage_source(self):
        source = {'kind': 'recorded', 'git_head': self.source['git_head'],
                  'dirty_patch_sha256': '0' * 64, 'input_source_sha256': '1' * 64}
        staged = deepcopy(self.raw)
        staged['source_provenance']['value'] = source
        result = validate_post_search(self.c, self.x, optimization_record=staged,
            source_provenance=source, validation_identity=self.source, budgets=self.budgets,
            run_dense=False, run_independent=False, record_sink=lambda _: None)
        self.assertEqual(result['source_provenance'], source)
        self.assertEqual(result['validation_identity'], self.source)
        bad = deepcopy(source)
        bad['git_head'] = '0' * 40
        staged['source_provenance']['value'] = bad
        with self.assertRaisesRegex(ValueError, 'source revisions differ'):
            validate_post_search(self.c, self.x, optimization_record=staged,
                source_provenance=bad, validation_identity=self.source, budgets=self.budgets,
                run_dense=False, run_independent=False, record_sink=lambda _: None)

    def test_packaging_index_and_failure_marker_in_isolated_git(self):
        for inject_failure in (False, True):
            with self.subTest(inject_failure=inject_failure), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                def git(*args):
                    return subprocess.check_output(['git', *args], cwd=root, stderr=subprocess.PIPE, text=True)
                git('init', '-q', '-b', 'main')
                git('config', 'user.name', 'Fixture')
                git('config', 'user.email', 'fixture@example.invalid')
                (root / '.gitignore').write_text('results/\n')
                expid = 'EXP-999'
                run = root / 'experiments/chatgpt_topology_search/runs' / expid
                run.mkdir(parents=True)
                (root / 'data').mkdir()
                raw = root / 'results' / expid
                raw.mkdir(parents=True)
                plan = {'schema': 'post-search-g1-1', 'selection_rule': 'fixture fixed candidate', 'search_guard': True,
                        'max_selected': 1, 'separate17': 476, 'dense1001': 28028,
                        'independent_forward84': 84, 'independent_mna84': 84}
                scope = {'input_source': {'fixture': True}, 'post_search_validation': plan}
                scope['input_source_sha256'] = canonical_config_hash(scope['input_source'])
                constraints = {'constraint_id': self.c.policy_id,
                               'effective_constraint_sha256': self.c.policy_fingerprint}
                g1 = {'experiment_id': expid, 'constraints': constraints, 'objective': 'full_lpf',
                      'search_scope': scope, 'code': {'execution_sha': self.source['git_head']},
                      'environment': {}, 'bands_sha256': 'b' * 64, 'random_seed': 23,
                      'execution': {'status': 'planned'},
                      'validation': {'numerical': 'not_run', 'independent': 'not_run'}}
                manifest = deepcopy(g1)
                manifest['execution']['status'] = 'completed'
                manifest['limitations'] = []
                checkpoint = run / 'checkpoints' / 'a.json'
                checkpoint.parent.mkdir()
                checkpoint.write_text(json.dumps({'candidate_record': {
                    'vector_sha256': __import__('lpf.phase2_models.problem_seed', fromlist=['vector_fingerprint']).vector_fingerprint(self.x),
                    'policy_sha256': self.c.policy_fingerprint,
                    'definition_sha256': self.raw['definition_sha256']}}))
                rel = lambda p: p.relative_to(root).as_posix()
                digest = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
                summary_path = run / 'run_summary.json'
                summary_path.write_text(json.dumps({'limitations': [], 'validation': {}}))
                storage = {'stage': 'preservation_incomplete', 'git_readback': 'not_run',
                           'summary': {'path': rel(summary_path), 'sha256': digest(summary_path)},
                           'checkpoints': [{'candidate_id': 'a', 'path': rel(checkpoint), 'sha256': digest(checkpoint)}],
                           'validation_overlays': [], 'supporting_evidence': [], 'limitations': []}
                atomic_write_json(run / 'manifest.json', manifest, compact=True)
                atomic_write_json(run / 'storage_record.json', storage, compact=True)
                index_path = root / 'data/experiment_index.csv'
                row = dict.fromkeys(INDEX_FIELDS, '')
                row.update(experiment_id=expid, constraint_id=self.c.policy_id,
                           effective_constraint_sha256=self.c.policy_fingerprint, objective='full_lpf',
                           execution_status='planned', numerical_validation='not_run', independent_validation='not_run',
                           manifest=rel(run / 'manifest.json'))
                with index_path.open('w', newline='') as f:
                    writer = csv.DictWriter(f, fieldnames=INDEX_FIELDS, lineterminator='\n')
                    writer.writeheader(); writer.writerow(row)
                git('add', '.'); git('commit', '-qm', 'fixture')
                source = self.source | {'kind': 'synthetic', 'dirty_patch_sha256': '0' * 64,
                                        'input_source_sha256': scope['input_source_sha256']}
                def guarded_optimizer(p, vector, maxiter, target):
                    return vector, dict(success=True, status=0, message='mock', nit=0, nfev=0)
                staged = run_c1_staged(self.c, self.raw['seed'], coarse_points=1, fine_points=2,
                    optimize_stage=guarded_optimizer, source_provenance=source,
                    cost_meter=SampleBudgetCost(1000), search_guard=True)
                identity = {'input_source_sha256': scope['input_source_sha256'], 'source_provenance': source}
                optimization = {'identity': identity, 'input_source': scope['input_source'], 'in_progress': None,
                                'completed': {'a': {'staged_record': staged}}}
                atomic_write_json(raw / 'run.json', {'body': optimization, 'sha256': canonical_config_hash(optimization)}, compact=True)
                kwargs = dict(optimization_record=staged, source_provenance=source,
                              budgets=self.budgets, run_dense=False, run_independent=False)
                binding = candidate_binding('a', self.c, self.x, **kwargs)
                journal = PostSearchJournal.create(raw / 'post-search', [binding])
                journal.run_candidate('a', self.c, self.x, **kwargs)
                loaded = {'actual': {'a': {'seed_record': self.raw['seed']}}, 'circuit': self.c,
                          'input_source': scope['input_source'], 'input_source_sha256': scope['input_source_sha256'],
                          'config': {'budgets': {'intermediate_samples': 476, 'dense_samples': 28028}}}
                gate = {'run': run, 'manifest': g1}
                if inject_failure:
                    with patch('lpf.phase2_models.experiment_post_search._write_text', side_effect=OSError('disk failure')):
                        with self.assertRaisesRegex(OSError, 'disk failure'):
                            package_post_search_fixture(root, expid, loaded, gate, raw, journal, lambda *a, **kw: None)
                    marker = json.loads((raw / 'post-search/packaging.json').read_text())
                    self.assertEqual(marker['state'], 'running')
                    self.assertEqual(json.loads((run / 'storage_record.json').read_text())['stage'], 'preservation_incomplete')
                    with self.assertRaisesRegex(ValueError, 'receipt'):
                        _post_search_finalize_guard(root, run, json.loads((run / 'manifest.json').read_text()),
                            json.loads((run / 'storage_record.json').read_text()), json.loads(summary_path.read_text()))
                else:
                    audits = []
                    result = package_post_search_fixture(root, expid, loaded, gate, raw, journal,
                                                         lambda *a, **kw: audits.append((a, kw)))
                    self.assertTrue(audits)
                    self.assertEqual(result['preservation'], 'awaiting_git_readback')
                    manifest = json.loads((run / 'manifest.json').read_text())
                    storage = json.loads((run / 'storage_record.json').read_text())
                    summary = json.loads(summary_path.read_text())
                    self.assertEqual(storage['stage'], 'preservation_incomplete')
                    self.assertEqual(manifest['validation']['independent'], 'not_run')
                    with index_path.open(newline='') as f:
                        saved = next(csv.DictReader(f))
                    self.assertEqual(saved['numerical_validation'], manifest['validation']['numerical'])
                    self.assertEqual(saved['independent_validation'], manifest['validation']['independent'])
                    self.assertEqual(_post_search_finalize_guard(root, run, manifest, storage, summary), index_path)

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

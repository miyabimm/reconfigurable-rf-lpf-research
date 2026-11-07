"""Bounded Stage-4B software checks. No EXP, optimizer loop or dense RF scan."""
import copy
from dataclasses import asdict, replace
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import yaml

from test_issue307_constraints import make, ROOT
from lpf.rf_core.model import RFEvaluator, power_response, RFResponse
from lpf.search.evaluation import FixedStageEvaluation
from lpf.search.plan import load_preflight, Plan
from lpf.search.problem import Problem
from lpf.search.storage import sha, canonical, vector_sha
from lpf.search.validation import rank_candidates


class FixedStageTests(unittest.TestCase):
    def setUp(self):
        self.sources = tempfile.TemporaryDirectory(dir=ROOT)
        self.addCleanup(self.sources.cleanup)
        self.raw = tempfile.TemporaryDirectory()
        self.addCleanup(self.raw.cleanup)
        self.config = yaml.safe_load((ROOT/'project/fixtures/issue313_preflight.yaml').read_text())
        self.counter = 0

    def setup_model(self, cid='RF-F003', mode='full_lpf', mutate=None):
        p, d, _, _, x = make(cid)
        source = Path(self.sources.name)/'definition.json'
        source.write_text(canonical(asdict(d)))
        config = copy.deepcopy(self.config)
        config['rf'] = dict(constraint_id=cid, allow_trial=cid.startswith('RF-T'))
        config['objective'] = mode
        config['definition'] = dict(path=str(source.relative_to(ROOT)),
            source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(), definition_sha256=sha(asdict(d)))
        if mutate:
            mutate(config)
        path = Path(self.sources.name)/'plan.yaml'
        path.write_text(yaml.safe_dump(config))
        plan = load_preflight(path)
        return plan, d, p, x

    def evaluator(self, plan, d, p):
        self.counter += 1
        return FixedStageEvaluation(plan, d, p, 'demo', 'coarse',
                                    Path(self.raw.name)/f'raw{self.counter}.json')

    def test_actual_all_models_and_full_trace(self):
        for cid in ('RF-F003', 'RF-T005', 'RF-T007', 'RF-T008', 'RF-T006'):
            with self.subTest(cid=cid):
                mode = 'matching_only' if cid == 'RF-T006' else 'full_lpf'
                plan, d, p, x = self.setup_model(cid, mode)
                e = self.evaluator(plan, d, p)
                # The fresh-interpreter regression in test_issue323_dependencies
                # runs this entire module with all legacy imports forbidden.
                result = e.evaluate(x)
                ranked = rank_candidates([result])['ranked']
                n = 28 if mode == 'matching_only' else 56
                self.assertEqual((e.requested, e.completed), (n, n))
                self.assertEqual(set(e.grid.setting), set(range(6)))
                self.assertEqual(len(set(e.grid.segment)), 14 if mode == 'matching_only' else 28)
                self.assertEqual(result['vector_sha256'], vector_sha(x))
                self.assertEqual(ranked[0]['assessment'], result['assessment'])
                audit = e.spot_check(0, [0, n-1])
                self.assertEqual((audit['status'], audit['completed']), ('pass', 2))
                saved = json.loads(e.path.read_text())
                self.assertEqual(saved['plan_sha256'], plan.sha256)
                self.assertEqual(saved['requested'], n)
                self.assertEqual(saved['completed'], n)
                self.assertEqual(saved['batches'][0]['vector'], x.tolist())
                self.assertEqual(saved['batches'][0]['assessment']['grid_fingerprint'], saved['grid_sha256'])
                self.assertEqual(len(saved['batches'][0]['response']['s_real']), n)
                self.assertEqual(saved['dense'], 'not_run')
                per_point = 14 if mode == 'matching_only' else 28
                self.assertEqual(saved['reservations']['selection'], 6*per_point)
                self.assertEqual(saved['reservations']['terminal'], 4*per_point)
                self.assertEqual(saved['reservations']['anytime'], 6*per_point)
                self.assertEqual(saved['batches'][0]['reservations'], saved['reservations'])
                self.assertFalse(saved['rf_compliance_certified'])

    def test_contract_mismatches_before_forward(self):
        plan, d, p, x = self.setup_model()
        wrong_policy = copy.deepcopy(p); wrong_policy['source_ohms']['real'] += 1
        for badplan, definition, policy in (
                (replace(plan, sha256='0'*64), d, p),
                (plan, replace(d, physical_order=tuple(reversed(d.physical_order))), p),
                (plan, d, wrong_policy)):
            with self.subTest(policy=policy['source_ohms']), patch.object(RFEvaluator, 'evaluate') as f:
                with self.assertRaises(ValueError): self.evaluator(badplan, definition, policy)
                f.assert_not_called()
        data = plan.data
        for mutate in (lambda v: v['grids']['demo/coarse']['frequency_hz'].__setitem__(0, 664e6),
                       lambda v: v['requirements'].update(mode='matching_only'),
                       lambda v: v['rf_inputs']['bands'].update(sha256='0'*64),
                       lambda v: v['rf_inputs']['input_parasitic'].update(sha256='0'*64),
                       lambda v: v['config'].update(definition=None)):
            value = copy.deepcopy(data); mutate(value)
            with patch.object(RFEvaluator, 'evaluate') as f:
                with self.assertRaises(ValueError):
                    self.evaluator(Plan(canonical(value), sha(value)), d, p)
                f.assert_not_called()

    def test_recheck_source_and_bands_s2p_bytes_before_forward(self):
        plan, d, p, x = self.setup_model()
        for key in ('bands', 'input_parasitic', 'output_parasitic'):
            e = self.evaluator(plan, d, p)
            from lpf.search.preflight import rf_input_file
            invalid = Path(self.raw.name)/'invalid'; invalid.write_bytes(b'changed bytes')
            def swapped(root, path):
                return invalid if path == plan.data['rf_inputs'][key]['path'] else rf_input_file(root, path)
            with patch('lpf.search.preflight.rf_input_file', side_effect=swapped), patch.object(RFEvaluator, 'evaluate') as f:
                with self.assertRaises((ValueError, KeyError)): e.evaluate(x)
                f.assert_not_called()
            self.assertEqual(e.requested, 0)
        e = self.evaluator(plan, d, p)
        (ROOT/plan.data['config']['definition']['path']).write_text('{}')
        with patch.object(RFEvaluator, 'evaluate') as f:
            with self.assertRaises(ValueError): e.evaluate(x)
            f.assert_not_called()
        self.assertEqual(e.requested, 0)

    def test_illegal_values_spd_and_budget_stop(self):
        plan, d, p, x = self.setup_model()
        for invalid in (np.r_[x, 1], np.full_like(x, np.nan), np.full_like(x, -1), x.astype(complex)):
            e = self.evaluator(plan, d, p)
            with patch.object(RFEvaluator, 'evaluate') as f:
                with self.assertRaises(ValueError): e.evaluate(invalid)
                f.assert_not_called()
            self.assertEqual((e.requested, e.completed), (0, 0))
            self.assertEqual(json.loads(e.path.read_text())['status'], 'stopped')
        e = self.evaluator(plan, d, p)
        with patch('lpf.rf_core.nominal_inductors.check_nominal_inductors', side_effect=ValueError('SPD failed')), \
             patch.object(RFEvaluator, 'evaluate') as f:
            with self.assertRaisesRegex(ValueError, 'SPD'): e.evaluate(x)
            f.assert_not_called()
        def small(config):
            config['arms'][0]['steps'][0]['max_requested_samples'] = 111
            config['anytime_samples'] = []
        plan, d, p, x = self.setup_model(mutate=small)
        e = self.evaluator(plan, d, p)
        e.evaluate(x)
        with patch.object(RFEvaluator, 'evaluate') as f:
            with self.assertRaisesRegex(ValueError, 'full batch'): e.evaluate(x)
            f.assert_not_called()
        self.assertEqual((e.requested, e.completed), (56, 56))

    def test_multiple_steps_job_trial_reservations_and_points(self):
        def multiple(config):
            first = config['arms'][0]['steps'][0]
            first.update(points_per_interval=5, max_requested_samples=281)
            config['anytime_samples'] = []
            second = copy.deepcopy(first)
            second.update(name='later', points_per_interval=3, max_requested_samples=84)
            config['arms'][0]['steps'].append(second)
            other = copy.deepcopy(config['arms'][0]); other['name'] = 'other'
            config['arms'].append(other)
            config['max_trial_requested_samples'] = 3000
        plan, d, p, x = self.setup_model(mutate=multiple)
        e = self.evaluator(plan, d, p)
        e.evaluate(x); e.evaluate(x)
        self.assertEqual((e.requested, e.completed), (280, 280))
        self.assertEqual(e.other_jobs, 1500)
        self.assertEqual(e.reserved, 84+168+112)
        self.assertEqual(e.snapshot()['reservations']['dense']['upper_reservation'], 392)
        with patch.object(RFEvaluator, 'evaluate') as f:
            with self.assertRaises(ValueError): e.evaluate(x)
            f.assert_not_called()
        e = self.evaluator(plan, d, p)
        # Runtime guard applies all three ceilings, not solver nfev.
        e.job = dict(e.job, max_requested_samples=e.reserved+139)
        with patch.object(RFEvaluator, 'evaluate') as f:
            with self.assertRaises(ValueError): e.evaluate(x)
            f.assert_not_called()
        self.assertEqual(e.requested, 0)

    def test_runtime_grid_and_candidate_identity_mismatch(self):
        plan, d, p, x = self.setup_model()
        e = self.evaluator(plan, d, p)
        e.grid = plan.requested_grid('selection')
        with patch.object(RFEvaluator, 'evaluate') as f:
            with self.assertRaisesRegex(ValueError, 'grid/Plan'): e.evaluate(x)
            f.assert_not_called()
        self.assertEqual(e.requested, 0)
        e = self.evaluator(plan, d, p)
        result = e.evaluate(x)
        changed = dict(result, vector=x.copy()); changed['vector'][0] += .01
        with self.assertRaisesRegex(ValueError, 'identity'): rank_candidates([changed])
        with self.assertRaisesRegex(ValueError, 'identity'):
            rank_candidates([dict(result, grid_sha256='0'*64)])

    def test_failure_unknown_checkpoint_and_no_retry(self):
        plan, d, p, x = self.setup_model()
        for target in ('lpf.rf_core.model.RFEvaluator.evaluate', 'lpf.search.evaluation.evaluate_requirements'):
            e = self.evaluator(plan, d, p)
            def fail(*args, **kwargs):
                saved = json.loads(e.path.read_text())
                self.assertEqual((saved['requested'], saved['completed'], saved['status']), (56, 0, 'unknown'))
                raise RuntimeError('injected numerical/evaluation failure')
            with patch(target, side_effect=fail):
                with self.assertRaises(RuntimeError): e.evaluate(x)
            saved = json.loads(e.path.read_text())
            self.assertEqual((saved['requested'], saved['completed'], saved['status']), (56, 0, 'failed'))
            with self.assertRaises(RuntimeError): e.evaluate(x)
            with self.assertRaisesRegex(ValueError, 'Existing'):
                FixedStageEvaluation(plan, d, p, 'demo', 'coarse', e.path)
        e = self.evaluator(plan, d, p)
        from lpf.search.evaluation import atomic
        def fail_final(path, value):
            if value['completed']: raise OSError('disk failure')
            return atomic(path, value)
        with patch('lpf.search.evaluation.atomic', side_effect=fail_final):
            with self.assertRaises(OSError): e.evaluate(x)
        saved = json.loads(e.path.read_text())
        self.assertEqual((saved['requested'], saved['completed'], saved['status']), (56, 0, 'unknown'))
        with self.assertRaises(RuntimeError): e.evaluate(x)

    def test_independent_failure_and_interruption_do_not_release_cost(self):
        plan, d, p, x = self.setup_model()
        e = self.evaluator(plan, d, p)
        e.evaluate(x)
        with patch('lpf.rf_core.independent.evaluate_independent_response', side_effect=ValueError('power balance')):
            with self.assertRaisesRegex(ValueError, 'power balance'): e.spot_check(0, [0])
        saved = json.loads(e.path.read_text())
        self.assertEqual((saved['requested'], saved['completed']), (56, 56))
        self.assertEqual(saved['batches'][0]['independent']['status'], 'failed')
        with self.assertRaises(RuntimeError): e.evaluate(x)
        e = self.evaluator(plan, d, p)
        with patch.object(RFEvaluator, 'evaluate', side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt): e.evaluate(x)
        saved = json.loads(e.path.read_text())
        self.assertEqual((saved['requested'], saved['completed'], saved['status']), (56, 0, 'interrupted'))

    def test_callbacks_duplicates_and_infinity_preserved(self):
        plan, d, p, x = self.setup_model()
        e = self.evaluator(plan, d, p)
        problem = Problem.from_fixed_stage(e)
        objective = problem.objective(x)
        g = problem.constraints(x)
        self.assertEqual((e.requested, e.completed), (112, 112))
        self.assertEqual(objective, e.rows[0]['assessment']['worst_il_db'])
        self.assertEqual(len(g), 28)  # 14 mandatory intervals x 2, nominal not hard
        self.assertEqual(e.rows[0]['independent']['status'], 'not_run')
        e = self.evaluator(plan, d, p)
        s = np.zeros((56, 2, 2), complex)
        arrays = power_response(s, 50, 60-40j)
        r = RFResponse(e.grid, e.model.policy_id, e.model.policy_fingerprint, *arrays)
        with patch.object(RFEvaluator, 'evaluate', return_value=r):
            result = e.evaluate(x)
        self.assertEqual(result['assessment']['worst_il_db'], np.inf)
        self.assertTrue(np.all(np.isposinf(result['assessment']['mandatory_g'])))
        saved = json.loads(e.path.read_text())
        self.assertEqual(saved['batches'][0]['response']['il_db'][0], {'nonfinite': '+inf'})


if __name__ == '__main__':
    unittest.main()

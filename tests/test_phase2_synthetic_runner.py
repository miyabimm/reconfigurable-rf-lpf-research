"""Synthetic only; mock callbacks, no production solver or EXP storage."""
import copy
import json
import subprocess
from pathlib import Path
import sys
import tempfile
import unittest

import numpy as np
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from test_phase2_problem_seed import make
from test_phase2_staged_optimization import status
from lpf.checkpoint_io import atomic_write_json, canonical_config_hash
from lpf.phase2_models.problem_seed import vector_fingerprint
from lpf.phase2_models.synthetic_plan import make_synthetic_plan
from lpf.phase2_models.synthetic_runner import run_synthetic, run_synthetic_preview
from lpf.phase2_models.staged_optimization import scipy_slsqp_stage
from lpf.phase2_models.candidate_records import _without_timing


def plan_for(circuit, vector, *, count=2):
    vector = list(map(float, vector))
    starts = [{'id': f'start-{i}', 'vector': vector, 'vector_sha256': vector_fingerprint(vector),
               'seed': i, 'jitter_fraction': 0.0} for i in range(count)]
    source = {'kind': 'synthetic', 'policy_id': circuit.policy_id,
              'vectors': {s['id']: s['vector'] for s in starts}}
    return make_synthetic_plan(circuit, starts, run_id='synthetic-unit', coarse_points=1,
        fine_points=2, input_source=source)


class SyntheticRunnerTests(unittest.TestCase):
    def test_preflight_trials_and_definitions(self):
        from test_phase2_topology_enumeration import first
        for policy in ('RF-T005', 'RF-T007', 'RF-T008'):
            for n in (3, 4):
                c, row = first(policy, n)
                x = row['representative_vector']
                a = plan_for(c, x, count=1)
                self.assertEqual(a, plan_for(c, x, count=1))
                self.assertEqual(a['plan']['policy_id'], policy)
                self.assertEqual(len(a['plan']['starts'][0]['seed_record']['input_vector']), c.schema.vector_length)

    def test_preflight_rejects_bad_inputs(self):
        p, x = make('RF-T008', 4)
        x = list(map(float, x))
        base = {'id': 's', 'vector': x, 'vector_sha256': vector_fingerprint(x), 'seed': 0, 'jitter_fraction': 0.0}
        def create(starts, **kw):
            args = dict(run_id='synthetic-test', coarse_points=1, fine_points=2,
                        input_source={'kind': 'synthetic', 'policy_id': 'RF-T008', 'vectors': {'s': x}})
            args.update(kw)
            return make_synthetic_plan(p.circuit, starts, **args)
        for starts, args in [([base, base], {}), ([{**base, 'vector': x[:-1]}], {}),
                             ([base], {'fine_points': 4}), ([base], {'input_source': {}}),
                             ([base], {'run_id': 'EXP-999'}), ([{**base, 'vector_sha256': '0'*64}], {}),
                             ([base], {'input_source': {'kind': 'synthetic', 'policy_id': 'RF-T005', 'vectors': {'s': x}}})]:
            with self.assertRaises((ValueError, TypeError)):
                create(starts, **args)

    def test_resume_and_failure(self):
        p, x = make('RF-T008', 4)
        plan = plan_for(p.circuit, x)
        calls = []
        def mock(problem, v, budget, target):
            calls.append(budget)
            return v, status(0)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'checkpoint.json'
            first = run_synthetic(p.circuit, plan, path, optimize_stage=mock, max_new_starts=1)
            self.assertEqual((len(first['completed']), first['not_started']), (1, 1))
            final = run_synthetic(p.circuit, plan, path, optimize_stage=mock)
            self.assertEqual(calls, [240, 120, 240, 120])
            self.assertEqual(len(final['completed']), 2)
            repeat = run_synthetic(p.circuit, plan, Path(tmp) / 'repeat.json', optimize_stage=mock)
            self.assertEqual(_without_timing(final), _without_timing(repeat))
            self.assertTrue(all(r['candidate_promotion_blocked'] for r in final['completed']))
            self.assertTrue(all(r['validation']['independent_mna'] == 'not_run' for r in final['completed']))
            with patch('lpf.phase2_models.synthetic_plan._source', return_value={'changed': True}):
                with self.assertRaises(ValueError):
                    run_synthetic(p.circuit, plan, path, optimize_stage=mock)
            altered = copy.deepcopy(plan)
            altered['plan']['starts'].reverse()
            altered['fingerprint'] = canonical_config_hash(altered['plan'])
            with self.assertRaises(ValueError):
                run_synthetic(p.circuit, altered, path, optimize_stage=mock)
            damaged = json.loads(path.read_text())
            damaged['body']['completed'][0]['candidate_id'] = 'bad'
            atomic_write_json(path, damaged)
            with self.assertRaises(ValueError):
                run_synthetic(p.circuit, plan, path, optimize_stage=mock)
            damaged['sha256'] = canonical_config_hash(damaged['body'])
            atomic_write_json(path, damaged)
            with self.assertRaises(ValueError):
                run_synthetic(p.circuit, plan, path, optimize_stage=mock)
            path.write_text('{"body":NaN,"sha256":"invalid"}')
            with self.assertRaises(ValueError):
                run_synthetic(p.circuit, plan, path, optimize_stage=mock)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'checkpoint.json'
            def fail(*args):
                raise RuntimeError('mock failure')
            result = run_synthetic(p.circuit, plan, path, optimize_stage=fail, max_new_starts=1)
            self.assertEqual(result['completed'][0]['numerical']['state'], 'failed')
            self.assertEqual(result['completed'][0]['staged_record']['exception']['message'], 'mock failure')
            with self.assertRaises(ValueError):
                run_synthetic(p.circuit, plan, path, optimize_stage=scipy_slsqp_stage)
        with tempfile.TemporaryDirectory() as tmp:
            def nonfinite(problem, v, budget, target):
                v[0] = float('nan')
                return v, status(0)
            result = run_synthetic(p.circuit, plan, Path(tmp) / 'bad.json',
                                   optimize_stage=nonfinite, max_new_starts=1)
            staged = result['completed'][0]['staged_record']
            self.assertEqual(staged['numerical_state'], 'failed')
            self.assertEqual(staged['stage_calls'][0]['output_vector'][0], 'nan')

    def test_synthetic_execution_all_trials_and_status_recovery(self):
        from test_phase2_topology_enumeration import first
        for policy in ('RF-T005', 'RF-T007', 'RF-T008'):
            for n in (3, 4):
                c, row = first(policy, n)
                plan = plan_for(c, row['representative_vector'], count=2)
                for codes in ((4, 0, 0, 0), (8, 9), (9, 0, 0, 0)):
                    remaining = iter(codes * 2)
                    def mock(problem, v, budget, target):
                        return v, status(next(remaining))
                    with tempfile.TemporaryDirectory() as tmp:
                        result = run_synthetic(c, plan, Path(tmp) / 'c.json', optimize_stage=mock)
                        self.assertEqual(len(result['completed']), 2)
                        for candidate in result['completed']:
                            staged = candidate['staged_record']
                            self.assertEqual([call['status']['status'] for call in staged['stage_calls']], list(codes))
                            self.assertTrue(staged['attempts'])
                            self.assertTrue(candidate['candidate_promotion_blocked'])


    def test_failed_checkpoint_rechecks_stage_history(self):
        p, x = make('RF-T008', 4)
        plan = plan_for(p.circuit, x, count=1)
        def fail_on_fine(problem, vector, budget, target):
            if budget == 120:
                raise RuntimeError('synthetic fine failure')
            return vector, status(0)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'checkpoint.json'
            run_synthetic(p.circuit, plan, path, optimize_stage=fail_on_fine)
            saved = json.loads(path.read_text())
            self.assertEqual(saved['body']['completed'][0]['numerical']['state'], 'failed')
            # A recomputed envelope hash does not validate internal failed-call history.
            for idx, field, replacement in (
                (0, 'maxiter', 1),
                (0, 'input_vector', [0.0]),
                (1, 'maxiter', 1),
            ):
                altered = copy.deepcopy(saved)
                altered['body']['completed'][0]['staged_record']['stage_calls'][idx][field] = replacement
                altered['sha256'] = canonical_config_hash(altered['body'])
                atomic_write_json(path, altered)
                with self.assertRaises(ValueError):
                    run_synthetic(p.circuit, plan, path,
                                  optimize_stage=lambda *args: self.fail('rerun'))
            atomic_write_json(path, saved)
            final = run_synthetic(p.circuit, plan, path,
                                  optimize_stage=lambda *args: self.fail('rerun'))
            self.assertEqual(len(final['completed']), 1)

    def test_one_start_preview_classification_and_storage_contract(self):
        # Artificial IL boundary tests classification, not RF performance.
        from scripts.audit_new_experiment_storage import validate_selection, validate_summary
        p, x = make('RF-T008', 3)
        x[6] = 0.  # Non-neighbor nominal coupling must be zero.
        cases = (
            ('legal', None, (1, 0, 1, 0, 0)),
            ('component', 'component_not_verified', (1, 0, 1, 0, 0)),
            ('epigraph', 'final_c2_epigraph_inequality_failed_on_grid', (1, 0, 1, 0, 0)),
            ('h2', 'mandatory_harmonics_failed_on_grid', (1, 0, 1, 0, 0)),
            ('h3', 'mandatory_harmonics_failed_on_grid', (1, 0, 1, 0, 0)),
            ('nonconverged', 'numerical_not_converged', (1, 0, 0, 1, 0)),
            ('failed', 'numerical_failed', (1, 0, 0, 0, 1)),
            ('stopped', None, (0, 1, 0, 0, 0)),
        )
        for case, reason, expected in cases:
            with self.subTest(case=case):
                calls = []
                def synthetic_il(evaluator, vector):
                    il = np.where(evaluator.role == 0, .25, 36.)
                    if case in ('h2', 'h3'):
                        il[evaluator.role == (1 if case == 'h2' else 2)] = 29.
                    return il
                def mock(problem, v, budget, target):
                    calls.append(budget)
                    if case == 'failed':
                        raise RuntimeError('explicit mock failure')
                    v[-1] = 0. if case == 'epigraph' else .5
                    if case == 'component':
                        v[0] = 99.
                    return v, status(8 if case == 'nonconverged' else 0)
                with patch('lpf.phase2_models.coupled_lc.CoupledLCEvaluator.il', synthetic_il), \
                        patch('lpf.phase2_models.staged_optimization.minimize',
                              side_effect=AssertionError('Real solver forbidden')), \
                        tempfile.TemporaryDirectory() as tmp:
                    plan = plan_for(p.circuit, x, count=1)
                    preview = run_synthetic_preview(p.circuit, plan, Path(tmp) / 'c.json',
                        optimize_stage=mock, max_new_starts=0 if case == 'stopped' else 1)
                    summary = preview['run_summary']
                    counts = summary['attempts']
                    self.assertEqual(counts['planned'], 1)
                    self.assertEqual(tuple(counts[k] for k in ('attempted', 'not_started',
                        'converged', 'nonconverged', 'failed')), expected)
                    selected = 1 if case == 'legal' else 0
                    self.assertEqual(summary['selected_candidate_count'], selected)
                    validate_selection(preview['selection'])
                    # Null identity is deliberate: no fake EXP or manifest.
                    validate_summary(summary, None, selected)
                    if not selected:
                        self.assertTrue(summary['no_candidate_reason'])
                    self.assertEqual(preview['plan_fingerprint'], plan['fingerprint'])
                    for field in ('source', 'input_source_sha256', 'policy_sha256', 'identity'):
                        self.assertEqual(preview[field], plan['plan'][field])
                    self.assertEqual(len(calls), 0 if case == 'stopped' else 1 if case == 'failed' else 2)
                    self.assertTrue(preview['candidate_promotion_blocked'])
                    self.assertFalse(preview['rf_compliance_certified'])
                    self.assertFalse(preview['execution_allowed'])
                    for field in ('git_readback', 'git_export', 'storage_audit', 'manifest', 'experiment_execution'):
                        self.assertEqual(preview[field], 'not_run')
                    self.assertEqual(preview['owner_approval'], 'not_verified')
                    if case != 'stopped':
                        record = preview['result']['completed'][0]
                        self.assertEqual(len(record['values']['capacitors_pf_by_setting']), 6)
                        self.assertEqual(record['source_provenance']['value']['input_source_sha256'],
                                         preview['input_source_sha256'])
                        self.assertEqual(record['validation']['independent_mna'], 'not_run')
                        self.assertEqual(record['validation']['power_balance'], 'not_run')
                        row = preview['pareto']['candidates'][0]
                        if reason:
                            self.assertIn(reason, row['reasons'])
                        else:
                            self.assertEqual(row['reasons'], [])
                            self.assertTrue(row['pareto_within_group'])
                    else:
                        self.assertEqual(preview['result']['completed'], [])

    def test_preview_reads_checkpoint_and_preserves_boundary_resume(self):
        p, x = make('RF-T008', 3)
        plan = plan_for(p.circuit, x, count=1)
        calls = []
        def mock(problem, v, budget, target):
            calls.append(budget)
            return v, status(0)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'c.json'
            stopped = run_synthetic_preview(p.circuit, plan, path, optimize_stage=mock, max_new_starts=0)
            self.assertEqual(stopped['run_summary']['attempts']['not_started'], 1)
            finished = run_synthetic_preview(p.circuit, plan, path, optimize_stage=mock)
            self.assertEqual(finished['run_summary']['attempts']['attempted'], 1)
            self.assertEqual(calls, [240, 120])
            saved = json.loads(path.read_text())
            saved['body']['completed'][0]['rf']['metrics']['min_h2_db'] = 99.
            saved['sha256'] = canonical_config_hash(saved['body'])
            atomic_write_json(path, saved)
            with self.assertRaises(ValueError):
                run_synthetic_preview(p.circuit, plan, path, optimize_stage=mock, max_new_starts=0)
            self.assertEqual(calls, [240, 120])
        with self.assertRaisesRegex(ValueError, 'exactly one'):
            run_synthetic_preview(p.circuit, plan_for(p.circuit, x), 'unused', optimize_stage=mock)

    def test_rejects_other_git_worktree(self):
        p, x = make('RF-T008', 4)
        plan = plan_for(p.circuit, x, count=1)
        with tempfile.TemporaryDirectory() as tmp:
            subprocess.run(['git', 'init', '-q', tmp], check=True)
            path = Path(tmp) / 'checkpoint.json'
            with self.assertRaisesRegex(ValueError, 'Git worktree'):
                run_synthetic(p.circuit, plan, path, optimize_stage=lambda *args: self.fail('called'))
            self.assertFalse(path.exists())

    def test_interrupted_start_fails_closed(self):
        p, x = make('RF-T008', 4)
        plan = plan_for(p.circuit, x, count=1)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'checkpoint.json'
            def crash(*args):
                raise KeyboardInterrupt()
            with self.assertRaises(KeyboardInterrupt):
                run_synthetic(p.circuit, plan, path, optimize_stage=crash)
            body = json.loads(path.read_text())['body']
            self.assertEqual(body['in_progress'], 'start-0')
            with self.assertRaisesRegex(ValueError, 'outcome unknown'):
                run_synthetic(p.circuit, plan, path, optimize_stage=lambda *args: self.fail('retried'))


if __name__ == '__main__':
    unittest.main()

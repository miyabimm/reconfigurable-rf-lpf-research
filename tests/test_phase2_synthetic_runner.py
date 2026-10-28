"""Synthetic only; mock callbacks, no production solver or EXP storage."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from test_phase2_problem_seed import make
from test_phase2_staged_optimization import status
from lpf.checkpoint_io import atomic_write_json, canonical_config_hash
from lpf.phase2_models.problem_seed import vector_fingerprint
from lpf.phase2_models.synthetic_plan import make_synthetic_plan
from lpf.phase2_models.synthetic_runner import run_synthetic
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

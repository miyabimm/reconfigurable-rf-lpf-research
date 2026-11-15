"""Bounded development-only Worker tests, not a scientific EXP."""
import copy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import numpy as np

import test_issue315_fixed_stage as fixtures
from lpf.search._development_worker import DevelopmentWorker
from lpf.search._worker_next import MinimalWorker
from lpf.search.worker import _development_options
from lpf.search.problem import Problem
from lpf.optimizers.hybrid import hybrid_minimize, HybridResult, LocalRun
from lpf.optimizers.slsqp import slsqp_minimize
from lpf.optimizers.slp import slp_minimize
from lpf.search.performance import summarize_mandatory
from lpf.search.storage import vector_sha
from lpf.search.evaluation import raw_numbers
from lpf.search.validation import rank_candidates
from lpf.search.plan import ROOT


class DevelopmentWorkerTests(unittest.TestCase):
    setUp = fixtures.FixedStageTests.setUp
    setup_model = fixtures.FixedStageTests.setup_model
    evaluator = fixtures.FixedStageTests.evaluator

    def make_worker(self, solver='hybrid', *, interval=100, spot_checks=None):
        def configure(c):
            step = c['arms'][0]['steps'][0]
            step.update(solver=solver, aggregation='signed_max' if solver == 'slp' else 'sum')
            step['options'] = (dict(maxiter=2, max_restarts=0, max_evaluations=3, restart_sigma=.1)
                               if solver == 'hybrid' else dict(max_iterations=2, max_evaluations=3))
        plan, d, p, x = self.setup_model('RF-T008', mutate=configure)
        path = Path(self.raw.name) / f'{solver}-checkpoints'
        w = DevelopmentWorker(plan, d, p, 'demo', 23, x, vector_sha(x), root=ROOT,
                              checkpoint=path, checkpoint_interval=interval, spot_checks=spot_checks)
        return plan, d, p, x, w

    def test_solvers_and_checkpoint_reevaluation(self):
        for solver in ('hybrid', 'slsqp', 'slp'):
            with self.subTest(solver=solver):
                plan, d, p, x, w = self.make_worker(solver, spot_checks={'terminal': [0, 111]})
                old_solver_eval = self.evaluator(plan, d, p)
                problem = Problem.from_fixed_stage(old_solver_eval)
                settings = plan.data['config']['arms'][0]['steps'][0]
                if solver == 'hybrid':
                    def residuals(v):
                        a = old_solver_eval.evaluate(v)['assessment']
                        return np.r_[np.sqrt(a['worst_il_db']), np.maximum(0., -np.asarray(a['mandatory_g']))]
                    expected = hybrid_minimize(residuals, x, w.bounds, seed=23,
                                               aggregation=settings['aggregation'], **_development_options(settings))
                else:
                    fn = slsqp_minimize if solver == 'slsqp' else slp_minimize
                    expected = fn(problem.residuals if solver == 'slsqp' else problem.errors,
                                  x, w.bounds, constraints=problem.constraints,
                                  aggregation=settings['aggregation'], **_development_options(settings))
                output = w.run()
                step = output['steps'][0]
                self.assertEqual(step['solver_result'], raw_numbers(expected))
                self.assertEqual(step['forward_count'], len(old_solver_eval.rows))
                self.assertEqual(step['solver'], solver)
                self.assertEqual(step['forward_count'], 3)
                self.assertEqual(output['terminal']['status'], 'completed')
                self.assertEqual(output['terminal']['candidates'][0]['independent']['status'], 'pass')
                snapshots = sorted(w.path.glob('*.json'))
                self.assertTrue(snapshots)
                snapshot = json.loads(snapshots[-1].read_text())
                self.assertEqual(snapshot['plan_sha256'], plan.sha256)
                self.assertEqual(snapshot['best']['vector_sha256'], vector_sha(snapshot['best']['vector']))
                w._activate('demo/coarse')
                response, assessment = w.evaluate(snapshot['best']['vector'])
                self.assertEqual(snapshot['best']['worst_il_db'], assessment['worst_il_db'])
                for k, v in summarize_mandatory(assessment, w.prepared_requirements).items():
                    self.assertEqual(snapshot['best'][k], v)
                old = self.evaluator(plan, d, p)
                legacy = old.evaluate(snapshot['best']['vector'])
                np.testing.assert_array_equal(response.s.real, old.rows[-1]['response']['s_real'])
                np.testing.assert_array_equal(response.s.imag, old.rows[-1]['response']['s_imag'])
                for name in ('il_db', 'apl_db', 'in_rl_db', 'out_rl_db'):
                    np.testing.assert_array_equal(getattr(response, name), old.rows[-1]['response'][name])
                np.testing.assert_array_equal(assessment['mandatory_g'], legacy['assessment']['mandatory_g'])
                self.assertEqual(set(response.grid.setting), set(range(6)))
                self.assertEqual(len(set(response.grid.segment)), 28)
                with self.assertRaisesRegex(RuntimeError, 'retry'):
                    w.run()

    def test_rf_best_matches_existing_ranking_and_spd_stop(self):
        plan, d, p, x, w = self.make_worker(interval=100)
        w._activate('demo/coarse')
        w.forward_count, w.saved_count, w.saved_sha = 0, 0, None
        w.best = w.best_key = None
        w._running = True
        old = self.evaluator(plan, d, p)
        assessed = []
        for fraction in (0., .1, .2):
            v = x.copy(); v[0] += fraction * (w.bounds[0][1] - x[0])
            w._evaluate(v)
            assessed.append(old.evaluate(v))
        self.assertEqual(w.best['vector_sha256'], rank_candidates(assessed)['ranked'][0]['vector_sha256'])
        with patch.object(type(w.model.topology), 'matrices', side_effect=ValueError('non-SPD')):
            with self.assertRaisesRegex(ValueError, 'non-SPD'):
                w._evaluate(x)
        self.assertEqual(w.forward_count, 3)
        w._running = False

    def test_multi_step_different_grids(self):
        def configure(c):
            first = c['arms'][0]['steps'][0]
            first.update(solver='hybrid', aggregation='sum', max_requested_samples=168,
                         options=dict(maxiter=2, max_restarts=0, max_evaluations=3, restart_sigma=.1))
            second = copy.deepcopy(first)
            second.update(name='fine', solver='slsqp', points_per_interval=3, max_requested_samples=252,
                          options=dict(max_iterations=2, max_evaluations=3))
            c['arms'][0]['steps'].append(second)
        plan, d, p, x = self.setup_model('RF-T008', mutate=configure)
        w = DevelopmentWorker(plan, d, p, 'demo', 23, x, vector_sha(x), root=ROOT,
                              checkpoint=Path(self.raw.name)/'multi-checkpoints')
        prior = {}
        original_save = w._save_best
        def observe_save():
            for path, data in prior.items():
                self.assertEqual(path.read_bytes(), data)
            original_save()
            for path in w.path.glob('*.json'):
                prior.setdefault(path, path.read_bytes())
        with patch.object(w, '_save_best', side_effect=observe_save):
            output = w.run()
        self.assertEqual([s['forward_count'] for s in output['steps']], [3, 3])
        self.assertNotEqual(plan.data['grids']['demo/coarse']['sha256'], plan.data['grids']['demo/fine']['sha256'])
        paths = sorted(w.path.glob('*.json'))
        self.assertGreaterEqual(len(paths), 2)
        records = [json.loads(path.read_text()) for path in paths]
        self.assertEqual([r['sequence'] for r in records], list(range(1, len(paths) + 1)))
        self.assertEqual([p.name for p in paths], [f'{i:06d}.json' for i in range(1, len(paths) + 1)])
        for step in ('coarse', 'fine'):
            rows = [r for r in records if r['step'] == step]
            self.assertTrue(rows)
            self.assertEqual(rows[0]['forward_count'], 1)
            self.assertEqual([r['forward_count'] for r in rows], sorted(r['forward_count'] for r in rows))
        for row in records:
            self.assertEqual(row['job_id'], 'development-demo-23')
            self.assertEqual(row['plan_sha256'], plan.sha256)
            self.assertEqual(row['best']['vector_sha256'], vector_sha(row['best']['vector']))
        self.assertEqual(records[0]['step'], 'coarse')
        self.assertEqual(records[0]['grid_sha256'], plan.data['grids']['demo/coarse']['sha256'])
        saved = records[-1]
        self.assertEqual(saved['step'], 'fine')
        self.assertEqual(saved['grid_sha256'], plan.data['grids']['demo/fine']['sha256'])
        self.assertEqual(saved['best'], output['steps'][1]['rf_best'])
        for path, data in prior.items():
            self.assertEqual(path.read_bytes(), data)

    def test_25_coordinate_box_all_three_solvers(self):
        from lpf.constraint_versions import load_constraint
        from lpf.rf_core import build_rf_model
        from lpf.search.component_constraints import physical_bounds
        from lpf.topology_management import CircuitDefinition
        from lpf.topology_management.circuit_layout import InductorTree, CapacitorPlacement
        p = load_constraint('RF-T008', allow_trial=True)
        var = ((0, -1), (1, 2))
        d = CircuitDefinition(InductorTree(5, ((0, 1), (1, 3), (1, 4), (1, 2))),
            ('LQP02HV',) * 4, (0, 1, 2, 3), ((0, 1), (0, 2), (1, 2), (2, 3)),
            CapacitorPlacement(5, ((0, 1), (4, -1), (1, 2)), var, var),
            ('GJM01',) * 3, ('shunt_to_ground', 'bridge'))
        model = build_rf_model(d, p)
        hard = physical_bounds(d, model.schema, p)
        x = np.mean(hard, axis=1)
        x[7:11] = 0.0  # SPD regardless of the four coupling slots
        self.assertEqual(len(x), 25)
        def configure(c):
            first = c['arms'][0]['steps'][0]
            first.update(solver='hybrid', aggregation='sum', max_requested_samples=168,
                         options=dict(maxiter=2, max_restarts=0, max_evaluations=3, restart_sigma=.1))
            for name, solver in (('fine', 'slsqp'), ('last', 'slp')):
                step = copy.deepcopy(first)
                step.update(name=name, solver=solver, aggregation='signed_max' if solver == 'slp' else 'sum',
                            options=dict(max_iterations=2, max_evaluations=3))
                c['arms'][0]['steps'].append(step)
        with patch.object(fixtures, 'make', return_value=(p, d, model, hard, x)):
            plan, d, p, x = self.setup_model('RF-T008', mutate=configure)
        box = [[float(v), float(v)] for v in x]
        box[0] = [x[0] - .1, x[0] + .1]
        w = DevelopmentWorker(plan, d, p, 'demo', 23, x, vector_sha(x), root=ROOT,
                              checkpoint=Path(self.raw.name)/'25-box', search_bounds=box)
        self.assertEqual(w._physical_bounds, hard)
        seen = []
        def observe(fn):
            def call(callback, start, bounds, **kw):
                seen.append([list(pair) for pair in bounds])
                return fn(callback, start, bounds, **kw)
            return call
        with patch('lpf.search._worker_next.hybrid_minimize', side_effect=observe(hybrid_minimize)), \
             patch('lpf.search._development_worker.slsqp_minimize', side_effect=observe(slsqp_minimize)), \
             patch('lpf.search._development_worker.slp_minimize', side_effect=observe(slp_minimize)):
            result = w.run()
        self.assertEqual(seen, [box] * 3)
        for step in result['steps']:
            for i in range(1, 25):
                self.assertEqual(step['solver_result']['best_x' if step['solver'] == 'hybrid' else 'x'][i], x[i])
                self.assertEqual(step['rf_best']['vector'][i], x[i])
        for path in w.path.glob('*.json'):
            self.assertEqual(json.loads(path.read_text())['best']['vector'][1:], x.tolist()[1:])

    def test_invalid_search_boxes_stop_before_solver(self):
        plan, d, p, x, existing = self.make_worker()
        good = [list(pair) for pair in existing._physical_bounds]
        cases = [[], good[:-1], [[1, 2, 3]] * len(good)]
        for bad in (float('nan'), float('inf'), True, '1'):
            box = copy.deepcopy(good); box[0][0] = bad; cases.append(box)
        box = copy.deepcopy(good); box[0] = [good[0][1], good[0][0]]; cases.append(box)
        box = copy.deepcopy(good); box[0][0] -= 1; cases.append(box)
        box = copy.deepcopy(good); box[0] = [good[0][0], float(x[0]) - .1]; cases.append(box)
        with patch('lpf.search._worker_next.hybrid_minimize') as solver:
            for i, box in enumerate(cases):
                with self.subTest(i=i), self.assertRaises(ValueError):
                    DevelopmentWorker(plan, d, p, 'demo', 23, x, vector_sha(x), root=ROOT,
                                      checkpoint=Path(self.raw.name)/f'bad-box-{i}', search_bounds=box)
            solver.assert_not_called()
            with self.assertRaisesRegex(ValueError, 'SHA'):
                DevelopmentWorker(plan, d, p, 'demo', 23, x, '0'*64, root=ROOT,
                                  checkpoint=Path(self.raw.name)/'bad-sha', search_bounds=good)
            illegal = x.copy(); illegal[0] = good[0][0] - 1
            with self.assertRaises(ValueError):
                DevelopmentWorker(plan, d, p, 'demo', 23, illegal, vector_sha(illegal), root=ROOT,
                                  checkpoint=Path(self.raw.name)/'bad-physical', search_bounds=good)
            solver.assert_not_called()

    def test_checkpoint_schedule(self):
        _, _, _, x, w = self.make_worker(interval=3)
        w.step = w.steps[0]
        w._activate('demo/coarse')
        w.forward_count, w.saved_count, w.saved_sha = 0, 0, None
        w.best = w.best_key = None
        w._running = True
        vectors = []
        for fraction in (0., .1, .2, .3, .4, .5, .6, .7):
            v = x.copy(); v[0] += fraction * (w.bounds[0][1] - x[0]); vectors.append(v)
        # Better metrics at forwards 2 and 5, no improvement at 3 or 4.
        ils = iter([5., 4., 6., 6., 3., 7., 7., 7.])
        def fake_forward(_self, vector):
            return None, {'worst_il_db': next(ils), 'mandatory_g': ()}
        summary = dict(strict_feasible=True, max_violation_db=0., sum_violation_db=0.)
        with patch.object(MinimalWorker, '_evaluate', fake_forward), \
             patch('lpf.search._development_worker.summarize_mandatory', return_value=summary), \
             patch('lpf.search._development_worker.validate_values'), \
             patch.object(w, '_save_best', wraps=w._save_best) as save:
            for v in vectors[:3]:
                w._evaluate(v)
            self.assertEqual(save.call_count, 1)  # first; interval not yet reached
            first_bytes = (w.path/'000001.json').read_bytes()
            w._evaluate(vectors[3])
            self.assertEqual(save.call_count, 2)  # pending improvement at N
            self.assertEqual((w.path/'000001.json').read_bytes(), first_bytes)
            second_bytes = (w.path/'000002.json').read_bytes()
            w._evaluate(vectors[4])
            self.assertEqual(save.call_count, 2)  # new improvement before N
            w._save_best()  # step-end flush
            self.assertEqual(save.call_count, 3)
            for v in vectors[5:]:
                w._evaluate(v)
            self.assertEqual(save.call_count, 3)  # N elapsed, but no improvement
        paths = sorted(w.path.glob('*.json'))
        self.assertEqual([p.name for p in paths], ['000001.json', '000002.json', '000003.json'])
        self.assertEqual((w.path/'000001.json').read_bytes(), first_bytes)
        self.assertEqual((w.path/'000002.json').read_bytes(), second_bytes)
        records = [json.loads(p.read_text()) for p in paths]
        self.assertEqual([r['sequence'] for r in records], [1, 2, 3])
        self.assertEqual([r['forward_count'] for r in records], [1, 4, 5])

    def test_step_end_flushes_pending_best(self):
        _, _, _, x, w = self.make_worker(interval=100)
        y = x.copy(); y[0] = (x[0] + w.bounds[0][1]) / 2
        def solver(callback, x0, bounds, **kw):
            callback(x); callback(y)
            run = LocalRun(x.tolist(), 1., y.tolist(), 1., False, 1, 'fixture', 0, 2)
            return HybridResult([run], y.tolist(), 1., 2, 'evaluation_budget_exhausted',
                                23, 2, 0, 3, .1)
        summaries = iter([dict(strict_feasible=False, max_violation_db=v, sum_violation_db=v)
                          for v in (2., 1.)])
        with patch('lpf.search._worker_next.hybrid_minimize', side_effect=solver), \
             patch('lpf.search._development_worker.summarize_mandatory', side_effect=lambda *a: next(summaries)), \
             patch.object(w, '_save_best', wraps=w._save_best) as save:
            output = w.run()
        self.assertEqual(save.call_count, 2)
        saved = json.loads((w.path/'000002.json').read_text())
        self.assertEqual(saved['forward_count'], 2)
        self.assertEqual(saved['best']['vector_sha256'], vector_sha(y))
        self.assertEqual(saved['best'], output['steps'][0]['rf_best'])

    def test_checkpoint_existing_directory_and_file_stop(self):
        plan, d, p, x, w = self.make_worker()
        with self.assertRaisesRegex(ValueError, 'Fresh'):
            DevelopmentWorker(plan, d, p, 'demo', 23, x, vector_sha(x), root=ROOT,
                              checkpoint=w.path)
        target = w.path/'000001.json'
        target.write_bytes(b'preserve this existing file')
        with self.assertRaises(FileExistsError):
            w.run()
        self.assertEqual(target.read_bytes(), b'preserve this existing file')
        with self.assertRaisesRegex(RuntimeError, 'retry'):
            w.run()

    def test_selection_compact_ranking_and_terminal_detail_matches_legacy(self):
        plan, d, p, x, w = self.make_worker(spot_checks={'selection': [0], 'terminal': [0, 111]})
        vectors = []
        for fraction in (0., .1, .2):
            v = x.copy(); v[0] += fraction * (w.bounds[0][1] - x[0]); vectors.append(v)
        def solver(callback, x0, bounds, **kw):
            callback(vectors[0])
            runs = [LocalRun(v.tolist(), 1., v.tolist(), 1., False, 1, 'fixture', 0, 1)
                    for v in vectors[:2]]
            return HybridResult(runs, vectors[2].tolist(), 1., 1, 'evaluation_budget_exhausted',
                                23, 2, 0, 3, .1)
        seen = []
        def rank(rows):
            seen.extend(rows)
            return rank_candidates(rows)
        with patch('lpf.search._worker_next.hybrid_minimize', side_effect=solver), \
             patch('lpf.search._development_worker.rank_candidates', side_effect=rank):
            actual = w.run()
        identity_keys = {'status', 'policy_id', 'policy_fingerprint', 'mode', 'requirements_fingerprint',
                         'grid_fingerprint', 'strict_feasible', 'worst_il_db', 'max_violation_db', 'sum_violation_db'}
        self.assertEqual(len(seen), 2)
        for row in seen:
            self.assertEqual(set(row['assessment']), identity_keys)
        unique = sorted((vector_sha(v), v) for v in vectors)
        self.assertEqual(actual['selection']['excluded'],
                         [dict(vector_sha256=unique[2][0], status='unrun', reason='max_candidates')])
        old = self.evaluator(plan, d, p)
        old.stage, old.grid = 'selection', plan.requested_grid('selection')
        assessed = []
        for digest, vector in unique[:2]:
            result = old.evaluate(vector)
            result['independent'] = dict(status='pass', sample_indices=[0], passivity='pass_at_samples',
                                         power_balance='pass_at_samples', whole_band_checked=False)
            assessed.append(result)
        expected = rank_candidates(assessed)['ranked']
        self.assertEqual([r['vector_sha256'] for r in actual['selection']['ranked']],
                         [r['vector_sha256'] for r in expected])
        for compact, full in zip(actual['selection']['ranked'], expected):
            self.assertEqual(compact['rank_key'], raw_numbers(full['rank_key']))
            self.assertEqual(compact['assessment'], raw_numbers({k: full['assessment'][k] for k in identity_keys}))
            self.assertEqual(compact['independent'], full['independent'])
        self.assertEqual(actual['terminal']['candidates'][0]['vector_sha256'], expected[0]['vector_sha256'])
        old.stage, old.grid = 'terminal', plan.requested_grid('terminal')
        terminal = old.evaluate(expected[0]['vector'])
        self.assertEqual(actual['terminal']['candidates'][0]['assessment'], raw_numbers(terminal['assessment']))
        self.assertIn('rows', actual['terminal']['candidates'][0]['assessment'])
        self.assertEqual(actual['terminal']['candidates'][0]['independent']['status'], 'pass')

    def test_second_checkpoint_failure_preserves_first_and_stops(self):
        _, _, _, x, w = self.make_worker(interval=1)
        y = x.copy(); y[0] = (x[0] + w.bounds[0][1]) / 2
        def solver(callback, *args, **kwargs):
            callback(x)
            callback(y)
            self.fail('must stop on checkpoint failure')
        summaries = iter([dict(strict_feasible=False, max_violation_db=v, sum_violation_db=v)
                          for v in (2., 1.)])
        from lpf.search._development_worker import _save_checkpoint
        saved = []
        def write(path, payload):
            if saved:
                raise OSError('disk full after first event')
            _save_checkpoint(path, payload)
            saved.append(path.read_bytes())
        with patch('lpf.search._worker_next.hybrid_minimize', side_effect=solver), \
             patch('lpf.search._development_worker.summarize_mandatory', side_effect=lambda *a: next(summaries)), \
             patch('lpf.search._development_worker._save_checkpoint', side_effect=write):
            with self.assertRaisesRegex(OSError, 'disk full after first event'):
                w.run()
        self.assertEqual((w.path/'000001.json').read_bytes(), saved[0])
        self.assertEqual(sorted(p.name for p in w.path.iterdir()), ['000001.json'])
        self.assertEqual(w.checkpoint_sequence, 1)
        self.assertEqual(w.saved_count, 1)
        with self.assertRaisesRegex(RuntimeError, 'retry'):
            w.run()

    def test_checkpoint_failure_stops_without_retry(self):
        _, _, _, _, w = self.make_worker()
        with patch('lpf.search._development_worker._save_checkpoint', side_effect=OSError('disk full')) as save:
            with self.assertRaisesRegex(OSError, 'disk full'):
                w.run()
            self.assertEqual(save.call_count, 1)
        self.assertEqual(list(w.path.iterdir()), [])
        with self.assertRaises(RuntimeError):
            w.run()


if __name__ == '__main__':
    unittest.main()

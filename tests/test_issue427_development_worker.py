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
        path = Path(self.raw.name) / f'{solver}.json'
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
                from lpf.search.evaluation import raw_numbers
                self.assertEqual(step['solver_result'], raw_numbers(expected))
                self.assertEqual(step['forward_count'], len(old_solver_eval.rows))
                self.assertEqual(step['solver'], solver)
                self.assertEqual(step['forward_count'], 3)
                self.assertEqual(output['terminal']['status'], 'completed')
                self.assertEqual(output['terminal']['candidates'][0]['independent']['status'], 'pass')
                snapshot = json.loads(w.path.read_text())
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
                              checkpoint=Path(self.raw.name)/'multi.json')
        output = w.run()
        self.assertEqual([s['forward_count'] for s in output['steps']], [3, 3])
        self.assertNotEqual(plan.data['grids']['demo/coarse']['sha256'], plan.data['grids']['demo/fine']['sha256'])
        saved = json.loads(w.path.read_text())
        self.assertEqual(saved['step'], 'fine')
        self.assertEqual(saved['grid_sha256'], plan.data['grids']['demo/fine']['sha256'])
        self.assertEqual(saved['best'], output['steps'][1]['rf_best'])

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
            w._evaluate(vectors[3])
            self.assertEqual(save.call_count, 2)  # pending improvement at N
            w._evaluate(vectors[4])
            self.assertEqual(save.call_count, 2)  # new improvement before N
            w._save_best()  # step-end flush
            self.assertEqual(save.call_count, 3)
            for v in vectors[5:]:
                w._evaluate(v)
            self.assertEqual(save.call_count, 3)  # N elapsed, but no improvement
        self.assertEqual(json.loads(w.path.read_text())['forward_count'], 5)

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
        saved = json.loads(w.path.read_text())
        self.assertEqual(saved['forward_count'], 2)
        self.assertEqual(saved['best']['vector_sha256'], vector_sha(y))
        self.assertEqual(saved['best'], output['steps'][0]['rf_best'])

    def test_checkpoint_failure_stops_without_retry(self):
        _, _, _, _, w = self.make_worker()
        with patch('lpf.search._development_worker._save_checkpoint', side_effect=OSError('disk full')) as save:
            with self.assertRaisesRegex(OSError, 'disk full'):
                w.run()
            self.assertEqual(save.call_count, 1)
        self.assertFalse(w.path.exists())
        with self.assertRaises(RuntimeError):
            w.run()


if __name__ == '__main__':
    unittest.main()

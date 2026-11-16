"""Issue 435: development-only objective and bounded single-job accounting."""
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np
import yaml

import test_issue315_fixed_stage as fixtures
from lpf.search._development_runner import _weighted_plan, run_development_worker
from lpf.search._development_worker import DevelopmentWorker, _weighted_residuals, WEIGHTED_OBJECTIVE
from lpf.search.plan import ROOT
from lpf.search.storage import sha, vector_sha
from lpf.optimizers.hybrid import HybridResult, LocalRun


class WeightedTests(unittest.TestCase):
    setUp = fixtures.FixedStageTests.setUp
    setup_model = fixtures.FixedStageTests.setup_model

    def inputs(self):
        _, d, policy, x = self.setup_model('RF-T008')
        config = Path(self.sources.name) / 'plan.yaml'
        c = yaml.safe_load(config.read_text())
        c['anytime_samples'] = []
        step = c['arms'][0]['steps'][0]
        step.update(solver='hybrid', aggregation='sum', points_per_interval=2, stop_points_per_interval=3)
        for obj, keys in ((step, ('options', 'max_requested_samples')),
                          (c['arms'][0], ('max_requested_samples',)),
                          (c, ('max_trial_requested_samples',)),
                          (c['validation'], ('max_requested_samples',))):
            for key in keys:
                obj.pop(key, None)
        c['selection']['points_per_interval'] = 3
        c['validation']['terminal_points'] = 17
        config.write_text(yaml.safe_dump(c))
        starts = Path(self.raw.name) / 'starts.json'
        starts.write_text(json.dumps({'23': {'vector': x.tolist(), 'vector_sha256': vector_sha(x)}}))
        return config, starts, d, policy, x

    def test_formula_two_terms_and_grid(self):
        config, _, d, p, x = self.inputs()
        plan = _weighted_plan(config, ROOT, 'demo', 3)
        worker = DevelopmentWorker(plan, d, p, 'demo', 23, x, vector_sha(x), root=ROOT,
                                   checkpoint=Path(self.raw.name)/'formula', objective_mode='weighted_violation')
        grid = worker.grid
        self.assertEqual((len(grid.frequency_hz), len(set(grid.segment)), len(set(grid.setting))), (70, 28, 6))
        # 42 harmonic samples, two violating; nominal 35 is not a penalty.
        values = np.full(70, 36.)
        segments = [i.segment for i in worker.requirements.intervals if i.region in ('H2', 'H3')]
        ix = np.flatnonzero(np.isin(grid.segment, segments))
        self.assertEqual(len(ix), 42)
        values[ix[:2]] = [29.01, 28.01]
        residuals = _weighted_residuals(SimpleNamespace(il_db=values), {'worst_il_db': .5}, worker.prepared_requirements)
        self.assertAlmostEqual(float(np.sum(residuals**2)), .2**2 + 100 * 5 / 42)
        values[ix] = 34.
        residuals = _weighted_residuals(SimpleNamespace(il_db=values), {'worst_il_db': .3}, worker.prepared_requirements)
        self.assertEqual(float(np.sum(residuals**2)), 0.)

    def test_runner_budget_checkpoint_terminal_and_spots(self):
        config, starts, _, _, _ = self.inputs()
        output = Path(self.raw.name)/'job'
        result = run_development_worker(config, starts, 23, 'demo', output, objective_mode='weighted_violation',
                                        max_search_forwards=3, spot_checks={'terminal': [0, 111]})
        record = json.loads((output/'input.json').read_text())
        plan = record['plan']; step = plan['config']['arms'][0]['steps'][0]
        self.assertEqual(step['options'], dict(max_search_forwards=3))
        self.assertEqual(step['max_requested_samples'], 210)
        costs = plan['costs']['jobs']['demo']
        self.assertEqual((costs['selection_upper_reservation'], costs['terminal_fixed_reservation'],
                          costs['total_upper_reservation']), (84, 476, 770))
        self.assertEqual(sha(plan), record['plan_sha256'])
        self.assertEqual(record['weighted_objective_sha256'], sha(WEIGHTED_OBJECTIVE))
        s = result['steps'][0]
        self.assertLessEqual(s['forward_count'], 3)
        self.assertEqual(s['solver_result']['nfev'], s['forward_count'])
        self.assertEqual(s['stop_reason'], 'evaluation_budget_exhausted')
        self.assertEqual(result['status'], 'not_converged')
        self.assertEqual(s['rf_best']['objective_j'], s['solver_result']['best_fun'])
        best = s['rf_best']['vector_sha256']
        self.assertEqual(json.loads(sorted((output/'checkpoints').glob('*.json'))[-1].read_text())['best'], s['rf_best'])
        self.assertEqual(result['selection']['forward_count'], 1)
        self.assertEqual(result['selection']['ranked'][0]['vector_sha256'], best)
        self.assertEqual(result['terminal']['candidates'][0]['vector_sha256'], best)
        self.assertEqual(result['terminal']['candidates'][0]['independent']['status'], 'pass')
        self.assertEqual(result['costs']['search_requested_samples'], s['forward_count']*70)
        self.assertEqual(result['costs']['selection_requested_samples'], 84)
        self.assertEqual(result['costs']['terminal_requested_samples'], 476)
        self.assertEqual(result['costs']['independent_mna_samples_by_stage'], {'terminal': 2})
        self.assertEqual(json.loads((output/'result.json').read_text()), result)

    def test_selection_uses_best_not_endpoint_or_strict(self):
        config, _, d, p, x = self.inputs()
        plan = _weighted_plan(config, ROOT, 'demo', 3)
        w = DevelopmentWorker(plan, d, p, 'demo', 23, x, vector_sha(x), root=ROOT,
                              checkpoint=Path(self.raw.name)/'best', objective_mode='weighted_violation')
        y = x.copy(); y[0] = (x[0] + w.bounds[0][1]) / 2
        # Use actual RF responses but arrange scores and strict status independently.
        summaries = iter([dict(strict_feasible=True, max_violation_db=0., sum_violation_db=0.),
                          dict(strict_feasible=False, max_violation_db=.1, sum_violation_db=.1)])
        def solver(callback, start, bounds, **kw):
            a, b = callback(x), callback(y)
            run = LocalRun(x.tolist(), float(a@a), x.tolist(), float(a@a), False, 1, 'fixture', 0, 2)
            return HybridResult([run], y.tolist(), float(b@b), 2, 'evaluation_budget_exhausted', 23, 3, 3, .1)
        # Each callback computes the same score once for best and once for solver.
        def score(*args):
            return next(evaluations_twice)
        evaluations_twice = iter([np.array([2.]), np.array([2.]), np.array([1.]), np.array([1.]), np.array([1.])])
        with patch('lpf.search._worker_next.hybrid_minimize', side_effect=solver), \
             patch('lpf.search._development_worker._weighted_residuals', side_effect=score), \
             patch('lpf.search._development_worker.summarize_mandatory', side_effect=lambda *a: next(summaries)), \
             patch('lpf.search._development_worker.rank_candidates', side_effect=AssertionError('must not rank')):
            result = w.run()
        self.assertEqual(result['steps'][0]['rf_best']['vector_sha256'], vector_sha(y))
        self.assertFalse(result['steps'][0]['rf_best']['strict_feasible'])
        self.assertEqual(result['selection']['ranked'][0]['vector_sha256'], vector_sha(y))
        self.assertEqual(result['terminal']['candidates'][0]['vector_sha256'], vector_sha(y))

    def test_cli(self):
        config, starts, _, _, _ = self.inputs()
        output = Path(self.raw.name)/'cli'
        process = subprocess.run([sys.executable, str(ROOT/'scripts/run_development_worker.py'),
                                  '--config', str(config), '--starts', str(starts), '--seed', '23',
                                  '--arm', 'demo', '--output', str(output), '--objective-mode',
                                  'weighted_violation', '--max-search-forwards', '2'],
                                 capture_output=True, text=True)
        self.assertEqual(process.returncode, 4, process.stderr)
        result = json.loads((output/'result.json').read_text())
        self.assertEqual(result['steps'][0]['solver_result']['maxiter'], 2)
        self.assertEqual(result['steps'][0]['solver_result']['max_evaluations'], 2)

    def test_equal_score_tie_and_optimizer_mismatch_stop(self):
        config, _, d, p, x = self.inputs()
        plan = _weighted_plan(config, ROOT, 'demo', 3)
        y = x.copy(); y[0] += .01
        first, second = sorted((x, y), key=vector_sha, reverse=True)
        def solver(callback, start, bounds, **kw):
            callback(first); callback(second)
            run = LocalRun(first.tolist(), 1., first.tolist(), 1., False, 1, 'fixture', 0, 2)
            return HybridResult([run], first.tolist(), 1., 2, 'evaluation_budget_exhausted', 23, 3, 3, .1)
        w = DevelopmentWorker(plan, d, p, 'demo', 23, x, vector_sha(x), root=ROOT,
                              checkpoint=Path(self.raw.name)/'ties', objective_mode='weighted_violation')
        with patch('lpf.search._worker_next.hybrid_minimize', side_effect=solver), \
             patch('lpf.search._development_worker._weighted_residuals', return_value=np.array([1.])):
            result = w.run()
        self.assertEqual(result['steps'][0]['rf_best']['vector_sha256'], vector_sha(second))
        self.assertEqual(vector_sha(result['steps'][0]['solver_result']['best_x']), vector_sha(first))
        w = DevelopmentWorker(plan, d, p, 'demo', 23, x, vector_sha(x), root=ROOT,
                              checkpoint=Path(self.raw.name)/'mismatch', objective_mode='weighted_violation')
        def bad(callback, start, bounds, **kw):
            out = solver(callback, start, bounds, **kw)
            out.best_x = second.tolist()  # not the first equal-score point retained by Hybrid
            return out
        with patch('lpf.search._worker_next.hybrid_minimize', side_effect=bad), \
             patch('lpf.search._development_worker._weighted_residuals', return_value=np.array([1.])):
            with self.assertRaisesRegex(ValueError, 'objective/vector mismatch'):
                w.run()

    def test_convergence_and_abnormal_no_best_stop(self):
        config, _, d, p, x = self.inputs()
        plan = _weighted_plan(config, ROOT, 'demo', 3)
        fixed = [[float(v), float(v)] for v in x]
        worker = DevelopmentWorker(plan, d, p, 'demo', 23, x, vector_sha(x), root=ROOT,
                                   checkpoint=Path(self.raw.name)/'fixed', search_bounds=fixed,
                                   objective_mode='weighted_violation')
        result = worker.run()
        self.assertEqual(result['status'], 'converged')
        self.assertEqual(result['steps'][0]['stop_reason'], 'all_coordinates_fixed')
        self.assertEqual(result['steps'][0]['forward_count'], 1)
        worker = DevelopmentWorker(plan, d, p, 'demo', 23, x, vector_sha(x), root=ROOT,
                                   checkpoint=Path(self.raw.name)/'no-best', objective_mode='weighted_violation')
        out = HybridResult([], None, None, 0, 'evaluation_budget_exhausted', 23, 3, 3, .1)
        with patch('lpf.search._worker_next.hybrid_minimize', return_value=out):
            with self.assertRaisesRegex(ValueError, 'No weighted best'):
                worker.run()
        self.assertFalse(list(worker.path.glob('*.json')))

    def test_invalid_budget_and_mode(self):
        config, starts, _, _, _ = self.inputs()
        for n in (0, -1, True, 2**63):
            with self.subTest(n=n), self.assertRaises(ValueError):
                _weighted_plan(config, ROOT, 'demo', n)
        with self.assertRaises(ValueError):
            run_development_worker(config, starts, 23, 'demo', Path(self.raw.name)/'bad', max_search_forwards=3)


if __name__ == '__main__':
    unittest.main()

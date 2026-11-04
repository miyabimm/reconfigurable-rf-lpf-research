import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from lpf.optimizers.pipeline import minimize_pipeline
from lpf.optimizers.hybrid import hybrid_minimize
from lpf.optimizers.slp import slp_minimize


def run(residuals, errors, bounds, **kwargs):
    options = dict(seed=7, sobol_m=1, max_evaluations=500,
                   hybrid_max_evaluations=40, hybrid_maxiter=30,
                   hybrid_max_restarts=0, restart_sigma=0.1,
                   slp_max_evaluations=80, slp_max_iterations=30,
                   max_slp_candidates=2)
    options.update(kwargs)
    return minimize_pipeline(residuals, errors, bounds, **options)


class PipelineTests(unittest.TestCase):
    def test_real_solvers_use_separate_objectives_and_improve(self):
        # Hybrid favors 0.1; signed minimax of x-1 and -x is at 0.5.
        with patch('lpf.optimizers.pipeline.hybrid_minimize', wraps=hybrid_minimize) as h, \
             patch('lpf.optimizers.pipeline.slp_minimize', wraps=slp_minimize) as s:
            result = run(lambda x: [x[0] - 0.1], lambda x: [x[0] - 1, -x[0]],
                         [(0, 1)], starts=[[0.1]], max_slp_candidates=1)
        self.assertTrue(all(c.kwargs['aggregation'] == 'sum' for c in h.call_args_list))
        self.assertEqual(s.call_args.kwargs['aggregation'], 'signed_max')
        self.assertNotIn('weights', s.call_args.kwargs)
        c = result['candidates'][result['selected'][0]]
        self.assertAlmostEqual(c['evaluation']['signed_max'], -0.4207400093, places=6)
        self.assertAlmostEqual(c['slp']['result']['signed_max'], -0.5, places=5)
        self.assertTrue(c['slp']['score_improved'])
        self.assertAlmostEqual(result['best']['x'][0], 0.5, places=5)
        self.assertEqual(result['starts'][0]['hybrid']['aggregation'], 'sum')
        self.assertLess(result['starts'][0]['hybrid']['best_fun'], 1e-12)

    def test_sobol_fixed_duplicates_and_seed(self):
        kw = dict(sobol_m=2, starts=[[0.25, 3], [0.2500000001, 3]])
        a = run(lambda x: [x[0]], lambda x: [x[0]], [(0, 1), (3, 3)], **kw)
        b = run(lambda x: [x[0]], lambda x: [x[0]], [(0, 1), (3, 3)], **kw)
        self.assertEqual([r['x'] for r in a['starts']], [r['x'] for r in b['starts']])
        self.assertEqual(a['starts'][1]['duplicate_of'], 0)
        self.assertEqual([r['sobol_index'] for r in a['starts'][2:]], list(range(4)))
        self.assertTrue(all(r['x'][1] == 3 for r in a['starts']))
        fixed = run(lambda x: [x[0]], lambda x: [x[0]], [(2, 2)], sobol_m=2)
        self.assertEqual([r['duplicate_of'] for r in fixed['starts']], [None, 0, 0, 0])
        with self.assertRaises(ValueError):
            run(lambda x: x, lambda x: x, [(0, 1)], starts=[[2]])

    def test_feasibility_precedes_better_signed_score(self):
        result = run(lambda x: [x[0]], lambda x: [x[0]], [(0, 1)],
                     starts=[[0], [0.9]], constraints=lambda x: [x[0] - 0.8],
                     max_slp_candidates=1)
        c = result['candidates'][result['selected'][0]]
        self.assertTrue(c['evaluation']['feasible'])
        self.assertGreaterEqual(c['evaluation']['signed_max'], 0.8)
        self.assertTrue(result['best']['feasible'])

    def test_multimodal_diversity_and_unconverged_preservation(self):
        result = run(lambda x: [(x[0] - 0.2) * (x[0] - 0.8)],
                     lambda x: [x[0] - 0.6, 0.4 - x[0]], [(0, 1)],
                     starts=[[0.2], [0.8]], max_slp_candidates=2,
                     slp_max_iterations=1, slp_max_evaluations=2)
        self.assertEqual(len(result['selected']), 2)
        selected = [result['candidates'][i] for i in result['selected']]
        self.assertNotEqual(selected[0]['x'], selected[1]['x'])
        for c in selected:
            self.assertFalse(c['slp']['result']['success'])
            self.assertIsNotNone(c['final'])
        self.assertFalse(result['best']['success'])

    def test_restart_and_weights_are_forwarded_only_to_hybrid(self):
        with patch('lpf.optimizers.pipeline.hybrid_minimize', wraps=hybrid_minimize) as h, \
             patch('lpf.optimizers.pipeline.slp_minimize', wraps=slp_minimize) as s:
            result = run(lambda x: [x[0], 1 - x[0]], lambda x: [x[0] - .3],
                         [(0, 1)], sobol_m=0, weights=[2, 1],
                         hybrid_max_restarts=1, hybrid_max_evaluations=100)
        self.assertEqual(h.call_args.kwargs['max_restarts'], 1)
        self.assertEqual(h.call_args.kwargs['weights'], [2, 1])
        self.assertEqual(len(result['starts'][0]['hybrid']['runs']), 2)
        self.assertNotIn('weights', s.call_args.kwargs)

    def test_budget_actual_callbacks_across_boundaries(self):
        for limit in range(0, 45):
            actual = {'residuals': 0, 'errors': 0, 'constraints': 0}
            def wrap(name, fun):
                def callback(x):
                    actual[name] += 1
                    return fun(x)
                return callback
            r = run(wrap('residuals', lambda x: [x[0] - .3]),
                    wrap('errors', lambda x: [x[0], -x[0]]), [(0, 1)],
                    constraints=wrap('constraints', lambda x: [x[0] - .2]),
                    max_evaluations=limit, hybrid_max_evaluations=5,
                    slp_max_evaluations=9)
            self.assertLessEqual(r['nfev'], limit)
            for name in actual:
                self.assertEqual(actual[name], sum(c[name] for c in r['counts'].values()))
            self.assertEqual(r['nfev'], sum(actual.values()))

    def test_invalid_candidates_and_slp_failure_preserve_prior(self):
        result = run(lambda x: [x[0]], lambda x: [float('nan')], [(0, 1)])
        self.assertIsNone(result['best'])
        self.assertFalse(result['selected'])
        self.assertTrue(all(c['evaluation_state'] == 'invalid_errors' for c in result['candidates']))
        calls = 0
        def errors(x):
            nonlocal calls
            calls += 1
            # selection evaluates all candidates; trigger invalid once SLP starts
            return [x[0]] if calls <= 2 else [float('nan')]
        result = run(lambda x: [x[0]], errors, [(0, 1)], sobol_m=0,
                     hybrid_max_evaluations=1, max_slp_candidates=1)
        c = result['candidates'][result['selected'][0]]
        self.assertEqual(c['slp_state'], 'invalid_errors')
        self.assertEqual(c['final']['origin'], 'before_slp')
        self.assertFalse(c['final']['success'])


if __name__ == '__main__':
    unittest.main()

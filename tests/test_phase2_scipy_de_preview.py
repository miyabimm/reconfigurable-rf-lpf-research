"""Issue #241: real public SciPy API, mocked RF only. No scientific budgets."""
import sys
from pathlib import Path
from dataclasses import replace
import unittest
from unittest.mock import patch

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from test_phase2_problem_seed import make
from lpf.phase2_models.evaluation_cost import EvaluationCost
from lpf.phase2_models.multistart import generate_starts
from lpf.phase2_models.optimizer_comparison import PhysicalComparison
from lpf.phase2_models.problem_seed import vector_fingerprint
from lpf.phase2_models.sampled_epigraph import SampledEpigraph
from lpf.phase2_models.scipy_de_preview import run_de_preview


def mock_il(evaluator, x):
    return np.choose(evaluator.role, [float(x[0]), 30., 31.])


class DEPreviewTests(unittest.TestCase):
    def setUp(self):
        p, self.x = make('RF-T008', 3)
        self.x[6] = 0.  # fixed nonadjacent coupling, not repaired by the generator
        self.p = SampledEpigraph(p.circuit, 2)
        self.patch = patch.object(type(self.p.evaluator), 'il', mock_il)
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def generate(self, meter=None, count=6):
        return generate_starts(self.p, self.x, seed=23, count=count, cost_meter=meter)

    def run_preview(self, **overrides):
        args = dict(initialize=self.generate, seed=241, maxiter=1,
                    max_frequency_samples=5600, max_proposals=200, max_wall_seconds=30.)
        args.update(overrides)
        self.comparison = PhysicalComparison(self.p.circuit, 2)
        return run_de_preview(self.comparison, **args)

    def test_population_prefix_fixed_coordinate_and_metering(self):
        legacy = self.generate(count=3)
        meter = EvaluationCost()
        expanded = self.generate(meter)
        self.assertEqual(legacy['starts'], expanded['starts'][:3])
        # Captured from main da24d404, not regenerated as the expectation.
        self.assertEqual([s['vector_sha256'] for s in legacy['starts']], [
            'b6a098b045772b02fee8ed619e5324481ed72cbcf3008cc522783df5009ba591',
            '2ada66b1b4fd8e42050cdd738f92dd60c795682ee3a4a484293be121a0a74268',
            '5ee144fcc21a1b4b3f16f87655201208648e8519d37f6fd4925934afe15c47a8'])
        self.assertEqual(expanded, self.generate())
        self.assertEqual(meter.RF_forward_calls, 6)
        self.assertEqual(meter.frequency_samples_requested, 336)
        self.assertEqual(meter.frequency_samples_completed, 336)
        self.assertEqual(len({s['vector_sha256'] for s in expanded['starts']}), 6)
        for s in expanded['starts']:
            self.assertEqual(s['vector_sha256'], vector_fingerprint(s['vector']))
            self.assertEqual(s['vector'][6], 0.)
            self.assertEqual(len(s['vector']), len(self.x))
            self.assertEqual(len(s['vector'][-12:]), 12)  # all six settings
            self.p.circuit.validate_components(s['vector'])

    def test_open_bound_spd_and_insufficient_population_fail_closed(self):
        self.x[3] = 0.
        with self.assertRaisesRegex(ValueError, 'open lower'):
            self.generate()
        self.x[3] = 1.
        with patch.object(type(self.p.circuit), 'validate_components', side_effect=ValueError(
                'Full inductance matrix is non-positive-definite or ill-conditioned')):
            meter = EvaluationCost()
            with self.assertRaises(ValueError):
                self.generate(meter)
            self.assertEqual(meter.spd_rejections, 1)
            self.assertEqual(meter.RF_forward_calls, 0)
        # Every Sobol point is identical in a fixed box: no regeneration/repair.
        fixed = tuple((float(v), float(v)) for v in self.x) + ((None, None),)
        with patch.object(self.p, 'box', replace(self.p.box, bounds=fixed, open_lower=())):
            with self.assertRaisesRegex(ValueError, 'Insufficient legal distinct starts: 1/6'):
                self.generate()

    def test_real_scipy_api_best_and_strict_boundary(self):
        r = self.run_preview()
        self.assertEqual(r['termination'], 'solver_returned')
        self.assertEqual(r['solver']['nit'], 1)
        self.assertTrue(r['best_observed']['score']['strict_feasible'])
        cost = r['evaluation_cost']
        self.assertEqual(cost['solver_objective_calls'], r['solver']['nfev'])
        self.assertEqual(cost['RF_forward_calls'] * 56, cost['frequency_samples_requested'])
        self.assertEqual(r['coarse2_equivalent'], cost['RF_forward_calls'])
        self.assertGreater(cost['cache_hits'], 0)
        self.assertGreater(cost['solver_constraint_calls'], cost['solver_objective_calls'])
        self.assertEqual(r['best_observed']['vector_sha256'],
                         vector_fingerprint(r['best_observed']['vector']))
        def near(evaluator, x):
            return np.choose(evaluator.role, [.1, np.nextafter(30., 0.), 31.])
        with patch.object(type(self.p.evaluator), 'il', near):
            r = self.run_preview()
        self.assertEqual(r['termination'], 'solver_returned')
        self.assertFalse(r['best_observed']['score']['strict_feasible'])
        self.assertEqual(r['solver']['nfev'], 0)  # Lampinen, not fabricated objective

    def test_budget_initialization_and_mid_solver_retains_best(self):
        initial = self.run_preview(max_frequency_samples=55)
        self.assertEqual(initial['termination'], 'budget_exhausted')
        self.assertEqual(initial['evaluation_cost']['RF_forward_calls'], 0)
        self.assertIsNone(initial['best_observed'])
        partial = self.run_preview(max_frequency_samples=56)
        self.assertEqual(partial['termination'], 'budget_exhausted')
        self.assertIsNotNone(partial['best_observed'])
        self.assertEqual(partial['evaluation_cost']['RF_forward_calls'], 1)
        r = self.run_preview(max_frequency_samples=6*56 + 56 + 20)
        self.assertEqual(r['termination'], 'budget_exhausted')
        self.assertEqual(r['evaluation_cost']['frequency_samples_requested'], 7*56)
        self.assertIsNotNone(r['best_observed'])
        self.assertIsNone(r['solver'])
        self.assertEqual(r['final_reevaluation'], 'not_run')

    def test_failure_interrupt_and_proposal_limit_preserve_meter(self):
        calls = 0
        def fail(evaluator, x):
            nonlocal calls
            calls += 1
            if calls == 8:
                raise RuntimeError('mock forward failed')
            return mock_il(evaluator, x)
        with patch.object(type(self.p.evaluator), 'il', fail):
            r = self.run_preview()
        self.assertEqual(r['termination'], 'failed')
        self.assertIn('mock forward failed', r['error'])
        self.assertIsNotNone(r['best_observed'])
        self.assertEqual(r['evaluation_cost']['forward_failures'], 1)
        self.assertEqual(r['evaluation_cost']['frequency_samples_requested'], 8*56)
        self.assertEqual(r['evaluation_cost']['frequency_samples_completed'], 7*56)
        r = self.run_preview(max_proposals=1)
        self.assertEqual(r['termination'], 'proposal_limit')
        self.assertEqual(r['proposal_requests'], 1)
        self.assertIsNotNone(r['best_observed'])
        def interrupt(meter):
            self.generate(meter)
            raise KeyboardInterrupt()
        r = self.run_preview(initialize=interrupt)
        self.assertEqual(r['termination'], 'interrupted')
        self.assertEqual(r['evaluation_cost']['RF_forward_calls'], 6)

    def test_cooperative_wall_limit_and_role_rejection(self):
        clock = [100.]
        def initialize(meter):
            result = self.generate(meter)
            clock[0] = 200.
            return result
        with patch('lpf.phase2_models.scipy_de_preview.time.perf_counter',
                   side_effect=lambda: clock[0]):
            r = self.run_preview(initialize=initialize, max_wall_seconds=1.)
        self.assertEqual(r['termination'], 'wall_limit')
        self.assertIsNotNone(r['best_observed'])
        self.assertEqual(r['evaluation_cost']['wall_seconds'], 100.)  # not double-timed
        with patch.object(type(self.p.circuit), 'validate_components',
                          return_value={'connection_role_evidence_incomplete': True}):
            r = self.run_preview()
        self.assertEqual(r['termination'], 'physical_rejected')
        self.assertEqual(r['evaluation_cost']['role_rejections'], 1)
        self.assertEqual(r['evaluation_cost']['RF_forward_calls'], 0)

    def test_past_rejection_does_not_mask_unrelated_solver_exception(self):
        def initialize(meter):
            invalid = self.x.copy()
            invalid[3] = 0.
            with self.assertRaises(ValueError):
                self.comparison.evaluate(invalid)  # genuine rejected proposal
            return self.generate(meter)

        with patch('lpf.phase2_models.scipy_de_preview.differential_evolution',
                   side_effect=RuntimeError('unrelated solver failure')):
            r = self.run_preview(initialize=initialize)
        self.assertEqual(r['termination'], 'failed')
        self.assertIn('unrelated solver failure', r['error'])
        self.assertEqual(r['evaluation_cost']['box_rejections'], 1)
        self.assertEqual(r['evaluation_cost']['RF_forward_calls'], 6)
        self.assertIsNotNone(r['best_observed'])

    def test_invalid_population_and_solver_proposal_are_not_rf_scores(self):
        def bad(meter):
            generated = self.generate(meter)
            x = generated['starts'][0]['vector']
            x[3] = 0.
            generated['starts'][0]['vector_sha256'] = vector_fingerprint(x)
            return generated
        r = self.run_preview(initialize=bad)
        self.assertEqual(r['termination'], 'physical_rejected')
        self.assertEqual(r['evaluation_cost']['RF_forward_calls'], 6)
        self.assertIsNotNone(r['best_observed'])  # legitimate initialization observations retained
        def solver(objective, bounds, **kw):
            good = kw['init'][0]
            kw['constraints'][0].fun(good)
            bad = good.copy()
            bad[3] = 0.
            kw['constraints'][0].fun(bad)
            self.fail('Invalid physical proposal must abort')
        with patch('lpf.phase2_models.scipy_de_preview.differential_evolution', solver):
            r = self.run_preview()
        self.assertEqual(r['termination'], 'physical_rejected')
        self.assertEqual(r['evaluation_cost']['box_rejections'], 1)
        self.assertIsNotNone(r['best_observed'])
        self.assertEqual(r['evaluation_cost']['RF_forward_calls'], 7)


if __name__ == '__main__':
    unittest.main()

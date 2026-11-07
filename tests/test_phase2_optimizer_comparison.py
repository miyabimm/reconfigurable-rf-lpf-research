"""Cost/strict-ranking contract; no real RF optimization or new EXP."""
import sys
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np
from scipy.optimize import differential_evolution, NonlinearConstraint

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from test_phase2_problem_seed import make
from lpf.phase2_models.evaluation_cost import EvaluationCost
from lpf.phase2_models.optimizer_comparison import PhysicalComparison, sampled_score
from lpf.phase2_models.staged_optimization import scipy_slsqp_stage


class ComparisonTests(unittest.TestCase):
    def test_slsqp_counts_forward_not_objective_and_does_not_cache(self):
        p, x = make('RF-T008', 4)
        for coordinates in ('physical', 'normalized'):
            meter = EvaluationCost()
            vector = np.r_[x, 1.]
            original_evaluator, original_circuit = p.evaluator, p.circuit
            if coordinates == 'normalized':
                from lpf.phase2_models.normalized_epigraph import NormalizedEpigraph
                baseline = NormalizedEpigraph(p)
                expected = baseline.residuals(baseline.to_normalized(vector))
            else:
                expected = p.residuals(vector)
            def solver(objective, initial, **kwargs):
                self.assertEqual(kwargs['method'], 'SLSQP')
                self.assertEqual(kwargs['options'], {'maxiter': 240})
                objective(initial)
                objective(initial)
                for _ in range(3):
                    np.testing.assert_array_equal(kwargs['constraints'][0]['fun'](initial), expected)
                return SimpleNamespace(x=initial, success=True, status=0,
                                       message='mock', nit=1, nfev=2)
            with patch('lpf.phase2_models.staged_optimization.minimize', side_effect=solver):
                result, state = scipy_slsqp_stage(p, vector, 240, None,
                    coordinates=coordinates, cost_meter=meter)
            np.testing.assert_allclose(result, vector, rtol=0, atol=1e-15)
            cost = state['evaluation_cost']
            self.assertEqual(cost['solver_objective_calls'], 2)
            self.assertEqual(cost['solver_constraint_calls'], 3)
            self.assertEqual(cost['RF_forward_calls'], 3)
            self.assertEqual(cost['frequency_samples_requested'], 84)
            self.assertEqual(cost['frequency_samples_completed'], 84)
            self.assertEqual(cost['cache_hits'], 0)
            if coordinates == 'physical':
                self.assertEqual(cost['component_checks'], 0)
            else:
                self.assertGreater(cost['component_checks'], 0)
            self.assertEqual(state['nfev'], 2)
            self.assertGreaterEqual(cost['wall_seconds'], 0.)
            self.assertGreaterEqual(cost['cpu_seconds'], 0.)
            self.assertIs(p.evaluator, original_evaluator)
            self.assertIs(p.circuit, original_circuit)

    def test_sample_budget_rejects_before_forward_and_counts_failed_requests(self):
        from lpf.phase2_models.evaluation_cost import SampleBudgetExceeded, SampleBudgetCost
        evaluator = SimpleNamespace(f=np.arange(3), il=lambda x: x)
        meter = SampleBudgetCost(6)
        meter.forward(evaluator, 1)
        evaluator.il = lambda x: (_ for _ in ()).throw(ValueError('forward failed'))
        with self.assertRaises(ValueError):
            meter.forward(evaluator, 2)
        with self.assertRaises(SampleBudgetExceeded):
            meter.forward(evaluator, 3)
        self.assertEqual(meter.frequency_samples_requested, 6)
        self.assertEqual(meter.frequency_samples_completed, 3)
        self.assertEqual(meter.RF_forward_calls, 2)
        self.assertEqual(meter.forward_failures, 1)
        for invalid in (-1, 1.5, True):
            with self.assertRaises(ValueError):
                SampleBudgetCost(invalid)


    def test_strict_no_tolerance_and_lexicographic_order(self):
        role = np.array([0, 0, 1, 2])
        good = sampled_score(np.array([.2, .3, 30., 35.]), role, 30.)
        near = sampled_score(np.array([.01, .02, np.nextafter(30., 0), 35.]), role, 30.)
        self.assertTrue(good.strict_feasible)
        self.assertFalse(near.strict_feasible)
        self.assertLess(good.rank_key(), near.rank_key())
        # Same maximum violation: sum then IL break ties.
        a = sampled_score(np.array([.2, .2, 29., 30.]), role, 30.)
        b = sampled_score(np.array([.01, .01, 29., 29.5]), role, 30.)
        self.assertLess(a.rank_key(), b.rank_key())
        self.assertEqual(a.max_violation_db, 1.)
        self.assertEqual(b.sum_violation_db, 1.5)
        for bad in (np.array([.2, np.nan, 30., 35.]), np.ones(3)):
            with self.assertRaises(ValueError):
                sampled_score(bad, role, 30.)

    def test_forward_only_grid_cost_and_rejected_physical_points(self):
        for points, samples in ((2, 56), (3, 84), (17, 476)):
            p, x = make('RF-T008', 4)
            comparison = PhysicalComparison(p.circuit, points, cache=True)
            raw = p.circuit.forward_evaluator(points).il(x)
            score = comparison.evaluate(x)
            self.assertEqual(score.worst_il_db, max(raw[comparison.evaluator.role == 0]))
            self.assertEqual(comparison.cost.RF_forward_calls, 1)
            self.assertEqual(comparison.cost.frequency_samples_completed, samples)
            comparison.evaluate(x.copy())
            self.assertEqual(comparison.cost.RF_forward_calls, 1)
            self.assertEqual(comparison.cost.cache_hits, 1)
            bad = x.copy()
            bad[4] = 0.  # excluded open GJM lower endpoint; never repair
            with self.assertRaises(ValueError):
                comparison.evaluate(bad)
            self.assertEqual(bad[4], 0.)
            self.assertEqual(comparison.cost.box_rejections, 1)
            self.assertEqual(comparison.cost.RF_forward_calls, 1)
            with self.assertRaises(ValueError):
                comparison.evaluate(np.r_[x, 1.])  # global API has no epigraph

    def test_failure_counters_survive_without_repair(self):
        from lpf.rf_core.numerical_diagnostics import CircuitNumericalError
        p, x = make('RF-T008', 4)
        comparison = PhysicalComparison(p.circuit, 2)
        with patch.object(type(p.circuit), 'validate_components',
                          side_effect=ValueError('Full inductance matrix is non-positive-definite or ill-conditioned')):
            with self.assertRaises(ValueError):
                comparison.evaluate(x)
        self.assertEqual(comparison.cost.component_rejections, 1)
        self.assertEqual(comparison.cost.spd_rejections, 1)
        self.assertEqual(comparison.cost.RF_forward_calls, 0)
        with patch.object(type(comparison.evaluator), 'il',
                          side_effect=CircuitNumericalError('mutual_not_spd', 'bad SPD')):
            with self.assertRaises(CircuitNumericalError):
                comparison.evaluate(x)
        self.assertEqual(comparison.cost.RF_forward_calls, 1)
        self.assertEqual(comparison.cost.forward_failures, 1)
        self.assertEqual(comparison.cost.frequency_samples_completed, 0)
        self.assertEqual(comparison.cost.frequency_samples_requested, 56)
        self.assertEqual(comparison.cost.spd_rejections, 2)
        self.assertEqual(comparison.cost.cache_hits, 0)

    def test_no_cache_and_role_rejection(self):
        p, x = make('RF-T008', 4)
        comparison = PhysicalComparison(p.circuit, 2)
        comparison.evaluate(x)
        comparison.evaluate(x)
        self.assertEqual(comparison.cost.RF_forward_calls, 2)
        self.assertEqual(comparison.cost.cache_hits, 0)
        with patch.object(type(p.circuit), 'validate_components',
                          return_value={'connection_role_evidence_incomplete': True}):
            with self.assertRaises(ValueError):
                comparison.evaluate(x)
        self.assertEqual(comparison.cost.role_rejections, 1)
        self.assertEqual(comparison.cost.RF_forward_calls, 2)

    def test_slsqp_failure_retains_external_meter(self):
        from lpf.rf_core.numerical_diagnostics import CircuitNumericalError
        p, x = make('RF-T008', 4)
        meter = EvaluationCost()
        def solver(objective, initial, **kwargs):
            return kwargs['constraints'][0]['fun'](initial)
        with patch('lpf.phase2_models.staged_optimization.minimize', side_effect=solver), \
             patch.object(type(p.evaluator), 'il',
                          side_effect=CircuitNumericalError('mutual_not_spd', 'bad SPD')):
            with self.assertRaises(CircuitNumericalError):
                scipy_slsqp_stage(p, np.r_[x, 1.], 240, None, cost_meter=meter)
        self.assertEqual(meter.RF_forward_calls, 1)
        self.assertEqual(meter.spd_rejections, 1)
        self.assertEqual(meter.solver_constraint_calls, 1)
        self.assertGreaterEqual(meter.wall_seconds, 0.)

    def test_scipy_de_nonlinear_constraint_on_analytic_mock_only(self):
        # API conformance, not an RF benchmark; budget/population below are test fixtures.
        calls = {'objective': 0, 'constraint': 0}
        def objective(x):
            calls['objective'] += 1
            return float(x[0] ** 2)
        def residual(x):
            calls['constraint'] += 1
            return np.array([x[0] - .5])
        result = differential_evolution(objective, [(0., 1.)],
            constraints=(NonlinearConstraint(residual, 0., np.inf),),
            init=np.array([[.1], [.2], [.4], [.6], [.8], [.9]]),
            maxiter=1, polish=False, rng=np.random.default_rng(239), workers=1)
        self.assertGreaterEqual(result.x[0], .5)
        self.assertEqual(result.nfev, calls['objective'])
        self.assertGreater(calls['constraint'], result.nfev)
        self.assertEqual(result.x.shape, (1,))


if __name__ == '__main__':
    unittest.main()

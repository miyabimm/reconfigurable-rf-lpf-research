"""RF adapter contract; fixture/mock tests, not an RF optimization experiment."""
import sys
from pathlib import Path
import unittest
from unittest.mock import patch

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from test_phase2_problem_seed import make
from lpf.optimizers.pipeline import minimize_pipeline
from lpf.phase2_models.evaluation_cost import SampleBudgetCost, SampleBudgetExceeded
from lpf.phase2_models.rf_pipeline_adapter import RFPipelineAdapter


class RFPipelineAdapterTests(unittest.TestCase):
    def setUp(self):
        p, self.x = make('RF-T008', 4)
        self.circuit = p.circuit
        self.a = RFPipelineAdapter(self.circuit, 2)

    def mock_il(self, stop=30.):
        return np.where(self.a.evaluator.role == 0, .4, stop)

    def test_grid_and_real_forward_wiring(self):
        e = self.a.evaluator
        self.assertEqual(set(e.setting), set(range(6)))
        self.assertEqual(set(e.segment), set(range(28)))
        self.assertTrue(all(sum(e.segment == i) == 2 for i in range(28)))
        raw = e.il(self.x)  # limited, read-only fixture forward, not optimization
        np.testing.assert_allclose(self.a.errors(self.x), raw[e.role == 0])
        self.assertEqual(self.a.cost.RF_forward_calls, 1)
        self.assertEqual(self.a.cost.frequency_samples_requested, 56)
        self.assertEqual(self.a.cost.frequency_samples_completed, 56)

    def test_objectives_constraints_and_strict_boundary(self):
        il = self.mock_il(np.nextafter(30., 0.))
        with patch.object(type(self.a.evaluator), 'il', return_value=il):
            r = self.a.residuals(self.x)
            errors = self.a.errors(self.x)
            g = self.a.constraints(self.x)
            verdict = self.a.assess(self.x)
        self.assertEqual(len(errors), 28)
        self.assertEqual(len(g), 28)
        np.testing.assert_array_equal(r[:len(errors)], errors)
        np.testing.assert_array_equal(r[len(errors):], np.maximum(0., -g))
        self.assertTrue(np.all(g < 0))
        self.assertFalse(verdict['strict_finite_grid_feasible'])
        self.assertTrue(verdict['candidate_promotion_blocked'])
        self.assertEqual(verdict['dense_rf'], 'not_run')
        with patch.object(type(self.a.evaluator), 'il', return_value=self.mock_il(30.)):
            verdict = self.a.assess(self.x)
        self.assertTrue(verdict['strict_finite_grid_feasible'])
        self.assertTrue(verdict['candidate_promotion_blocked'])
        self.assertEqual(verdict['independent_mna'], 'not_run')

    def test_mock_pipeline_uses_callbacks_and_does_not_promote(self):
        # All-fixed physical fixture box ensures the generic Sobol points are
        # identical and lawful; real numerical pipeline, mocked RF forward.
        fixed = [(float(v), float(v)) for v in self.x]
        with patch.object(type(self.a.evaluator), 'il', return_value=self.mock_il(30.)):
            result = minimize_pipeline(self.a.residuals, self.a.errors, fixed,
                constraints=self.a.constraints, seed=23, sobol_m=0,
                max_evaluations=20, hybrid_max_evaluations=2,
                hybrid_maxiter=1, hybrid_max_restarts=0, restart_sigma=.1,
                slp_max_evaluations=4, slp_max_iterations=1, max_slp_candidates=1)
            self.assertEqual(result['starts'][0]['hybrid']['aggregation'], 'sum')
            candidate = result['candidates'][result['selected'][0]]
            self.assertEqual(candidate['slp']['aggregation'], 'signed_max')
            self.assertTrue(self.a.assess(result['best']['x'])['candidate_promotion_blocked'])
        self.assertEqual(self.a.cost.RF_forward_calls, result['nfev'] + 1)
        self.assertEqual(self.a.cost.frequency_samples_requested, 56 * (result['nfev'] + 1))

    def test_solver_tolerance_never_becomes_strict_rf_pass(self):
        fixed = [(float(v), float(v)) for v in self.x]
        il = self.mock_il(np.nextafter(30., 0.))
        with patch.object(type(self.a.evaluator), 'il', return_value=il):
            result = minimize_pipeline(self.a.residuals, self.a.errors, fixed,
                constraints=self.a.constraints, seed=23, sobol_m=0,
                max_evaluations=20, hybrid_max_evaluations=2,
                hybrid_maxiter=1, hybrid_max_restarts=0, restart_sigma=.1,
                slp_max_evaluations=4, slp_max_iterations=1, max_slp_candidates=1)
            self.assertTrue(result['best']['feasible'])  # numerical tolerance only
            self.assertFalse(self.a.assess(result['best']['x'])['strict_finite_grid_feasible'])

    def test_rejects_invalid_box_spd_role_and_keeps_failure_cost(self):
        bad = self.x.copy(); bad[4] = 0.
        with self.assertRaises(ValueError):
            self.a.errors(bad)
        with self.assertRaises(ValueError):
            self.a.errors(np.r_[self.x, 0.])
        with patch.object(type(self.circuit), 'validate_components',
                side_effect=ValueError('Full inductance matrix is non-positive-definite or ill-conditioned')):
            with self.assertRaises(ValueError):
                self.a.errors(self.x)
        self.assertEqual(self.a.cost.spd_rejections, 1)
        with patch.object(type(self.circuit), 'validate_components',
                          return_value={'connection_role_evidence_incomplete': True}):
            with self.assertRaises(ValueError):
                self.a.errors(self.x)
        self.assertEqual(self.a.cost.role_rejections, 1)
        self.assertEqual(self.a.cost.RF_forward_calls, 0)
        with patch.object(type(self.a.evaluator), 'il', side_effect=ValueError('failure')):
            with self.assertRaises(ValueError):
                self.a.errors(self.x)
        self.assertEqual(self.a.cost.forward_failures, 1)
        self.assertEqual(self.a.cost.frequency_samples_requested, 56)
        self.assertEqual(self.a.cost.frequency_samples_completed, 0)
        with patch.object(type(self.a.evaluator), 'il', return_value=np.full(56, np.nan)):
            with self.assertRaises(ValueError):
                self.a.assess(self.x)

    def test_pipeline_exception_propagates_with_meter_not_a_success(self):
        fixed = [(float(v), float(v)) for v in self.x]
        meter = SampleBudgetCost(112)
        a = RFPipelineAdapter(self.circuit, 2, cost_meter=meter)
        with patch.object(type(a.evaluator), 'il',
                          side_effect=[self.mock_il(30.), ValueError('selection failed')]):
            with self.assertRaisesRegex(ValueError, 'selection failed'):
                minimize_pipeline(a.residuals, a.errors, fixed,
                    constraints=a.constraints, seed=23, sobol_m=0,
                    max_evaluations=20, hybrid_max_evaluations=2,
                    hybrid_maxiter=1, hybrid_max_restarts=0, restart_sigma=.1,
                    slp_max_evaluations=4, slp_max_iterations=1, max_slp_candidates=1)
        self.assertEqual(meter.frequency_samples_requested, 112)
        self.assertEqual(meter.frequency_samples_completed, 56)
        self.assertEqual(meter.forward_failures, 1)

    def test_exploratory_absence_and_budget(self):
        meter = SampleBudgetCost(56)
        a = RFPipelineAdapter(self.circuit, 2, cost_meter=meter, for_exploration=True)
        x = self.x.copy(); x[4] = 0.
        with patch.object(type(a.evaluator), 'il', return_value=self.mock_il(30.)):
            verdict = a.assess(x)
            self.assertFalse(verdict['strict_finite_grid_feasible'])
            self.assertTrue(verdict['candidate_promotion_blocked'])
            with self.assertRaises(SampleBudgetExceeded):
                a.errors(x)
        self.assertEqual(meter.frequency_samples_requested, 56)
        p, _ = make('RF-T005', 4)
        with self.assertRaises(ValueError):
            RFPipelineAdapter(p.circuit, 2)


if __name__ == '__main__':
    unittest.main()

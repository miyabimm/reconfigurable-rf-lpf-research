"""C2 orchestration uses only synthetic callbacks, never runs SLSQP."""
import copy
import json
import sys
from pathlib import Path
import unittest
from unittest.mock import patch
from types import SimpleNamespace

import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from test_phase2_problem_seed import make, seed
from lpf.phase2_models.candidate_records import record_candidate, recheck_record, pareto_report
from lpf.phase2_models.staged_optimization import run_c1_staged, scipy_slsqp_stage


def status(code):
    return {"success": code == 0, "status": code, "message": {
        0: "success", 4: "incompatible inequalities", 8: "line search",
        9: "Iteration limit reached"}[code], "nit": 4, "nfev": 12}


class StageTests(unittest.TestCase):
    def setUp(self):
        self.p, x = make("RF-T008", 4)
        self.seed = seed(self.p, x)

    def run_codes(self, codes, *, mutate=None):
        calls = []
        def callback(problem, x, maxiter, target):
            self.assertIsNone(target)
            calls.append((problem.points_per_interval, maxiter, x.copy()))
            if mutate:
                x = mutate(len(calls), x)
            return x, status(codes[len(calls)-1])
        record = run_c1_staged(self.p.circuit, self.seed, coarse_points=1,
                               fine_points=2, optimize_stage=callback)
        return record, calls

    def test_exchange_extras_apply_to_both_grids_and_warm_t_is_preserved(self):
        calls = []
        warm = np.asarray(self.seed['vector'], float).copy()
        warm[-1] += 0.1
        def callback(problem, x, maxiter, target):
            calls.append((problem, x.copy()))
            return x, status(0)
        result = run_c1_staged(self.p.circuit, self.seed, coarse_points=1,
            fine_points=2, optimize_stage=callback, warm_start_vector=warm,
            extra_frequencies=((0, 670.5),))
        self.assertEqual(result['numerical_state'], 'converged')
        np.testing.assert_array_equal(calls[0][1], warm)
        for problem, _ in calls:
            self.assertIn(670.5, problem.evaluator.f[problem.evaluator.segment == 0])
        self.assertEqual(result['frequency_exchange_input']['warm_start_vector'], warm.tolist())
        candidate = record_candidate('exchange-test', self.p.circuit, warm[:-1], staged_record=result)
        self.assertEqual(candidate.as_dict()['numerical']['state'], 'converged')
        self.assertEqual(recheck_record(candidate).as_dict()['numerical']['state'], 'converged')

    def test_search_guard_is_opt_in_and_propagated_to_both_stages(self):
        seen = []
        def callback(problem, vector, maxiter, target):
            seen.append((problem.mandatory_stop_db, problem.search_stop_db))
            return vector, status(0)
        result = run_c1_staged(self.p.circuit, self.seed, coarse_points=1,
                               fine_points=2, optimize_stage=callback, search_guard=True,
                               source_provenance={'kind': 'synthetic', 'git_head': 'a' * 40,
                                                  'dirty_patch_sha256': 'b' * 64, 'input_source_sha256': 'c' * 64})
        self.assertEqual(seen, [(30., 30.005), (30., 30.005)])
        self.assertEqual(result['search_guard']['mandatory_stop_db'], 30.)
        self.assertEqual(result['search_guard']['search_stop_db'], 30.005)
        candidate = record_candidate('guarded', self.p.circuit,
                                     result['stage_calls'][-1]['output_vector'][:-1], staged_record=result)
        self.assertEqual(recheck_record(candidate).as_dict()['numerical']['state'], 'converged')
        for row in result['stage_calls']:
            observed = row['observation']['sampled_rf']
            residual = np.asarray(observed['residuals_db'])
            problem = __import__('lpf.phase2_models.sampled_epigraph', fromlist=['SampledEpigraph']).SampledEpigraph(
                self.p.circuit, row['grid']['points_per_interval'], search_guard=True)
            self.assertAlmostEqual(observed['min_h2_db'],
                                   30.005 + min(residual[problem.evaluator.role == 1]))
        with self.assertRaises(TypeError):
            run_c1_staged(self.p.circuit, self.seed, coarse_points=1, fine_points=2,
                          optimize_stage=callback, search_guard='yes')
        with self.assertRaisesRegex(ValueError, 'source provenance'):
            run_c1_staged(self.p.circuit, self.seed, coarse_points=1, fine_points=2,
                          optimize_stage=callback, search_guard=True)

    def test_success_and_separate_gates(self):
        result, calls = self.run_codes([0, 0])
        self.assertEqual([c[1] for c in calls], [240, 120])
        self.assertEqual(result["numerical_state"], "converged")
        self.assertEqual(result["iteration_policy_id"], "slsqp-staged-v2")
        self.assertEqual(result["validation"]["independent_mna"], "not_run")
        self.assertEqual(result["validation"]["dense_rf"], "not_run")
        self.assertTrue(result["candidate_promotion_blocked"])
        self.assertFalse(result["rf_compliance_certified"])
        for i, stage in enumerate(result["stage_calls"]):
            self.assertEqual(stage["status"], status(0))
            self.assertEqual(stage["warm_start_source"], "seed" if i == 0 else "stage_call_0")
            self.assertEqual(stage["observation"]["sampled_rf"]["state"], "observed")
            self.assertEqual(stage["observation"]["component_policy"]["state"], "pass")
        self.assertEqual(len(result["stage_calls"][1]["observation"]["sampled_rf"]["residuals_db"]), 56)
        json.dumps(result, allow_nan=False)

    def test_shared_sample_ceiling_includes_observation_and_stops_recovery(self):
        from lpf.phase2_models.evaluation_cost import SampleBudgetCost
        meter = SampleBudgetCost(140)
        snapshots = []
        def callback(problem, x, maxiter, target):
            problem.residuals(x)
            return x, status(4 if maxiter == 240 else 0)
        result = run_c1_staged(self.p.circuit, self.seed, coarse_points=1,
            fine_points=2, optimize_stage=callback, cost_meter=meter,
            record_sink=snapshots.append)
        self.assertEqual(result['numerical_state'], 'budget_exhausted')
        self.assertEqual(len(result['stage_calls']), 2)  # no v2 restart
        self.assertEqual(result['stage_calls'][1]['status']['status'], 0)
        self.assertEqual(result['exception']['type'], 'SampleBudgetExceeded')
        self.assertEqual(result['evaluation_cost']['frequency_samples_requested'], 140)
        self.assertEqual(result['evaluation_cost']['RF_forward_calls'], 4)
        self.assertEqual(result['stage_calls'][0]['evaluation_cost']['frequency_samples_requested'], 56)
        self.assertEqual(result['stage_calls'][1]['evaluation_cost']['frequency_samples_requested'], 56)
        self.assertEqual(snapshots[-1], result)
        json.dumps(result, allow_nan=False)

    def test_scipy_sample_exhaustion_is_not_solver_status_and_is_durable(self):
        from lpf.phase2_models.evaluation_cost import SampleBudgetCost
        meter = SampleBudgetCost(56)  # seed replay + exactly one coarse forward
        snapshots = []
        def solver(objective, x, **kwargs):
            objective(x)
            residuals = kwargs['constraints'][0]['fun']
            residuals(x)
            residuals(x)  # reject before entering forward
            self.fail('budget exception must escape SciPy')
        with patch('lpf.phase2_models.staged_optimization.minimize', side_effect=solver):
            result = run_c1_staged(self.p.circuit, self.seed, coarse_points=1,
                fine_points=2, cost_meter=meter, record_sink=snapshots.append)
        self.assertEqual(result['numerical_state'], 'budget_exhausted')
        self.assertEqual(len(result['stage_calls']), 1)
        self.assertIsNone(result['stage_calls'][0]['status'])
        self.assertEqual(meter.frequency_samples_requested, 56)
        self.assertEqual(meter.solver_constraint_calls, 2)
        self.assertEqual(meter.RF_forward_calls, 2)
        self.assertEqual(snapshots[-1]['numerical_state'], 'budget_exhausted')

    def test_normalized_partial_keeps_solver_meter_and_sample_ceiling(self):
        from functools import partial
        from lpf.phase2_models.evaluation_cost import SampleBudgetCost
        meter = SampleBudgetCost(56)
        def solver(objective, x, **kwargs):
            objective(x)
            residuals = kwargs['constraints'][0]['fun']
            residuals(x)
            residuals(x)  # same frozen ceiling, no hidden forward
            self.fail('must stop at sample ceiling')
        with patch('lpf.phase2_models.staged_optimization.minimize', side_effect=solver):
            result = run_c1_staged(self.p.circuit, self.seed, coarse_points=1,
                fine_points=2, cost_meter=meter,
                optimize_stage=partial(scipy_slsqp_stage, coordinates='normalized'))
        self.assertEqual(result['numerical_state'], 'budget_exhausted')
        self.assertEqual(meter.frequency_samples_requested, 56)
        self.assertEqual(meter.RF_forward_calls, 2)
        self.assertEqual(meter.solver_objective_calls, 1)
        self.assertEqual(meter.solver_constraint_calls, 2)
        self.assertGreater(meter.cpu_seconds, 0)

    def test_shared_cost_preserves_v2_recovery_and_stage_deltas(self):
        from lpf.phase2_models.evaluation_cost import SampleBudgetCost
        meter = SampleBudgetCost(1000)
        codes = iter([9, 0, 0, 0])
        def callback(problem, x, maxiter, target):
            problem.residuals(x)
            return x, status(next(codes))
        result = run_c1_staged(self.p.circuit, self.seed, coarse_points=1,
            fine_points=2, optimize_stage=callback, cost_meter=meter)
        self.assertEqual(result['numerical_state'], 'converged')
        self.assertEqual([s['maxiter'] for s in result['stage_calls']], [240, 120, 500, 280])
        self.assertEqual(meter.frequency_samples_requested, 28 + 2 * (28 + 56 + 28 + 56))
        self.assertEqual(result['evaluation_cost'], meter.snapshot())

    def test_nonlimit_restart_and_unconverged(self):
        for code in (4, 8):
            result, calls = self.run_codes([code, 0, 8, 0])
            self.assertEqual([v[1] for v in calls], [240, 120, 240, 120])
            self.assertEqual(result["controller"]["recovery_cause"], "nonlimit_feasible_restart")
            self.assertEqual([a["converged"] for a in result["attempts"]], [False, False])
            self.assertEqual(result["numerical_state"], "not_converged")
            for previous, following in zip(calls, calls[1:]):
                np.testing.assert_array_equal(previous[2], following[2])

    def test_iteration_limit_rescue_and_bounds(self):
        for codes, budgets, cause in (([9, 0, 9, 9], [240, 120, 500, 280], "iteration_rescue_both"),
                                      ([0, 9, 0], [240, 120, 280], "iteration_rescue_fine"),
                                      ([4, 9], [240, 120], None)):
            result, calls = self.run_codes(codes)
            self.assertEqual([v[1] for v in calls], budgets)
            self.assertEqual(result["controller"]["recovery_cause"], cause)
            self.assertLessEqual(len(calls), 4)
            self.assertEqual(result["stage_calls"][0]["status"]["status"], codes[0])

    def test_exception_retains_prior_calls_and_no_retry(self):
        calls = []
        def callback(problem, x, maxiter, target):
            calls.append(1)
            if len(calls) == 3:
                raise FloatingPointError("broken evaluator")
            return x, status([4, 0][len(calls)-1])
        result = run_c1_staged(self.p.circuit, self.seed, coarse_points=1, fine_points=2,
                               optimize_stage=callback)
        self.assertEqual(len(calls), 3)
        self.assertEqual(result["numerical_state"], "failed")
        self.assertEqual(result["exception"]["type"], "FloatingPointError")
        self.assertEqual(result["stage_calls"][0]["status"]["status"], 4)
        self.assertEqual(result["stage_calls"][1]["status"]["status"], 0)
        self.assertEqual(result["stage_calls"][2]["exception"]["message"], "broken evaluator")
        self.assertEqual(result["attempts"][0]["stage_call_indices"], [0, 1])
        self.assertEqual(result["attempts"][1]["state"], "interrupted")
        self.assertTrue(result["candidate_promotion_blocked"])

    def test_open_bound_component_reject_even_when_converged(self):
        def mutate(i, x):
            x[4] = 0.0
            return x
        result, _ = self.run_codes([0, 0], mutate=mutate)
        self.assertEqual(result["numerical_state"], "converged")
        observed = result["stage_calls"][-1]["observation"]
        self.assertEqual(observed["box"]["state"], "fail")
        self.assertEqual(observed["component_policy"]["state"], "fail")
        self.assertTrue(result["candidate_promotion_blocked"])

    def test_vector_warm_start_and_seed_json_roundtrip(self):
        def callback(problem, x, maxiter, target):
            x[-1] += .125
            return x, status(0)
        restored = json.loads(json.dumps(self.seed))
        result = run_c1_staged(self.p.circuit, restored, coarse_points=1, fine_points=2,
                               optimize_stage=callback)
        stages = result["stage_calls"]
        self.assertEqual(stages[0]["output_vector"], stages[1]["input_vector"])
        self.assertEqual(result["attempts"][0]["vector"], stages[1]["output_vector"])
        self.assertEqual(result["seed"]["input_vector_sha256"], self.seed["input_vector_sha256"])

    def test_isolated_one_start_to_checked_pareto_without_solver(self):
        # Direct C1/C2 integration fixture, never a production authorization.
        problem, vector = make('RF-T008', 3)
        vector[6] = 0.0
        from lpf.phase2_models.synthetic_plan import _source
        source = _source()
        provenance = {'kind': 'synthetic', 'optimizer_kind': 'synthetic_callback',
                      'git_head': source['git_head'], 'dirty_patch_sha256': source['dirty_patch_sha256'],
                      'input_source_sha256': '0' * 64}  # isolated fixture, not an EXP input
        for codes, state, reason in [((0, 0), 'converged', None),
                                     ((4, 9), 'not_converged', 'numerical_not_converged'),
                                     ((8, 9), 'not_converged', 'numerical_not_converged'),
                                     ((9, 0, 0, 0), 'converged', None)]:
            with self.subTest(codes=codes):
                def fake_il(evaluator, x):
                    return np.where(evaluator.role == 0, .25, 36.)
                calls = []
                def mock(p, x, budget, target):
                    code = codes[len(calls)]
                    calls.append(budget)
                    x[-1] = .5
                    return x, status(code)
                with patch('lpf.phase2_models.coupled_lc.CoupledLCEvaluator.il', fake_il), \
                     patch('lpf.phase2_models.staged_optimization.minimize',
                           side_effect=AssertionError('solver forbidden')) as minimize:
                    initial = seed(problem, vector)
                    staged = run_c1_staged(problem.circuit, initial, coarse_points=1,
                                           fine_points=2, optimize_stage=mock,
                                           source_provenance=provenance)
                    candidate = record_candidate('fixture', problem.circuit,
                        staged['stage_calls'][-1]['output_vector'][:-1],
                        staged_record=staged, source_provenance=provenance)
                    checked = recheck_record(candidate)
                    row = pareto_report([checked])['candidates'][0]
                    minimize.assert_not_called()
                self.assertEqual(staged['numerical_state'], state)
                self.assertEqual(len(calls), len(codes))
                self.assertTrue(row['candidate_promotion_blocked'])
                if reason:
                    self.assertIn(reason, row['reasons'])
                else:
                    self.assertEqual(row['reasons'], [])
                    self.assertTrue(row['pareto_within_group'])
                self.assertEqual(checked.as_dict()['validation']['independent_mna'], 'not_run')

    def test_scipy_callback_wiring_without_running_solver(self):
        x = np.asarray(self.seed["vector"])
        fake = SimpleNamespace(x=x, success=True, status=0, message="ok", nit=2, nfev=3)
        with patch("lpf.phase2_models.staged_optimization.minimize", return_value=fake) as solver:
            result, state = scipy_slsqp_stage(self.p, x, 240, None)
        args, kwargs = solver.call_args
        self.assertEqual(kwargs["method"], "SLSQP")
        self.assertEqual(kwargs["options"]["maxiter"], 240)
        self.assertEqual(kwargs["bounds"], self.p.box.bounds)
        self.assertIs(args[0].__self__, self.p)
        self.assertEqual(kwargs["constraints"][0]["fun"].__self__, self.p)
        np.testing.assert_array_equal(result, x)
        self.assertEqual(state["nfev"], 3)
        with self.assertRaises(ValueError):
            scipy_slsqp_stage(self.p, x, 240, 35.)

    def test_nonfinite_output_preserved_and_serializable(self):
        def bad(problem, x, maxiter, target):
            x[0] = np.nan
            return x, status(0)
        result = run_c1_staged(self.p.circuit, self.seed, coarse_points=1, fine_points=2,
                               optimize_stage=bad)
        self.assertEqual(result["numerical_state"], "failed")
        self.assertEqual(result["stage_calls"][0]["output_vector"][0], "nan")
        self.assertEqual(result["stage_calls"][0]["status"], status(0))
        json.dumps(result, allow_nan=False)

    def test_non_spd_output_preserves_numerical_diagnostic(self):
        def bad(problem, x, maxiter, target):
            x[6:9] = -.9
            return x, status(0)
        result = run_c1_staged(self.p.circuit, self.seed, coarse_points=1, fine_points=2,
                               optimize_stage=bad)
        stage = result["stage_calls"][0]
        self.assertEqual(result["numerical_state"], "failed")
        self.assertEqual(stage["status"]["status"], 0)
        self.assertEqual(stage["observation"]["sampled_rf"]["error"]["code"], "mutual_not_spd")
        self.assertEqual(stage["observation"]["component_policy"]["state"], "fail")

    def test_invalid_callback_and_seed_fail_closed(self):
        def bad(problem, x, maxiter, target):
            return x, {**status(9), "success": True}
        result = run_c1_staged(self.p.circuit, self.seed, coarse_points=1, fine_points=2,
                               optimize_stage=bad)
        self.assertEqual(result["numerical_state"], "failed")
        self.assertTrue(result["stage_calls"][0]["status"]["success"])
        changed = copy.deepcopy(self.seed)
        changed["vector"] = tuple([1.] * len(changed["vector"]))
        with self.assertRaises(ValueError):
            run_c1_staged(self.p.circuit, changed, coarse_points=1, fine_points=2,
                          optimize_stage=bad)


if __name__ == "__main__":
    unittest.main()

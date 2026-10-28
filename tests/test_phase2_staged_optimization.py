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

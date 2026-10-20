"""No numerical experiment is launched: deterministic tests of the search budget policy."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from lpf.slsqp_budget import (
    POLICY_ID, IterationBudget, STANDARD_SLSQP_BUDGET,
    reached_iteration_limit, run_staged_slsqp,
)


class TestSLSQPIterationBudget(unittest.TestCase):
    def test_defaults_and_constraints(self):
        self.assertEqual(POLICY_ID, "slsqp-staged-v1")
        self.assertEqual(STANDARD_SLSQP_BUDGET.as_dict()["primary"],
                         {"coarse": 240, "fine": 120})
        self.assertEqual(STANDARD_SLSQP_BUDGET.as_dict()["recovery"],
                         {"coarse": 500, "fine": 280})
        with self.assertRaises(ValueError):
            IterationBudget(coarse=0)
        with self.assertRaises(ValueError):
            IterationBudget(coarse=True)
        with self.assertRaises(ValueError):
            IterationBudget(coarse=501)
        with self.assertRaises(TypeError):
            run_staged_slsqp(None, None, 0, 30.0, lambda *args: None, budget=123)

    def test_precise_iteration_limit_detection(self):
        self.assertTrue(reached_iteration_limit({
            "converged": False, "message": "Iteration limit reached"}))
        self.assertTrue(reached_iteration_limit({
            "converged": False, "message": "Maximum number of iterations has been exceeded."}))
        self.assertFalse(reached_iteration_limit({
            "converged": False, "message": "Positive directional derivative for linesearch"}))
        self.assertFalse(reached_iteration_limit({
            "converged": False, "message": "Inequality constraints incompatible"}))
        self.assertFalse(reached_iteration_limit({
            "converged": True, "message": "Iteration limit reached"}))

    def test_normal_success_never_uses_recovery(self):
        calls = []
        def stage(ev, x, maxiter, target):
            calls.append((ev, x, maxiter, target))
            return x+1, {"converged": True, "message": "Optimization terminated successfully", "iterations": 8}
        got = run_staged_slsqp("c", "f", 10, 30.005, stage)
        self.assertEqual([(z[0], z[2]) for z in calls], [("c", 240), ("f", 120)])
        self.assertFalse(got["recovery_invoked"])
        self.assertEqual(got["attempts"][0]["vector"], 12)
        self.assertTrue(got["attempts"][0]["converged"])

    def test_coarse_limit_recovers_from_fine_vector(self):
        calls = []
        def stage(ev, x, maxiter, target):
            calls.append((ev, x, maxiter))
            if len(calls) == 1:
                return x+1, {"converged": False, "message": "Iteration limit reached"}
            return x+1, {"converged": True, "message": "Optimization terminated successfully"}
        got = run_staged_slsqp("coarse", "fine", 10, 30.005, stage)
        self.assertEqual(calls, [("coarse", 10, 240), ("fine", 11, 120),
                                 ("coarse", 12, 500), ("fine", 13, 280)])
        self.assertTrue(got["recovery_invoked"])
        self.assertFalse(got["attempts"][0]["converged"])
        self.assertTrue(got["attempts"][1]["converged"])
        self.assertEqual(got["attempts"][1]["tier"], "recovery_both")

    def test_fine_limit_only_retries_fine(self):
        calls = []
        def stage(ev, x, maxiter, target):
            calls.append((ev, x, maxiter))
            return x+1, {"converged": len(calls) != 2,
                         "message": "Iteration limit reached" if len(calls) == 2 else "Success"}
        got = run_staged_slsqp("c", "f", 10, 30.0, stage)
        self.assertEqual(calls, [("c", 10, 240), ("f", 11, 120), ("f", 12, 280)])
        self.assertEqual(got["attempts"][1]["tier"], "recovery_fine")
        self.assertTrue(got["attempts"][1]["converged"])

    def test_nonlimit_failure_does_not_recurse(self):
        calls = []
        def stage(ev, x, maxiter, target):
            calls.append(maxiter)
            if ev == "c":
                return x, {"converged": False, "message": "Singular matrix E in LSQ subproblem"}
            return x, {"converged": True, "message": "Success"}
        got = run_staged_slsqp("c", "f", 10, 30.0, stage)
        self.assertEqual(calls, [240, 120])
        self.assertFalse(got["recovery_invoked"])
        self.assertFalse(got["attempts"][0]["converged"])

    def test_recovery_exhaustion_is_not_disguised_as_success(self):
        def stage(ev, x, maxiter, target):
            return x, {"converged": False, "message": "Iteration limit reached"}
        got = run_staged_slsqp("c", "f", 10, 30.0, stage)
        self.assertEqual(len(got["attempts"]), 2)
        self.assertFalse(got["attempts"][1]["converged"])


if __name__ == "__main__":
    unittest.main()

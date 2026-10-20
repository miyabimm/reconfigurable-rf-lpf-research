"""Versioned Phase 2 SLSQP iteration policy for NEW RF-LPF optimizer runs.

Only numerical *search resources* are controlled here; RF constraints, S2Ps,
physical assumptions, and experimental provenance are NOT changed.

The initial evaluator is free to use a coarse frequency sampling policy, but
independent dense-grid H2/H3 and MNA verification must still be performed by
the calling experiment before promoting any candidate. Nothing in this module
calls a historical run or changes any historical optimizer source.
"""
from dataclasses import dataclass
from typing import Callable


POLICY_ID = "slsqp-staged-v1"


@dataclass(frozen=True)
class IterationBudget:
    """Two-stage normal budget; one capped recovery only on iteration exhaustion."""

    coarse: int = 240
    fine: int = 120
    recovery_coarse: int = 500
    recovery_fine: int = 280

    def __post_init__(self):
        for name in ("coarse", "fine", "recovery_coarse", "recovery_fine"):
            value = getattr(self, name)
            if type(value) is not int or value < 1:
                raise ValueError(f"{name} must be a positive integer")
        if self.recovery_coarse < self.coarse or self.recovery_fine < self.fine:
            raise ValueError("Recovery maxiter cannot be smaller than the primary budget")

    def as_dict(self):
        return {
            "policy_id": POLICY_ID,
            "primary": {"coarse": self.coarse, "fine": self.fine},
            "recovery": {"coarse": self.recovery_coarse, "fine": self.recovery_fine},
            "retries_on_iteration_limit": 1,
        }


STANDARD_SLSQP_BUDGET = IterationBudget()


def reached_iteration_limit(status):
    """A false 'converged' result is retryable *only* when SLSQP hit maxiter.

    Other failures (infeasible, singular subproblem, line-search errors, etc.)
    are returned, not disguised as iteration-limit events.
    """
    if not isinstance(status, dict) or status.get("converged") is True:
        return False
    msg = str(status.get("message", "")).casefold()
    return ("iteration limit" in msg or "maximum number of iterations" in msg
            or "maxiter reached" in msg)


def run_staged_slsqp(
    coarse_evaluator,
    fine_evaluator,
    initial_vector,
    target,
    optimize_stage: Callable,
    budget=STANDARD_SLSQP_BUDGET,
):
    """Run a two-stage constrained optimizer with at most one targeted recovery.

    `optimize_stage(evaluator, vector, maxiter, target)` must return
    `(vector, {"converged": bool, "message": str, ...})`. The calling script
    chooses among returned attempts *after* dense checks and independent MNA.
    A finite-grid-eligible nonconverged point remains labelled nonconverged.

    If coarse exhausted its iteration budget, rerun both coarse and fine from
    the initial fine-stage output (continuation / warm start). If only fine
    exhausted the budget, retry only fine, retaining the converged coarse
    stage. Do not retry for another kind of SLSQP termination.
    """
    if not isinstance(budget, IterationBudget):
        raise TypeError("budget must be an IterationBudget")

    xc, first_coarse = optimize_stage(coarse_evaluator, initial_vector,
                                      budget.coarse, target)
    xf, first_fine = optimize_stage(fine_evaluator, xc, budget.fine, target)
    attempts = [{
        "tier": "primary",
        "vector": xf,
        "coarse": first_coarse,
        "fine": first_fine,
        "converged": bool(first_coarse.get("converged")
                          and first_fine.get("converged")),
        "warm_start_source": "supplied_initial_vector",
        "coarse_maxiter": budget.coarse,
        "fine_maxiter": budget.fine,
    }]

    if reached_iteration_limit(first_coarse):
        x2, second_coarse = optimize_stage(coarse_evaluator, xf,
                                           budget.recovery_coarse, target)
        xf2, second_fine = optimize_stage(fine_evaluator, x2,
                                         budget.recovery_fine, target)
        attempts.append({
            "tier": "recovery_both", "vector": xf2,
            "coarse": second_coarse, "fine": second_fine,
            "converged": bool(second_coarse.get("converged")
                              and second_fine.get("converged")),
            "warm_start_source": "primary_fine_vector",
            "coarse_maxiter": budget.recovery_coarse,
            "fine_maxiter": budget.recovery_fine,
        })
    elif reached_iteration_limit(first_fine):
        xf2, second_fine = optimize_stage(fine_evaluator, xf,
                                         budget.recovery_fine, target)
        attempts.append({
            "tier": "recovery_fine", "vector": xf2,
            "coarse": first_coarse, "fine": second_fine,
            "converged": bool(first_coarse.get("converged")
                              and second_fine.get("converged")),
            "warm_start_source": "primary_fine_vector",
            "coarse_maxiter": budget.coarse,
            "fine_maxiter": budget.recovery_fine,
        })

    return {"iteration_policy": budget.as_dict(), "attempts": attempts,
            "recovery_invoked": len(attempts) > 1}

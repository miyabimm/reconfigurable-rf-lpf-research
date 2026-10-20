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


# ---------------------------------------------------------------------------
# New Phase2 standard from 2026-10-20: termination-aware staged SLSQP, v2.
# v1 above is retained unchanged for historical callers/tests.
# Numerical caps remain 240/120; true iteration exhaustion only => 500/280.
# EXP-060/061 show that status4/8 + successful fine grid responds better
# to a SAME-budget restart from the fine vector than to raising maxiter.
# ---------------------------------------------------------------------------
TERMINATION_AWARE_POLICY_ID = "slsqp-staged-v2"


def _stage_converged(status):
    """Support the normalized callback contract; never infer from finite RF pass."""
    if not isinstance(status, dict):
        raise TypeError("stage status must be a dict")
    if "converged" in status:
        return status["converged"] is True
    if "success" in status:
        return status["success"] is True
    raise KeyError("status must include converged or success")


def _iteration_exhausted(status):
    if _stage_converged(status):
        return False
    # SciPy SLSQP status 9 is the documented iteration limit. No status
    # 4/8 classification is recoverable merely by increasing maxiter.
    if status.get("status") == 9:
        return True
    return reached_iteration_limit({**status, "converged": False})


def run_termination_aware_slsqp(
    coarse_evaluator,
    fine_evaluator,
    initial_vector,
    target,
    optimize_stage: Callable,
    budget=STANDARD_SLSQP_BUDGET,
):
    """Phase2 v2: terminate/restart based on actual *stage* exit cause.

    The primary coarse (240) and fine (120) runs are ALWAYS separately
    recorded and immutable. One targeted continuation is permitted:
    - coarse iteration exhausted: repeat coarse/fine from fine output with
      up to 500/280.
    - coarse converged and fine iteration exhausted: repeat fine only up
      to 280.
    - coarse did *not* converge for a non-iteration reason, but fine DID
      converge: repeat BOTH stages once from the fine output at the normal
      240/120 budgets (feasible-basin warm restart).
    - coarse failed noniteration and fine failed (including fine status9):
      no automatic limit rescue; fix feasibility/start instead.
    Never make more than four stage optimizer calls per invocation.
    Caller must still apply finite-frequency six-setting RF checks and
    independent coupled-L MNA before claiming a valid design.
    """
    if not isinstance(budget, IterationBudget):
        raise TypeError("budget must be IterationBudget")
    x_coarse, c0 = optimize_stage(coarse_evaluator, initial_vector,
                                  budget.coarse, target)
    x_fine, f0 = optimize_stage(fine_evaluator, x_coarse,
                                budget.fine, target)
    c_ok, f_ok = _stage_converged(c0), _stage_converged(f0)
    attempts = [{
        "tier": "primary",
        "vector": x_fine,
        "coarse": c0,
        "fine": f0,
        "converged": c_ok and f_ok,
        "warm_start_source": "supplied_initial_vector",
        "coarse_maxiter": budget.coarse,
        "fine_maxiter": budget.fine,
    }]
    if not c_ok and _iteration_exhausted(c0):
        c_vec, c1 = optimize_stage(coarse_evaluator, x_fine,
                                    budget.recovery_coarse, target)
        f_vec, f1 = optimize_stage(fine_evaluator, c_vec,
                                   budget.recovery_fine, target)
        attempts.append({
            "tier": "iteration_rescue_both",
            "vector": f_vec,
            "coarse": c1,
            "fine": f1,
            "converged": _stage_converged(c1) and _stage_converged(f1),
            "warm_start_source": "primary_fine_vector",
            "coarse_maxiter": budget.recovery_coarse,
            "fine_maxiter": budget.recovery_fine,
        })
    elif c_ok and not f_ok and _iteration_exhausted(f0):
        f_vec, f1 = optimize_stage(fine_evaluator, x_fine,
                                   budget.recovery_fine, target)
        attempts.append({
            "tier": "iteration_rescue_fine",
            "vector": f_vec,
            "coarse": c0,
            "fine": f1,
            "converged": _stage_converged(f1),
            "warm_start_source": "primary_fine_vector",
            "coarse_maxiter": budget.coarse,
            "fine_maxiter": budget.recovery_fine,
        })
    elif not c_ok and f_ok and not _iteration_exhausted(c0):
        c_vec, c1 = optimize_stage(coarse_evaluator, x_fine,
                                    budget.coarse, target)
        f_vec, f1 = optimize_stage(fine_evaluator, c_vec,
                                   budget.fine, target)
        attempts.append({
            "tier": "nonlimit_feasible_restart",
            "vector": f_vec,
            "coarse": c1,
            "fine": f1,
            "converged": _stage_converged(c1) and _stage_converged(f1),
            "warm_start_source": "primary_fine_vector",
            "coarse_maxiter": budget.coarse,
            "fine_maxiter": budget.fine,
        })
    return {
        "iteration_policy": {
            **budget.as_dict(), "policy_id": TERMINATION_AWARE_POLICY_ID,
            "max_continuations": 1,
            "max_stage_calls_per_initial_start": 4,
            "noniteration_warm_restart":
                "once_if_coarse_failed_and_fine_converged",
            "prohibit_fine_maxiter_extension_if_coarse_noniteration_failure": True,
        },
        "attempts": attempts,
        "recovery_invoked": len(attempts)>1,
        "recovery_cause": (attempts[1]["tier"] if len(attempts)>1 else None),
    }

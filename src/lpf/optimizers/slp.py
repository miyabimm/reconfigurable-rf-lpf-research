"""Bounded sequential linear programming for synthetic objectives.

This solver uses HiGHS, finite differences and a trust box; it does not run
SLSQP or imply global optimality, RF feasibility, or ADS equivalence.
"""
from dataclasses import dataclass
from typing import Callable

import numpy as np

from .minimax import Stage, _minimize_core


@dataclass(frozen=True)
class SlpResult:
    x: np.ndarray
    aggregation: str
    objective: float
    max_violation: float
    feasible: bool
    success: bool  # local numerical convergence AND feasibility
    slp: Stage
    slsqp: Stage  # not_run; retained alongside the legacy reporting format


def slp_minimize(
    residuals: Callable, x0, bounds, *, aggregation: str = "sum", weights=None,
    constraints: Callable | None = None, max_iterations: int, max_evaluations: int,
    initial_step: float = 0.25, min_step: float = 1e-8, fd_step: float = 1e-6,
    tolerance: float = 1e-7, constraint_tolerance: float = 1e-7,
) -> SlpResult:
    """Minimize a weighted squared residual sum or max, or a signed maximum.

    'sum' linearizes the total scalar; 'max' linearizes each weighted square
    in an epigraph. Weights default to one, and must be finite, nonnegative,
    and match the residual length. 'signed_max' uses max(residuals) unchanged
    and rejects weights, exactly as the legacy minimize_minimax calculation.
    Constraints are vectors g(x)>=0. All callbacks and finite differences share
    the evaluation budget, and LP solves count as iterations. Invalid or
    nonfinite callback outputs and transformed objectives raise ValueError.
    Feasibility is distinct from convergence: success is only a local
    linearized-stationarity heuristic, subject to HiGHS tolerances and not a
    global optimum guarantee. See slp.reason for nonconvergence and budgets.
    """
    result = _minimize_core(
        residuals, x0, bounds, aggregation=aggregation, weights=weights,
        constraints=constraints, max_iterations=max_iterations, max_evaluations=max_evaluations,
        initial_step=initial_step, min_step=min_step, fd_step=fd_step,
        tolerance=tolerance, constraint_tolerance=constraint_tolerance,
    )
    return SlpResult(result.x, aggregation, result.max_error, result.max_violation,
                     result.feasible, result.success, result.slp, result.slsqp)

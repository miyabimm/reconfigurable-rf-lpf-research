"""Bounded sequential linear programming for synthetic objectives.

This solver uses HiGHS, finite differences and a trust box; it does not run
SLSQP or imply global optimality, RF feasibility, or ADS equivalence.
"""
from dataclasses import dataclass
from typing import Callable

import numpy as np
from scipy.optimize import linprog

from ._objectives import aggregate, squared_terms, validate_weights


@dataclass(frozen=True)
class Stage:
    reason: str
    iterations: int
    evaluations: int  # individual errors / constraints callback invocations


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


class _BudgetExhausted(Exception):
    pass


def _minimize_core(
    errors: Callable,
    x0,
    bounds,
    *,
    max_iterations: int,
    max_evaluations: int,
    constraints: Callable | None = None,
    initial_step: float = 0.25,
    min_step: float = 1e-8,
    fd_step: float = 1e-6,
    tolerance: float = 1e-7,
    constraint_tolerance: float = 1e-7,
    aggregation: str = "signed_max",
    weights=None,
) -> SlpResult:
    """Minimize transformed errors with box bounds and optional constraints(x)>=0.

    Step sizes are fractions of each bound width. Finite differences and every
    actual callback invocation, including rejected trials, count toward the
    shared evaluation budget. Iterations count LP solves, including failures.
    Shapes must remain fixed and outputs finite; callback contract violations
    raise ValueError. Success is a local linearized stationarity heuristic,
    not a global optimum certificate. A feasible result is not necessarily
    converged. LP failures and exhausted budgets never imply infeasibility or
    optimality. No SLSQP refinement is currently used.
    """
    if not isinstance(aggregation, str) or aggregation not in ("sum", "max", "signed_max"):
        raise ValueError("aggregation must be 'sum', 'max', or 'signed_max'")
    if aggregation == "signed_max" and weights is not None:
        raise ValueError("weights are not supported for signed_max")
    weights = validate_weights(weights)
    if weights is not None:
        weights = weights.copy()

    x = np.asarray(x0, dtype=float)
    box = np.asarray(bounds, dtype=float)
    if x.ndim != 1 or not x.size or not np.all(np.isfinite(x)):
        raise ValueError("x0 must be a finite nonempty vector")
    if box.shape != (x.size, 2) or not np.all(np.isfinite(box)):
        raise ValueError("bounds must be finite (n, 2) pairs")
    lo, hi = box[:, 0], box[:, 1]
    width = hi - lo
    if not np.all(np.isfinite(width)) or np.any(width < 0) or np.any(x < lo) or np.any(x > hi):
        raise ValueError("invalid bounds or x0 outside bounds")
    if (not isinstance(max_iterations, int) or isinstance(max_iterations, bool) or max_iterations < 1
            or not isinstance(max_evaluations, int) or isinstance(max_evaluations, bool)
            or max_evaluations < 1 + (constraints is not None)):
        raise ValueError("positive iteration and sufficient evaluation budgets required")
    if (not all(np.isfinite(v) and v > 0 for v in (initial_step, min_step, fd_step, tolerance, constraint_tolerance))
            or initial_step > 1 or min_step > initial_step or fd_step > 1):
        raise ValueError("invalid step or tolerance")

    x = x.copy()
    calls = 0
    sizes = [None, None]

    def evaluate(point):
        nonlocal calls
        values = []
        for i, fun in enumerate((errors, constraints)):
            if fun is None:
                values.append(np.empty(0))
                continue
            if calls >= max_evaluations:
                raise _BudgetExhausted
            calls += 1
            value = np.asarray(fun(point.copy()), dtype=float)
            if value.ndim != 1 or (i == 0 and not value.size) or not np.all(np.isfinite(value)):
                raise ValueError("callbacks must return finite vectors; errors must be nonempty")
            if sizes[i] is None:
                sizes[i] = value.size
            elif sizes[i] != value.size:
                raise ValueError("callback output shape changed")
            if i == 0 and aggregation != "signed_max":
                if weights is not None and weights.size != value.size:
                    raise ValueError("weights must match residual length")
                value = squared_terms(value, weights)
                if aggregation == "sum":
                    value = np.array([aggregate(value, aggregation)])
                if not np.all(np.isfinite(value)):
                    raise ValueError("weighted squared objective must be finite")
            values.append(value)
        return values

    def violation(g):
        return max(0.0, -float(np.min(g))) if g.size else 0.0

    e, g = evaluate(x)
    radius = initial_step
    iterations = 0
    reason = "iteration_limit"
    converged = False
    try:
        while iterations < max_iterations:
            # One-sided, box-aware differences; fixed coordinates have zero columns.
            je = np.zeros((e.size, x.size))
            jg = np.zeros((g.size, x.size))
            for j in range(x.size):
                if width[j] == 0:
                    continue
                forward, backward = hi[j] - x[j], x[j] - lo[j]
                h = min(fd_step * width[j], forward)
                if forward < fd_step * width[j] and backward > forward:
                    h = -min(fd_step * width[j], backward)
                trial = x.copy()
                trial[j] += h
                h = trial[j] - x[j]  # actual representable displacement
                if h == 0:
                    reason = "finite_difference_step_unrepresentable"
                    break
                et, gt = evaluate(trial)
                je[:, j] = (et - e) / h
                jg[:, j] = (gt - g) / h
            else:
                if not np.all(np.isfinite(je)) or not np.all(np.isfinite(jg)):
                    reason = "nonfinite_jacobian"
                    break
                iterations += 1
                a = np.vstack((np.column_stack((je, -np.ones(e.size))),
                               np.column_stack((-jg, np.zeros(g.size)))))
                b = np.concatenate((-e, g))
                step_bounds = [(max(lo[j] - x[j], -radius * width[j]),
                                min(hi[j] - x[j], radius * width[j])) for j in range(x.size)]
                lp = linprog(np.r_[np.zeros(x.size), 1.0], A_ub=a, b_ub=b,
                             bounds=step_bounds + [(None, None)], method="highs")
                if not lp.success:
                    # A too-small trust box may exclude the linearized feasible set.
                    if lp.status == 2 and radius < 1:
                        radius = min(1.0, 2 * radius)
                        continue
                    reason = f"lp_failure:{lp.status}: {lp.message}"
                    break
                f, v = float(np.max(e)), violation(g)
                predicted = f - lp.x[-1]
                # A small trust box alone must not masquerade as stationarity.
                if v <= constraint_tolerance and predicted <= tolerance * radius:
                    converged = True
                    reason = "linearized_stationary"
                    break
                candidate = np.clip(x + lp.x[:-1], lo, hi)
                ec, gc = evaluate(candidate)
                fc, vc = float(np.max(ec)), violation(gc)
                # Feasibility first until feasible; then require actual improvement
                # without stepping outside the stated constraint tolerance.
                accepted = ((v > constraint_tolerance and vc < v - tolerance * 0.01)
                            or (v <= constraint_tolerance and vc <= constraint_tolerance
                                and f - fc > max(0.0, 1e-4 * predicted)))
                if accepted:
                    x, e, g = candidate, ec, gc
                    radius = min(1.0, 2 * radius)
                else:
                    radius *= 0.5
                    if radius < min_step:
                        reason = "step_too_small"
                        break
                continue
            break
    except _BudgetExhausted:
        reason = "evaluation_limit"

    v = violation(g)
    feasible = v <= constraint_tolerance
    return SlpResult(x.copy(), aggregation, float(np.max(e)), v, feasible, converged and feasible,
                     Stage(reason, iterations, calls), Stage("not_run", 0, 0))


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
    and rejects weights; it preserves the signed error components unchanged.
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
    return result

"""Bounded sequential linear programming for synthetic objectives.

This solver uses HiGHS, finite differences and a trust box; it does not run
SLSQP or imply global optimality, RF feasibility, or ADS equivalence.
"""
from typing import Callable

import numpy as np
from scipy.optimize import linprog

from .result import OptimizerResult


class _BudgetExhausted(Exception):
    pass


def slp_minimize(
    errors: Callable,
    x0,
    bounds,
    *,
    max_iterations: int,
    max_evaluations: int,
    initial_step: float = 0.25,
    min_step: float = 1e-8,
    fd_step: float = 1e-6,
    tolerance: float = 1e-7,
    aggregation: str = "signed_max",
    objective_callback=None,
) -> OptimizerResult:
    """Minimize the signed maximum of errors with box bounds.

    Step sizes are fractions of each bound width. Finite differences and every
    actual callback invocation, including rejected trials, count toward the
    shared evaluation budget. Iterations count LP solves, including failures.
    Shapes must remain fixed and outputs finite; callback contract violations
    raise ValueError. Success is a local linearized stationarity heuristic,
    not a global optimum certificate. LP failures and exhausted budgets never
    imply infeasibility or optimality. No SLSQP refinement is currently used.
    """
    if aggregation != "signed_max":
        raise ValueError("aggregation must be 'signed_max'")
    if objective_callback is not None and not callable(objective_callback):
        raise ValueError('objective_callback must be callable')
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
            or max_evaluations < 1):
        raise ValueError("positive iteration and sufficient evaluation budgets required")
    if (not all(np.isfinite(v) and v > 0 for v in (initial_step, min_step, fd_step, tolerance))
            or initial_step > 1 or min_step > initial_step or fd_step > 1):
        raise ValueError("invalid step or tolerance")

    x = x.copy()
    calls = 0
    size = None

    def evaluate(point):
        nonlocal calls, size
        if calls >= max_evaluations:
            raise _BudgetExhausted
        calls += 1
        value = np.asarray(errors(point.copy()), dtype=float)
        if value.ndim != 1 or not value.size or not np.all(np.isfinite(value)):
            raise ValueError("callbacks must return finite nonempty vectors")
        if size is None:
            size = value.size
        elif size != value.size:
            raise ValueError("callback output shape changed")
        if objective_callback is not None:
            objective_callback(point.copy(), float(np.max(value)))
        return value

    e = evaluate(x)
    radius = initial_step
    iterations = 0
    reason = "iteration_limit"
    converged = False
    try:
        while iterations < max_iterations:
            # One-sided, box-aware differences; fixed coordinates have zero columns.
            je = np.zeros((e.size, x.size))
            for j in range(x.size):
                if width[j] == 0:
                    continue
                forward, backward = hi[j] - x[j], x[j] - lo[j]
                h = min(fd_step * width[j], forward)
                if forward < fd_step * width[j] and backward > forward:
                    h = -min(fd_step * width[j], backward)
                trial = x.copy()
                # Subtracting and then adding a distance to a bound can
                # round just outside the closed box.
                trial[j] = min(hi[j], max(lo[j], x[j] + h))
                h = trial[j] - x[j]  # actual representable displacement
                if h == 0:
                    reason = "finite_difference_step_unrepresentable"
                    break
                et = evaluate(trial)
                je[:, j] = (et - e) / h
            else:
                if not np.all(np.isfinite(je)):
                    reason = "nonfinite_jacobian"
                    break
                iterations += 1
                a = np.column_stack((je, -np.ones(e.size)))
                b = -e
                step_bounds = [(max(lo[j] - x[j], -radius * width[j]),
                                min(hi[j] - x[j], radius * width[j])) for j in range(x.size)]
                lp = linprog(np.r_[np.zeros(x.size), 1.0], A_ub=a, b_ub=b,
                             bounds=step_bounds + [(None, None)], method="highs")
                if not lp.success:
                    # HiGHS reports numerical or linear-program failure.
                    if lp.status == 2 and radius < 1:
                        radius = min(1.0, 2 * radius)
                        continue
                    reason = f"lp_failure:{lp.status}: {lp.message}"
                    break
                f = float(np.max(e))
                predicted = f - lp.x[-1]
                # A small trust box alone must not masquerade as stationarity.
                if predicted <= tolerance * radius:
                    converged = True
                    reason = "linearized_stationary"
                    break
                candidate = np.clip(x + lp.x[:-1], lo, hi)
                ec = evaluate(candidate)
                fc = float(np.max(ec))
                if f - fc > max(0.0, 1e-4 * predicted):
                    x, e = candidate, ec
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

    return OptimizerResult(x.copy(), float(np.max(e)), converged, reason, calls)

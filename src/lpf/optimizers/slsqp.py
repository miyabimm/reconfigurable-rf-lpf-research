"""Generic bounded SLSQP for weighted squared residuals; not the RF runner."""
from dataclasses import dataclass
from typing import Callable

import numpy as np
from scipy.optimize import minimize


@dataclass(frozen=True)
class SLSQPResult:
    x: np.ndarray
    aggregation: str
    fun: float | None
    max_violation: float | None  # physical constraints and box, not epigraph
    feasible: bool
    success: bool
    stop_reason: str
    status: int | None  # None if SciPy did not return
    message: str
    nit: int
    nfev: int  # residual callback invocations
    ncev: int  # physical constraint callback invocations
    evaluations: int  # shared hard budget: nfev + ncev
    epigraph_violation: float | None
    epigraph_gap: float | None  # abs(t - max weighted squared residual)
    solver_success: bool | None


class _Stop(Exception):
    pass


def slsqp_minimize(residuals: Callable, x0, bounds, *, aggregation='sum',
                   weights=None, constraints: Callable | None = None,
                   max_iterations: int, max_evaluations: int,
                   tolerance: float = 1e-9, constraint_tolerance: float = 1e-7) -> SLSQPResult:
    """Minimize weighted squared residual sum or maximum under g(x) >= 0.

    Both budgets are mandatory. Each actual residual or physical-constraint
    invocation, including finite differences and final verification, consumes
    one shared evaluation. On interruption the returned point is the initial
    point (with any available initial observations), not an unverified solver
    iterate. No callbacks are called after interruption. Callback exceptions
    other than malformed/nonfinite output propagate. Invalid weights and box
    inputs raise ValueError. An infeasible initial point may be repaired.

    Max uses one epigraph inequality per residual. Success requires SciPy
    success, independently evaluated physical/epigraph feasibility, and an
    epigraph gap within constraint_tolerance; all-fixed boxes are evaluated directly. No global
    optimum, RF compliance, or physical realizability is implied.
    """
    if not isinstance(aggregation, str) or aggregation not in ('sum', 'max'):
        raise ValueError("aggregation must be 'sum' or 'max'")
    if not callable(residuals) or (constraints is not None and not callable(constraints)):
        raise ValueError('callbacks must be callable')
    for name, value in (('max_iterations', max_iterations), ('max_evaluations', max_evaluations)):
        if type(value) is not int or value < 1:
            raise ValueError(f'{name} must be a positive integer')
    if not np.isfinite(tolerance) or tolerance <= 0 or not np.isfinite(constraint_tolerance) or constraint_tolerance <= 0:
        raise ValueError('tolerances must be finite and positive')
    x0 = np.asarray(x0, dtype=float)
    box = np.asarray(bounds, dtype=float)
    if x0.ndim != 1 or not x0.size or box.shape != (x0.size, 2):
        raise ValueError('x0 and bounds must have shapes (n,) and (n, 2), n > 0')
    if not np.all(np.isfinite(x0)) or not np.all(np.isfinite(box)):
        raise ValueError('x0 and bounds must be finite')
    lo, hi = box[:, 0], box[:, 1]
    with np.errstate(over='ignore', invalid='ignore'):
        width = hi - lo
    if np.any(width < 0) or not np.all(np.isfinite(width)) or np.any(x0 < lo) or np.any(x0 > hi):
        raise ValueError('invalid bounds or x0 outside bounds')
    if weights is not None:
        weights = np.asarray(weights, dtype=float)
        if weights.ndim != 1 or not weights.size or not np.all(np.isfinite(weights)) or np.any(weights < 0):
            raise ValueError('weights must be a nonempty finite nonnegative vector')

    free = width > 0
    counts = [0, 0]
    sizes = [None, None]
    nit = 0
    status = solver_success = None
    initial_fun = initial_v = None

    def evaluate(x, kind):
        if sum(counts) >= max_evaluations:
            raise _Stop('evaluation_budget_exhausted')
        counts[kind] += 1
        raw = (residuals if kind == 0 else constraints)(x.copy())
        try:
            value = np.asarray(raw, dtype=float)
        except (TypeError, ValueError):
            raise _Stop('invalid_residual' if kind == 0 else 'invalid_constraint') from None
        if (value.ndim != 1 or (kind == 0 and not value.size) or
                not np.all(np.isfinite(value)) or
                (sizes[kind] is not None and value.size != sizes[kind])):
            raise _Stop('invalid_residual' if kind == 0 else 'invalid_constraint')
        if kind == 0 and weights is not None and weights.size != value.size:
            raise ValueError('weights length must match residuals')
        sizes[kind] = value.size
        if kind == 0:
            with np.errstate(over='ignore', invalid='ignore'):
                value = value * value if weights is None else weights * value * value
            with np.errstate(over='ignore'):
                invalid_sum = aggregation == 'sum' and not np.isfinite(np.sum(value))
            if not np.all(np.isfinite(value)) or invalid_sum:
                raise _Stop('invalid_residual')
        return value

    def objective_value(terms):
        return float(np.sum(terms) if aggregation == 'sum' else np.max(terms))

    def violation(x, g):
        return max(0.0, float(np.max(lo - x)), float(np.max(x - hi)),
                   -float(np.min(g)) if g.size else 0.0)

    def physical(z):
        x = x0.copy()
        x[free] = z[:np.count_nonzero(free)]
        return x

    def result(x, fun, v, epiv, epigap, success, reason, message):
        return SLSQPResult(x.copy(), aggregation, fun, v,
                           v is not None and v <= constraint_tolerance,
                           success, reason, status, message, nit, counts[0], counts[1],
                           sum(counts), epiv, epigap, solver_success)

    try:
        initial_terms = evaluate(x0, 0)
        initial_fun = objective_value(initial_terms)
        initial_g = evaluate(x0, 1) if constraints is not None else np.empty(0)
        initial_v = violation(x0, initial_g)
        if not np.any(free):
            feasible = initial_v <= constraint_tolerance
            return result(x0, initial_fun, initial_v, 0.0 if aggregation == 'max' else None,
                          0.0 if aggregation == 'max' else None, feasible, 'all_coordinates_fixed' if feasible else 'fixed_infeasible',
                          'all coordinates fixed; evaluated directly')

        z0 = x0[free].copy()
        solver_bounds = list(zip(lo[free], hi[free]))
        if aggregation == 'max':
            z0 = np.r_[z0, initial_fun]
            solver_bounds.append((None, None))
            objective = lambda z: float(z[-1])
            scipy_constraints = [{'type': 'ineq',
                                  'fun': lambda z: z[-1] - evaluate(physical(z), 0)}]
        else:
            objective = lambda z: objective_value(evaluate(physical(z), 0))
            scipy_constraints = []
        if constraints is not None:
            scipy_constraints.append({'type': 'ineq', 'fun': lambda z: evaluate(physical(z), 1)})

        def callback(_z):
            nonlocal nit
            nit += 1

        sol = minimize(objective, z0, method='SLSQP', bounds=solver_bounds,
                       constraints=scipy_constraints, callback=callback,
                       options={'maxiter': max_iterations, 'ftol': tolerance})
        status, solver_success, nit = int(sol.status), bool(sol.success), int(sol.nit)
        if not np.all(np.isfinite(sol.x)):
            return result(x0, initial_fun, initial_v, None, None, False,
                          'invalid_solver_result', str(sol.message))
        x = physical(sol.x)
        # Do not trust sol.fun or constraint values without checking this exact point.
        terms = evaluate(x, 0)
        g = evaluate(x, 1) if constraints is not None else np.empty(0)
        fun, v = objective_value(terms), violation(x, g)
        epiv = max(0.0, float(np.max(terms - sol.x[-1]))) if aggregation == 'max' else None
        epigap = abs(float(sol.x[-1]) - fun) if aggregation == 'max' else None
        success = (solver_success and v <= constraint_tolerance and
                   (epigap is None or epigap <= constraint_tolerance))
        reason = 'converged' if success else ('verification_failed' if solver_success else 'solver_failure')
        return result(x, fun, v, epiv, epigap, success, reason, str(sol.message))
    except _Stop as exc:
        return result(x0, initial_fun, initial_v, None, None, False, str(exc), str(exc))

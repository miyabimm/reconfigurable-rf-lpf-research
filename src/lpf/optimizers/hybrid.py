"""Bounded Hybrid approximation, not the proprietary ADS algorithm.

Only box constraints are supported. Restarts perturb the *last local endpoint*,
not necessarily the best point, by independent N(0, restart_sigma**2) in
[0, 1] coordinates, then project to the box. This permits uphill restarts.
No global optimality or physical feasibility is implied.
"""
from dataclasses import dataclass
from typing import Callable

import numpy as np
from scipy.optimize import minimize

from ._objectives import aggregate, squared_terms, validate_weights


@dataclass
class LocalRun:
    start_x: list[float]
    start_fun: float | None
    end_x: list[float] | None
    end_fun: float | None
    success: bool
    status: int | None  # None means the solver was interrupted, not a SciPy status
    message: str
    nit: int
    nfev: int  # actual residual calls, including finite differences and invalid calls


@dataclass
class HybridResult:
    runs: list[LocalRun]
    best_x: list[float] | None
    best_fun: float | None
    nfev: int
    stop_reason: str
    seed: int
    maxiter: int
    max_restarts: int
    max_evaluations: int
    restart_sigma: float
    aggregation: str = 'sum'


class _Stop(Exception):
    pass


def hybrid_minimize(residuals: Callable, x0, bounds, *, seed: int, maxiter: int,
                    max_restarts: int, max_evaluations: int, restart_sigma: float,
                    weights=None, aggregation: str = 'sum') -> HybridResult:
    """Minimize sum or max of weights * residuals(x)**2 with bounded L-BFGS-B.

    The default 'sum' is weighted least squares; 'max' is the maximum weighted
    squared residual, not the maximum signed error. The 'max' objective is
    nonsmooth, so L-BFGS-B may fail to converge or stop in its line search.

    All budgets are mandatory: maxiter is per local run; max_restarts excludes
    the initial run; max_evaluations is a hard total cap on residual calls,
    including finite differences. A partially evaluated gradient can interrupt
    SciPy: its end is the last *valid evaluated point*, not a converged iterate;
    status=None and success=False. best is the best valid evaluated point,
    including finite-difference probes, independently of solver convergence.
    Invalid residuals (empty, nonfinite, changing length, overflow) stop the
    entire search and preserve prior valid observations. Other exceptions from
    the caller propagate. Weights must be finite, nonnegative and match the
    residual length. Out-of-bounds x0 is rejected, never projected.
    All-fixed boxes require one evaluation and no SciPy call or restarts.
    """
    if not isinstance(aggregation, str) or aggregation not in ('sum', 'max'):
        raise ValueError("aggregation must be 'sum' or 'max'")
    for name, value, minimum in (('seed', seed, 0), ('maxiter', maxiter, 1),
                                  ('max_restarts', max_restarts, 0),
                                  ('max_evaluations', max_evaluations, 1)):
        if type(value) is not int or value < minimum:
            raise ValueError(f'{name} must be an integer >= {minimum}')
    if not np.isscalar(restart_sigma) or not np.isfinite(restart_sigma) or restart_sigma <= 0:
        raise ValueError('restart_sigma must be finite and positive')
    if not callable(residuals):
        raise ValueError('residuals must be callable')
    x0 = np.asarray(x0, dtype=float)
    box = np.asarray(bounds, dtype=float)
    if x0.ndim != 1 or not x0.size or box.shape != (x0.size, 2):
        raise ValueError('x0 and bounds must have shapes (n,) and (n, 2), n > 0')
    if not np.all(np.isfinite(x0)) or not np.all(np.isfinite(box)):
        raise ValueError('x0 and bounds must be finite')
    lo, hi = box[:, 0], box[:, 1]
    with np.errstate(over='ignore', invalid='ignore'):
        width = hi - lo
    if np.any(lo > hi) or not np.all(np.isfinite(width)):
        raise ValueError('bounds must be ordered with finite widths')
    if np.any(x0 < lo) or np.any(x0 > hi):
        raise ValueError('x0 outside bounds')
    weights = validate_weights(weights)

    free = width > 0
    rng = np.random.default_rng(seed)
    best_x = best_fun = None
    total = 0
    residual_size = None
    runs = []
    reason = 'restarts_exhausted'

    def physical(z):
        x = lo.copy()
        # Protect the physical bounds against floating-point reconstruction error.
        x[free] = np.clip(lo[free] + z * width[free], lo[free], hi[free])
        return x

    z_start = (x0[free] - lo[free]) / width[free]
    for run_index in range(max_restarts + 1):
        if total >= max_evaluations:
            reason = 'evaluation_budget_exhausted'
            break
        start_x = x0.copy() if run_index == 0 else physical(z_start)
        start_fun = None
        last_x = last_fun = None
        local_nfev = nit = 0

        def objective(z):
            nonlocal total, local_nfev, start_fun, last_x, last_fun, best_x, best_fun, residual_size
            if total >= max_evaluations:
                raise _Stop('evaluation_budget_exhausted')
            x = start_x.copy() if np.array_equal(z, z_start) else physical(z)
            total += 1
            local_nfev += 1
            raw = residuals(x.copy())
            try:
                r = np.asarray(raw, dtype=float)
            except (TypeError, ValueError):
                raise _Stop('invalid_residual') from None
            if (r.ndim != 1 or not r.size or not np.all(np.isfinite(r)) or
                    (residual_size is not None and r.size != residual_size) or
                    (weights is not None and weights.size != r.size)):
                raise _Stop('invalid_residual')
            residual_size = r.size
            terms = squared_terms(r, weights)
            value = aggregate(terms, aggregation)
            if not np.isfinite(value):
                raise _Stop('invalid_residual')
            if local_nfev == 1:
                start_fun = value
            last_x, last_fun = x.copy(), value
            if best_fun is None or value < best_fun:
                best_x, best_fun = x.copy(), value
            return value

        def callback(_):
            nonlocal nit
            nit += 1

        try:
            if not np.any(free):
                value = objective(z_start)
                run = LocalRun(start_x.tolist(), start_fun, start_x.tolist(), value,
                               True, 0, 'all coordinates fixed', 0, local_nfev)
                reason = 'all_coordinates_fixed'
            else:
                sol = minimize(objective, z_start, method='L-BFGS-B',
                               bounds=[(0.0, 1.0)] * int(np.sum(free)),
                               callback=callback, options={'maxiter': maxiter,
                                                           'maxfun': max_evaluations})
                end_x = start_x if np.array_equal(sol.x, z_start) else physical(sol.x)
                run = LocalRun(start_x.tolist(), start_fun, end_x.tolist(),
                               float(sol.fun), bool(sol.success), int(sol.status),
                               str(sol.message), int(sol.nit), local_nfev)
        except _Stop as exc:
            reason = str(exc)
            run = LocalRun(start_x.tolist(), start_fun,
                           None if last_x is None else last_x.tolist(), last_fun,
                           False, None, reason, nit, local_nfev)
        runs.append(run)
        if reason != 'restarts_exhausted':
            break
        if run_index < max_restarts:
            if total >= max_evaluations:
                reason = 'evaluation_budget_exhausted'
                break
            # Project only the random restart, never the user's initial point.
            z_start = np.clip(np.asarray(sol.x) + rng.normal(0.0, restart_sigma, size=z_start.size), 0.0, 1.0)

    return HybridResult(runs, None if best_x is None else best_x.tolist(), best_fun,
                        total, reason, seed, maxiter, max_restarts,
                        max_evaluations, float(restart_sigma), aggregation)

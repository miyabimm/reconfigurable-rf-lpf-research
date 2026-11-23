"""Normalized TRF local solver with analytic residual sensitivities."""
from dataclasses import dataclass
from time import perf_counter, process_time

import numpy as np
from scipy.optimize import least_squares

from ._objectives import squared_terms, aggregate
from .result import OptimizerResult


@dataclass(frozen=True)
class LeastSquaresResult:
    x: np.ndarray
    objective: float
    best_x: np.ndarray
    best_objective: float
    initial_evaluated_x: np.ndarray
    success: bool
    status: int
    message: str
    nfev: int
    njev: int
    sensitivity_evaluations: int
    requested_samples: int
    computed_samples: int
    wall_s: float
    cpu_s: float
    optimality: float | None


def least_squares_local(evaluate_with_jacobian, x0, bounds, max_evaluations=100, objective_callback=None,
                        ftol=1e-8, x_scale=1.0):
    """Run one TRF solve. Callback returns (residual, physical Jacobian).

    The one-entry cache shares only exactly equal normalized vectors. Callback
    exceptions propagate (and are never reported as success). nfev is SciPy's
    count, not an RF forward limit. Each callback must compute all residual rows.
    """
    x0 = np.asarray(x0, dtype=float)
    bounds = np.asarray(bounds, dtype=float)
    if (x0.ndim != 1 or not x0.size or bounds.shape != (len(x0), 2) or
            not np.all(np.isfinite(x0)) or not np.all(np.isfinite(bounds)) or
            np.any(bounds[:, 1] < bounds[:, 0]) or np.any(x0 < bounds[:, 0]) or
            np.any(x0 > bounds[:, 1]) or type(max_evaluations) is not int or max_evaluations < 1):
        raise ValueError('Expected finite in-box x0, bounds and positive max_evaluations')
    with np.errstate(over='ignore', invalid='ignore'):
        lo, width = bounds[:, 0], bounds[:, 1] - bounds[:, 0]
    if not np.all(np.isfinite(width)):
        raise ValueError('Non-finite bounds width')
    free = width > 0
    z0 = np.clip((x0[free] - lo[free]) / width[free], 0., 1.)
    cached_z = cached = None
    evaluations = samples = 0
    first = best_x = None
    best = np.inf
    wall, cpu = perf_counter(), process_time()

    def calc(z):
        nonlocal cached_z, cached, evaluations, samples, first, best_x, best
        if cached_z is not None and np.array_equal(z, cached_z):
            return cached
        cached_z = cached = None
        x = lo.copy()
        x[free] = np.clip(lo[free] + z * width[free], lo[free], bounds[free, 1])
        r, j = evaluate_with_jacobian(x.copy())
        evaluations += 1
        r, j = np.asarray(r, dtype=float), np.asarray(j, dtype=float)
        if (r.ndim != 1 or not r.size or j.shape != (len(r), len(x0)) or
                not np.all(np.isfinite(r)) or not np.all(np.isfinite(j))):
            raise ValueError('Invalid residual or Jacobian')
        samples += len(r)
        objective = float(.5 * np.dot(r, r))
        if not np.isfinite(objective):
            raise ValueError('Non-finite objective')
        if objective_callback is not None:
            objective_callback(x.copy(), objective)
        if first is None:
            first = x.copy()
        if objective < best:
            best, best_x = objective, x.copy()
        cached_z = np.array(z, copy=True)
        cached = (r.copy(), j[:, free] * width[free])
        return cached

    if np.any(free):
        result = least_squares(lambda z: calc(z)[0], z0, jac=lambda z: calc(z)[1],
                               bounds=(0., 1.), method='trf', loss='linear',
                               ftol=ftol, x_scale=x_scale, tr_solver='exact', max_nfev=max_evaluations)
        z = np.asarray(result.x, dtype=float)
        final_r = np.asarray(result.fun, dtype=float)
        if (z.shape != z0.shape or not np.all(np.isfinite(z)) or np.any(z < 0) or np.any(z > 1) or
                cached is None or final_r.shape != cached[0].shape or not np.all(np.isfinite(final_r)) or
                not isinstance(result.success, (bool, np.bool_)) or
                not isinstance(result.status, (int, np.integer)) or bool(result.success) != (result.status > 0) or
                not isinstance(result.nfev, (int, np.integer)) or result.nfev < 1 or
                (result.njev is not None and (not isinstance(result.njev, (int, np.integer)) or result.njev < 0))):
            raise ValueError('Invalid SciPy result')
        x = lo.copy()
        x[free] = np.clip(lo[free] + z * width[free], lo[free], bounds[free, 1])
        objective = float(.5 * np.dot(final_r, final_r))
        if not np.isfinite(objective):
            raise ValueError('Invalid SciPy objective')
        success, status, message = bool(result.success), int(result.status), str(result.message)
        nfev, njev = int(result.nfev), int(result.njev or 0)
        optimality = float(result.optimality)
        if not np.isfinite(optimality) or optimality < 0:
            raise ValueError('Invalid SciPy optimality')
    else:
        r, _ = calc(z0)
        x, objective = lo.copy(), float(.5 * np.dot(r, r))
        success, status, message, nfev, njev = True, 0, 'All variables fixed; evaluated once', 1, 0
        optimality = None
    return LeastSquaresResult(x, objective, best_x, best, first, success, status, message,
                              nfev, njev, evaluations, samples, samples,
                              perf_counter()-wall, process_time()-cpu, optimality)


def to_optimizer_result(result):
    """Select the best observed point, not necessarily SciPy's final point."""
    reason = ('all_variables_fixed' if result.success and result.status == 0 else
              'converged' if result.success else
              'evaluation_limit' if result.status == 0 else 'solver_failure')
    return OptimizerResult(result.best_x.copy(), result.best_objective, result.success,
                           reason, result.sensitivity_evaluations)


def reported_margin_objective(margins):
    """Recompute legacy sum separately; sqrt(2) may round differently."""
    return aggregate(squared_terms(np.asarray(margins), None), 'sum')

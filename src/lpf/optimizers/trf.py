"""Normalized TRF local solver with analytic residual sensitivities."""
from dataclasses import dataclass
from time import perf_counter, perf_counter_ns, process_time

import numpy as np
from scipy.optimize import least_squares

from .result import OptimizerResult
from lpf.timing import timed_call


@dataclass(frozen=True)
class _LocalResult:
    x: np.ndarray
    objective: float
    best_x: np.ndarray
    best_objective: float
    initial_evaluated_x: np.ndarray
    success: bool
    status: int
    message: str
    scipy_nfev: int
    scipy_njev: int
    sensitivity_evaluations: int
    requested_samples: int
    computed_samples: int
    wall_s: float
    cpu_s: float
    optimality: float | None


def _trf_local(evaluate_with_jacobian, x0, bounds, max_evaluations=100, objective_callback=None,
               ftol=1e-6, x_scale=1.0, _timing=None):
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
        if _timing: started = perf_counter_ns()
        hit = cached_z is not None and np.array_equal(z, cached_z)
        if _timing: _timing[0].add(_timing[1] + '/trf/calc/cache_check', perf_counter_ns() - started)
        if hit:
            if _timing: _timing[0].add(_timing[1] + '/trf/calc/cache_hit', 0)
            return cached
        if _timing: started = perf_counter_ns()
        cached_z = cached = None
        x = lo.copy()
        x[free] = np.clip(lo[free] + z * width[free], lo[free], bounds[free, 1])
        if _timing: _timing[0].add(_timing[1] + '/trf/calc/coordinates', perf_counter_ns() - started)
        if _timing:
            r, j = _timing[0].call(_timing[1] + '/trf/calc/worker', evaluate_with_jacobian, x.copy())
        else:
            r, j = evaluate_with_jacobian(x.copy())
        if _timing: started = perf_counter_ns()
        evaluations += 1
        r, j = np.asarray(r, dtype=float), np.asarray(j, dtype=float)
        if (r.ndim != 1 or not r.size or j.shape != (len(r), len(x0)) or
                not np.all(np.isfinite(r)) or not np.all(np.isfinite(j))):
            raise ValueError('Invalid residual or Jacobian')
        samples += len(r)
        objective = float(.5 * np.dot(r, r))
        if not np.isfinite(objective):
            raise ValueError('Non-finite objective')
        if _timing: _timing[0].add(_timing[1] + '/trf/calc/validate_objective', perf_counter_ns() - started)
        if _timing: started = perf_counter_ns()
        if objective_callback is not None:
            objective_callback(x.copy(), objective)
        if first is None:
            first = x.copy()
        if objective < best:
            best, best_x = objective, x.copy()
        cached_z = np.array(z, copy=True)
        cached = (r.copy(), j[:, free] * width[free])
        if _timing: _timing[0].add(_timing[1] + '/trf/calc/observe_cache', perf_counter_ns() - started)
        return cached

    if _timing:
        calc_impl = calc
        def calc(z):
            return _timing[0].call(_timing[1] + '/trf/calc', calc_impl, z)

    if np.any(free):
        result = timed_call(_timing[0] if _timing else None, _timing[1] + '/trf/least_squares' if _timing else '',
                            least_squares, lambda z: calc(z)[0], z0, jac=lambda z: calc(z)[1],
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
    return _LocalResult(x, objective, best_x, best, first, success, status, message,
                              nfev, njev, evaluations, samples, samples,
                              perf_counter()-wall, process_time()-cpu, optimality)


def trf_minimize(evaluate_with_jacobian, x0, bounds, *, seed, max_evaluations,
                 restart_sigma, ftol, x_scale, objective_callback=None, local_run_callback=None, _timing=None):
    """Run TRF local solves, selecting the best observation across restarts."""
    if type(seed) is not int or seed < 0 or type(max_evaluations) is not int or max_evaluations < 1:
        raise ValueError('Expected nonnegative seed and positive evaluation budget')
    if restart_sigma is not None and (type(restart_sigma) not in (int, float) or
                                      not np.isfinite(restart_sigma) or restart_sigma <= 0):
        raise ValueError('restart_sigma must be None or finite and positive')
    rng = np.random.default_rng(seed) if restart_sigma is not None else None
    box = np.asarray(bounds, dtype=float)
    # _trf_local validates the full input before this geometry is used.
    start = np.asarray(x0, dtype=float).copy()
    total = 0
    best = None
    while True:
        run = timed_call(_timing[0] if _timing else None, _timing[1] + '/trf/local' if _timing else '',
                         _trf_local, evaluate_with_jacobian, start, box, max_evaluations=max_evaluations - total,
                         objective_callback=objective_callback, ftol=ftol, x_scale=x_scale,
                         **({'_timing': _timing} if _timing else {}))
        total += run.sensitivity_evaluations
        if local_run_callback is not None:
            local_run_callback(start.copy(), run)
        if best is None or run.best_objective < best.best_objective:
            best = run
        lo, width = box[:, 0], box[:, 1] - box[:, 0]
        free = width > 0
        if restart_sigma is None or not free.any() or not run.success or total >= max_evaluations:
            break
        z = (best.best_x[free] - lo[free]) / width[free]
        start = lo.copy()
        start[free] = np.clip(lo[free] + np.clip(z + rng.normal(0, restart_sigma, size=z.size), 0, 1) * width[free],
                              lo[free], box[free, 1])
    if not free.any():
        reason, converged = 'all_variables_fixed', True
    elif restart_sigma is None:
        reason = ('converged' if run.success else 'solver_failure' if run.status < 0 else
                  'evaluation_budget_exhausted' if total >= max_evaluations else 'evaluation_limit')
        converged = run.success
    else:
        reason = ('solver_failure' if not run.success and run.status < 0 else
                  'evaluation_budget_exhausted' if total >= max_evaluations else 'evaluation_limit')
        converged = False
    return OptimizerResult(best.best_x.copy(), best.best_objective, converged, reason, total)

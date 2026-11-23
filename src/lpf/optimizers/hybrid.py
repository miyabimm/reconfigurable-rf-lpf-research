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
from time import perf_counter_ns

from lpf.timing import timed_call
from ._objectives import aggregate, squared_terms, validate_weights
from .result import OptimizerResult


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


class _Stop(Exception):
    pass


def hybrid_minimize(residuals: Callable, x0, bounds, *, seed: int,
                    max_evaluations: int, restart_sigma: float,
                    weights=None, aggregation: str = 'sum', event_callback=None,
                    run_callback=None, objective_callback=None, progress_callback=None,
                    local_run_callback=None, batch_fd=False, residuals_batch=None,
                    group_callback=None, _timing=None) -> OptimizerResult:
    """Minimize sum or max of weights * maximum(residuals(x), 0)**2.

    Bounded L-BFGS-B penalizes positive violations only; negative residuals
    contribute zero. 'max' is not the maximum signed error. The 'max' objective is
    nonsmooth, so L-BFGS-B may fail to converge or stop in its line search.

    In batch_fd mode max_evaluations limits starting new groups, and a started
    finite-difference group completes even if it exceeds that nominal limit.
    Otherwise max_evaluations is the hard total cap on residual calls; the per-local-run
    maxiter safety guard is derived from it. Finite local endpoints restart
    until this cap is exhausted. The cap includes
    including finite differences. A partially evaluated gradient can interrupt
    SciPy: its end is the last *valid evaluated point*, not a converged iterate;
    status=None and success=False. best is the best valid evaluated point,
    including finite-difference probes, independently of solver convergence.
    Invalid residuals (empty, nonfinite, changing length, overflow) stop the
    entire search and preserve prior valid observations. Other exceptions from
    the caller propagate. Weights must be finite, nonnegative and match the
    residual length. Out-of-bounds x0 is rejected, never projected.
    All-fixed boxes require one evaluation and no SciPy call or restarts. The
    overall result is converged only for this all-fixed case: with free
    coordinates, successful local runs restart until the evaluation budget is
    exhausted, and a local success is not overall convergence. Individual
    local outcomes remain available through local_run_callback.
    objective_callback receives each valid observed (x, f(x)); progress_callback
    also receives whether Hybrid chose that observation as its new best.
    Both callbacks propagate exceptions, without retry or extra RF evaluation.
    """
    if not isinstance(aggregation, str) or aggregation not in ('sum', 'max'):
        raise ValueError("aggregation must be 'sum' or 'max'")
    for name, value, minimum in (('seed', seed, 0), ('max_evaluations', max_evaluations, 1)):
        if type(value) is not int or value < minimum:
            raise ValueError(f'{name} must be an integer >= {minimum}')
    maxiter = max_evaluations
    if not np.isscalar(restart_sigma) or not np.isfinite(restart_sigma) or restart_sigma <= 0:
        raise ValueError('restart_sigma must be finite and positive')
    if not callable(residuals):
        raise ValueError('residuals must be callable')
    if type(batch_fd) is not bool or (batch_fd and not callable(residuals_batch)):
        raise ValueError('batch_fd requires a callable residuals_batch')
    if group_callback is not None and not callable(group_callback):
        raise ValueError('group_callback must be callable')
    if run_callback is not None and not callable(run_callback):
        raise ValueError('run_callback must be callable')
    if objective_callback is not None and not callable(objective_callback):
        raise ValueError('objective_callback must be callable')
    if progress_callback is not None and not callable(progress_callback):
        raise ValueError('progress_callback must be callable')
    if local_run_callback is not None and not callable(local_run_callback):
        raise ValueError('local_run_callback must be callable')
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
    run = None
    reason = 'restarts_exhausted'

    def physical(z):
        x = lo.copy()
        # Protect the physical bounds against floating-point reconstruction error.
        x[free] = np.clip(lo[free] + z * width[free], lo[free], hi[free])
        return x

    # Optional diagnostics never control the scientific path.
    def emit(event):
        if event_callback is not None:
            try:
                event_callback(event)
            except Exception:
                pass

    import time
    z_start = (x0[free] - lo[free]) / width[free]
    # Each local run makes at least one residual call; N is also a safe bound
    # on the number of runs in the budget-only mode.
    for run_index in range(max_evaluations):
        if total >= max_evaluations:
            reason = 'evaluation_budget_exhausted'
            break
        if run_index and event_callback is not None:
            wall_start, cpu_start = time.monotonic(), time.process_time()
            start_x = physical(z_start)
            wall_end, cpu_end = time.monotonic(), time.process_time()
            emit(dict(event='restart_start_generated', seed=seed, run_index=run_index,
                      monotonic_s=wall_end, process_cpu_s=cpu_end,
                      wall_s=restart_wall_s + (wall_end - wall_start),
                      cpu_s=restart_cpu_s + (cpu_end - cpu_start)))
        else:
            start_x = x0.copy() if run_index == 0 else physical(z_start)
        if run_callback is not None:
            run_callback(run_index)
        start_fun = None
        last_x = last_fun = None
        local_nfev = nit = 0
        pending = None

        def objective(z):
            nonlocal total, local_nfev, start_fun, last_x, last_fun, best_x, best_fun, residual_size
            if _timing: started, failed = perf_counter_ns(), False
            try:
                if pending is None and total >= max_evaluations:
                    raise _Stop('evaluation_budget_exhausted')
                x = start_x.copy() if np.array_equal(z, z_start) else physical(z)
                total += 1
                local_nfev += 1
            except BaseException:
                if _timing: failed = True
                raise
            finally:
                if _timing: _timing[0].add(f'{_timing[1]}/objective/prepare', perf_counter_ns() - started, failed=failed)
            if _timing: started, failed = perf_counter_ns(), False
            try:
                raw = residuals(x.copy()) if pending is None else next(pending)
                if isinstance(raw, BaseException):
                    raise raw
            except BaseException:
                if _timing: failed = True
                raise
            finally:
                if _timing:
                    kind = 'scalar' if pending is None else 'batch'
                    _timing[0].add(f'{_timing[1]}/objective/raw_{kind}', perf_counter_ns() - started, failed=failed)
            if _timing: started, failed = perf_counter_ns(), False
            try:
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
            except BaseException:
                if _timing: failed = True
                raise
            finally:
                if _timing: _timing[0].add(f'{_timing[1]}/objective/value', perf_counter_ns() - started, failed=failed)
            if _timing: started, failed = perf_counter_ns(), False
            try:
                if objective_callback is not None:
                    objective_callback(x.copy(), value)
                if local_nfev == 1:
                    start_fun = value
                last_x, last_fun = x.copy(), value
                improved = best_fun is None or value < best_fun
                if improved:
                    best_x, best_fun = x.copy(), value
                if progress_callback is not None:
                    progress_callback(x.copy(), value, improved)
                if pending is None and group_callback is not None:
                    if _timing:
                        timed_call(_timing[0], f'{_timing[1]}/objective/group_callback', group_callback)
                    else:
                        group_callback()
            except BaseException:
                if _timing: failed = True
                raise
            finally:
                if _timing: _timing[0].add(f'{_timing[1]}/objective/state', perf_counter_ns() - started, failed=failed)
            return value

        if _timing:
            objective_impl = objective
            def objective(z):
                kind = 'scalar' if pending is None else 'batch'
                return timed_call(_timing[0], f'{_timing[1]}/objective/{kind}', objective_impl, z)

        def batch_map(fun, iterable):
            nonlocal pending
            if total >= max_evaluations:
                raise _Stop('evaluation_budget_exhausted')
            if _timing:
                zs = timed_call(_timing[0], f'{_timing[1]}/batch/list', list, iterable)
            else:
                zs = list(iterable)
            if not zs:
                return []
            if _timing: started, failed = perf_counter_ns(), False
            try:
                vectors = [start_x.copy() if np.array_equal(z, z_start) else physical(z) for z in zs]
            except BaseException:
                if _timing: failed = True
                raise
            finally:
                if _timing: _timing[0].add(f'{_timing[1]}/batch/vectors', perf_counter_ns() - started, failed=failed)
            results = residuals_batch(vectors)
            pending = iter(results)
            try:
                values = [fun(z) for z in zs]
            finally:
                pending = None
            if group_callback is not None:
                if _timing:
                    timed_call(_timing[0], f'{_timing[1]}/batch/group_callback', group_callback)
                else:
                    group_callback()
            return values

        if _timing:
            batch_map_impl = batch_map
            def batch_map(fun, iterable):
                return timed_call(_timing[0], f'{_timing[1]}/batch/parent', batch_map_impl, fun, iterable)

        def callback(_):
            nonlocal nit
            nit += 1

        if _timing:
            callback_impl = callback
            def callback(arg):
                return timed_call(_timing[0], f'{_timing[1]}/scipy/callback', callback_impl, arg)

        timed = event_callback is not None and np.any(free)
        if timed:
            wall_start, cpu_start = time.monotonic(), time.process_time()
            emit(dict(event='local_run_start', seed=seed, run_index=run_index,
                      monotonic_s=wall_start, process_cpu_s=cpu_start))
        try:
            if not np.any(free):
                value = objective(z_start)
                run = LocalRun(start_x.tolist(), start_fun, start_x.tolist(), value,
                               True, 0, 'all coordinates fixed', 0, local_nfev)
                reason = 'all_coordinates_fixed'
            else:
                options = {'maxiter': maxiter, 'maxfun': max_evaluations}
                if batch_fd:
                    options['workers'] = batch_map
                if _timing:
                    sol = timed_call(_timing[0], f'{_timing[1]}/scipy/minimize', minimize, objective, z_start,
                                     method='L-BFGS-B', bounds=[(0.0, 1.0)] * int(np.sum(free)),
                                     callback=callback, options=options)
                else:
                    sol = minimize(objective, z_start, method='L-BFGS-B',
                                   bounds=[(0.0, 1.0)] * int(np.sum(free)),
                                   callback=callback, options=options)
                if (local_nfev == 0 or np.asarray(sol.x).shape != z_start.shape or
                        not np.all(np.isfinite(sol.x)) or not np.isfinite(sol.fun) or
                        np.any(np.asarray(sol.x) < 0) or np.any(np.asarray(sol.x) > 1)):
                    raise _Stop('invalid_solver_endpoint')
                end_x = start_x if np.array_equal(sol.x, z_start) else physical(sol.x)
                run = LocalRun(start_x.tolist(), start_fun, end_x.tolist(),
                               float(sol.fun), bool(sol.success), int(sol.status),
                               str(sol.message), int(sol.nit), local_nfev)
        except _Stop as exc:
            if batch_fd and group_callback is not None:
                group_callback(force=True)
            reason = str(exc)
            run = LocalRun(start_x.tolist(), start_fun,
                           None if last_x is None else last_x.tolist(), last_fun,
                           False, None, reason, nit, local_nfev)
        except BaseException as exc:
            if batch_fd and group_callback is not None:
                group_callback(force=True)
            if timed:
                emit(dict(event='local_run_end', seed=seed, run_index=run_index,
                          monotonic_s=time.monotonic(), process_cpu_s=time.process_time(),
                          wall_s=time.monotonic()-wall_start, cpu_s=time.process_time()-cpu_start,
                          nfev=local_nfev, nit=nit, success=False, status=None,
                          message=f'{type(exc).__name__}: {exc}', interrupted=True))
            raise
        if timed:
            wall_end, cpu_end = time.monotonic(), time.process_time()
            emit(dict(event='local_run_end', seed=seed, run_index=run_index,
                      monotonic_s=wall_end, process_cpu_s=cpu_end,
                      wall_s=wall_end-wall_start, cpu_s=cpu_end-cpu_start,
                      nfev=run.nfev, nit=run.nit, success=run.success,
                      status=run.status, message=run.message, interrupted=run.status is None))
        if local_run_callback is not None:
            local_run_callback(run)
        if reason != 'restarts_exhausted':
            break
        if total >= max_evaluations:
            reason = 'evaluation_budget_exhausted'
            break
        # Project only the random restart, never the user's initial point.
        if event_callback is not None:
            wall_start, cpu_start = time.monotonic(), time.process_time()
        z_start = np.clip(np.asarray(sol.x) + rng.normal(0.0, restart_sigma, size=z_start.size), 0.0, 1.0)
        if event_callback is not None:
            restart_wall_s = time.monotonic() - wall_start
            restart_cpu_s = time.process_time() - cpu_start

    selected = None if best_x is None else best_x.tolist()
    converged = reason == 'all_coordinates_fixed' and run is not None and run.success
    return OptimizerResult(selected, best_fun, bool(converged), reason, total)

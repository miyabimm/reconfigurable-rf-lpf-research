"""Independent, normalized TRF local solver; not connected to the runner."""
from dataclasses import dataclass
from time import perf_counter, process_time

import numpy as np
from scipy.optimize import least_squares

from lpf.minimax_profile import _margin_parameters
from ._objectives import squared_terms, aggregate


def signed_margin_residual(profile, response, il_jacobian):
    """Unweighted sum residual and physical Jacobian; at kink use zero.

    At m=0 the positive-part residual is nondifferentiable. The zero row is
    the chosen one-sided convention, not a claim of differentiability.
    """
    if (response.policy_id != profile.profile['constraint_id'] or
            response.policy_fingerprint != profile.fingerprint):
        raise ValueError('Response profile mismatch')
    threshold, direction = _margin_parameters(profile, response.grid)
    jac = np.asarray(il_jacobian, dtype=float)
    margin = direction * (response.il_db - threshold)
    if jac.ndim != 2 or jac.shape[0] != len(margin) or not np.all(np.isfinite(jac)) or not np.all(np.isfinite(margin)):
        raise ValueError('Non-finite or mismatched margin sensitivity')
    residual = np.sqrt(2.) * np.maximum(margin, 0)
    return residual, np.sqrt(2.) * direction[:, None] * jac * (margin > 0)[:, None]


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


def least_squares_local(evaluate_with_jacobian, x0, bounds, max_evaluations=100):
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
                               x_scale=1., tr_solver='exact', max_nfev=max_evaluations)
        x = lo.copy()
        x[free] = np.clip(lo[free] + result.x * width[free], lo[free], bounds[free, 1])
        objective = float(.5 * np.dot(result.fun, result.fun))
        success, status, message = bool(result.success), int(result.status), str(result.message)
        nfev, njev = int(result.nfev), int(result.njev or 0)
    else:
        r, _ = calc(z0)
        x, objective = lo.copy(), float(.5 * np.dot(r, r))
        success, status, message, nfev, njev = True, 0, 'All variables fixed; evaluated once', 1, 0
    return LeastSquaresResult(x, objective, best_x, best, first, success, status, message,
                              nfev, njev, evaluations, samples, samples,
                              perf_counter()-wall, process_time()-cpu)


def reported_margin_objective(margins):
    """Recompute legacy sum separately; sqrt(2) may round differently."""
    return aggregate(squared_terms(np.asarray(margins), None), 'sum')

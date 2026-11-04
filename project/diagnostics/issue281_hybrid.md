# Issue #281: bounded Hybrid approximation

`lpf.optimizers.hybrid.hybrid_minimize` is an RF-independent optimization
utility, not an EXP runner. It approximates the published concept of ADS Hybrid
using SciPy L-BFGS-B and random restarts; it does **not** reproduce the
proprietary implementation or guarantee a global optimum.

```python
from lpf.optimizers.hybrid import hybrid_minimize

result = hybrid_minimize(
    lambda x: [x[0] - 0.25, 2 * (x[1] - 0.75)],
    [0.9, 0.1], [(0.0, 1.0), (0.0, 1.0)],
    weights=[1.0, 1.0], seed=42,
    maxiter=100, max_restarts=5, max_evaluations=1000,
    restart_sigma=0.2,
)
```

`aggregation="sum"` (the default) minimizes `sum(weights * residuals(x)**2)`;
`aggregation="max"` minimizes `max(weights * residuals(x)**2)`. Omitted
weights are 1; the selected mode is recorded in `result.aggregation`. Max is
nonsmooth and uses the same L-BFGS-B: nonconvergence or line-search failure is
not success, even when the best observed point is near the optimum. This
maximum *squared* error is not the signed-error `max(errors(x))` objective of
the separate MiniMax solver (Issue #282), nor is it ADS standard Hybrid's
least-squares objective.

Bounds and initial values must be finite and ordered, with x0 inside the box.
Each free coordinate is normalized to [0,1]; fixed coordinates are removed
from the solver and restored before each call. Each restart independently adds
Gaussian noise with standard deviation `restart_sigma` to the **last local
endpoint** in normalized space and projects the restart to the box. No
acceptance test rejects uphill points. The same seed and environment give the
same sequence for a deterministic residual; different SciPy/NumPy versions or
platforms are not promised bitwise identical results.

`maxiter` is per local run, `max_restarts` is in addition to the initial run,
and `max_evaluations` is a hard total cap on actual residual calls, including
finite differences and invalid calls. A budget interrupt during a gradient has
`status=None`, `success=False`, and the last valid evaluated point as endpoint;
this may be a finite-difference probe, not an accepted solver iterate. Other
runs report the SciPy endpoint and status. All-fixed boxes are evaluated once
without invoking SciPy. `best_x`/`best_fun` report the best valid observation
(including probes), **not** a convergence certificate; examine each run's
`success`, `status`, `message`, `nit`, and `nfev` independently. Stop reasons
are `restarts_exhausted`, `evaluation_budget_exhausted`,
`invalid_residual`, and `all_coordinates_fixed`. An invalid or changing
residual vector, incompatible weights, or objective overflow stops without
fabricating a score; earlier valid points are retained. Exceptions raised by
the user's residual function propagate. No nonlinear constraints are supported.

Verification is synthetic only: RF forward, production search, new EXP,
independent RF validation and physical feasibility have not been evaluated.

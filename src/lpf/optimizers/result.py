"""Small adapter for solver-native results; not an RF acceptance decision.

The adapters preserve each solver's own selection rule: SLSQP's verified end
point (or initial point on interruption), SLP's accepted iterate, and Hybrid's
first best observed point. Callers must separately verify that the pair was
observed on the intended Search grid and validate the physical circuit.
"""
from dataclasses import dataclass
import math

import numpy as np

from .hybrid import HybridResult
from .slp import SlpResult
from .slsqp import SLSQPResult


@dataclass(frozen=True)
class OptimizerResult:
    x: tuple[float, ...]
    objective: float
    converged: bool
    stop_reason: str
    evaluations: int


def optimizer_result(native):
    """Adapt native diagnostics without changing the solver's objective or x.

    Evaluation counts are native callback counts, not RF forward counts. An
    interrupted or invalid result cannot become converged through this adapter.
    """
    if isinstance(native, SLSQPResult):
        x, value, converged, reason, count = (native.x, native.fun, native.success,
                                               native.stop_reason, native.evaluations)
    elif isinstance(native, SlpResult):
        x, value, converged, reason, count = (native.x, native.objective, native.success,
                                               native.slp.reason, native.slp.evaluations)
    elif isinstance(native, HybridResult):
        x, value, reason, count = native.best_x, native.best_fun, native.stop_reason, native.nfev
        # Hybrid normally runs until its budget; successful local runs do not
        # make a budget-interrupted global search numerically converged.
        converged = reason == 'all_coordinates_fixed' and bool(native.runs) and native.runs[-1].success
    else:
        raise ValueError('Unknown optimizer result')
    if not isinstance(reason, str) or not reason or reason.startswith('invalid_'):
        raise ValueError('Invalid optimizer stop reason')
    if type(count) is not int or count < 1:
        raise ValueError('No optimizer callback observations')
    try:
        vector = np.asarray(x, dtype=float)
        objective = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError('Invalid optimizer output') from exc
    if vector.ndim != 1 or not vector.size or not np.all(np.isfinite(vector)) or not math.isfinite(objective):
        raise ValueError('Invalid optimizer output')
    return OptimizerResult(tuple(float(v) for v in vector), objective, bool(converged), reason, count)

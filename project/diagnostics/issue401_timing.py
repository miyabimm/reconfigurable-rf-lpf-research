#!/usr/bin/env python3
"""Issue 401 opt-in instrumentation for the development-only MinimalWorker.

Only install in a dedicated benchmark process, never in a production worker.
Regions are inclusive and exceptions are propagated unchanged.
"""
from contextlib import ExitStack, contextmanager
from functools import wraps
from unittest.mock import patch

from lpf.search import _worker_next as wn
from lpf.timing import TimerCollector


def _wrap(timer, name, function):
    @wraps(function)
    def wrapped(*args, **kwargs):
        return timer.call(name, function, *args, **kwargs)
    return wrapped


@contextmanager
def instrument(worker, timer):
    """Install L1/L2 probes on the *actual* solver path for one process."""
    if not isinstance(timer, TimerCollector):
        raise TypeError('TimerCollector required')
    cls = type(worker.evaluator)
    with ExitStack() as stack:
        for obj, attr, region in (
            (worker, 'solve', 'solve_total'),
            (worker, '_solver_residuals', 'solver_callback'),
            (worker, '_residuals', 'residual'),
            (cls, 'evaluate', 'rf_forward'),
            (wn, 'evaluate_requirements', 'requirements'),
            (wn, 'hybrid_minimize', 'hybrid_minimize'),
            (wn, 'validate_values', 'postsolve_validation'),
        ):
            stack.enter_context(patch.object(obj, attr, _wrap(timer, region, getattr(obj, attr))))
        yield

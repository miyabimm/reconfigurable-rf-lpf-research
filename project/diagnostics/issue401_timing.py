#!/usr/bin/env python3
"""Issue 401 opt-in instrumentation for the development-only MinimalWorker.

Only install in a dedicated benchmark process, never in a production worker.
Regions are inclusive and exceptions are propagated unchanged.
"""
from contextlib import ExitStack, contextmanager
from functools import wraps
from unittest.mock import patch

import numpy as np

from lpf.search import _worker_next as wn
from lpf.rf_core import model as rf_model
from lpf.rf_core.coupled_lc import CoupledLCTopology
from lpf.timing import TimerCollector


def _wrap(timer, name, function):
    @wraps(function)
    def wrapped(*args, **kwargs):
        return timer.call(name, function, *args, **kwargs)
    return wrapped


@contextmanager
def instrument(worker, timer, *, deep=False):
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
        if deep:
            # The direct evaluator solve is Y->S. Exclude solves inside port
            # assembly and power renormalization, even when either raises.
            nested = [0]
            active = [0]
            forward = cls.evaluate
            @wraps(forward)
            def forward_probe(*args, **kwargs):
                active[0] += 1
                try:
                    return forward(*args, **kwargs)
                finally:
                    active[0] -= 1
            stack.enter_context(patch.object(cls, 'evaluate', forward_probe))
            def nested_wrap(function, region):
                @wraps(function)
                def wrapped(*args, **kwargs):
                    nested[0] += 1
                    try:
                        return timer.call(region, function, *args, **kwargs)
                    finally:
                        nested[0] -= 1
                return wrapped
            for obj, attr, region in (
                (CoupledLCTopology, 'port_admittance', 'l3_port_admittance'),
                (rf_model, 'power_response', 'l3_power_response'),
            ):
                stack.enter_context(patch.object(obj, attr, nested_wrap(getattr(obj, attr), region)))
            for obj, attr, region in (
                (CoupledLCTopology, 'node_admittance', 'l3_node_admittance'),
                (CoupledLCTopology, 'matrices', 'l3_matrices'),
                (rf_model.RFModel, 'decode', 'l3_decode'),
                (rf_model.RFModel, 'encode', 'l3_encode'),
                (rf_model, '_cascade', 'l3_cascade'),
            ):
                stack.enter_context(patch.object(obj, attr, _wrap(timer, region, getattr(obj, attr))))
            solve = np.linalg.solve
            @wraps(solve)
            def solve_probe(*args, **kwargs):
                if not active[0] or nested[0]:
                    return solve(*args, **kwargs)
                return timer.call('l3_y_to_s_solve', solve, *args, **kwargs)
            stack.enter_context(patch.object(np.linalg, 'solve', solve_probe))
        yield

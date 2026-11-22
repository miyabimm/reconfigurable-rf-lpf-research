"""Search-only, opt-in inclusive RF function timings for the development runner."""
from contextlib import ExitStack, contextmanager
from functools import wraps

from lpf.rf_core import model, coupled_lc
from lpf.rf_core.coupled_lc import CoupledLCTopology


@contextmanager
def search_rf_timing(timer, stage):
    """Temporarily wrap existing calls; count only within evaluator entry points.

    The development runner executes jobs sequentially. These process-global
    wrappers are not intended for concurrent searches.
    """
    active = False
    batch_active = False
    with ExitStack() as stack:
        def replace(owner, name, wrapper):
            original = getattr(owner, name)
            setattr(owner, name, wrapper(original))
            stack.callback(setattr, owner, name, original)

        def evaluate_wrapper(original):
            @wraps(original)
            def wrapped(*args, **kwargs):
                nonlocal active
                previous, active = active, True
                previous_model, previous_coupled = model._deep_timing, coupled_lc._deep_timing
                model._deep_timing = coupled_lc._deep_timing = (timer, f'{stage}/rf')
                try:
                    return original(*args, **kwargs)
                finally:
                    model._deep_timing, coupled_lc._deep_timing = previous_model, previous_coupled
                    active = previous
            return wrapped

        def batch_wrapper(original):
            @wraps(original)
            def wrapped(*args, **kwargs):
                nonlocal batch_active
                if not active:
                    return original(*args, **kwargs)
                previous, batch_active = batch_active, True
                previous_coupled, coupled_lc._deep_timing = coupled_lc._deep_timing, None
                try:
                    return timer.call(f'{stage}/rf/batch', original, *args, **kwargs)
                finally:
                    coupled_lc._deep_timing = previous_coupled
                    batch_active = previous
            return wrapped

        def region_wrapper(name):
            def decorate(original):
                @wraps(original)
                def wrapped(*args, **kwargs):
                    if active:
                        if batch_active and name == 'decode':
                            return original(*args, **kwargs)
                        region = 'batch/matrices' if batch_active and name == 'matrices' else name
                        return timer.call(f'{stage}/rf/{region}', original, *args, **kwargs)
                    return original(*args, **kwargs)
                return wrapped
            return decorate

        def batch_matrices_wrapper(original):
            @wraps(original)
            def wrapped(*args, **kwargs):
                if active and batch_active:
                    return timer.call(f'{stage}/rf/batch/matrices', original, *args, **kwargs)
                return original(*args, **kwargs)
            return wrapped

        replace(CoupledLCTopology, '_matrices_lk', batch_matrices_wrapper)
        for method in ('evaluate', 'evaluate_batch', 'evaluate_partial_batch'):
            replace(model.RFEvaluator, method, evaluate_wrapper)
        replace(model.RFEvaluator, '_compute_batch', batch_wrapper)
        for owner, method, name in (
                (model.RFModel, 'decode', 'decode'),
                (CoupledLCTopology, 'port_admittance', 'port_admittance'),
                (CoupledLCTopology, 'node_admittance', 'node_admittance'),
                (CoupledLCTopology, 'matrices', 'matrices'),
                (model, '_cascade', 'cascade'),
                (model, 'power_response', 'power_response')):
            replace(owner, method, region_wrapper(name))
        yield

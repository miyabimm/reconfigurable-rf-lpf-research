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

        def region_wrapper(name):
            def decorate(original):
                @wraps(original)
                def wrapped(*args, **kwargs):
                    if active:
                        return timer.call(f'{stage}/rf/{name}', original, *args, **kwargs)
                    return original(*args, **kwargs)
                return wrapped
            return decorate

        for method in ('evaluate', 'evaluate_batch', 'evaluate_partial_batch'):
            replace(model.RFEvaluator, method, evaluate_wrapper)
        for owner, method, name in (
                (model.RFEvaluator, '_compute_batch', 'batch'),
                (model.RFModel, 'decode', 'decode'),
                (CoupledLCTopology, 'port_admittance', 'port_admittance'),
                (CoupledLCTopology, 'node_admittance', 'node_admittance'),
                (CoupledLCTopology, 'matrices', 'matrices'),
                (model, '_cascade', 'cascade'),
                (model, 'power_response', 'power_response')):
            replace(owner, method, region_wrapper(name))
        yield

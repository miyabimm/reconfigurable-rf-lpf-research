"""Bounded coarse-grid selection helpers, not RF certification or a runner."""
from dataclasses import asdict

import numpy as np

from .optimizer_comparison import sampled_score


class StartSelectionError(ValueError):
    """Fail-closed preparation; partial vectors, exceptions and costs survive."""
    def __init__(self, message, report):
        super().__init__(message)
        self.report = report


class SelectionForward:
    def __init__(self, evaluator, meter, limit, threshold):
        self.original, self.meter = evaluator, meter
        self.limit = None if limit is None else meter.frequency_samples_requested + limit
        self.threshold = threshold
        self.failed = False
        self.score = None

    def __getattr__(self, name):
        return getattr(self.original, name)

    def il(self, vector):
        try:
            if (self.limit is not None and
                    self.meter.frequency_samples_requested + len(self.original.f) > self.limit):
                raise ValueError('Initialization sample budget exhausted before forward')
            il = self.meter.forward(self.original, vector)
            self.score = asdict(sampled_score(il, self.original.role, self.threshold))
            return il
        except BaseException:
            self.failed = True
            raise


def select_pair(starts, bounds):
    """F/V Pareto low-IL anchor, then constraint-side nondominated alternative.

    Remove the anchor before computing the second front (Pareto peeling when
    one point dominates all). Ties prefer normalized distance from the anchor,
    then F, H2/H3 summed deficit and Sobol index. Fixed coordinates contribute
    zero distance. No weighted objective or RF hard cutoff is introduced.
    """
    def front(items):
        return [a for a in items if not any(
            b['score']['worst_il_db'] <= a['score']['worst_il_db'] and
            b['score']['max_violation_db'] <= a['score']['max_violation_db'] and
            (b['score']['worst_il_db'] < a['score']['worst_il_db'] or
             b['score']['max_violation_db'] < a['score']['max_violation_db'])
            for b in items)]

    def f(a):
        s = a['score']
        return (s['worst_il_db'], s['max_violation_db'],
                s['sum_violation_db'], a.get('pool_index', a['sobol_index']))

    candidates = starts[1:]
    anchor = min(front(candidates), key=f)
    width = bounds[:, 1] - bounds[:, 0]
    def distance(a):
        delta = np.asarray(a['vector']) - anchor['vector']
        normalized = np.divide(delta, width, out=np.zeros_like(delta), where=width != 0)
        return float(normalized @ normalized)
    remaining = [a for a in candidates if a is not anchor]
    other = min(front(remaining), key=lambda a: (
        a['score']['max_violation_db'], -distance(a), *f(a)))
    return anchor, other

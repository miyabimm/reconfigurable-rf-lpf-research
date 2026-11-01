"""Minimal forward-only comparison proposal, not a global optimizer/runner.

One instance binds a circuit/policy/grid. It accepts the physical vector only,
checks box/components/SPD/role, then computes external-port sampled F and V.
Invalid points raise, are counted and are never repaired or made feasible.
No EXP export, promotion, adaptive grid or global-search budget is supplied.
"""
from dataclasses import dataclass

import numpy as np

from .evaluation_cost import EvaluationCost
from .sampled_epigraph import SampledEpigraph


@dataclass(frozen=True)
class SampledScore:
    worst_il_db: float
    min_h2_db: float
    min_h3_db: float
    max_violation_db: float
    sum_violation_db: float
    strict_feasible: bool

    def rank_key(self):
        if self.strict_feasible:
            return (0, self.worst_il_db, 0., 0.)
        return (1, self.max_violation_db, self.sum_violation_db, self.worst_il_db)


def sampled_score(il, role, mandatory_stop_db):
    """RF-only strict result; caller must separately establish physical validity.

    Sum violation is the sum of the two regional worst deficits (H2/H3), not
    a sum over samples. Neither rounding, solver tolerance nor nominal targets
    enter this comparison. Scores may only be compared on the same bound grid.
    """
    il, role = np.asarray(il, float), np.asarray(role)
    if (il.ndim != 1 or il.shape != role.shape or not np.all(np.isfinite(il))
            or set(role.tolist()) != {0, 1, 2} or not np.isfinite(mandatory_stop_db)):
        raise ValueError('Expected finite IL and all pass/H2/H3 roles on the same grid')
    worst = float(np.max(il[role == 0]))
    h2, h3 = (float(np.min(il[role == r])) for r in (1, 2))
    deficits = (max(0., mandatory_stop_db - h2), max(0., mandatory_stop_db - h3))
    maximum = max(deficits)
    return SampledScore(worst, h2, h3, maximum, sum(deficits), maximum == 0.)


class PhysicalComparison:
    """Forward-only API proposal; default has no cache, like existing SLSQP.

    Optional exact one-entry cache can share F/V requests, but is NOT a common
    benchmark default until all adapters share an approved cache policy.
    No rounding of cache keys, no caching of failures, no cross-grid/circuit
    reuse. Create separate instances for coarse/fine/read-only validation.
    A solver adapter must handle rejected proposals explicitly, not silently
    convert them into RF scores. This module intentionally supplies no adapter.
    """
    def __init__(self, circuit, points_per_interval, *, cache=False):
        problem = SampledEpigraph(circuit, points_per_interval)
        self.circuit = circuit
        self.evaluator = problem.evaluator
        self.box = problem.box
        self.mandatory_stop_db = problem.mandatory_stop_db
        self.cost = EvaluationCost()
        self.cache = cache
        self._last = None

    def evaluate(self, vector):
        with self.cost.timed():
            x = np.asarray(vector, float)
            bounds = self.box.bounds[:-1]
            if x.shape != (len(bounds),) or not np.all(np.isfinite(x)):
                self.cost.box_rejections += 1
                raise ValueError('Expected complete finite physical vector without epigraph')
            if (any(v < lo or v > hi for v, (lo, hi) in zip(x, bounds)) or
                    any(x[i] <= bounds[i][0] for i in self.box.open_lower)):
                self.cost.box_rejections += 1
                raise ValueError('Physical vector outside box or at excluded open endpoint')
            key = x.tobytes()
            if self.cache and self._last is not None and self._last[0] == key:
                self.cost.cache_hits += 1
                return self._last[1]
            component = self.cost.components(self.circuit, x)
            if component['connection_role_evidence_incomplete']:
                self.cost.role_rejections += 1
                raise ValueError('Declared connection role lacks evidence')
            il = self.cost.forward(self.evaluator, x)
            score = sampled_score(il, self.evaluator.role, self.mandatory_stop_db)
            if self.cache:
                self._last = key, score
            return score

"""Thin, opt-in RF-T008 callbacks for the generic Hybrid/SLP pipeline.

This is a finite-grid development adapter, not an experiment runner or an RF
acceptance gate. Physical/forward errors propagate; no invalid point is repaired.
"""
import numpy as np

from .evaluation_cost import EvaluationCost
from .optimizer_comparison import PhysicalComparison, sampled_score


class RFPipelineAdapter:
    """Bind one nominal trial circuit and all 28 intervals on a fixed grid.

    ``residuals`` uses equal-weight, 1 dB-scaled pass IL and positive harmonic
    shortfalls, for Hybrid's sum of squares. This exploratory penalty is NOT an
    approved RF objective or a feasibility test. ``errors`` is pass IL in dB,
    and ``constraints`` is stop IL minus the mandatory minimum in dB. Thus
    SLP minimizes the signed maximum pass IL subject to sampled stop >= 30 dB.
    The optimizer's constraint tolerance is not an RF acceptance tolerance.
    """
    def __init__(self, circuit, points_per_interval, *, cost_meter=None,
                 for_exploration=False):
        if circuit.policy_id != 'RF-T008':
            raise ValueError('Explicit RF-T008 trial circuit required')
        if type(for_exploration) is not bool:
            raise TypeError('for_exploration must be bool')
        if cost_meter is not None and not isinstance(cost_meter, EvaluationCost):
            raise TypeError('cost_meter must be an EvaluationCost')
        self.comparison = PhysicalComparison(circuit, points_per_interval)
        if cost_meter is not None:
            self.comparison.cost = cost_meter
        self.for_exploration = for_exploration
        self.bounds = self.comparison.box.bounds[:-1]
        self.evaluator = self.comparison.evaluator
        self.cost = self.comparison.cost
        self.mandatory_stop_db = self.comparison.mandatory_stop_db

    def _evaluate(self, vector):
        with self.cost.timed():
            x, component = self.comparison.validate_vector(
                vector, for_exploration=self.for_exploration)
            il = np.asarray(self.cost.forward(self.evaluator, x), dtype=float)
            # Validate finite data and the presence of each role before using it.
            score = sampled_score(il, self.evaluator.role, self.mandatory_stop_db)
            return il, component, score

    def residuals(self, vector):
        il, _, _ = self._evaluate(vector)
        role = self.evaluator.role
        return np.concatenate((il[role == 0],
                               np.maximum(0., self.mandatory_stop_db - il[role != 0])))

    def errors(self, vector):
        il, _, _ = self._evaluate(vector)
        return il[self.evaluator.role == 0]

    def constraints(self, vector):
        il, _, _ = self._evaluate(vector)
        return il[self.evaluator.role != 0] - self.mandatory_stop_db

    def assess(self, vector):
        """Recheck a point strictly; never promote or equate solver success to RF PASS.

        Exploratory absent-GJM or unsupported-role results remain blocked even
        when the RF-only strict finite-grid result passes. Independent validation
        and dense RF always remain not_run here.
        """
        _, component, score = self._evaluate(vector)
        physical = (component['component_policy_pass'] and
                    not component['connection_role_evidence_incomplete'])
        return {'score': score, 'component_policy': component,
                'strict_finite_grid_feasible': bool(physical and score.strict_feasible),
                'candidate_promotion_blocked': True,
                'dense_rf': 'not_run', 'independent_mna': 'not_run',
                'power_balance': 'not_run', 'passivity': 'not_run'}

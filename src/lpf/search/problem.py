"""Explicit numerical callbacks for a fixed RF evaluation stage (physical x)."""
import numpy as np
from lpf.timing import timed_method


class Problem:
    def __init__(self, evaluation):
        self.evaluation = evaluation

    @classmethod
    def from_fixed_stage(cls, evaluation):
        """Thin Stage-4B callbacks; no solver iterations or hidden caching."""
        from .evaluation import FixedStageEvaluation
        if not isinstance(evaluation, FixedStageEvaluation):
            raise TypeError('Expected FixedStageEvaluation')
        return cls(evaluation)

    def objective(self, x):
        return self.evaluation.evaluate(x)['assessment']['worst_il_db']

    @timed_method('solver_callback')
    def residuals(self, x):
        objective = self.objective(x)
        if not np.isfinite(objective) or objective < 0:
            raise ValueError('Squared-residual solver requires finite nonnegative worst IL; no floor')
        return np.array([np.sqrt(objective)])

    @timed_method('solver_callback')
    def errors(self, x):
        return np.array([self.objective(x)])

    @timed_method('solver_callback')
    def constraints(self, x):
        # Preserve legitimate infinities; never floor or clamp them.
        return np.asarray(self.evaluation.evaluate(x)['assessment']['mandatory_g'])

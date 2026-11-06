"""RF core construction and explicit numerical callbacks (physical x only)."""
import numpy as np

def nominal_area(circuit):
    """Policy chip-area accounting only, not physical footprint feasibility."""
    from collections import Counter
    from fractions import Fraction
    p, d = circuit.resolved_policy, circuit.definition
    counts = Counter(d.inductor_types + d.fixed_c_types)
    counts['IC_VARIABLE_C'] = circuit.schema.n_variable
    counts['IC_FIXED_C'] = circuit.schema.n_ic_fixed
    total = Fraction(0)
    for name, count in counts.items():
        if name in ('LQP02HV', 'LQP02HQ'):
            unit = p['components']['LQP02']['series'][name]['area_units']
        elif name == 'IC_FIXED_C':
            unit = p['trial_ic_fixed_c_by_connection']['additional_chip_area_units']
        else:
            spec = p['components'][name]
            unit = spec.get('area_units_fraction', spec.get('area_units'))
        total += count * Fraction(str(unit))
    return {'area_units_fraction': str(total), 'area_units': float(total),
            'installed_counts': dict(counts), 'external_s2p_area': 'excluded_by_policy',
            'layout_feasibility': 'not_verified'}


class Problem:
    def __init__(self, evaluation, points, stage, target):
        self.evaluation, self.points, self.stage, self.target = evaluation, points, stage, target

    @classmethod
    def from_fixed_stage(cls, evaluation):
        """Thin Stage-4B callbacks; no solver iterations or hidden caching."""
        from .evaluation import FixedStageEvaluation
        if not isinstance(evaluation, FixedStageEvaluation):
            raise TypeError('Expected FixedStageEvaluation')
        return cls(evaluation, None, None, None)

    def objective(self, x):
        if self.points is not None:
            raise ValueError('Stage-4B objective requires from_fixed_stage')
        return self.evaluation.evaluate(x)['assessment']['worst_il_db']

    def il(self, x):
        return self.evaluation.forward(x, self.points, self.stage)

    def residuals(self, x):
        if self.points is None:
            objective = self.objective(x)
            if not np.isfinite(objective) or objective < 0:
                raise ValueError('Squared-residual solver requires finite nonnegative worst IL; no floor')
            return np.array([np.sqrt(objective)])
        il = self.il(x)
        role = self.evaluation.grid(self.points).role
        return np.r_[il[role == 0], np.maximum(0., self.target - il[role != 0])]

    def errors(self, x):
        if self.points is None:
            return np.array([self.objective(x)])
        il = self.il(x)
        return il[self.evaluation.grid(self.points).role == 0]

    def constraints(self, x):
        if self.points is None:
            # Preserve legitimate infinities. The caller/solver must explicitly
            # handle unsupported nonfinite callbacks, not floor or clamp them.
            return np.asarray(self.evaluation.evaluate(x)['assessment']['mandatory_g'])
        il = self.il(x)
        return il[self.evaluation.grid(self.points).role != 0] - self.target

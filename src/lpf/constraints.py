"""Canonical policy access, component count limits, and fixed PCB-C checks."""
import math

from .constraint_versions import load_constraint


def load_policy():
    return load_constraint()


def chip_area(n_lqp02=0, n_lqp01=0, n_lqw04=0, n_gjm01=0,
              n_pcb_pattern_c=0):
    """Chip area only: PCB pattern C consumes no chip-package area."""
    return (3*n_lqp02 + 2*n_lqp01 + 9*n_lqw04 + 2*n_gjm01
            + 0*n_pcb_pattern_c)/3


def check_counts(n_lqp02=0, n_lqp01=0, n_lqw04=0, n_gjm01=0,
                 n_pcb=0, n_var=0, n_pcb_pattern_c=0, *, resolved_policy=None):
    """Check component counts; chip area is a Pareto metric, not a cap."""
    counts=(n_lqp02,n_lqp01,n_lqw04,n_gjm01,n_pcb,n_var,n_pcb_pattern_c)
    if any(not isinstance(x,int) or isinstance(x,bool) or x<0 for x in counts):
        return False
    p=load_policy() if resolved_policy is None else resolved_policy
    # Chip area is a Pareto objective, NOT a formal feasibility cap.
    # Trial counts must be checked against that explicit resolved policy.
    return (n_pcb<=p['components']['PCB_L']['max_count_principle']
            and n_var<=p['components']['IC_VARIABLE_C']['max_branches_principle']
            and n_pcb_pattern_c<=p['components']['PCB_PATTERN_C']['max_count'])


def validate_pcb_pattern_caps(values_pf, q_values=None):
    """Validate fixed PCB-pattern C values/Q against the owner-approved policy.

    values_pf must be a sequence of per-component capacitances in pF.
    q_values, if supplied, must contain the corresponding per-component Q.
    PCB pattern C is FIXED; cross-setting invariance is checked separately.
    Each fixed PCB pattern capacitor must be within [0.02, 0.2] pF.
    """
    spec=load_policy()['components']['PCB_PATTERN_C']
    values=tuple(values_pf)
    if len(values)>spec['max_count']:
        raise ValueError('PCB pattern C count exceeds maximum')
    if any(not isinstance(c,(float,int)) or not math.isfinite(c)
           or c<spec['min_pf_per_component']
           or c>spec['max_pf_per_component'] for c in values):
        raise ValueError('PCB pattern C outside approved range or invalid')
    if q_values is not None:
        qs=tuple(q_values)
        if len(qs)!=len(values) or any(
            not isinstance(q,(float,int)) or q!=spec['q'] for q in qs
        ):
            raise ValueError('PCB pattern C Q mismatch')
    return True

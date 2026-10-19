"""Per-shunt-DTC fixed parasitic branches for an explicit Phase 2 trial.

This module does NOT mutate topology/old candidate parameters automatically.
Circuit evaluators must instantiate/stamp each returned branch in the nodal MNA
(or its algebraically equivalent network) and include it in independent checks.
Ground node is 0 in the connection metadata validated by constraint_versions.
"""
import math

from .constraint_versions import validate_variable_c_connections


def shunt_dtc_parasitic_branches(policy, variable_c_branches):
    """Return one additional fixed C/Q branch for each grounded variable C.

    variable_c_branches: [{'a': node, 'b': 0, 'role': 'shunt_to_ground'}, ...]
    Node 0 represents GND (remap any experiment-internal GND=-1 first).
    Non-ground variable C is intentionally excluded. A zero programmed DTC
    capacitance does not remove the associated fixed parasitic branch.
    """
    spec = policy.get("trial_shunt_dtc_parasitic")
    if policy.get("active_constraint_status") != "trial" or not isinstance(spec, dict):
        raise ValueError("Explicit shunt-DTC-parasitic trial policy required")
    validate_variable_c_connections(variable_c_branches, policy)
    parasitics = []
    for index, branch in enumerate(variable_c_branches):
        a, b = branch["a"], branch["b"]
        if a == 0 or b == 0:
            parasitics.append({
                "variable_branch_index": index,
                "node": b if a == 0 else a,
                "ground": 0,
                "capacitance_pf": spec["fixed_capacitance_pf"],
                "q": spec["q"],
                "setting_invariant": True,
            })
    return tuple(parasitics)


def single_parasitic_admittance(policy, frequency_hz):
    """Return the independent C=0.5pF/Q40 branch admittance in siemens.

    Matches the existing EXP-042 lossy-capacitor model:
    Y = omega * (C in farads) / (1/Q - j).
    The variable C/Q35 branch MUST be stamped separately by the caller.
    """
    spec = policy.get("trial_shunt_dtc_parasitic")
    if policy.get("active_constraint_status") != "trial" or not isinstance(spec, dict):
        raise ValueError("Explicit shunt-DTC-parasitic trial policy required")
    if (type(frequency_hz) not in (int, float)
            or not math.isfinite(frequency_hz) or frequency_hz < 0):
        raise ValueError("Frequency must be a nonnegative finite number")
    return (2 * math.pi * frequency_hz * spec["fixed_capacitance_pf"] * 1e-12
            / (1 / spec["q"] - 1j))

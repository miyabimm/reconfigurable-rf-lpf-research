"""Connection-aware fixed PCB capacitor policy for the RF-T008 Phase 2 trial.

Validation node convention: 0 denotes GND (remap experiment-local -1).
This module must be explicitly called by a T008 circuit evaluator: loading
the trial alone cannot retroactively change a legacy fixed-C Q or stamp.
Grounded IC DTC's always-on 0.5pF/Q40 parasitic is NOT a PCB_PATTERN_C.
"""
import math


def validate_trial_pcb_pattern_c_branches(policy, branches):
    """Validate fixed PCB C count, endpoints, capacitance and Q, per connection.

    branches: dicts with a,b (distinct nonnegative int node IDs),
      capacitance_pf (float, pF) and q (float).
    Must be used on the full list of PCB_PATTERN_C branches.
    """
    spec = policy.get("trial_pcb_pattern_c_by_connection")
    if policy.get("active_constraint_status") != "trial" or not isinstance(spec, dict):
        raise ValueError("Explicit connection-aware PCB-C trial policy required")
    if not isinstance(branches, (list, tuple)):
        raise ValueError("PCB C branches must be a sequence")
    if len(branches) > spec["max_count"]:
        raise ValueError("PCB C count exceeds authorized maximum")
    for branch in branches:
        if not isinstance(branch, dict):
            raise ValueError("PCB C branch must be a mapping")
        a, b = branch.get("a"), branch.get("b")
        if (type(a) is not int or type(b) is not int
                or a < 0 or b < 0 or a == b):
            raise ValueError("Invalid fixed PCB C endpoint pair; 0 means ground")
        rule = spec["grounded"] if (a == 0 or b == 0) else spec["non_ground"]
        cap, q = branch.get("capacitance_pf"), branch.get("q")
        if (type(cap) not in (int, float) or not math.isfinite(cap)
                or not rule["min_pf_per_component"] <= cap <= rule["max_pf_per_component"]):
            raise ValueError("PCB C capacitance violates connection-dependent range")
        if type(q) not in (int, float) or not math.isfinite(q) or q != rule["q"]:
            raise ValueError("PCB C Q violates connection-dependent rule")
    return True


def pcb_pattern_c_branch_admittance(policy, branch, frequency_hz):
    """Nominal lossy Y for an RF-T008 fixed PCB-C branch in siemens.

    Formula: omega * C / (1/Q - 1j). Use declared per-branch Q, never a
    global Q40 shortcut for grounded branches. No stamp is performed.
    """
    validate_trial_pcb_pattern_c_branches(policy, [branch])
    if (type(frequency_hz) not in (int, float) or not math.isfinite(frequency_hz)
            or frequency_hz < 0):
        raise ValueError("Frequency must be a nonnegative finite number")
    return (2 * math.pi * frequency_hz * branch["capacitance_pf"] * 1e-12
            / (1 / branch["q"] - 1j))

"""RF-T008 revision 3: at most two DTCs, each with a high-Q IC fixed capacitor.

For EACH installed variable-C branch stamp BOTH separate lossy admittances
on the same two nodes. A fixed IC-C remains at Cvar=0 and is optimized
once, shared across all six LTE settings. Ground ID is 0 here; remap a
circuit's local GND=-1 before calling this module.

Not applicable to old RF-T007 fixed 0.5pF/Q40 grounded DTC parasite.
RF-T008 has replaced that model, NOT appended a second parasitic.
"""
import math

from .constraint_versions import validate_variable_c_connections


def _spec(policy):
    spec = policy.get("trial_ic_fixed_c_by_connection")
    if (policy.get("active_constraint_id") != "RF-T008"
            or policy.get("active_constraint_status") != "trial"
            or not isinstance(spec, dict)
            or "trial_shunt_dtc_parasitic" in policy):
        raise ValueError("Revised RF-T008 trial IC fixed C policy required")
    return spec


def ic_fixed_c_branches(policy, variable_branches, fixed_values_pf):
    """Construct ALL high-Q fixed branches matching installed DTC endpoints.

    Fixed_values_pf: one *setting-invariant* design value per installed DTC.
    Use once per physical design, reuse exactly for every LTE setting.
    Returns ordered stamped fixed branches, each with source DTC index.
    """
    spec = _spec(policy)
    validate_variable_c_connections(variable_branches, policy)
    if not isinstance(fixed_values_pf, (list, tuple)):
        raise ValueError("One fixed IC capacitance per installed DTC is mandatory")
    if len(fixed_values_pf) != len(variable_branches):
        raise ValueError("IC fixed C count must equal installed DTC branch count")
    if len(variable_branches) > spec["max_composite_branches"]:
        raise ValueError("Too many IC variable C branches")
    out = []
    for idx, (branch, cap) in enumerate(zip(variable_branches, fixed_values_pf)):
        rule = (spec["grounded"] if 0 in (branch["a"], branch["b"])
                else spec["non_ground"])
        if (type(cap) not in (int, float) or not math.isfinite(cap)
                or not rule["min_pf_per_branch"] <= cap <= rule["max_pf_per_branch"]):
            raise ValueError("IC fixed C outside approved connection-specific range")
        out.append({"variable_branch_index": idx,
                    "a": branch["a"], "b": branch["b"],
                    "capacitance_pf": cap, "q": spec["fixed_c_q"],
                    "setting_invariant": True,
                    "kind": "IC_FIXED_C"})
    return tuple(out)


def ic_c_pair_admittances(policy, variable_branch, fixed_capacitance_pf,
                          variable_capacitance_pf, frequency_hz):
    """Return two independent lossy terms and total for one composite DTC.

    Return {"fixed": Yfixed, "variable": Yvariable, "total": Ysum}.
    This numerical helper validates capacitances, Q and terminal endpoints;
    the optimizer must also reuse the same fixed capacitance for all modes.
    """
    spec = _spec(policy)
    fixed = ic_fixed_c_branches(policy, [variable_branch], [fixed_capacitance_pf])[0]
    low, high = spec["variable_capacitance_pf_range"]
    if (type(variable_capacitance_pf) not in (int, float)
            or not math.isfinite(variable_capacitance_pf)
            or not low <= variable_capacitance_pf <= high):
        raise ValueError("Variable IC C outside 0..3pF")
    if (type(frequency_hz) not in (int, float)
            or not math.isfinite(frequency_hz) or frequency_hz < 0):
        raise ValueError("Frequency must be nonnegative and finite")
    w = 2 * math.pi * frequency_hz
    yf = w * fixed["capacitance_pf"] * 1e-12 / (1 / spec["fixed_c_q"] - 1j)
    yv = w * variable_capacitance_pf * 1e-12 / (1 / spec["variable_c_q"] - 1j)
    return {"fixed": yf, "variable": yv, "total": yf + yv}


def validate_ic_fixed_c_settings(policy, variable_branches, fixed_values_pf,
                                 variable_pf_by_setting):
    """Check six-setting completeness and common fixed values.

    Rejects an attempt to replace one installed DTC by a standalone IC C.
    The fixed values are specified once, outside per-setting variable data.
    """
    fixed = ic_fixed_c_branches(policy, variable_branches, fixed_values_pf)
    settings = ("B71", "B12", "B28", "B13+B14", "B26", "B8")
    if (not isinstance(variable_pf_by_setting, dict)
            or set(variable_pf_by_setting) != set(settings)):
        raise ValueError("Exactly the six LTE settings are required")
    minvar, maxvar = _spec(policy)["variable_capacitance_pf_range"]
    for setting in settings:
        values = variable_pf_by_setting[setting]
        if not isinstance(values, (list, tuple)) or len(values) != len(fixed):
            raise ValueError("One per-setting variable capacity per installed DTC")
        for cap in values:
            if (type(cap) not in (int, float) or not math.isfinite(cap)
                    or not minvar <= cap <= maxvar):
                raise ValueError("Invalid per-setting IC variable capacitance")
    return True

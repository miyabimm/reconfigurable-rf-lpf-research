"""Shared nominal inductor series and physical coupling checks for Phase 2.

The input coupling matrix contains zeros for all unspecified pairs; the
physical layout and RF constraints decide which nonzero entries are legal.
L is supplied in nH in the circuit vector but checked in SI henries by the
existing independent formal coupling validator.
"""
import numpy as np

from lpf.validation import validate_inductor_coupling


def nominal_inductor_series(policy, name):
    """Return (Q, min_nH, max_nH) only for fully specified series.

    Missing inductor range data is NOT a license to assume a bound.
    """
    components = policy["components"]
    if name in ("LQP02HV", "LQP02HQ"):
        spec = components["LQP02"]["series"][name]
        return (float(spec["q"]), float(spec["min_inductance_nH"]),
                float(spec["max_inductance_nH"]))
    if name == "PCB_L":
        spec = components["PCB_L"]
        return float(spec["q"]), 0.0, float(spec["max_inductance_nh"])
    raise ValueError("No fully specified nominal inductor range for " + str(name))


def nominal_coupling_matrix(topology, values):
    """Explicit symmetric k including zeros at every absent coupling slot."""
    count = len(topology.inductor_tree.edges)
    if len(values.coupling_k) != len(topology.coupling_pairs):
        raise ValueError("Coupling vector and topology slot counts differ")
    K = np.eye(count)
    for (a, b), coeff in zip(topology.coupling_pairs, values.coupling_k):
        K[a, b] = K[b, a] = float(coeff)
    return K


def check_nominal_inductors(policy, topology, values, inductor_types, physical_order):
    """Check type/Q/range/physical order/nominal k/SPD, using current RF rules."""
    types = tuple(inductor_types)
    if len(types) != len(topology.inductor_tree.edges):
        raise ValueError("One explicit inductor type per L branch required")
    if len(values.inductances_nh) != len(types):
        raise ValueError("L vector length mismatch")
    for kind, q, value in zip(types, topology.inductor_q, values.inductances_nh):
        approved_q, minimum, maximum = nominal_inductor_series(policy, kind)
        if q != approved_q or not minimum < value <= maximum:
            # LQP02HV/HQ min_nH is inclusive; PCB_L zero is exclusive.
            if not (q == approved_q and kind != "PCB_L"
                    and minimum <= value <= maximum):
                raise ValueError("L series Q or inductance outside resolved policy")
    return validate_inductor_coupling(
        types, np.asarray(values.inductances_nh, float) * 1e-9,
        nominal_coupling_matrix(topology, values),
        physical_order=tuple(physical_order),
        nominal=True, resolved_policy=policy
    )

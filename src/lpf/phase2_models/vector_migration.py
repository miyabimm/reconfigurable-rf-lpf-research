"""Explicit legacy-to-generic zero-variable-C placeholder migration.

This module is NOT required for ordinary new-EXP circuit definition or
forward evaluation. Only hot-hot absent devices without any IC-fixed-C
or permanent shunt parasitic may be removed, subject to strict checks.
""" 
from dataclasses import dataclass
from .circuit_layout import normalized_capacitor_edge
from .coupled_lc import CircuitValues


@dataclass(frozen=True)
class ZeroBranchProjection:
    """Verified lossless projection of an all-zero legacy DTC slot.

    The tuple does not alias the caller's mutable vector. The projection
    is restricted to topology- and policy-identical T005/T007 circuits
    with zero removed *hot-hot* variable Cs. RF-T008's paired IC-fixed C
    is intentionally not projectable even when Cvar is zero.
    """

    vector: tuple[float, ...]
    kept_variable_indices: tuple[int, ...]
    removed_variable_indices: tuple[int, ...]
    policy_fingerprint: str


def project_zero_variable_branches(source, target, vector, kept_indices):
    """Drop exact-zero DTC placeholders without changing physical circuit.

    Restrict to RF-T005/T007, same approved policy, L/physical layout,
    coupling slots, fixed C branches/types, and constant parasitic edges.
    Reject changes to any installed RF-T007 shunt parasite or RF-T008
    paired IC-fixed-C. The caller remains responsible for independent
    MNA and dense RF verification before any candidate promotion.
    """
    # Local import avoids a cycle with the public facade re-export.
    from .api import NominalCircuit
    if not isinstance(source, NominalCircuit) or not isinstance(target, NominalCircuit):
        raise TypeError("Expected two constructed NominalCircuit instances")
    if (source.policy_id != target.policy_id or
            source.policy_id not in ("RF-T005", "RF-T007") or
            source.policy_fingerprint != target.policy_fingerprint):
        raise ValueError("Projection requires the same approved T005/T007 policy")
    d0, d1 = source.definition, target.definition
    if (d0.inductor_tree != d1.inductor_tree or
            d0.inductor_types != d1.inductor_types or
            d0.physical_order != d1.physical_order or
            d0.coupling_pairs != d1.coupling_pairs or
            d0.fixed_c_types != d1.fixed_c_types or
            d0.capacitor_placement.fixed_edges !=
            d1.capacitor_placement.fixed_edges):
        raise ValueError("Projection cannot change L, k or fixed C topology")
    a, b = source.schema, target.schema
    if (a.n_fixed != b.n_fixed or a.n_inductors != b.n_inductors or
            a.n_coupling != b.n_coupling or
            a.n_ic_fixed or b.n_ic_fixed or
            a.n_variable <= b.n_variable):
        raise ValueError("Not a removable T005/T007 zero-variable placeholder")
    keep = tuple(kept_indices)
    if (len(keep) != b.n_variable or
            any(type(i) is not int or not 0 <= i < a.n_variable for i in keep)
            or len(set(keep)) != len(keep)):
        raise ValueError("Invalid explicit retained-variable index mapping")
    removed = tuple(i for i in range(a.n_variable) if i not in keep)
    # Conservative migration: do not erase a declared physical shunt device.
    # T007 shunts also retain a Q40 parasite even when the variable part is 0.
    if any(-1 in d0.capacitor_placement.variable_edges[i] for i in removed):
        raise ValueError("Only zero-valued hot-hot placeholders may be removed")
    n0 = d0.inductor_tree.node_count
    for destination, origin in enumerate(keep):
        old_edge = d0.capacitor_placement.variable_edges[origin]
        new_edge = d1.capacitor_placement.variable_edges[destination]
        if (normalized_capacitor_edge(old_edge, n0) !=
                normalized_capacitor_edge(new_edge, n0) or
                d0.variable_roles[origin] != d1.variable_roles[destination]):
            raise ValueError("Retained variable C terminal or role changed")
    # Complete equality of the fixed parasite stamps (including Q/location).
    old_const = slice(a.n_fixed + a.n_variable + a.n_ic_fixed, None)
    new_const = slice(b.n_fixed + b.n_variable + b.n_ic_fixed, None)
    if (a.constant_caps_pf != b.constant_caps_pf or
            source.topology.capacitor_edges[old_const] !=
            target.topology.capacitor_edges[new_const] or
            source.topology.capacitor_q[old_const] !=
            target.topology.capacitor_q[new_const]):
        raise ValueError("Projection would remove or alter fixed parasitics")
    values = source.decode(vector)
    nf, nv = a.n_fixed, a.n_variable
    for i in removed:
        if any(row[nf + i] != 0 for row in values.capacitors_pf_by_setting):
            raise ValueError("Removed variable C must be exactly zero in all six settings")
    source.validate_components(vector)
    projected_rows = tuple(
        row[:nf] + tuple(row[nf + index] for index in keep) + row[nf + nv:]
        for row in values.capacitors_pf_by_setting
    )
    projected = CircuitValues(values.inductances_nh, values.coupling_k,
                              projected_rows)
    x = target.encode(projected)
    target.validate_components(x)
    return ZeroBranchProjection(
        tuple(map(float, x)), keep, removed, source.policy_fingerprint
    )

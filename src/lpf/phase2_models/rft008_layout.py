"""Policy-bound RF-T008 v3 capacitor layout and lossy nodal C stamp.

This module is for NEW Phase-2 nominal evaluations only. Legacy EXP source
and archived evidence are unchanged. The IC-fixed and variable capacitors
are separate branches even when their terminal pairs are identical.

Local circuit nodes: 0..N-1; ground=-1. Trial policy dictionaries use
1..N for hot nodes, ground=0. No RF numerical limit is introduced here.
"""
from dataclasses import dataclass

import numpy as np

from lpf.constraint_versions import validate_variable_c_connections
from lpf.trial_ic_fixed_c import (
    ic_fixed_c_branches, validate_ic_fixed_c_settings,
)
from lpf.trial_pcb_pattern_c import validate_trial_pcb_pattern_c_branches
from ._grid import CASES
from .circuit_layout import CapacitorPlacement


def policy_edges(edges, *, roles=None):
    """Remap circuit-local endpoints to 0-ground validator coordinates."""
    if roles is not None and len(roles) != len(edges):
        raise ValueError("One variable-C role per installed variable branch required")
    return tuple({
        "a": a + 1, "b": b + 1,
        **({} if roles is None else {"role": roles[i]}),
    } for i, (a, b) in enumerate(edges))


@dataclass(frozen=True)
class RFT008CapacitorLayout:
    """Immutable ordering, RF-policy Q and bounds for one installed C layout.

    Q order for nodal stamping is [fixed PCB/GJM, variable IC, fixed IC].
    Parameter-vector order is [fixed PCB/GJM, fixed IC, six-setting variable IC].
    The caller keeps the L/k fields and their parameter positions.

    The historical GJM optimization lower bound (0.02 pF) may be
    explicitly supplied as a study bound; by default it is NOT applied
    to the formal component-policy validator.
    """

    placement: CapacitorPlacement
    gjm_positions: tuple[int, ...]
    variable_roles: tuple[str, ...]
    q: tuple[float, ...]
    fixed_bounds_pf: tuple[tuple[float, float], ...]
    ic_fixed_bounds_pf: tuple[tuple[float, float], ...]
    variable_bounds_pf: tuple[float, float]

    @classmethod
    def for_policy(cls, policy, placement, gjm_positions=(),
                   *, variable_roles=None, gjm_lower_pf=None):
        if (policy.get("active_constraint_id") != "RF-T008" or
                policy.get("active_constraint_status") != "trial" or
                "trial_shunt_dtc_parasitic" in policy):
            raise ValueError("RF-T008 v3 resolved trial policy required")
        if not isinstance(placement, CapacitorPlacement):
            raise TypeError("placement must be CapacitorPlacement")
        variable_edges = placement.variable_edges
        if placement.ic_fixed_edges != variable_edges:
            # A reversed branch is a valid physical parallel attachment:
            from .circuit_layout import normalized_capacitor_edge
            if (len(placement.ic_fixed_edges) != len(variable_edges) or
                    any(normalized_capacitor_edge(f, placement.node_count)
                        != normalized_capacitor_edge(v, placement.node_count)
                        for f, v in zip(placement.ic_fixed_edges, variable_edges))):
                raise ValueError("RF-T008 requires a fixed IC C per installed DTC")
        count = len(variable_edges)
        roles = tuple(variable_roles) if variable_roles is not None else tuple(
            "shunt_to_ground" if -1 in edge else "bridge"
            for edge in variable_edges
        )
        variable = policy_edges(variable_edges, roles=roles)
        validate_variable_c_connections(variable, policy)
        spec = policy["trial_ic_fixed_c_by_connection"]
        if count > spec["max_composite_branches"]:
            raise ValueError("RF-T008 v3 permits at most two composite IC-C branches")
        fixed_bounds = tuple(
            (float((spec["grounded"] if -1 in edge else spec["non_ground"])[
                "min_pf_per_branch"]),
             float((spec["grounded"] if -1 in edge else spec["non_ground"])[
                "max_pf_per_branch"]))
            for edge in variable_edges
        )
        # Existing IC policy API additionally validates the one-to-one count
        # and fixed-Q requirement for the specified installed variable edges.
        ic_fixed_c_branches(policy, list(variable),
                            [low for low, _ in fixed_bounds])

        positions = tuple(gjm_positions)
        if (len(set(positions)) != len(positions) or
                any(type(i) is not int or not 0 <= i < len(placement.fixed_edges)
                    for i in positions)):
            raise ValueError("Invalid or duplicate GJM fixed-C index")
        pcb_spec = policy["trial_pcb_pattern_c_by_connection"]
        gjm_spec = policy["components"]["GJM01"]
        if gjm_lower_pf is not None and (
                not np.isfinite(gjm_lower_pf) or gjm_lower_pf <= 0 or
                gjm_lower_pf > gjm_spec["max_pf_per_component"]):
            raise ValueError("Invalid explicit GJM study lower bound")
        fixed_q, fixed_ranges, pcb_dicts = [], [], []
        for index, edge in enumerate(placement.fixed_edges):
            if index in positions:
                fixed_q.append(float(gjm_spec["q"]))
                fixed_ranges.append((0. if gjm_lower_pf is None
                                     else float(gjm_lower_pf),
                                     float(gjm_spec["max_pf_per_component"])))
            else:
                rule = (pcb_spec["grounded"] if -1 in edge
                        else pcb_spec["non_ground"])
                fixed_q.append(float(rule["q"]))
                fixed_ranges.append((float(rule["min_pf_per_component"]),
                                     float(rule["max_pf_per_component"])))
                pcb_dicts.append({
                    **policy_edges((edge,))[0],
                    "capacitance_pf": float(rule["min_pf_per_component"]),
                    "q": float(rule["q"]),
                })
        validate_trial_pcb_pattern_c_branches(policy, pcb_dicts)
        varrange = tuple(float(z) for z in spec["variable_capacitance_pf_range"])
        if len(varrange) != 2 or varrange[0] < 0 or varrange[0] > varrange[1]:
            raise ValueError("Invalid trial variable-C range")
        stamp_q = tuple(fixed_q) + (float(spec["variable_c_q"]),) * count + (
            float(spec["fixed_c_q"]),) * count
        return cls(placement, positions, roles, stamp_q, tuple(fixed_ranges),
                   fixed_bounds, varrange)

    def validate_values(self, policy, fixed_pf, ic_fixed_pf, variable_pf_by_setting):
        """Check a physical six-setting candidate; no optimizer state mutation."""
        f = np.asarray(fixed_pf, dtype=float)
        c = np.asarray(ic_fixed_pf, dtype=float)
        v = np.asarray(variable_pf_by_setting, dtype=float)
        n_fixed = len(self.placement.fixed_edges)
        n_var = len(self.placement.variable_edges)
        if (f.shape != (n_fixed,) or c.shape != (n_var,) or
                v.shape != (len(CASES), n_var) or
                not np.all(np.isfinite(f)) or not np.all(np.isfinite(c)) or
                not np.all(np.isfinite(v))):
            raise ValueError("Invalid fixed/IC/setting C vector shape or values")
        for index, (value, (lo, hi)) in enumerate(zip(f, self.fixed_bounds_pf)):
            if not lo <= value <= hi or (
                    index in self.gjm_positions and value <= 0):
                raise ValueError("Fixed C value outside layout bounds")
        variable = policy_edges(self.placement.variable_edges,
                                roles=self.variable_roles)
        # Explicit current RF-T008 policy validation, including per-connection
        # IC-fixed ranges, six setting completeness and per-branch var limits.
        validate_ic_fixed_c_settings(
            policy, list(variable), list(map(float, c)),
            {name: list(map(float, v[i])) for i, name in enumerate(CASES)}
        )
        return True

    def sampled_admittance(self, omega_rad_s, fixed_pf, ic_fixed_pf,
                           six_setting_var_pf, sampled_setting_indices):
        """Return lossy capacitor admittance (siemens) in placement.edges order.

        Uses the approved Q values per component type and connection.
        The source vector must retain one setting-invariant IC-fixed value
        per DTC, even when all six variable C values equal zero.
        """
        omega = np.asarray(omega_rad_s, dtype=float)
        settings = np.asarray(sampled_setting_indices, dtype=int)
        fixed = np.asarray(fixed_pf, dtype=float)
        ic_fixed = np.asarray(ic_fixed_pf, dtype=float)
        variable = np.asarray(six_setting_var_pf, dtype=float)
        n = len(self.placement.variable_edges)
        nf = len(self.placement.fixed_edges)
        if (omega.ndim != 1 or settings.shape != omega.shape or
                fixed.shape != (nf,) or ic_fixed.shape != (n,) or
                variable.shape != (6, n) or
                np.any(settings < 0) or np.any(settings >= 6) or
                not np.all(np.isfinite(omega)) or np.any(omega < 0) or
                not np.all(np.isfinite(fixed)) or not np.all(np.isfinite(ic_fixed))
                or not np.all(np.isfinite(variable))):
            raise ValueError("Non-finite or mismatched sampled C input")
        capacitance = np.column_stack((
            np.broadcast_to(fixed, (omega.size, nf)),
            variable[settings],
            np.broadcast_to(ic_fixed, (omega.size, n))
        ))
        return (omega[:, None] * 1e-12 * capacitance /
                (1/np.asarray(self.q, float)[None, :] - 1j))

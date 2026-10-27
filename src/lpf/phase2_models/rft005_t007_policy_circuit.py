"""RF-T005 and RF-T007 graph-parametric nominal circuit policy adapters.

The sole T007-vs-T005 difference is the *explicit* one-per-grounded-DTC
constant 0.5pF/Q40 shunt branch. T005 never installs those parasitics;
T008 is a different model with paired IC fixed-C (handled elsewhere).
Source code from historical EXPs is not imported by this module.

Policy/component validity is distinct from six-setting RF attenuation,
independent MNA, optimization convergence, and physical RF validation.
"""
from dataclasses import dataclass
import json

import numpy as np

from lpf.constraint_versions import (
    constraint_fingerprint, load_constraint, validate_variable_c_connections,
)
from lpf.trial_shunt_dtc import shunt_dtc_parasitic_branches
from .circuit_layout import CapacitorPlacement, InductorTree
from .coupled_lc import (
    CircuitValues, CoupledLCTopology, CoupledLCEvaluator, ParameterVectorSchema,
)
from .nominal_inductors import check_nominal_inductors
from .nominal_parts import checked_inductor_metadata, checked_fixed_c_types


def _policy_connections(edges, roles):
    return [
        {"a": a + 1, "b": b + 1, "role": role}
        for (a, b), role in zip(edges, roles)
    ]


@dataclass(frozen=True)
class PolicyBoundRFT005T007Circuit:
    """Immutable nominal component-policy gate and generic forward evaluator.

    Only explicitly documented component series and trial-specific Q,
    C ranges and installed branch counts are accepted. The local validator
    does not determine whether a hot-hot capacitor is physically a "series"
    versus "bridge" component; that role is explicit input metadata and
    requires separate graph-relationship verification before promotion.
    """

    topology: CoupledLCTopology
    schema: ParameterVectorSchema
    placement: CapacitorPlacement
    fixed_c_types: tuple[str, ...]
    variable_roles: tuple[str, ...]
    inductor_types: tuple[str, ...]
    physical_order: tuple[int, ...]
    policy_json: str
    policy_fingerprint: str

    @classmethod
    def from_policy(cls, policy, *, inductor_tree, inductor_types,
                    physical_order, coupling_pairs, capacitor_placement,
                    fixed_c_types, variable_roles):
        if (not isinstance(policy, dict) or
                policy.get("active_constraint_id") not in ("RF-T005", "RF-T007")
                or policy.get("active_constraint_status") != "trial"
                or policy.get("trial_base_constraint_id") != "RF-F003"):
            raise ValueError("Resolved RF-T005 or RF-T007 trial required")
        name = policy["active_constraint_id"]
        approved = load_constraint(name, allow_trial=True)
        if constraint_fingerprint(policy) != constraint_fingerprint(approved):
            raise ValueError("Resolved trial differs from approved registry")
        is_t007 = name == "RF-T007"
        if (is_t007 != ("trial_shunt_dtc_parasitic" in policy) or
                "trial_ic_fixed_c_by_connection" in policy or
                policy["trial_variable_c_layout"].get("branch_count") != 3):
            raise ValueError("Incorrect RF-T005/T007 variable-C/parasitic trial")
        if not isinstance(inductor_tree, InductorTree):
            raise TypeError("inductor_tree must be InductorTree")
        if not isinstance(capacitor_placement, CapacitorPlacement):
            raise TypeError("capacitor_placement must be CapacitorPlacement")
        p = capacitor_placement
        if (p.node_count != inductor_tree.node_count or p.ic_fixed_edges):
            raise ValueError("T005/T007 cannot install composite IC-fixed C")
        types, order, L_q = checked_inductor_metadata(
            policy, inductor_tree, inductor_types, physical_order
        )
        c_types = checked_fixed_c_types(p.fixed_edges, fixed_c_types)
        roles = tuple(variable_roles)
        if len(roles) != len(p.variable_edges):
            raise ValueError("Explicit role per installed variable C required")
        variable_branches = _policy_connections(p.variable_edges, roles)
        validate_variable_c_connections(variable_branches, policy)
        parasitic_edges = ()
        constants = ()
        qpar = ()
        if is_t007:
            extras = shunt_dtc_parasitic_branches(policy, variable_branches)
            # Each grounded variable branch gets precisely one permanent
            # 0.5pF/Q40 shunt at the same hot node, including when Cv=0.
            parasitic_edges = tuple((int(extra["node"])-1, -1) for extra in extras)
            constants = tuple(float(extra["capacitance_pf"]) for extra in extras)
            qpar = tuple(float(extra["q"]) for extra in extras)
        pcb_spec = policy["components"]["PCB_PATTERN_C"]
        gjm_spec = policy["components"]["GJM01"]
        if c_types.count("PCB_PATTERN_C") > pcb_spec["max_count"]:
            raise ValueError("Too many PCB pattern capacitors")
        fixed_q = tuple(float(gjm_spec["q"]) if kind == "GJM01"
                        else float(pcb_spec["q"]) for kind in c_types)
        var_q = (float(policy["components"]["IC_VARIABLE_C"]["q"]),) * len(p.variable_edges)
        topology = CoupledLCTopology(
            inductor_tree, tuple(coupling_pairs), L_q,
            p.fixed_edges + p.variable_edges + parasitic_edges,
            fixed_q + var_q + qpar
        )
        schema = ParameterVectorSchema(
            len(inductor_tree.edges), len(p.fixed_edges),
            len(topology.coupling_pairs), 0, len(p.variable_edges), constants
        )
        snapshot = json.dumps(policy, sort_keys=True, ensure_ascii=False,
                              allow_nan=False, separators=(",", ":"))
        return cls(topology, schema, p, c_types, roles, types, order,
                   snapshot, constraint_fingerprint(policy))

    @property
    def policy(self):
        return json.loads(self.policy_json)

    def validate_candidate(self, vector):
        """Fail closed on specified component limits; never claim RF PASS."""
        values = (vector if isinstance(vector, CircuitValues)
                  else self.schema.decode(vector))
        self.schema.encode(values)
        policy = self.policy
        if constraint_fingerprint(policy) != self.policy_fingerprint:
            raise ValueError("Policy fingerprint mismatch")
        coupling = check_nominal_inductors(
            policy, self.topology, values,
            self.inductor_types, self.physical_order
        )
        cf = values.capacitors_pf_by_setting[0][:self.schema.n_fixed]
        pcbs = policy["components"]["PCB_PATTERN_C"]
        gjms = policy["components"]["GJM01"]
        for kind, cap in zip(self.fixed_c_types, cf):
            if kind == "PCB_PATTERN_C":
                if not pcbs["min_pf_per_component"] <= cap <= pcbs["max_pf_per_component"]:
                    raise ValueError("PCB fixed C outside approved range")
            elif kind == "GJM01":
                if not 0 < cap <= gjms["max_pf_per_component"]:
                    raise ValueError("GJM fixed C must be positive and <= approved max")
            else:
                raise ValueError("Unsupported fixed-C type")
        nv = self.schema.n_variable
        low = policy["components"]["IC_VARIABLE_C"]["min_total_variable_pf_per_branch"]
        high = policy["components"]["IC_VARIABLE_C"]["max_total_variable_pf_per_branch"]
        for row in values.capacitors_pf_by_setting:
            if any(not low <= v <= high for v in
                   row[self.schema.n_fixed:self.schema.n_fixed + nv]):
                raise ValueError("Variable C outside approved 0..3pF")
        validate_variable_c_connections(
            _policy_connections(self.placement.variable_edges, self.variable_roles),
            policy
        )
        return {
            "component_policy_pass": True,
            "constraint_id": policy["active_constraint_id"],
            "constraint_fingerprint": self.policy_fingerprint,
            "checked_settings": len(values.capacitors_pf_by_setting),
            "installed_variable_c_branches": nv,
            "installed_shunt_parasites": len(self.schema.constant_caps_pf),
            "min_L_eigenvalue_H": coupling["min_inductance_eigenvalue"],
            "rf_performance_checked": False,
            "independent_mna_checked": False,
            "physical_q_srf_em_checked": False,
        }

    def evaluator(self, points):
        return CoupledLCEvaluator(self.policy, points, self.topology, self.schema)

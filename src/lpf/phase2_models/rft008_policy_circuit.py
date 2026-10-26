"""Fail-closed RF-T008 v3 nominal component / placement policy boundary.

NEW Phase-2 candidates must explicitly opt in to this resolved trial model.
The resulting object is immutable and retains an unmodifiable policy snapshot.
It validates *component and connection constraints*, not RF attenuation,
optimizer convergence, independent MNA, physical Q(f), SRF, EM or tolerance.

Local graph nodes 0..N-1, ground -1; L values nH, C values pF. Existing
lpf.validation.validate_inductor_coupling uses SI henries, hence explicit
1e-9 conversion below. Historical EXP checkpoints are not modified.
"""
from dataclasses import dataclass
import json

import numpy as np

from lpf.constraint_versions import constraint_fingerprint, load_constraint
from .nominal_inductors import nominal_inductor_series, check_nominal_inductors
from .circuit_layout import CapacitorPlacement, InductorTree
from .coupled_lc import (
    CircuitValues, CoupledLCTopology, CoupledLCEvaluator, ParameterVectorSchema,
)
from .rft008_layout import RFT008CapacitorLayout


@dataclass(frozen=True)
class PolicyBoundRFT008Circuit:
    """Immutable policy-bound network ready for *checked* nominal evaluation.

    A bare CoupledLCEvaluator remains numerically usable without constraints
    by design (for frozen historical parity). New-candidate callers should
    use validate_candidate or checked_summary before saving/selecting designs.
    """

    topology: CoupledLCTopology
    schema: ParameterVectorSchema
    capacitor_layout: RFT008CapacitorLayout
    inductor_types: tuple[str, ...]
    physical_order: tuple[int, ...]
    policy_json: str
    policy_fingerprint: str

    @classmethod
    def from_policy(cls, policy, *, inductor_tree, inductor_types,
                    physical_order, coupling_pairs, capacitor_placement,
                    fixed_c_types, variable_roles):
        if (not isinstance(policy, dict) or
                policy.get("active_constraint_id") != "RF-T008" or
                policy.get("active_constraint_status") != "trial" or
                policy.get("trial_base_constraint_id") != "RF-F003" or
                "trial_shunt_dtc_parasitic" in policy):
            raise ValueError("Explicit resolved RF-T008 v3 trial required")
        # A user-supplied dictionary with forged RF-T008 labels is not an
        # approved constraint revision. Compare against the current resolved
        # registry content; the fingerprint in the report is provenance data,
        # not a substitute for this authorization check.
        approved = load_constraint("RF-T008", allow_trial=True)
        if constraint_fingerprint(policy) != constraint_fingerprint(approved):
            raise ValueError("Resolved RF-T008 policy differs from approved registry")
        spec = policy.get("trial_ic_fixed_c_by_connection")
        if (not isinstance(spec, dict) or
                spec.get("max_composite_branches") != 2 or
                policy.get("trial_variable_c_layout", {}).get("branch_count") != 2):
            raise ValueError("RF-T008 revision 3, maximum two DTCs required")
        if not isinstance(inductor_tree, InductorTree):
            raise TypeError("inductor_tree must be InductorTree")
        if not isinstance(capacitor_placement, CapacitorPlacement):
            raise TypeError("capacitor_placement must be CapacitorPlacement")
        if inductor_tree.node_count != capacitor_placement.node_count:
            raise ValueError("L and C circuit node counts differ")
        types = tuple(inductor_types)
        if len(types) != len(inductor_tree.edges):
            raise ValueError("One explicit inductor series per physical L required")
        ql = tuple(nominal_inductor_series(policy, kind)[0] for kind in types)
        order = tuple(physical_order)
        chips = tuple(i for i, kind in enumerate(types) if kind != "PCB_L")
        if (len(order) != len(chips) or set(order) != set(chips) or
                any(type(i) is not int for i in order)):
            raise ValueError("Physical chip order must list each chip L exactly once")
        fixed_types = tuple(fixed_c_types)
        if (len(fixed_types) != len(capacitor_placement.fixed_edges) or
                any(kind not in ("GJM01", "PCB_PATTERN_C")
                    for kind in fixed_types)):
            raise ValueError("Fixed C requires explicit GJM01/PCB_PATTERN_C type")
        positions = tuple(i for i, kind in enumerate(fixed_types)
                          if kind == "GJM01")
        var_roles = tuple(variable_roles)
        if len(var_roles) != len(capacitor_placement.variable_edges):
            raise ValueError("Explicit variable-C roles required")
        layout = RFT008CapacitorLayout.for_policy(
            policy, capacitor_placement, positions, variable_roles=var_roles
        )
        topo = CoupledLCTopology(
            inductor_tree, tuple(coupling_pairs), ql,
            capacitor_placement.edges, layout.q
        )
        schema = ParameterVectorSchema(
            len(inductor_tree.edges), len(capacitor_placement.fixed_edges),
            len(topo.coupling_pairs), len(capacitor_placement.ic_fixed_edges),
            len(capacitor_placement.variable_edges)
        )
        policy_json = json.dumps(policy, ensure_ascii=False, sort_keys=True,
                                 separators=(",", ":"), allow_nan=False)
        circuit = cls(topo, schema, layout, types, order,
                      policy_json, constraint_fingerprint(policy))
        # Verify structural type/physical-order admissibility even before a
        # design vector exists. Candidate L/k ranges checked separately.
        return circuit

    @property
    def policy(self):
        """Return a fresh snapshot: callers cannot change retained RF rules."""
        return json.loads(self.policy_json)

    def validate_candidate(self, vector):
        """Validate nominal component/Q/k/layout and six setting values.

        This check neither calls nor replaces independent MNA. The returned
        state explicitly leaves sampled/dense RF performance unverified.
        """
        values = (vector if isinstance(vector, CircuitValues)
                  else self.schema.decode(vector))
        # For typed values as well as flat vectors, guarantee six setting
        # invariance and the exact fixed/variable/IC-C parameter ordering.
        self.schema.encode(values)
        policy = self.policy
        if constraint_fingerprint(policy) != self.policy_fingerprint:
            raise ValueError("Resolved RF policy fingerprint mismatch")
        # Reuse the same RF physical-L checks for T005/T007/T008.
        coupling = check_nominal_inductors(
            policy, self.topology, values,
            self.inductor_types, self.physical_order
        )
        nf = self.schema.n_fixed
        nv = self.schema.n_variable
        ni = self.schema.n_ic_fixed
        fixed = values.capacitors_pf_by_setting[0][:nf]
        ic_fixed = values.capacitors_pf_by_setting[0][nf + nv:nf + nv + ni]
        variable = np.asarray([
            row[nf:nf + nv] for row in values.capacitors_pf_by_setting
        ], dtype=float)
        self.capacitor_layout.validate_values(
            policy, fixed, ic_fixed, variable
        )
        return {
            "component_policy_pass": True,
            "constraint_id": policy["active_constraint_id"],
            "constraint_fingerprint": self.policy_fingerprint,
            "min_L_eigenvalue_H": coupling["min_inductance_eigenvalue"],
            "checked_settings": len(values.capacitors_pf_by_setting),
            "installed_variable_c_branches": nv,
            "rf_performance_checked": False,
            "independent_mna_checked": False,
            "physical_q_srf_em_checked": False,
        }

    def evaluator(self, points):
        """Construct generic forward sampled evaluator with this RF policy."""
        return CoupledLCEvaluator(
            self.policy, points, self.topology, self.schema
        )

    def checked_summary(self, vector, points=3):
        """Return policy evidence and *finite-grid* RF metrics separately.

        Attenuation/insertion-loss numerical metrics are not interpreted as
        globally verified RF compliance or an independent MNA result.
        """
        component = self.validate_candidate(vector)
        metrics = self.evaluator(points).summary(vector)
        return {"component_policy": component,
                "sampled_forward_metrics": metrics,
                "points_per_interval": int(points),
                "independent_mna_checked": False,
                "rf_compliance_certified": False}

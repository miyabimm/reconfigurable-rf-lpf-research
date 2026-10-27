"""Stable, EXP-independent Phase-2 nominal circuit construction API.

Public users supply one immutable circuit definition and one currently
approved resolved RF trial. Trial-specific C behavior stays behind the
builder. Numerical forward IL, component-policy checks, and independent
MNA validation are distinct operations.

Supported here: RF-T005 / RF-T007 / RF-T008 v3.
RF-F003 and RF-T006 are intentionally rejected until their own policy
adapters are reviewed; never silently reinterpret them as another trial.
"""
from dataclasses import dataclass

from .circuit_layout import InductorTree, CapacitorPlacement, normalized_capacitor_edge
from .rft005_t007_policy_circuit import PolicyBoundRFT005T007Circuit
from .rft008_policy_circuit import PolicyBoundRFT008Circuit
from .role_audit import audit_variable_connection_roles


@dataclass(frozen=True)
class CircuitDefinition:
    """Ordered electrical and physical configuration, without C/L values.

    The physical chip order is a permutation of chip-inductor indices,
    *not* the orientation of electrical L-tree edges. The signed coupling
    slot order is the parameter vector's k order. Each C connection role
    is explicit; bridge-versus-series classification is not yet inferred
    from a physical layout or independently proved by this definition.
    """

    inductor_tree: InductorTree
    inductor_types: tuple[str, ...]
    physical_order: tuple[int, ...]
    coupling_pairs: tuple[tuple[int, int], ...]
    capacitor_placement: CapacitorPlacement
    fixed_c_types: tuple[str, ...]
    variable_roles: tuple[str, ...]

    def __post_init__(self):
        if not isinstance(self.inductor_tree, InductorTree):
            raise TypeError("inductor_tree must be InductorTree")
        if not isinstance(self.capacitor_placement, CapacitorPlacement):
            raise TypeError("capacitor_placement must be CapacitorPlacement")
        if self.inductor_tree.node_count != self.capacitor_placement.node_count:
            raise ValueError("L and C nodes must agree")
        # Coerce caller-owned sequences into immutable, snapshot-like tuples.
        # Actual allowed component types, k roles, bounds and branch counts
        # are checked by the approved trial-specific policy adapter.
        for key in ("inductor_types", "physical_order", "fixed_c_types",
                    "variable_roles"):
            object.__setattr__(self, key, tuple(getattr(self, key)))
        object.__setattr__(self, "coupling_pairs",
                           tuple(tuple(pair) for pair in self.coupling_pairs))


@dataclass(frozen=True)
class NominalCircuit:
    """One public interface for all supported Phase-2 trial models.

    Do not interpret numerical IL or successful component validation as
    independent MNA or complete RF/physical acceptance.
    """

    _adapter: object
    definition: CircuitDefinition

    @property
    def policy_id(self):
        return self._adapter.policy["active_constraint_id"]

    @property
    def policy_fingerprint(self):
        return self._adapter.policy_fingerprint

    @property
    def topology(self):
        return self._adapter.topology

    @property
    def schema(self):
        return self._adapter.schema

    def decode(self, vector):
        return self.schema.decode(vector)

    def encode(self, values):
        return self.schema.encode(values)

    def connection_role_audit(self):
        """Report which declared variable-C roles the L graph can prove.

        The L spanning tree proves grounded and hot-hot chord connectivity.
        A declared 'series' placement needs independent physical/main-path
        evidence before candidate promotion; it is not rejected as an RF
        policy violation merely because this graph lacks that extra proof.
        """
        d = self.definition
        return audit_variable_connection_roles(
            d.inductor_tree, d.capacitor_placement.variable_edges,
            d.variable_roles
        ).as_dict()

    def validate_components(self, vector):
        """Separate component-policy pass from physical-role evidence."""
        result = dict(self._adapter.validate_candidate(vector))
        roles = self.connection_role_audit()
        result["connection_role_audit"] = roles
        result["connection_role_promotion_blocked"] = not roles["all_verified"]
        blockers = ["independent_mna_not_checked", "dense_rf_not_checked"]
        if not roles["all_verified"]:
            blockers.append("connection_role_unverified")
        result["promotion_blockers"] = tuple(blockers)
        # A Stage-1 component check MUST NEVER authorize final candidate
        # promotion: the Stage-2 independent MNA and dense RF gate have
        # not run even when all electrical C roles are checked.
        result["candidate_promotion_blocked"] = True
        return result

    def evaluate_sampled(self, vector, *, points_per_interval=3):
        """Evaluate sampled forward IL after policy checking; NOT RF PASS."""
        component = self.validate_components(vector)
        metrics = self.forward_evaluator(points_per_interval).summary(vector)
        return {
            "component_policy": component,
            "sampled_forward_metrics": metrics,
            "points_per_interval": int(points_per_interval),
            "independent_mna_checked": False,
            "rf_compliance_certified": False,
            "candidate_promotion_blocked": component[
                "candidate_promotion_blocked"
            ],
        }

    def forward_evaluator(self, points_per_interval):
        """Unchecked forward kernel for numerical/optimization work only.

        Optimization iterates may temporarily violate component limits;
        results MUST pass validate_components and independent verification
        before any candidate can be recorded or compared.
        """
        return self._adapter.evaluator(points_per_interval)


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
    from .coupled_lc import CircuitValues
    projected = CircuitValues(values.inductances_nh, values.coupling_k,
                              projected_rows)
    x = target.encode(projected)
    target.validate_components(x)
    return ZeroBranchProjection(
        tuple(map(float, x)), keep, removed, source.policy_fingerprint
    )


def build_nominal_circuit(policy, definition):
    """Construct an approved, policy-bound nominal model from circuit data.

    This is the supported entry point for NEW EXPs. It has no historical
    EXP import, no global-graph patching and no automatic optimization.
    """
    if not isinstance(definition, CircuitDefinition):
        raise TypeError("Expected CircuitDefinition")
    if not isinstance(policy, dict):
        raise TypeError("Expected a resolved RF constraint dictionary")
    constraint_id = policy.get("active_constraint_id")
    common = {
        "inductor_tree": definition.inductor_tree,
        "inductor_types": definition.inductor_types,
        "physical_order": definition.physical_order,
        "coupling_pairs": definition.coupling_pairs,
        "capacitor_placement": definition.capacitor_placement,
        "fixed_c_types": definition.fixed_c_types,
        "variable_roles": definition.variable_roles,
    }
    if constraint_id in ("RF-T005", "RF-T007"):
        backend = PolicyBoundRFT005T007Circuit.from_policy(policy, **common)
    elif constraint_id == "RF-T008":
        backend = PolicyBoundRFT008Circuit.from_policy(policy, **common)
    else:
        raise ValueError("No reviewed Stage-1 nominal adapter for " +
                         str(constraint_id))
    return NominalCircuit(backend, definition)

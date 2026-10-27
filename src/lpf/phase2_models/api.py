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

from .circuit_layout import InductorTree, CapacitorPlacement
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
        result["connection_role_evidence_incomplete"] = not roles[
            "all_declared_roles_supported_by_l_tree"
        ]
        blockers = ["independent_mna_not_checked", "dense_rf_not_checked"]
        if result["connection_role_evidence_incomplete"]:
            blockers.append("declared_role_not_proven_by_l_tree")
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

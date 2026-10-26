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

    def validate_components(self, vector):
        """Check all covered component/k and six-setting values, not RF IL."""
        return self._adapter.validate_candidate(vector)

    def evaluate_sampled(self, vector, *, points_per_interval=3):
        """Validate first, then return sampled metrics with explicit caveats."""
        return self._adapter.checked_summary(vector, points=points_per_interval)

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
    return NominalCircuit(backend)

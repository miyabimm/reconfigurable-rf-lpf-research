"""Stable, EXP-independent Phase-2 nominal circuit construction API.

Public users supply one immutable circuit definition and one currently
approved resolved RF trial. Trial-specific C behavior stays behind the
builder. Numerical forward IL, component-policy checks, and independent
MNA validation are distinct operations.

Supported: RF-F003 and explicit RF-T005/T006/T007/T008 v3 trials.
T006 retains its additional performance requirement, not a different forward.
"""
from dataclasses import dataclass
from copy import deepcopy

from lpf.topology_management import CircuitDefinition, InductorTree, CapacitorPlacement
from .rft005_t007_policy_circuit import PolicyBoundRFT005T007Circuit
from .rft008_policy_circuit import PolicyBoundRFT008Circuit
from .role_audit import audit_variable_connection_roles


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
    def resolved_policy(self):
        """Return a defensive copy of the approved trial policy snapshot."""
        return deepcopy(self._adapter.policy)

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

    def validate_components(self, vector, *, allow_absent_gjm=False):
        """Shared closed physical check; never authorize RF promotion."""
        # Compatibility-only reverse dependency retained: the legacy adapter's
        # coupling tolerance is not the exact closed-box acceptance contract.
        # Do not weaken endpoint rejection just to remove this import (#323).
        from lpf.search.component_constraints import validate_values
        if allow_absent_gjm:
            raise ValueError('Absent GJM requires an explicit topology change, not a bounds exception')
        return validate_values(self.definition, self.schema, vector, self.resolved_policy)

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

    def forward_evaluator(self, points_per_interval, *, extra_frequencies=()):
        """Unchecked forward kernel for numerical/optimization work only.

        Optimization iterates may temporarily violate component limits;
        results MUST pass validate_components and independent verification
        before any candidate can be recorded or compared.
        """
        return self._adapter.evaluator(points_per_interval, extra_frequencies=extra_frequencies)


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
    if constraint_id in ('RF-F003', 'RF-T005', 'RF-T006', 'RF-T007'):
        backend = PolicyBoundRFT005T007Circuit.from_policy(policy, **common)
    elif constraint_id == "RF-T008":
        backend = PolicyBoundRFT008Circuit.from_policy(policy, **common)
    else:
        raise ValueError("No reviewed Stage-1 nominal adapter for " +
                         str(constraint_id))
    return NominalCircuit(backend, definition)

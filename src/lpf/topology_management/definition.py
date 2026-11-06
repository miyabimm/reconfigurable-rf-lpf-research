"""Immutable value-free circuit definition."""
from dataclasses import dataclass
from .circuit_layout import InductorTree, CapacitorPlacement


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



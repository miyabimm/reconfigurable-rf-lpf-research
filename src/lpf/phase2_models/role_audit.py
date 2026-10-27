"""Electrical connection-role evidence for NEW Phase-2 C layouts.

A connected hot-node inductor tree lets us verify: (a) a ground-shunt
branch reaches ground; and (b) a hot-hot C is a chord across an existing
inductive path. It CANNOT prove the physical/main-path designation of a
'series' capacitor. Do not silently convert a declared series role into
a bridge or claim a complete physical layout proof.

This audit is deliberately orthogonal to validate_variable_c_connections:
the latter decides whether the resolved RF policy permits the declared
branch and role; this module reports what the *L graph* actually proves.
"""
from dataclasses import dataclass

from .circuit_layout import InductorTree, _edges


@dataclass(frozen=True)
class ConnectionRoleEvidence:
    """One ordered C branch; no implication of RF or physical feasibility."""

    edge: tuple[int, int]
    declared_role: str
    electrical_class: str
    evidence: str
    declared_role_supported_by_l_tree: bool


@dataclass(frozen=True)
class ConnectionRoleAudit:
    """Electrical L-tree report only; no physical-layout certification."""

    branches: tuple[ConnectionRoleEvidence, ...]

    @property
    def all_declared_roles_supported_by_l_tree(self):
        return all(item.declared_role_supported_by_l_tree for item in self.branches)

    @property
    def unsupported_role_indices(self):
        return tuple(i for i, b in enumerate(self.branches)
                     if not b.declared_role_supported_by_l_tree)

    def as_dict(self):
        return {
            "all_declared_roles_supported_by_l_tree":
                self.all_declared_roles_supported_by_l_tree,
            "unsupported_role_indices": self.unsupported_role_indices,
            "physical_layout_checked": False,
            "branches": tuple({
                "edge": b.edge,
                "declared_role": b.declared_role,
                "electrical_class": b.electrical_class,
                "evidence": b.evidence,
                "declared_role_supported_by_l_tree":
                    b.declared_role_supported_by_l_tree,
            } for b in self.branches)
        }


def audit_variable_connection_roles(inductor_tree, variable_edges, roles):
    """Audit declared shunt/bridge/series roles against a hot-node L tree.

    For a tree, any hot-hot capacitor adds a chord: its two terminals
    already have a unique path through L branches. That is enough to
    establish a bridging *electrical path*, not a manufacturing claim.
    'Series' remains unverified because a spanning-L-tree model alone
    cannot establish insertion into a mandatory signal path. A future
    path-aware physical topology model must supply that separate proof.
    """
    if not isinstance(inductor_tree, InductorTree):
        raise TypeError("Expected InductorTree")
    edges = _edges(variable_edges, inductor_tree.node_count,
                   ground_allowed=True)
    roles = tuple(roles)
    if len(roles) != len(edges):
        raise ValueError("One role per installed variable-C branch required")

    results = []
    for edge, role in zip(edges, roles):
        grounded = -1 in edge
        if grounded:
            if role != "shunt_to_ground":
                raise ValueError("Grounded C must declare shunt_to_ground")
            results.append(ConnectionRoleEvidence(
                edge, role, "shunt_to_ground",
                "verified_ground_endpoint", True
            ))
        else:
            if role not in ("bridge", "series"):
                raise ValueError("Hot-hot C must declare bridge or series")
            if role == "bridge":
                results.append(ConnectionRoleEvidence(
                    edge, role, "inductor_tree_chord",
                    "verified_L_path_between_terminals", True
                ))
            else:
                results.append(ConnectionRoleEvidence(
                    edge, role, "inductor_tree_chord",
                    "series_path_not_provable_from_spanning_L_tree", False
                ))
    return ConnectionRoleAudit(tuple(results))

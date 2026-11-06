"""Immutable topology/branch placement inputs for new Phase-2 evaluators.

Nodes are zero based, ground is -1.  An inductor's edge orientation is
electrically significant when its mutual-coupling sign is specified; do not
sort or silently reverse inductor edges.  Capacitor orientation is irrelevant
to its symmetric admittance stamp.

These structural checks do NOT replace RF policy, fixed-S2P verification,
independent branch-current MNA, or numerical feasibility checks.
"""
from dataclasses import dataclass

import numpy as np


def _edges(items, node_count, *, ground_allowed):
    if type(node_count) is not int or node_count < 2:
        raise ValueError("node_count must be an integer >= 2")
    result = []
    for item in items:
        try:
            a, b = item
        except (TypeError, ValueError) as exc:
            raise ValueError("Each branch must have exactly two endpoints") from exc
        if (type(a) is not int or type(b) is not int or a == b
                or a < (-1 if ground_allowed else 0)
                or b < (-1 if ground_allowed else 0)
                or a >= node_count or b >= node_count):
            raise ValueError("Invalid branch endpoints")
        result.append((a, b))
    return tuple(result)


def normalized_capacitor_edge(edge, node_count):
    """Return the undirected capacitor edge, using (hot, -1) for shunts."""
    a, b = _edges((edge,), node_count, ground_allowed=True)[0]
    return (b, -1) if a == -1 else ((a, -1) if b == -1 else tuple(sorted((a, b))))


def incidence_matrix(edges, node_count):
    """Return a fresh node-by-branch matrix, retaining each branch orientation."""
    pairs = _edges(edges, node_count, ground_allowed=True)
    B = np.zeros((node_count, len(pairs)), dtype=float)
    for j, (a, b) in enumerate(pairs):
        if a >= 0:
            B[a, j] = 1.0
        if b >= 0:
            B[b, j] = -1.0
    return B


@dataclass(frozen=True)
class InductorTree:
    """Connected, orientation-preserving n-1 branch L tree over hot nodes.

    The order of edges is the order of the L vector and coupling-matrix axes.
    Physical chip order and allowed coupling strengths are separate RF-policy
    inputs; this class does not infer them from the electrical tree.
    """

    node_count: int
    edges: tuple[tuple[int, int], ...]
    source_node: int = 0
    load_node: int = 2

    def __post_init__(self):
        pairs = _edges(self.edges, self.node_count, ground_allowed=False)
        if (type(self.source_node) is not int or
                type(self.load_node) is not int or
                self.source_node == self.load_node or
                not 0 <= self.source_node < self.node_count or
                not 0 <= self.load_node < self.node_count):
            raise ValueError("Invalid source/load nodes")
        if len(pairs) != self.node_count - 1:
            raise ValueError("An inductor tree requires node_count - 1 branches")
        if len({frozenset(edge) for edge in pairs}) != len(pairs):
            raise ValueError("Duplicate inductor connection")
        adjacency = [set() for _ in range(self.node_count)]
        for a, b in pairs:
            adjacency[a].add(b)
            adjacency[b].add(a)
        reached = {self.source_node}
        pending = [self.source_node]
        while pending:
            for neighbor in adjacency[pending.pop()] - reached:
                reached.add(neighbor)
                pending.append(neighbor)
        if len(reached) != self.node_count:
            raise ValueError("Inductor graph must be connected")
        object.__setattr__(self, "edges", pairs)

    def incidence(self):
        return incidence_matrix(self.edges, self.node_count)


@dataclass(frozen=True)
class CapacitorPlacement:
    """Ordered fixed/variable/composite-C connections, without capacitance values.

    Each IC-fixed branch (if provided) must parallel its corresponding variable
    branch. For RF-T007 use no IC-fixed branches; for RF-T008 v3 provide one
    IC-fixed edge per installed variable edge. The validated RF policy decides
    branch-count caps, Q and capacitance limits, not this structure.
    """

    node_count: int
    fixed_edges: tuple[tuple[int, int], ...] = ()
    variable_edges: tuple[tuple[int, int], ...] = ()
    ic_fixed_edges: tuple[tuple[int, int], ...] = ()

    def __post_init__(self):
        for name in ("fixed_edges", "variable_edges", "ic_fixed_edges"):
            object.__setattr__(
                self, name, _edges(getattr(self, name), self.node_count,
                                   ground_allowed=True)
            )
        if self.ic_fixed_edges:
            if len(self.variable_edges) != len(self.ic_fixed_edges):
                raise ValueError("IC-fixed C branches must match variable C branches")
            for fixed, variable in zip(self.ic_fixed_edges, self.variable_edges):
                if normalized_capacitor_edge(fixed, self.node_count) != (
                        normalized_capacitor_edge(variable, self.node_count)):
                    raise ValueError("IC-fixed C must parallel its variable C")

    @property
    def edges(self):
        return self.fixed_edges + self.variable_edges + self.ic_fixed_edges

    def incidence(self):
        return incidence_matrix(self.edges, self.node_count)

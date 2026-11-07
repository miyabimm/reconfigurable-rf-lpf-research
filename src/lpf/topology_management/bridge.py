"""Small graph-theoretic safeguards for variable-C bridge classification.

The graph proof is structural: an authorized non-ground variable capacitor
must close a loop in the ground-excluded FIXED-element signal network.
This does not certify RF behavior, electrical orientation, or implementation.
"""
from collections import deque


def _reachable(start, adjacency):
    found = {start}
    pending = deque([start])
    while pending:
        node = pending.popleft()
        for neighbor in adjacency[node] - found:
            found.add(neighbor)
            pending.append(neighbor)
    return found


def validate_bridge_topology(fixed_edges, variable_branches, source_node,
                             load_node, n_nodes):
    """Reject a labelled variable bridge that is a series-only signal link.

    Ground node 0 cannot provide a spurious path from source to load. Both
    bridge endpoints must be connected to source/load through FIXED non-ground
    elements with the bridge removed; therefore the bridge closes a loop.
    """
    if (type(n_nodes) is not int or n_nodes < 1 or
            type(source_node) is not int or type(load_node) is not int or
            not 1 <= source_node <= n_nodes or not 1 <= load_node <= n_nodes):
        raise ValueError("Invalid circuit nodes")
    adjacency = {node: set() for node in range(1, n_nodes + 1)}
    for a, b in fixed_edges:
        if (type(a) is not int or type(b) is not int or a == b or
                a < 0 or b < 0 or a > n_nodes or b > n_nodes):
            raise ValueError("Invalid fixed component edge")
        if a and b:
            adjacency[a].add(b)
            adjacency[b].add(a)
    if not any(b.get("role") == "bridge" for b in variable_branches):
        return True
    connected = _reachable(source_node, adjacency)
    if load_node not in connected:
        raise ValueError("Bridge cannot be the sole fixed-graph source/load path")
    for b in variable_branches:
        if b.get("role") != "bridge":
            continue
        a, other = b["a"], b["b"]
        if (type(a) is not int or type(other) is not int or
                a not in connected or other not in connected or a == other):
            raise ValueError("Non-ground variable C does not close a fixed-element loop")
    return True

"""Bounded, ordered structural choices; no RF or component-value validation."""
from itertools import combinations, product

from .circuit_layout import InductorTree


def _positive_int(value, label):
    if type(value) is not int or value < 1:
        raise ValueError(label + " must be a positive integer")


def labelled_trees(n_inductors, *, limit, reverse_edges=False,
                   source_node=0, load_node=2):
    """First ``limit`` labelled 3L/4L trees in lexicographic edge/mask order."""
    if type(n_inductors) is not int or n_inductors not in (3, 4):
        raise ValueError("Only 3L/4L enumeration is supported")
    _positive_int(limit, "limit")
    if type(reverse_edges) is not bool:
        raise ValueError("reverse_edges must be boolean")
    n = n_inductors + 1
    InductorTree(n, tuple((0, i) for i in range(1, n)), source_node, load_node)
    result = []
    for edges in combinations(combinations(range(n), 2), n_inductors):
        try:
            tree = InductorTree(n, edges, source_node, load_node)
        except ValueError:
            continue
        masks = product((False, True), repeat=n_inductors) if reverse_edges else [(False,)*n_inductors]
        for mask in masks:
            oriented = tuple((b, a) if flip else (a, b)
                             for (a, b), flip in zip(tree.edges, mask))
            result.append(InductorTree(n, oriented, source_node, load_node))
            if len(result) == limit:
                return tuple(result)
    return tuple(result)


def capacitor_choices(node_count, *, kind, max_branches, limit):
    """Explicit prefix of distinct-edge ordered C layouts, including empty."""
    _positive_int(limit, "limit")
    if (type(node_count) is not int or node_count not in (4, 5)
            or type(max_branches) is not int or not 0 <= max_branches <= 3
            or kind not in ("fixed", "variable")):
        raise ValueError("Expected 4/5 nodes, 0..3 C branches and fixed/variable kind")
    edges = tuple((i, -1) for i in range(node_count)) + tuple(combinations(range(node_count), 2))
    result = [()]
    for count in range(1, max_branches+1):
        for selected in combinations(edges, count):
            labels = [("GJM01", "PCB_PATTERN_C") if kind == "fixed" else
                      (("shunt_to_ground",) if -1 in edge else ("bridge", "series"))
                      for edge in selected]
            for kinds in product(*labels):
                if len(result) == limit:
                    return tuple(result)
                result.append(tuple(zip(selected, kinds)))
    return tuple(result)

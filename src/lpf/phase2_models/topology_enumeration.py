"""Bounded nominal topology samples for Issue #189 / PR-S4A, not an RF search.

Only exact labelled, ordered definitions are deduplicated. No node isomorphism,
L reversal, sign compensation, C-role inference or parameter projection is
attempted. A representative box-midpoint vector checks that each emitted
structure can instantiate legal components; this is NOT validation of all
vectors, RF performance, physical feasibility or a promotion gate.
"""
from collections import Counter
from dataclasses import asdict, dataclass
from fractions import Fraction
from itertools import combinations, islice, permutations, product
import hashlib
import json

from lpf.constraint_versions import constraint_fingerprint, load_constraint
from .api import CircuitDefinition, build_nominal_circuit
from .circuit_layout import CapacitorPlacement, InductorTree, normalized_capacitor_edge
from .problem_seed import circuit_box


def _sha(value):
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"),
                     allow_nan=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _positive_int(value, label):
    if type(value) is not int or value < 1:
        raise ValueError(label + " must be a positive integer")


def _approved(policy):
    if not isinstance(policy, dict) or policy.get("active_constraint_id") not in (
            "RF-T005", "RF-T007", "RF-T008"):
        raise ValueError("Explicit approved RF-T005/T007/T008 trial required")
    approved = load_constraint(policy["active_constraint_id"], allow_trial=True)
    if constraint_fingerprint(policy) != constraint_fingerprint(approved):
        raise ValueError("Resolved trial differs from approved registry")
    return approved


def labelled_trees(n_inductors, *, limit, reverse_edges=False,
                   source_node=0, load_node=2):
    """First ``limit`` labelled trees in lexicographic edge/mask order.

    3L/4L only, on n+1 hot nodes. Edge permutations are NOT enumerated.
    Optional orientation masks retain electrical directions, never quotient
    them out. The finite class has at most 210 edge sets x 16 masks.
    """
    if type(n_inductors) is not int or n_inductors not in (3, 4):
        raise ValueError("Only 3L/4L enumeration is supported")
    _positive_int(limit, "limit")
    if type(reverse_edges) is not bool:
        raise ValueError("reverse_edges must be boolean")
    n = n_inductors + 1
    # Validate ports even if a disconnected first edge set would be skipped.
    InductorTree(n, tuple((0, i) for i in range(1, n)), source_node, load_node)
    result = []
    for edges in combinations(combinations(range(n), 2), n_inductors):
        try:
            tree = InductorTree(n, edges, source_node, load_node)
        except ValueError:
            continue  # disconnected n-1-edge set, not a tree
        masks = product((False, True), repeat=n_inductors) if reverse_edges else [(False,)*n_inductors]
        for mask in masks:
            oriented = tuple((b, a) if flip else (a, b)
                             for (a, b), flip in zip(tree.edges, mask))
            result.append(InductorTree(n, oriented, source_node, load_node))
            if len(result) == limit:
                return tuple(result)
    return tuple(result)


def capacitor_choices(node_count, *, kind, max_branches, limit):
    """Explicit prefix of distinct-edge ordered C layouts, including empty.

    ``kind='fixed'`` labels each edge GJM01/PCB_PATTERN_C; ``'variable'``
    labels ground shunts and hot-hot bridge/series alternatives. No C edge
    permutations are generated. Policy/count/value gates still run downstream.
    Empty layouts encode absence, never an installed zero-pF fixed capacitor.
    """
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


@dataclass(frozen=True)
class TopologySpace:
    """Finite explicit axes; tuples are snapshotted, sorted before iteration.

    L assignments and C choices are supplied explicitly (helpers above can
    generate bounded prefixes). All physical chip permutations are generated,
    then only the first ``physical_order_limit`` per assignment are considered.
    Coupling slots are subsets of all L pairs (including forced-zero pairs);
    their allowed signed bounds come exclusively from circuit_box / policy.
    """
    trees: tuple[InductorTree, ...]
    inductor_assignments: tuple[tuple[str, ...], ...]
    fixed_layouts: tuple[tuple[tuple[tuple[int, int], str], ...], ...]
    variable_layouts: tuple[tuple[tuple[tuple[int, int], str], ...], ...]
    coupling_slot_counts: tuple[int, ...]
    physical_order_limit: int
    max_candidates: int

    def __post_init__(self):
        _positive_int(self.physical_order_limit, "physical_order_limit")
        _positive_int(self.max_candidates, "max_candidates")
        object.__setattr__(self, "trees", tuple(self.trees))
        object.__setattr__(self, "inductor_assignments", tuple(tuple(t) for t in self.inductor_assignments))
        for name in ("fixed_layouts", "variable_layouts"):
            object.__setattr__(self, name, tuple(tuple((tuple(e), k) for e, k in layout)
                                                for layout in getattr(self, name)))
        object.__setattr__(self, "coupling_slot_counts", tuple(self.coupling_slot_counts))
        if not all((self.trees, self.inductor_assignments, self.fixed_layouts,
                    self.variable_layouts, self.coupling_slot_counts)):
            raise ValueError("Every search axis must be explicit and nonempty")
        if any(not isinstance(t, InductorTree) or len(t.edges) not in (3, 4) for t in self.trees):
            raise ValueError("Expected explicit 3L/4L trees")
        if len({len(t.edges) for t in self.trees}) != 1:
            raise ValueError("Use separate spaces for 3L and 4L")
        n = len(self.trees[0].edges)
        if any(len(t) != n for t in self.inductor_assignments):
            raise ValueError("One inductor type per branch required")
        if any(type(c) is not int or not 0 <= c <= n*(n-1)//2 for c in self.coupling_slot_counts):
            raise ValueError("Invalid coupling slot count")


def exact_candidate_key(circuit, vector=None):
    """Safe exact key; topology-only and complete-vector keys are distinct.

    Policy SHA includes ports, fixed S2P hashes and trial definitions; actual
    stamped topology/schema explicitly retains T007 constants/Q and T008 IC-C.
    Parameter values (including all six settings and signed k) are included
    ONLY when supplied. Never use a topology-only key to deduplicate vectors.
    """
    values = None
    if vector is not None:
        values = asdict(circuit.decode(vector))
        circuit.encode(circuit.decode(vector))
    return _sha({"version": "s4a-exact-v1", "policy_id": circuit.policy_id,
                 "policy_sha256": circuit.policy_fingerprint,
                 "definition": asdict(circuit.definition),
                 "schema": asdict(circuit.schema),
                 "topology": asdict(circuit.topology), "values": values})


def nominal_area(circuit):
    """Policy-derived nominal chip area and installed counts, not layout area.

    Fixed external S2P resources excluded by approved policy. IC zero area is
    nominal accounting only. OFF variable branches remain installed/countable.
    """
    p, d = circuit.resolved_policy, circuit.definition
    counts = Counter(d.inductor_types + d.fixed_c_types)
    counts["IC_VARIABLE_C"] = circuit.schema.n_variable
    counts["IC_FIXED_C"] = circuit.schema.n_ic_fixed
    counts["SHUNT_DTC_PARASITIC"] = len(circuit.schema.constant_caps_pf)
    terms = []
    total = Fraction(0)
    for name, count in sorted(counts.items()):
        if name in ("LQP02HV", "LQP02HQ"):
            path = ("components", "LQP02", "series", name, "area_units")
        elif name == "IC_FIXED_C":
            path = ("trial_ic_fixed_c_by_connection", "additional_chip_area_units")
        elif name == "SHUNT_DTC_PARASITIC":
            path = ("trial_shunt_dtc_parasitic", "additional_chip_area_units")
        else:
            spec = p["components"][name]
            path = ("components", name, "area_units_fraction" if "area_units_fraction" in spec else "area_units")
        # Zero-count trial-specific resources need no nonexistent policy field.
        if count == 0:
            continue
        value = p
        for key in path:
            value = value[key]
        unit = Fraction(str(value))
        total += count * unit
        terms.append({"part": name, "count": count, "unit_area_fraction": str(unit),
                      "policy_path": ".".join(path)})
    return {"counts": dict(sorted(counts.items())), "area_fraction": str(total),
            "area_units": float(total), "area_unit": p["chip_area_unit"],
            "terms": tuple(terms), "policy_id": circuit.policy_id,
            "policy_sha256": circuit.policy_fingerprint,
            "physical_area_verified": False,
            "fixed_external_s2p_area_included": False,
            "ic_zero_area_is_nominal_only": True}


def _distinct_cap_edges(definition):
    # Parallel fixed + variable and paired T008 IC-fixed branches are intentional.
    # Duplicate branches WITHIN either independently installed class are excluded.
    p = definition.capacitor_placement
    for edges in (p.fixed_edges, p.variable_edges):
        normalized = [normalized_capacitor_edge(e, p.node_count) for e in edges]
        if len(set(normalized)) != len(normalized):
            raise ValueError("Duplicate capacitor connection within branch class")


def enumerate_topologies(policy, space):
    """Return reproducible bounded structures, rejection counts and fingerprints.

    No evaluator, SLSQP, independent MNA or RF grid is executed. All gates are
    existing public nominal gates, plus conservative duplicate-C exclusion.
    At most max_candidates raw combinations are built, INCLUDING rejected and
    duplicate entries. No seed/random sampling is used; input axis order does
    not affect output. The unvisited Cartesian suffix is counted, not evaluated.
    """
    p = _approved(policy)
    if not isinstance(space, TopologySpace):
        raise TypeError("Expected TopologySpace")
    sort_key = lambda v: json.dumps(asdict(v) if isinstance(v, InductorTree) else v,
                                    sort_keys=True, separators=(",", ":"))
    trees = sorted(space.trees, key=sort_key)
    assignments = sorted(space.inductor_assignments)
    fixed = sorted(space.fixed_layouts, key=sort_key)
    variable = sorted(space.variable_layouts, key=sort_key)
    slots = sorted(space.coupling_slot_counts)
    n = len(trees[0].edges)
    pairs = tuple(combinations(range(n), 2))
    pair_sets = tuple(c for count in slots for c in combinations(pairs, count))
    orders = {types: tuple(islice(permutations(tuple(i for i, kind in enumerate(types)
                                                    if kind != "PCB_L")),
                                 space.physical_order_limit)) for types in assignments}
    total = len(trees)*len(fixed)*len(variable)*len(pair_sets)*sum(len(orders[t]) for t in assignments)
    # Fingerprint describes normalized axes incl. multiplicity, limits and order.
    configuration = {"version": "s4a-space-v1", "policy_sha256": constraint_fingerprint(p),
                     "trees": [asdict(t) for t in trees], "assignments": assignments,
                     "fixed_layouts": fixed, "variable_layouts": variable,
                     "coupling_slot_counts": slots, "physical_order_limit": space.physical_order_limit,
                     "max_candidates": space.max_candidates,
                     "order": "tree,type,physical_order,coupling_slots,fixed,variable:lex-v1"}
    accepted, rejected, seen = [], Counter(), set()
    visited = duplicates = 0
    def definitions():
        for tree, types in product(trees, assignments):
            for order, coupling, cf, cv in product(orders[types], pair_sets, fixed, variable):
                yield tree, types, order, coupling, cf, cv
    for tree, types, order, coupling, cf, cv in islice(definitions(), space.max_candidates):
        visited += 1
        try:
            ve = tuple(e for e, _ in cv)
            definition = CircuitDefinition(tree, types, order, coupling,
                CapacitorPlacement(tree.node_count, tuple(e for e, _ in cf), ve,
                                   ve if p["active_constraint_id"] == "RF-T008" else ()),
                tuple(k for _, k in cf), tuple(r for _, r in cv))
            _distinct_cap_edges(definition)
            circuit = build_nominal_circuit(p, definition)
            roles = circuit.connection_role_audit()
            box = circuit_box(circuit)
            vector = tuple((lo+hi)/2 for lo, hi in box.bounds[:-1])
            component = circuit.validate_components(vector)
            area = nominal_area(circuit)
        except (ValueError, TypeError) as exc:
            rejected[type(exc).__name__ + ": " + str(exc)] += 1
            continue
        key = exact_candidate_key(circuit)
        if key in seen:
            duplicates += 1
            continue
        seen.add(key)
        accepted.append({"definition": definition, "topology_key": key,
                         "representative_vector": vector,
                         "representative_vector_key": exact_candidate_key(circuit, vector),
                         "component_check": component, "connection_role_audit": roles,
                         "nominal_area": area})
    return {"candidates": tuple(accepted), "policy_id": p["active_constraint_id"],
            "policy_sha256": constraint_fingerprint(p),
            "space_sha256": _sha(configuration), "configuration": configuration,
            "output_sha256": _sha([c["representative_vector_key"] for c in accepted]),
            "counts": {"raw_space": total, "visited": visited,
                       "rejected": sum(rejected.values()), "duplicates": duplicates,
                       "retained": len(accepted), "unvisited": total-visited},
            "rejection_reasons": dict(sorted(rejected.items())),
            "truncated": visited < total,
            "equivalence": "exact_labelled_ordered_only; no_node_isomorphism",
            "overcomplete_equivalence_classes": True,
            "exhaustive_topology_search": False,
            "rf_evaluation": "not_run", "independent_mna": "not_run",
            "candidate_promotion_blocked": True}

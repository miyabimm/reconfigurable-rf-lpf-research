"""Shared, policy-scoped enumeration of inductor alphabets and variable-C layouts.

The output order and bounded two-pass coverage are retained from the historical
P4-A search. This enumerates electrical candidates, not physical feasibility
or globally exhaustive circuit designs. Always pass an explicit RF policy.
"""
from itertools import combinations

from .constraint_versions import validate_variable_c_connections
from .topology import validate_bridge_topology


def inductor_types(series_mode=None):
    """Return the fixed-element alphabet; None preserves the original P4-A set."""
    if series_mode in (None, "legacy"):
        return ("LQP01", "LQP02", "PCB_L", "GJM01")
    if series_mode == "HV":
        return ("LQP01", "LQP02HV", "PCB_L", "GJM01")
    if series_mode == "HQ":
        return ("LQP01", "LQP02HQ", "PCB_L", "GJM01")
    if series_mode == "both":
        return ("LQP01", "LQP02HV", "LQP02HQ", "PCB_L", "GJM01")
    raise ValueError(f"Unknown LQP02 search series mode: {series_mode!r}")


def enumerate_variable_c_layouts(graph, resolved_policy, *, max_layouts=None):
    """Enumerate bounded policy-authorized variable-C edge assignments.

    RF-F002/RF-T004 permit 1..N branches: grounded shunts, fixed-path
    bridges and explicitly marked series branches. A series element may
    close a previously open input-to-output path. Legacy RF-F001 trial
    layouts remain exact-count/exact-role. The enumerator excludes multiple
    independently controlled capacitors on the same physical edge.
    This is not an exhaustive physical-layout feasibility check.
    """
    n_nodes, fixed_edges = graph
    if type(n_nodes) is not int or n_nodes < 3:
        raise ValueError("A grounded graph needs ground and two terminals")
    if max_layouts is not None and (type(max_layouts) is not int or max_layouts < 1):
        raise ValueError("max_layouts must be a positive integer or None")
    spec = resolved_policy["components"]["IC_VARIABLE_C"]
    flex_layout = resolved_policy.get("trial_variable_c_layout", {})
    unrestricted = (
        "series" in spec["positions_allowed_by_default"]
        and not spec["series_requires_separate_approval"]
        and (not flex_layout or flex_layout.get("connection_policy") == "any_allowed")
    )
    if unrestricted:
        # Enumerate 1..N independently controlled branches rather than
        # assuming an exact count or a preselected shunt/bridge breakdown.
        active_nodes = tuple(range(1, n_nodes))
        fixed_map = [(a, b) for a, b, _ in fixed_edges]
        possible = []
        if "shunt_to_ground" in spec["positions_allowed_by_default"]:
            possible.extend(((node, 0), None) for node in active_nodes)
        for a, b in combinations(active_nodes, 2):
            if "non_ground_bridge" in spec["positions_allowed_by_default"]:
                candidate = {"a": a, "b": b, "role": "bridge"}
                try:
                    validate_bridge_topology(fixed_map, (candidate,), 1, 2, n_nodes - 1)
                except ValueError:
                    pass
                else:
                    possible.append(((a, b), "bridge"))
            possible.append(((a, b), "series"))

        def generate():
            # Only distinct physical edges are enumerated. Co-located
            # parallel independently controlled branches are not explored
            # by this particular bounded topology enumerator.
            max_count = spec["max_branches_principle"]
            for count in range(1, max_count + 1):
                for indices in combinations(range(len(possible)), count):
                    chosen = [possible[i] for i in indices]
                    edges = tuple(item[0] for item in chosen)
                    if len({tuple(sorted(edge)) for edge in edges}) != count:
                        continue
                    roles = tuple(item[1] for item in chosen)
                    metadata = tuple({"a": a, "b": b, **({"role": role} if role else {})}
                                     for (a, b), role in chosen)
                    try:
                        validate_variable_c_connections(metadata, resolved_policy)
                        validate_bridge_topology(fixed_map, metadata, 1, 2, n_nodes - 1)
                    except ValueError:
                        continue
                    yield {"edges": edges, "roles": roles}
    else:
        # Immutable RF-F001 and its RF-T001/T002/T003 trials keep their
        # original exact-count shunt/bridge enumeration and ordering.
        layout = resolved_policy.get("trial_variable_c_layout")
        if layout is None:
            branch_count = resolved_policy["components"]["IC_VARIABLE_C"]["max_branches_principle"]
            shunt_count, bridge_count = branch_count, 0
        else:
            branch_count = layout["branch_count"]
            shunt_count = layout["shunt_to_ground"]
            bridge_count = layout["non_ground_bridge"]
        active_nodes = tuple(range(1, n_nodes))
        def generate():
            for shunts in combinations(active_nodes, shunt_count):
                shunt_edges = tuple((node, 0) for node in shunts)
                if bridge_count == 0:
                    yield {"edges": shunt_edges,
                           "roles": (None,) * branch_count}
                    continue
                for a, b in combinations(active_nodes, 2):
                    edges = shunt_edges + ((a, b),)
                    roles = (None,) * shunt_count + ("bridge",)
                    metadata = tuple({"a": x, "b": y, **({"role": "bridge"}
                                    if role == "bridge" else {})}
                                     for (x, y), role in zip(edges, roles))
                    try:
                        validate_variable_c_connections(metadata, resolved_policy)
                        validate_bridge_topology(
                            [(x, y) for x, y, _ in fixed_edges], metadata,
                            1, 2, n_nodes - 1)
                    except ValueError:
                        continue
                    yield {"edges": edges, "roles": roles}

    if max_layouts is None:
        return list(generate())
    if max_layouts == 1:
        first=next(generate(),None)
        return [] if first is None else [first]
    # Two bounded-memory passes preserve even coverage of the full ordered
    # class without retaining every candidate layout in memory.
    total=sum(1 for _ in generate())
    if total<=max_layouts:
        return list(generate())
    indices={round(i*(total-1)/(max_layouts-1)) for i in range(max_layouts)}
    return [candidate for index,candidate in enumerate(generate())
            if index in indices]

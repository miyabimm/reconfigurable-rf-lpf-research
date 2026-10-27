"""Shared nominal part labels used by the supported Phase-2 trials.

Only names, counts and physical chip order are checked here. RF limits
and frequency-dependent behavior stay with the resolved policy validators.
"""
from .nominal_inductors import nominal_inductor_series


def checked_inductor_metadata(policy, tree, inductor_types, physical_order):
    """Return ordered L types, physical chip order and approved nominal Q."""
    types = tuple(inductor_types)
    if len(types) != len(tree.edges):
        raise ValueError("One explicit inductor type per L branch required")
    q = tuple(nominal_inductor_series(policy, name)[0] for name in types)
    order = tuple(physical_order)
    chips = {i for i, name in enumerate(types) if name != "PCB_L"}
    if (len(order) != len(chips) or set(order) != chips or
            any(type(i) is not int for i in order)):
        raise ValueError("Physical chip order must list every chip inductor once")
    return types, order, q


def checked_fixed_c_types(fixed_edges, fixed_c_types):
    """Return GJM01/PCB_PATTERN_C labels, one per installed fixed C."""
    names = tuple(fixed_c_types)
    if (len(names) != len(fixed_edges) or
            any(name not in ("GJM01", "PCB_PATTERN_C") for name in names)):
        raise ValueError("One approved GJM01/PCB_PATTERN_C type per fixed C required")
    return names

"""Validate fixed six-setting topology and policy-scoped variable capacitors."""
from functools import lru_cache

import numpy as np

from .constraint_versions import load_constraint, validate_variable_c_connections
from .evaluate import CASES
from .topology_management.bridge import validate_bridge_topology


@lru_cache(maxsize=1)
def formal_policy():
    """Avoid re-reading immutable formal files on every optimizer evaluation."""
    return load_constraint()


def validate_six_settings(settings, variable_cap_indices, *, resolved_policy=None,
                          variable_roles=None):
    """Only declared variable-C values may change across the six RF settings.

    variable_roles is parallel to variable_cap_indices. A non-ground variable
    must be explicitly labelled 'bridge' (fixed-path bypass) or 'series'.
    Default behavior follows the active formal version.
    """
    policy = formal_policy() if resolved_policy is None else resolved_policy
    if set(settings) != set(CASES):
        raise ValueError("Exactly six settings required")
    indices = tuple(variable_cap_indices)
    if (any(type(i) is not int for i in indices)
            or len(set(indices)) != len(indices)):
        raise ValueError("Variable capacitor indices must be distinct integers")
    roles = ((None,) * len(indices) if variable_roles is None
             else tuple(variable_roles))
    if len(roles) != len(indices):
        raise ValueError("Variable capacitor role count mismatch")
    reference = settings[CASES[0]]
    base_caps = list(reference.get("capacitors", ()))
    if any(i < 0 or i >= len(base_caps) for i in indices):
        raise ValueError("Variable capacitor index out of range")
    if (type(reference.get("n_nodes")) is not int or
            reference["n_nodes"] < 1):
        raise ValueError("Invalid node count")
    metadata = []
    for i, role in zip(indices, roles):
        c = base_caps[i]
        if any(type(node) is not int or node < 0 or node > reference["n_nodes"]
               for node in (c.a, c.b)):
            raise ValueError("Variable C node outside circuit")
        if role not in (None, "bridge", "series"):
            raise ValueError("Unknown variable capacitor role")
        metadata.append({"a": c.a, "b": c.b, "role": role})
    validate_variable_c_connections(metadata, policy)
    fixed_edges = [(x.a, x.b) for x in reference.get("inductors", ())]
    fixed_edges += [(x.a, x.b) for i, x in enumerate(base_caps)
                    if i not in indices]
    validate_bridge_topology(fixed_edges, metadata, reference["source_node"],
                             reference["load_node"], reference["n_nodes"])
    spec = policy["components"]["IC_VARIABLE_C"]
    for case in CASES:
        cfg = settings[case]
        if set(cfg) != set(reference):
            raise ValueError("Configuration keys differ")
        for key in reference:
            if key in ("capacitors", "inductors", "coupling"):
                continue
            if cfg[key] != reference[key]:
                raise ValueError("Non-capacitor setting change: " + key)
        if list(cfg.get("inductors", ())) != list(reference.get("inductors", ())):
            raise ValueError("Inductors must be fixed")
        a = cfg.get("coupling")
        b = reference.get("coupling")
        if ((a is None) != (b is None) or
                (a is not None and not np.array_equal(np.asarray(a), np.asarray(b)))):
            raise ValueError("Coupling must be fixed")
        caps = list(cfg.get("capacitors", ()))
        if len(caps) != len(base_caps):
            raise ValueError("Capacitor topology differs")
        for i, (c, original) in enumerate(zip(caps, base_caps)):
            if i in indices:
                if ((c.a, c.b, c.q) != (original.a, original.b, original.q)
                    or not np.isfinite(c.value)
                    or c.q != spec["q"]
                    or not (spec['bounds']['min'] * 1e-12
                            <= c.value <=
                            spec['bounds']['max'] * 1e-12)):
                    raise ValueError("Variable C connection, Q or capacitance range invalid")
            elif c != original:
                raise ValueError("Fixed C changed")
    return True

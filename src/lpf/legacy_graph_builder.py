"""Compatibility-preserved legacy bounded graph-to-six-setting MNA builder.

The Q/series alias and fixed component limits retain historical P4-A/F002
semantics. This is not a generic RF-F003/T008 optimizer or proof of physical
buildability; pass explicit resolved policies for applicable checks.

The implementation below is unchanged from main commit
25bcf092daadaf70959b2598cc7c150871a77945.
"""

import numpy as np

from lpf.circuit import Branch
from lpf.configuration import formal_policy, validate_six_settings
from lpf.evaluate import CASES
from lpf.lqp02_series import select_series
from lpf.constraints import validate_pcb_pattern_caps

Q = {"LQP01": 15, "LQP02": 25, "LQP02HV": 25,
     "LQP02HQ": 20, "LQW04": 33, "PCB_L": 12, "GJM01": 80, "PCB_PATTERN_C": 40}
DEFAULT = {"LQP01": 2e-9, "LQP02": 2e-9, "LQP02HV": 2e-9,
           "LQP02HQ": 2e-9, "LQW04": 2e-9, "PCB_L": 2e-9,
           "GJM01": 2e-12, "PCB_PATTERN_C": .1e-12}
AREA_THIRDS = {"LQP01": 2, "LQP02": 3, "LQP02HV": 3,
               "LQP02HQ": 3, "LQW04": 9, "PCB_L": 0, "GJM01": 2, "PCB_PATTERN_C": 0}
CAP_TYPES = ("GJM01", "PCB_PATTERN_C")


def branch_q(component_type, value_henry_or_farad):
    if component_type in ("LQP02", "LQP02HV", "LQP02HQ"):
        series = "LQP02HV" if component_type == "LQP02" else component_type
        return select_series(float(value_henry_or_farad) * 1e9,
                             series=series)["Q"]
    return Q[component_type]


def check_graph(graph, *, require_explicit_series=False):
    n, edges = graph
    if type(n) is not int or n < 2 or not edges:
        raise ValueError("Empty graph")
    if any(type(a) is not int or type(b) is not int or
           a == b or a < 0 or b < 0 or a >= n or b >= n for a, b, _ in edges):
        raise ValueError("Invalid edge")
    if any(t not in Q for _, _, t in edges):
        raise ValueError("Unknown component")
    if require_explicit_series and any(t == "LQP02" for _, _, t in edges):
        raise ValueError("New candidates require explicit LQP02HV/HQ labels")
    if sum(t == "PCB_L" for _, _, t in edges) > 3:
        raise ValueError("PCB L limit")
    if sum(t == "PCB_PATTERN_C" for _, _, t in edges) > 3:
        raise ValueError("PCB pattern C limit")
    return sum(AREA_THIRDS[t] for _, _, t in edges) / 3


def _fixed_parts(graph, values, shift=0, resolved_policy=None):
    n, edges = graph
    policy = formal_policy() if resolved_policy is None else resolved_policy
    if values is None:
        values = [DEFAULT[t] for _, _, t in edges]
    if len(values) != len(edges):
        raise ValueError("Value count mismatch")
    validate_pcb_pattern_caps([float(v) * 1e12 for (_, _, t), v in zip(edges, values)
                               if t == "PCB_PATTERN_C"])
    inductors, capacitors = [], []
    for (a, b, t), value in zip(edges, values):
        v = float(value)
        if t == 'PCB_L' and v > policy['components']['PCB_L'].get('max_inductance_nh', policy['components']['PCB_L']['max_inductance_nh_approx'])*1e-9+1e-21:
            raise ValueError('PCB-L inductance exceeds policy limit')
        if not np.isfinite(v) or v <= 0:
            raise ValueError("Fixed component value must be finite and positive")
        branch = Branch(a + shift, b + shift, v, branch_q(t, v))
        (capacitors if t in CAP_TYPES else inductors).append(branch)
    return inductors, capacitors


def _build_settings(graph, values, caps, coupling, variable_cap_edges,
                    variable_roles, resolved_policy, shift, node_count):
    policy = formal_policy() if resolved_policy is None else resolved_policy
    inductors, fixed = _fixed_parts(graph, values, shift=shift, resolved_policy=policy)
    edges = ([(1, 0), (2, 0)] if variable_cap_edges is None
             else list(variable_cap_edges))
    if caps is None:
        caps = np.zeros((len(CASES), len(edges)))
    caps = np.asarray(caps, dtype=float)
    if caps.shape != (len(CASES), len(edges)):
        raise ValueError("Variable C array must have six rows and one column per branch")
    for a, b in edges:
        if (type(a) is not int or type(b) is not int or
                a == b or a < 0 or b < 0 or a > node_count or b > node_count):
            raise ValueError("Invalid variable-C edge")
    result = {}
    fixed_count = len(fixed)
    q = policy["components"]["IC_VARIABLE_C"]["q"]
    for case, values_pf in zip(CASES, caps):
        variable = [Branch(a, b, float(value) * 1e-12, q)
                    for (a, b), value in zip(edges, values_pf)]
        result[case] = dict(n_nodes=node_count, source_node=1, load_node=2,
                            inductors=tuple(inductors),
                            capacitors=tuple(fixed + variable),
                            coupling=coupling)
    validate_six_settings(result, range(fixed_count, fixed_count + len(edges)),
                          resolved_policy=policy, variable_roles=variable_roles)
    return result


def build_settings(graph, values=None, caps=None, coupling=None, *,
                   variable_cap_edges=None, variable_roles=None,
                   resolved_policy=None, require_explicit_series=False):
    """Ungrounded enumeration: graph node 0=input, 1=output, >=2 internal.

    variable_cap_edges use SOLVER nodes 1=input, 2=output, >=3 internal,
    0=ground. Legacy default remains two input/output shunt capacitors.
    """
    check_graph(graph, require_explicit_series=require_explicit_series)
    return _build_settings(graph, values, caps, coupling,
                           variable_cap_edges, variable_roles, resolved_policy,
                           shift=1, node_count=graph[0])


def build_grounded_settings(graph, values=None, caps=None, coupling=None, *,
                            variable_cap_edges=None, variable_roles=None,
                            resolved_policy=None, require_explicit_series=False):
    """Grounded enumeration: 0=ground, 1=input, 2=output, >=3 internal."""
    check_graph(graph, require_explicit_series=require_explicit_series)
    if graph[0] < 3:
        raise ValueError("Ground and two terminals required")
    return _build_settings(graph, values, caps, coupling,
                           variable_cap_edges, variable_roles, resolved_policy,
                           shift=0, node_count=graph[0] - 1)

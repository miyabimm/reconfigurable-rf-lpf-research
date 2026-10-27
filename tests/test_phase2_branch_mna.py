"""Small synthetic MNA regressions; no new RF or optimization evidence."""
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from lpf.constraint_versions import load_constraint
from lpf.phase2_models.api import CircuitDefinition, build_nominal_circuit
from lpf.phase2_models.branch_mna import solve_branch_mna
from lpf.phase2_models.circuit_layout import CapacitorPlacement, InductorTree
from lpf.phase2_models.coupled_lc import CoupledLCTopology
from lpf.phase2_models.numerical_diagnostics import CircuitNumericalError


def circuit(n, trial="RF-T005"):
    edges = tuple((i, i + 1) for i in range(n))
    variable = ((0, -1),)
    definition = CircuitDefinition(
        InductorTree(n + 1, edges, 0, n), ("LQP02HV",) * n,
        tuple(range(n)), ((0, 1),),
        CapacitorPlacement(n + 1, ((n, -1),), variable,
                           variable if trial == "RF-T008" else ()),
        ("PCB_PATTERN_C",), ("shunt_to_ground",),
    )
    return build_nominal_circuit(load_constraint(trial, allow_trial=True), definition)


def values(c, k=.2):
    # construct through schema to include trial-specific fixed parasitics
    s = c.schema
    return s.decode([3.] * s.n_inductors + [.1] * s.n_fixed + [k] * s.n_coupling
                    + [.5] * s.n_ic_fixed + [0.] * (6 * s.n_variable))


def compare_reference(n, trial):
    c = circuit(n, trial)
    v = values(c)
    term = np.zeros(n + 1, complex)
    term[0], term[-1] = 1 / 50, 1 / (60 - 40j)
    source = np.zeros(n + 1, complex)
    source[0] = 1 / 50
    frequency = 1e9
    y = c.topology.node_admittance(v, np.array([2*np.pi*frequency]), np.array([0]))[0]
    reference = np.linalg.solve(y + np.diag(term), source)
    # Fail if the independent solver delegates to either forward operation.
    def forbidden(*args, **kwargs):
        raise AssertionError("forward kernel was called")
    with patch.object(CoupledLCTopology, "node_admittance", forbidden), \
            patch.object(CoupledLCTopology, "matrices", forbidden):
        voltage, current = solve_branch_mna(c, v, frequency, 0,
            injected_currents_a=source, termination_admittances_s=term)
    assert len(voltage) + len(current) == 2*n + 1
    np.testing.assert_allclose(voltage, reference, rtol=1e-11, atol=1e-11)
    assert np.all(np.isfinite(current))


def check_off_state():
    a, b, d = (circuit(3, t) for t in ("RF-T005", "RF-T007", "RF-T008"))
    assert values(a).capacitors_pf_by_setting[0][-1] == 0
    assert values(b).capacitors_pf_by_setting[0][-1] == .5
    assert b.topology.capacitor_q[-1] == 40
    assert values(d).capacitors_pf_by_setting[0][-1] == .5
    assert d.topology.capacitor_q[-1] == 60
    source = [0.02, 0, 0, 0]
    term = [0.02, 0, 0, 1/60]
    outputs = [solve_branch_mna(c, values(c), 1e9, 0,
              injected_currents_a=source, termination_admittances_s=term)[0]
               for c in (a, b, d)]
    assert not np.allclose(outputs[0], outputs[1])
    assert not np.allclose(outputs[1], outputs[2])


def check_invalid():
    c = circuit(3)
    kwargs = dict(injected_currents_a=[.02, 0, 0, 0],
                  termination_admittances_s=[.02, 0, 0, 1/60])
    with unittest.TestCase().assertRaisesRegex(CircuitNumericalError, expected_regex="mutual_not_spd"):
        solve_branch_mna(c, values(c, 1.1), 1e9, 0, **kwargs)
    for f, setting in [(float('nan'), 0), (0, 0), (1e9, True), (1e9, 6)]:
        with unittest.TestCase().assertRaises(ValueError):
            solve_branch_mna(c, values(c), f, setting, **kwargs)
    with unittest.TestCase().assertRaises(ValueError):
        solve_branch_mna(c, values(c), 1e9, 0,
                         injected_currents_a=[0]*4,
                         termination_admittances_s=[-1, 0, 0, 0])
    floating = c.schema.decode([3.] * 3 + [0.] + [.2] + [0.] * 6)
    with unittest.TestCase().assertRaisesRegex(CircuitNumericalError, expected_regex="mna_ill_conditioned"):
        solve_branch_mna(c, floating, 1e9, 0,
                         injected_currents_a=[0]*4,
                         termination_admittances_s=[0]*4)


class BranchMNATests(unittest.TestCase):
    def test_references(self):
        for n in (3, 4):
            for trial in ("RF-T005", "RF-T007", "RF-T008"):
                with self.subTest(n=n, trial=trial):
                    compare_reference(n, trial)

    def test_orientation_and_signed_coupling(self):
        original = circuit(3)
        definition = original.definition
        tree = definition.inductor_tree
        reversed_tree = replace(tree, edges=((1, 0),) + tree.edges[1:])
        other = build_nominal_circuit(load_constraint("RF-T005", allow_trial=True),
                                      replace(definition, inductor_tree=reversed_tree))
        boundary = dict(injected_currents_a=[.02, 0, 0, 0],
                        termination_admittances_s=[.02, 0, 0, 1/60])
        va, ia = solve_branch_mna(original, values(original), 1e9, 0, **boundary)
        vb, ib = solve_branch_mna(other, values(other, -.2), 1e9, 0, **boundary)
        np.testing.assert_allclose(va, vb, atol=1e-12, rtol=1e-12)
        np.testing.assert_allclose(ia, ib * [-1, 1, 1], atol=1e-12, rtol=1e-12)

    def test_off(self):
        check_off_state()

    def test_invalid(self):
        check_invalid()

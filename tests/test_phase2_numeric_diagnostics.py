"""Stage-1 boundary regression: typed forward errors and arbitrary L/C graphs.

All tests use synthetic circuits or frozen numeric fixtures. They do not
claim RF feasibility, optimizer convergence or independent MNA validation.
"""
import copy
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from lpf.constraint_versions import load_constraint
from lpf.phase2_models.circuit_layout import (
    CapacitorPlacement, InductorTree, incidence_matrix,
)
from lpf.phase2_models.coupled_lc import (
    CircuitValues, CoupledLCTopology, CoupledLCEvaluator, ParameterVectorSchema,
)
from lpf.phase2_models.numerical_diagnostics import CircuitNumericalError
from lpf.phase2_models import exp055

RUNS = ROOT / "experiments/chatgpt_topology_search/runs"


class Stage1NumericalFailureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.policy = load_constraint("RF-T007", allow_trial=True)

    def legacy_fixture(self):
        x = np.asarray(json.loads((
            RUNS / "EXP-055/checkpoints/cv1_input_tip_best.json"
        ).read_text())["vector"], float)
        edges = exp055.capacitor_edges("cv1_input_tip")
        topo = CoupledLCTopology(
            InductorTree(5, exp055.L_EDGES),
            exp055.K_PAIRS, (25.,) * 4,
            edges, tuple(float(z) for z in exp055.Q_C),
        )
        schema = ParameterVectorSchema(4, 4, 3, 0, 3, (0.5,))
        return CoupledLCEvaluator(self.policy, 3, topo, schema), x

    def test_mutual_spd_failure_has_stable_error_code(self):
        t = CoupledLCTopology(
            InductorTree(4, ((0, 1), (1, 2), (1, 3))),
            ((0, 1), (0, 2), (1, 2)), (25.,)*3,
            ((0, 1),), (40.,),
        )
        bad = CircuitValues((1., 1., 1.), (-.9, -.9, -.9),
                            ((.1,),)*6)
        with self.assertRaises(CircuitNumericalError) as c:
            t.matrices(bad)
        self.assertEqual(c.exception.code, "mutual_not_spd")
        self.assertIsNone(c.exception.sample_index)

    def test_batched_schur_singular_has_diagnostic(self):
        ev, x = self.legacy_fixture()
        count, nodes = ev.f.size, ev.topology.inductor_tree.node_count
        disconnected = np.zeros((count, nodes, nodes), complex)
        # The L/C assembled model is synthetically replaced ONLY in the
        # regression harness to isolate the Schur solver failure path.
        with patch.object(CoupledLCTopology, "node_admittance",
                          return_value=disconnected):
            with self.assertRaises(CircuitNumericalError) as c:
                ev.il(x)
        self.assertEqual(c.exception.code, "schur_solve_failed")

    def test_transfer_zero_has_indexed_diagnostic(self):
        ev, x = self.legacy_fixture()
        nodes = ev.topology.inductor_tree.node_count
        diagonal = np.broadcast_to(
            np.eye(nodes, dtype=complex), (ev.f.size, nodes, nodes)
        ).copy()
        with patch.object(CoupledLCTopology, "node_admittance",
                          return_value=diagonal):
            with self.assertRaises(CircuitNumericalError) as c:
                ev.il(x)
        self.assertEqual(c.exception.code, "transfer_singular")
        self.assertEqual(c.exception.sample_index, 0)

    def test_bad_frequency_setting_and_early_schema_rejection(self):
        ev, x = self.legacy_fixture()
        val = ev.schema.decode(x)
        t = ev.topology
        for omega, settings in (
            ([0.], [0]), ([float("nan")], [0]),
            ([1.], [6]), ([1.], [-1]), ([1.], [0.5]),
            ([1.], [True]), ([1., 2.], [0]),
        ):
            with self.subTest(omega=omega, settings=settings):
                with self.assertRaises(ValueError):
                    t.node_admittance(val, omega, settings)
        for index in (0, 1):
            y = x.copy()
            y[index] = float("inf") if index == 0 else float("nan")
            with self.assertRaises(ValueError):
                ev.il(y)
        with self.assertRaises(ValueError):
            ev.il(x[:-1])

    def test_port_impedance_came_from_policy_and_bad_values_rejected(self):
        ev, x = self.legacy_fixture()
        self.assertEqual(ev.source_ohms, 50.0 + 0j)
        self.assertEqual(ev.load_ohms, 60.0 - 40j)
        self.assertTrue(np.all(np.isfinite(ev.il(x))))
        for key, val in (
            ("source_ohms", {"real": 0, "imag": 0}),
            ("source_ohms", {"real": float("nan"), "imag": 0}),
            ("load_ohms", {"real": -1, "imag": -40}),
            ("load_ohms", {"real": 60, "imag": float("inf")}),
            ("load_ohms", {"real": 60, "imag": -40,
                           "frequency_dependent": True}),
        ):
            with self.subTest(key=key, val=val):
                policy = copy.deepcopy(self.policy)
                policy[key] = val
                with self.assertRaises(ValueError):
                    CoupledLCEvaluator(policy, 3, ev.topology, ev.schema)

    def test_graph_dimension_ports_orientation_and_duplicate_checks(self):
        good = InductorTree(
            6, ((0, 1), (1, 2), (1, 3), (4, 3), (4, 5)),
            source_node=1, load_node=5,
        )
        self.assertEqual(good.incidence().shape, (6, 5))
        self.assertEqual(good.source_node, 1)
        self.assertEqual(good.load_node, 5)
        for edges in (
            ((0, 1), (1, 2), (1, 3), (3, 4), (4, 0)),
            ((0, 1), (1, 2), (1, 3), (3, 4), (4, 6)),
            ((0, 1), (1, 2), (1, 3), (3, 4), (1, 0)),
            ((0, 1), (1, 2), (1, 3), (3, 4), (5, 5)),
        ):
            with self.subTest(edges=edges), self.assertRaises(ValueError):
                InductorTree(6, edges)
        for kwargs in ({"source_node": 2, "load_node": 2},
                       {"source_node": -1, "load_node": 2},
                       {"source_node": 0, "load_node": 6}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                InductorTree(6, good.edges, **kwargs)
        with self.assertRaises(ValueError):
            InductorTree(3, ((0, -1), (1, 2)))
        cap = CapacitorPlacement(
            6, fixed_edges=((0, 3), (3, 0)),
            variable_edges=((5, -1), (0, 4)),
            ic_fixed_edges=((-1, 5), (4, 0)),
        )
        self.assertEqual(cap.incidence().shape, (6, 6))
        self.assertEqual(cap.fixed_edges[0], (0, 3))
        self.assertEqual(cap.fixed_edges[1], (3, 0))
        with self.assertRaises(ValueError):
            CapacitorPlacement(6, (), ((3, -1),), ((4, -1),))
        with self.assertRaises(ValueError):
            CapacitorPlacement(6, ((-1, -1),), (), ())
        with self.assertRaises(ValueError):
            CapacitorPlacement(6, ((0, 7),), (), ())

    def test_synthetic_non_three_or_four_l_graph_uses_same_nodal_kernel(self):
        tree = InductorTree(
            6, ((0, 1), (1, 3), (3, 4), (4, 5), (5, 2)),
            source_node=0, load_node=2,
        )
        topo = CoupledLCTopology(
            tree, (), (25.,)*5,
            ((0, -1), (5, -1), (2, -1)), (60., 60., 60.),
        )
        schema = ParameterVectorSchema(5, 3, 0, 0, 0)
        x = np.array([2., 3., 4., 5., 6., .1, .1, .1])
        ev = CoupledLCEvaluator(self.policy, 3, topo, schema)
        self.assertEqual(ev.schema.decode(x).inductances_nh, (2., 3., 4., 5., 6.))
        y = ev.il(x)
        self.assertEqual(y.shape, (84,))
        self.assertTrue(np.all(np.isfinite(y)))
        np.testing.assert_array_equal(y, ev.il(x))
        # Synthetic numeric graph is NOT a policy-verified physical design.


if __name__ == "__main__":
    unittest.main()

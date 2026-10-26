"""Issue #163 Stage-1 topology injection: structural and numeric regressions.

These tests reuse frozen saved vectors; they are not new optimization runs and
do not promote alternate graphs to verified feasible RF candidates.
"""
from dataclasses import FrozenInstanceError
import json
import sys
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from lpf.constraint_versions import load_constraint
from lpf.phase2_models.circuit_layout import (
    CapacitorPlacement, InductorTree, incidence_matrix,
    normalized_capacitor_edge,
)
from lpf.phase2_models import exp055, exp058_area4, exp058_area4l_gjm

RUNS = ROOT / "experiments/chatgpt_topology_search/runs"
SNAP = ROOT / "data/pareto_snapshots"

DEFAULT = ((0, 1), (1, 3), (1, 4), (1, 2))
ALTERNATE = ((0, 1), (0, 3), (1, 4), (1, 2))


class Phase2ImmutableCircuitLayoutTests(unittest.TestCase):
    def test_3l_and_4l_tree_incidence_matches_frozen_branch_orientation(self):
        tree3 = InductorTree(4, ((0, 1), (1, 2), (1, 3)))
        tree4 = InductorTree(5, DEFAULT)
        self.assertEqual(tree3.incidence().shape, (4, 3))
        np.testing.assert_array_equal(tree3.incidence(),
                                      np.array(((1, 0, 0), (-1, 1, 1),
                                                (0, -1, 0), (0, 0, -1))))
        np.testing.assert_array_equal(tree4.incidence(),
                                      exp055.incidence(DEFAULT))
        self.assertEqual(tree4.edges, DEFAULT)
        with self.assertRaises(FrozenInstanceError):
            tree4.edges = ALTERNATE
        # No shared mutable incidence matrix is returned.
        mutable = tree4.incidence()
        mutable[0, 0] = 999
        self.assertEqual(tree4.incidence()[0, 0], 1)

    def test_invalid_inductor_trees_are_rejected(self):
        bad = (
            ((0, 1), (1, 3), (1, 4), (1, 0)),  # undirected duplicate
            ((0, 1), (1, 2), (2, 0), (3, 4)),  # disconnected cycle
            ((0, 1), (1, 3), (1, 4), (3, -1)), # L grounded in hot-node tree
            ((0, 1), (1, 3), (1, 4), (3, 3)),  # loop
            ((0, 1), (1, 3), (1, 4), (3, 5)),  # outside node range
        )
        for edges in bad:
            with self.subTest(edges=edges), self.assertRaises(ValueError):
                InductorTree(5, edges)
        with self.assertRaises(ValueError):
            InductorTree(5, DEFAULT, source_node=0, load_node=0)

    def test_capacitor_shunt_and_parallel_composite_placement(self):
        p = CapacitorPlacement(
            5, fixed_edges=((0, 1), (-1, 4)),
            variable_edges=((3, -1), (1, 2)),
            ic_fixed_edges=((-1, 3), (2, 1)),
        )
        self.assertEqual(p.edges[0], (0, 1))
        self.assertEqual(p.incidence().shape, (5, 6))
        self.assertEqual(normalized_capacitor_edge((-1, 4), 5), (4, -1))
        np.testing.assert_array_equal(
            incidence_matrix(((3, -1), (-1, 3)), 5),
            np.array(((0, 0), (0, 0), (0, 0), (1, -1), (0, 0)))
        )
        # T007 style: variable C with no composite IC fixed C.
        self.assertEqual(CapacitorPlacement(
            5, variable_edges=((3, -1),)).ic_fixed_edges, ())
        with self.assertRaises(ValueError):
            CapacitorPlacement(5, variable_edges=((3, -1),),
                               ic_fixed_edges=((2, 1),))
        with self.assertRaises(ValueError):
            CapacitorPlacement(5, variable_edges=((3, -1), (1, 2)),
                               ic_fixed_edges=((3, -1),))

    def test_exp055_inductor_tree_injection_is_isolated(self):
        policy = load_constraint("RF-T007", allow_trial=True)
        doc = json.loads((RUNS / "EXP-055/checkpoints/cv1_input_tip_best.json").read_text())
        x = np.asarray(doc["vector"], float)
        original = exp055.L_EDGES
        baseline = exp055.Evaluator(policy, 3, "cv1_input_tip")
        modified = exp055.Evaluator(
            policy, 3, "cv1_input_tip", l_edges=InductorTree(5, ALTERNATE)
        )
        original_il = baseline.il(x).copy()
        other_il = modified.il(x)
        self.assertGreater(float(np.max(np.abs(original_il - other_il))), 1e-6)
        np.testing.assert_array_equal(baseline.il(x), original_il)
        self.assertEqual(exp055.L_EDGES, original)
        with self.assertRaises(AttributeError):
            baseline.L_edges = ALTERNATE
        mna = exp055.independent_mna(
            policy, x, "cv1_input_tip", 3, l_edges=modified.inductor_tree
        )
        self.assertTrue(mna["pass"], mna)

    def test_exp058_mixed_4l_graph_has_independent_mna_without_mutation(self):
        policy = load_constraint("RF-T008", allow_trial=True)
        row = json.loads((SNAP / "rf_t008_exp058_area4p667_20261020.json").read_text())["best"]
        x = np.asarray(row["vector"], float)
        baseline = exp058_area4l_gjm.Evaluator(
            policy, "input_output", ("cf0",), 3
        )
        changed = exp058_area4l_gjm.Evaluator(
            policy, "input_output", ("cf0",), 3, l_edges=ALTERNATE
        )
        v0 = baseline.il(x).copy()
        v1 = changed.il(x)
        self.assertGreater(float(np.max(np.abs(v0 - v1))), 1e-6)
        np.testing.assert_array_equal(baseline.il(x), v0)
        self.assertEqual(exp055.L_EDGES, DEFAULT)
        check = exp058_area4l_gjm.independent_mna(
            policy, "input_output", ("cf0",), x, l_edges=ALTERNATE
        )
        self.assertTrue(check["pass"], check)

    def test_exp058_zero_gjm_4l_accepts_explicit_graph(self):
        policy = load_constraint("RF-T008", allow_trial=True)
        row = json.loads((SNAP / "rf_t008_exp058_area4_20261020.json").read_text())["best_cost_cell"]
        x = np.asarray(row["vector"], float)
        baseline = exp058_area4.Evaluator(policy, "shunt_output", "cp", 3)
        changed = exp058_area4.Evaluator(
            policy, "shunt_output", "cp", 3, l_edges=ALTERNATE
        )
        v0 = baseline.il(x).copy()
        v1 = changed.il(x)
        self.assertGreater(float(np.max(np.abs(v0 - v1))), 1e-6)
        np.testing.assert_array_equal(baseline.il(x), v0)
        check = exp058_area4.independent_mna(
            policy, "shunt_output", "cp", x, l_edges=ALTERNATE
        )
        self.assertTrue(check["pass"], check)


if __name__ == "__main__":
    unittest.main()

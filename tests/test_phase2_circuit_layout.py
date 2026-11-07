"""Synthetic structural regressions, independent of historical EXP models."""
from dataclasses import FrozenInstanceError
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import numpy as np
from lpf.topology_management.circuit_layout import (
    CapacitorPlacement, InductorTree, incidence_matrix, normalized_capacitor_edge,
)


class Phase2ImmutableCircuitLayoutTests(unittest.TestCase):
    def test_tree_orientation_immutability_and_invalid_graphs(self):
        tree3 = InductorTree(4, ((0, 1), (1, 2), (1, 3)))
        np.testing.assert_array_equal(tree3.incidence(),
            [[1, 0, 0], [-1, 1, 1], [0, -1, 0], [0, 0, -1]])
        edges = ((0, 1), (1, 3), (1, 4), (1, 2))
        tree4 = InductorTree(5, edges)
        np.testing.assert_array_equal(tree4.incidence(),
            [[1, 0, 0, 0], [-1, 1, 1, 1], [0, 0, 0, -1],
             [0, -1, 0, 0], [0, 0, -1, 0]])
        with self.assertRaises(FrozenInstanceError):
            tree4.edges = edges
        mutable = tree4.incidence(); mutable[0, 0] = 999
        self.assertEqual(tree4.incidence()[0, 0], 1)
        for bad in (((0, 1), (1, 3), (1, 4), (1, 0)),
                    ((0, 1), (1, 2), (2, 0), (3, 4)),
                    ((0, 1), (1, 3), (1, 4), (3, -1)),
                    ((0, 1), (1, 3), (1, 4), (3, 3)),
                    ((0, 1), (1, 3), (1, 4), (3, 5))):
            with self.subTest(edges=bad), self.assertRaises(ValueError):
                InductorTree(5, bad)
        with self.assertRaises(ValueError):
            InductorTree(5, edges, source_node=0, load_node=0)

    def test_capacitor_shunt_and_parallel_composite_placement(self):
        p = CapacitorPlacement(5, ((0, 1), (-1, 4)), ((3, -1), (1, 2)),
                               ((-1, 3), (2, 1)))
        self.assertEqual(p.edges[0], (0, 1))
        self.assertEqual(p.incidence().shape, (5, 6))
        self.assertEqual(normalized_capacitor_edge((-1, 4), 5), (4, -1))
        np.testing.assert_array_equal(incidence_matrix(((3, -1), (-1, 3)), 5),
            [[0, 0], [0, 0], [0, 0], [1, -1], [0, 0]])
        self.assertEqual(CapacitorPlacement(5, variable_edges=((3, -1),)).ic_fixed_edges, ())
        for var, fixed in ((((3, -1),), ((2, 1),)),
                           (((3, -1), (1, 2)), ((3, -1),))):
            with self.assertRaises(ValueError):
                CapacitorPlacement(5, variable_edges=var, ic_fixed_edges=fixed)

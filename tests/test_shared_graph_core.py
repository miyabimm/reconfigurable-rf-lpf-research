"""Backwards compatibility and policy-scoped shared graph primitives.

The legacy P2/P3/P4 budget in graph_search is NOT a formal RF constraint.
"""
import sys
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "experiments" / "matching_limit"))

import topology_selection as old_selection
import selection_patch as old_node_selection
import coupling_layout as old_coupling
from lpf import legacy_graph_search as core
from lpf import coupling_layout as shared_coupling
from lpf.constraint_versions import load_constraint


class GraphCoreCompatibilityTests(unittest.TestCase):
    def test_legacy_imports_delegate_to_one_canonical_implementation(self):
        for name in (
            "area_thirds", "has_signal_path",
            "has_unproductive_internal_leaf", "topology_signature",
            "select_balanced",
        ):
            self.assertIs(getattr(old_selection, name), getattr(core, name))
        self.assertIs(old_node_selection.select_node_balanced,
                      core.select_node_balanced)
        for name in (
            "admissible_matrix", "validate_coupling_matrix",
            "adjacent_patterns",
        ):
            self.assertIs(getattr(old_coupling, name),
                          getattr(shared_coupling, name))

    def test_legacy_finite_balancing_still_keeps_all_three_bins(self):
        graphs = [
            (3, ((1, 2, "LQP02"),) * 1),
            (3, ((1, 2, "LQP02"),) * 3),
            (3, ((1, 2, "LQP02"),) * 5),
        ]
        selected, counts = core.select_balanced(graphs, 1)
        self.assertEqual([bin_index for bin_index, _ in selected], [0, 1, 2])
        self.assertEqual(list(counts.values()), [1, 1, 1])
        self.assertEqual(core.select_balanced(graphs, 1),
                         old_selection.select_balanced(graphs, 1))
        self.assertEqual(core.select_node_balanced(graphs, 1),
                         old_node_selection.select_node_balanced(graphs, 1))

    def test_rff003_signed_neighbor_coupling_remains_physical_and_spd(self):
        policy = load_constraint("RF-F003")
        types = ("LQP02HV", "LQP02HV")
        values = (3e-9, 4e-9)
        edges = {frozenset((0, 1)): 0.05}
        k = shared_coupling.admissible_matrix(
            types, values, chip_edges=edges, resolved_policy=policy
        )
        self.assertTrue(np.allclose(k, ((1, 0.05), (0.05, 1))))
        self.assertTrue(shared_coupling.validate_coupling_matrix(
            types, values, k, resolved_policy=policy
        ))
        self.assertTrue(np.array_equal(
            old_coupling.admissible_matrix(
                types, values, chip_edges=edges, resolved_policy=policy
            ), k
        ))
        with self.assertRaises(ValueError):
            shared_coupling.admissible_matrix(
                types, values,
                chip_edges={frozenset((0, 1)): 0.11},
                resolved_policy=policy
            )


if __name__ == "__main__":
    unittest.main()

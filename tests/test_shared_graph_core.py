"""Historical finite-search graph primitives.

The legacy P2/P3/P4 budget in graph_search is NOT a formal RF constraint.
"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from lpf import legacy_graph_search as core


class GraphCoreCompatibilityTests(unittest.TestCase):
    def test_legacy_finite_balancing_still_keeps_all_three_bins(self):
        graphs = [
            (3, ((1, 2, "LQP02"),) * 1),
            (3, ((1, 2, "LQP02"),) * 3),
            (3, ((1, 2, "LQP02"),) * 5),
        ]
        selected, counts = core.select_balanced(graphs, 1)
        self.assertEqual([bin_index for bin_index, _ in selected], [0, 1, 2])
        self.assertEqual(list(counts.values()), [1, 1, 1])
        node_selected, node_counts = core.select_node_balanced(graphs, 1)
        self.assertEqual([cell for cell, _ in node_selected], [(0, 0), (0, 1), (0, 2)])
        self.assertEqual(list(node_counts.values()), [1, 1, 1])

if __name__ == "__main__":
    unittest.main()

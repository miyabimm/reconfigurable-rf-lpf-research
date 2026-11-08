import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'experiments'/'matching_limit'))
from coverage_sampler import sample_graphs
from selection_patch import select_node_balanced
class NodeAreaSelectionTest(unittest.TestCase):
    def test_all_15_cells_with_seeded_sample(self):
        graphs,_=sample_graphs(attempts_per_cell=200,seed=20261011)
        chosen,eligible=select_node_balanced(graphs,2)
        self.assertEqual(len(eligible),15)
        self.assertEqual(len(chosen),30)
        self.assertEqual(set(cell for cell,_ in chosen),
                         {(n,b) for n in range(5) for b in range(3)})
    def test_invalid_budget(self):
        with self.assertRaises(ValueError):
            select_node_balanced([], -1)

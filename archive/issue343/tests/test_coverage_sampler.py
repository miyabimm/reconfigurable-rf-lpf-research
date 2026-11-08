import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'experiments'/'matching_limit'))
from coverage_sampler import sample_graphs
from topology_selection import area_thirds,has_signal_path,has_unproductive_internal_leaf
class CoverageTest(unittest.TestCase):
    def test_reproducible_and_physical_structure(self):
        a,c=sample_graphs(attempts_per_cell=150)
        b,d=sample_graphs(attempts_per_cell=150)
        self.assertEqual(a,b);self.assertEqual(c,d)
        for g in a:
            self.assertTrue(has_signal_path(g))
            self.assertFalse(has_unproductive_internal_leaf(g))
            self.assertLessEqual(area_thirds(g),18)
            self.assertLessEqual(sum(t=='PCB_L' for _,_,t in g[1]),3)
    def test_all_node_and_area_bins(self):
        _,counts=sample_graphs(attempts_per_cell=500)
        for internal in range(5):
            for bin_index in range(3):
                self.assertGreater(counts[(internal,bin_index,'accepted')],0)

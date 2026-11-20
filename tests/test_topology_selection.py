import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from lpf.legacy_graph_search import select_balanced,has_signal_path,has_unproductive_internal_leaf
class TestSelection(unittest.TestCase):
    def test_no_ground_only_path(self):
        self.assertFalse(has_signal_path((3,((0,1,'GJM01'),(0,2,'GJM01')))))
    def test_grounded_series_path(self):
        self.assertTrue(has_signal_path((3,((1,2,'LQP02'),(0,2,'GJM01')))))
    def test_internal_leaf(self):
        self.assertTrue(has_unproductive_internal_leaf((4,((1,2,'LQP02'),(1,3,'LQP02')))))
    def test_three_bins(self):
        g=[(3,((1,2,'LQP02'),)),(3,((1,2,'LQP02'),)*3),(3,((1,2,'LQP02'),)*5)]
        picked,counts=select_balanced(g,1)
        self.assertEqual([i for i,_ in picked],[0,1,2])
        self.assertEqual(list(counts.values()),[1,1,1])
    def test_empty_bin_not_misreported(self):
        picked,counts=select_balanced([(3,((1,2,'LQP02'),))],3)
        self.assertEqual(counts['P4'],0)
        self.assertEqual(len(picked),1)

import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'experiments'/'matching_limit'))
from selection_patch import select_node_balanced
class NodeAreaSelectionTest(unittest.TestCase):
    def test_invalid_budget(self):
        with self.assertRaises(ValueError):
            select_node_balanced([], -1)

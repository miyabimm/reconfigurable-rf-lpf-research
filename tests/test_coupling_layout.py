import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'experiments'/'matching_limit'))
from coupling_layout import admissible_matrix,adjacent_patterns
from functools import partial
from src.lpf.constraint_versions import load_constraint
legacy=load_constraint('RF-F003')
admissible_matrix=partial(admissible_matrix,resolved_policy=legacy)
adjacent_patterns=partial(adjacent_patterns,resolved_policy=legacy)
class CouplingLayoutTests(unittest.TestCase):
    def test_neighbor_only(self):
        types=['LQP02','LQP02','LQP02']
        admissible_matrix(types,[1,1,1],chip_edges={frozenset((0,1)):.1,frozenset((1,2)):.1})
        with self.assertRaises(ValueError):
            admissible_matrix(types,[1,1,1],chip_edges={frozenset((0,2)):.1})
    def test_patterns(self):
        self.assertEqual(len(list(adjacent_patterns(['LQP02']*3))),9)
    def test_spd(self):
        with self.assertRaises(ValueError):
            admissible_matrix(['PCB_L']*3,[1e-9]*3,pcb_pairs={
                frozenset((0,1)):.6,frozenset((1,2)):.6,frozenset((0,2)):-.6})
    def test_chip_pcb_limit(self):
        with self.assertRaises(ValueError):
            admissible_matrix(['LQP02','PCB_L'],[1e-9,1e-9],chip_pcb={frozenset((0,1)):.04})

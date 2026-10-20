"""EXP-055 F003 circuit provenance and T007 parasitic regression tests."""
import json
import sys
import unittest
from pathlib import Path
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
sys.path.insert(0,str(ROOT/"experiments/chatgpt_topology_search/runs/EXP-055"))
import adapt_f003_4l as e
from lpf.constraint_versions import load_constraint

class TestExp055(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.policy=load_constraint("RF-T007",allow_trial=True)
        cls.seed=np.asarray(json.loads(e.SRC.read_text())["vector"],float)

    def test_one_grounded_dtc_and_valid_branch_bounds(self):
        self.assertEqual(e.L_EDGES,((0,1),(1,3),(1,4),(1,2)))
        self.assertEqual(e.K_PAIRS,((0,1),(1,3),(3,2)))
        self.assertEqual(e.Q_C.tolist(),[80.,80.,40.,40.,35.,35.,35.,40.])
        self.assertEqual(len(e.VARIANTS),6)
        for name in e.VARIANTS:
            edges=e.capacitor_edges(name)
            self.assertEqual(edges[4],edges[7])
            self.assertEqual(edges[4],(3,-1))
            self.assertTrue(edges[5][0]>=0 and edges[5][1]>=0)
            self.assertEqual(e.bounds(name).shape,(29,2))
        self.assertTrue(np.all(e.bounds("two_dtc")[12::3,1]==0))

    def test_f003_original_and_t007_parasitic_are_distinct(self):
        old=e.Evaluator(self.policy,17,"two_dtc",False)
        new=e.Evaluator(self.policy,17,"two_dtc",True)
        original=old.summary(self.seed)
        self.assertLess(abs(original["worst_IL_db"]-.8436523315639586),2e-3)
        off=self.seed.copy()
        off[11::3]=0
        delta=float(np.max(np.abs(new.il(off)-old.il(off))))
        self.assertGreater(delta,1e-5)
        self.assertTrue(np.isfinite(new.il(self.seed)).all())
        self.assertGreater(new.summary(self.seed)["min_M_eigenvalue_nH"],0)

    def test_non_ground_cv1_off_is_not_an_extra_parasitic(self):
        a=e.Evaluator(self.policy,3,"two_dtc",True)
        b=e.Evaluator(self.policy,3,"cv1_input_output",True)
        self.assertLess(float(np.max(abs(a.il(self.seed)-b.il(self.seed)))),1e-9)
        cross=e.independent_mna(self.policy,self.seed,"two_dtc",3)
        self.assertTrue(cross["pass"],cross)

if __name__=="__main__":
    unittest.main()

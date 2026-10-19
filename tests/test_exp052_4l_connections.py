"""EXP-052 Phase2 4L connection enumeration and RF-T007 parasitic count."""
import json
import sys
import unittest
from pathlib import Path

import numpy as np

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
sys.path.insert(0,str(ROOT/"experiments/chatgpt_topology_search/runs/EXP-052"))
import sweep_4l_connections as sweep
from lpf.constraint_versions import load_constraint

class FourLConnectionTests(unittest.TestCase):
    def test_topological_enumeration(self):
        self.assertEqual(len(sweep.VARIANTS),9)
        self.assertEqual(len(set(sweep.VARIANTS.values())),9)
        for name,edges in sweep.VARIANTS.items():
            self.assertEqual(edges[0][1],-1,name)
            self.assertEqual(edges[1][1]!=-1,True)
            self.assertEqual(edges[2][1]!=-1,True)
            self.assertNotEqual(edges[1][0],edges[1][1])
            self.assertNotEqual(edges[2][0],edges[2][1])
            self.assertEqual(sweep.CF_EDGES,((0,1),(1,2),(4,-1)))
            self.assertEqual(sweep.Q.tolist(),[80,40,80,35,35,35,40])

    def test_legacy_4l_reference_identity(self):
        policy=load_constraint("RF-T007",allow_trial=True)
        x=np.array(json.loads(sweep.CP.read_text())["vector"],float)
        src=sweep.exp51.Evaluator(policy,3,False)
        ref=sweep.Evaluator(policy,3,"reference")
        self.assertLess(float(np.max(np.abs(src.il(x)-ref.il(x)))),1e-8)
        self.assertAlmostEqual(ref.summary(x)["worst_IL_db"],src.summary(x)["worst_IL_db"],places=8)
        for name in sweep.VARIANTS:
            ev=sweep.Evaluator(policy,3,name)
            self.assertEqual(ev.cap_inc.shape,(5,7))
            self.assertEqual(ev.cap_edges[3],ev.cap_edges[-1])
            self.assertEqual(ev.cap_edges[3][1],-1)
            m=ev.summary(x)
            self.assertTrue(np.isfinite(m["worst_IL_db"]))
            self.assertGreater(m["L_matrix_min_eig_nH"],0)

if __name__=="__main__":
    unittest.main()

"""EXP-052 fixed-capacitor electrical topology enumeration regression."""
import json
import sys
import unittest
from pathlib import Path
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
sys.path.insert(0,str(ROOT/"experiments/chatgpt_topology_search/runs/EXP-052"))
import sweep_4l_fixed_c as research
from lpf.constraint_versions import load_constraint

class TestFixedCapTopology(unittest.TestCase):
    def test_physical_fixed_C_count_and_distinct_edges(self):
        self.assertEqual(len(research.CONFIGS),10)
        self.assertEqual(len(set(research.CONFIGS.values())),10)
        for key,edges in research.CONFIGS.items():
            self.assertEqual(len(edges),3)
            self.assertEqual(edges[0][0]>=0,True)
            self.assertTrue(all(a>=0 and -1<=b<5 and a!=b for a,b in edges))
            self.assertEqual(research.edge.Q.tolist(),[80,40,80,35,35,35,40])

    def test_reproduce_reference_and_all_finite(self):
        p=load_constraint("RF-T007",allow_trial=True)
        vector=np.asarray(json.loads(research.edge.CP.read_text())["vector"],float)
        base=research.edge.exp51.Evaluator(p,3,False)
        ref=research.Evaluator(p,3,"reference")
        self.assertLess(float(np.max(abs(base.il(vector)-ref.il(vector)))),1e-8)
        for name,edges in research.CONFIGS.items():
            ev=research.Evaluator(p,3,name)
            self.assertEqual(ev.cap_edges[:3],edges)
            self.assertEqual(ev.cap_edges[3],(4,-1))
            self.assertEqual(ev.cap_edges[-1],(4,-1))
            self.assertEqual(ev.cap_inc.shape,(5,7))
            self.assertTrue(np.all(np.isfinite(ev.il(vector))))

if __name__=="__main__":
    unittest.main()

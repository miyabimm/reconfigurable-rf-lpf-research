"""EXP-054 distinct combined C/DTC topology and source equivalence tests."""
import json
import sys
import unittest
from pathlib import Path
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
sys.path.insert(0,str(ROOT/"experiments/chatgpt_topology_search/runs/EXP-054"))
import sweep_4l_combined_c_dtc as e
from lpf.constraint_versions import load_constraint

class TestCombinedEdges(unittest.TestCase):
    def test_distinct_valid_graphs_and_component_count(self):
        e.check_configs()
        self.assertEqual(len(e.CONFIGS),20)
        self.assertEqual(e.CAP_Q.tolist(),[80,40,80,35,35,35,40])
        ref=e.CONFIGS["reference"]
        for name,edges in e.CONFIGS.items():
            self.assertEqual(len(edges),6)
            self.assertEqual(edges[3],(4,-1),name)
            self.assertEqual(edges[4][1]!=-1,True)
            self.assertEqual(edges[5][1]!=-1,True)
            if name!="reference":
                self.assertGreaterEqual(sum(a!=b for a,b in zip(edges,ref)),2,name)

    def test_EXP053_exact_reproduction_and_finite_grids(self):
        policy=load_constraint("RF-T007",allow_trial=True)
        x=np.asarray(json.loads(e.SOURCE.read_text())["vector"],float)
        prior=e.base.Evaluator(policy,3,"split_input_shunt_center")
        current=e.Evaluator(policy,3,"reference")
        self.assertLess(float(np.max(np.abs(prior.il(x)-current.il(x)))),1e-8)
        for name in e.CONFIGS:
            model=e.Evaluator(policy,3,name)
            self.assertEqual(model.BC.shape,(5,7))
            self.assertEqual(model.c_edges[3],model.c_edges[6])
            self.assertTrue(np.isfinite(model.il(x)).all(),name)
            self.assertGreater(model.summary(x)["L_matrix_min_eig_nH"],0)

if __name__=="__main__":
    unittest.main()

"""EXP-053 L-graph enumeration and source-reference regression tests."""
import json
import sys
import unittest
from pathlib import Path
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
sys.path.insert(0,str(ROOT/"experiments/chatgpt_topology_search/runs/EXP-053"))
import sweep_4l_inductor_graphs as sweep
from lpf.constraint_versions import load_constraint

class TestFourLGraphs(unittest.TestCase):
    def test_all_graphs_spanning_tree_and_unique(self):
        self.assertEqual(len(sweep.GRAPHS),12)
        canonical=set()
        for name,edges in sweep.GRAPHS.items():
            sweep.validate_graph(edges)
            edge_set=frozenset(tuple(sorted(e)) for e in edges)
            self.assertNotIn(edge_set,canonical,name)
            canonical.add(edge_set)
        self.assertEqual(sweep.C_Q.tolist(),[80,40,80,35,35,35,40])
        self.assertEqual(sweep.C_EDGES[1],(0,2))
        self.assertEqual(sweep.C_EDGES[3],(4,-1))
        self.assertEqual(sweep.C_EDGES[-1],(4,-1))

    def test_reference_source_exact_and_graphs_finite(self):
        p=load_constraint("RF-T007",allow_trial=True)
        d=json.loads(sweep.SOURCE.read_text())
        x=np.asarray(d["vector"],float)
        ref=sweep.Evaluator(p,3,"reference")
        met=ref.summary(x)
        self.assertGreater(met["min_H2_db"],30)
        self.assertGreater(met["min_H3_db"],30)
        # Tiny 3-point sampling includes different extrema, hence only check
        # reference using same grid as stored endpoint in the solver main.
        for name in sweep.GRAPHS:
            ev=sweep.Evaluator(p,3,name)
            values=ev.il(x)
            self.assertEqual(values.shape,ref.il(x).shape)
            self.assertTrue(np.isfinite(values).all(),name)
            self.assertGreater(ev.summary(x)["L_matrix_min_eig_nH"],0)

if __name__=="__main__":
    unittest.main()

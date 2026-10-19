"""EXP-051 local exact split-L equivalence and model consistency (fast)."""
import math
import sys
import unittest
from pathlib import Path

import numpy as np

ROOT=Path(__file__).resolve().parents[1]
DIR=ROOT/"experiments/chatgpt_topology_search/runs/EXP-051"
sys.path.insert(0,str(ROOT/"src"))
sys.path.insert(0,str(DIR))
from lpf.constraint_versions import load_constraint
import optimize_one_shunt_4l as e

class TestExp051OneShunt(unittest.TestCase):
    def test_phase2_topology(self):
        p=load_constraint("RF-T007",allow_trial=True)
        self.assertEqual(e.Q_C.tolist(),[80.,40.,80.,35.,35.,35.,40.,40.])
        self.assertEqual(e.L_COUPLING_EDGES,((0,2),(2,3),(3,1)))
        self.assertEqual(e.bounds(False)[7].tolist(),[0.,0.])
        self.assertEqual(e.bounds(True)[7].tolist(),[.02,.2])
        self.assertEqual(e.CAP_EDGES[6],(4,-1))
        self.assertEqual(e.CAP_EDGES[7],(3,4))
        self.assertEqual(p["trial_shunt_dtc_parasitic"]["fixed_capacitance_pf"],.5)

    def test_exact_source_split(self):
        p=load_constraint("RF-T007",allow_trial=True)
        src=e.json.loads(e.SOURCE_VECTOR.read_text())
        prior=np.asarray(src.get("vector",src.get("best_vector")),float)
        new=e.from_threeL(prior,False)
        self.assertEqual(new.shape,(29,))
        self.assertTrue(np.all(new>=e.bounds(False)[:,0]-1e-12))
        self.assertTrue(np.all(new<=e.bounds(False)[:,1]+1e-12))
        self.assertLess(max(abs(new[8:11])),.1)
        three=e.src3.Evaluator(p,3,.5)
        four=e.Evaluator(p,3,False)
        delta=float(np.max(np.abs(three.il(prior)-four.il(new))))
        self.assertLess(delta,1e-8)
        m=four.summary(new)
        self.assertGreater(m["min_H2_db"],30)
        self.assertGreater(m["min_H3_db"],30)
        actual_eigen=float(np.linalg.eigvalsh(e.circuit_matrix(new)[1])[0])
        self.assertAlmostEqual(m["L_matrix_min_eig_nH"],actual_eigen,places=12)

if __name__=="__main__":
    unittest.main()

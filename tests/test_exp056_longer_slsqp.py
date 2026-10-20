"""EXP-056 source checkpoint, warm-start validity and RF-T007 topology guard."""
import json
import sys
import unittest
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
sys.path.insert(0,str(ROOT/"experiments/chatgpt_topology_search/runs/EXP-056"))
import refine_nonconverged as exp
from lpf.constraint_versions import load_constraint

class TestExp056(unittest.TestCase):
 def test_saved_seeds_match_original_dense_grid_and_one_parasitic(self):
  pol=load_constraint("RF-T007",allow_trial=True)
  self.assertEqual(len(exp.SELECTED),2)
  for name,filename in exp.SELECTED.items():
   ed=exp.src.Evaluator(pol,17,name)
   path=ROOT/"experiments/chatgpt_topology_search/runs/EXP-055/checkpoints"/filename
   x,metrics=exp.load_checked_vector(path,name,ed)
   self.assertEqual(x.shape,(29,))
   self.assertEqual(ed.BC.shape,(5,8))
   edges=exp.src.capacitor_edges(name)
   self.assertEqual(edges[4],edges[7])
   self.assertEqual(edges[4],(3,-1))
   self.assertTrue(metrics["min_M_eigenvalue_nH"]>0)
   self.assertEqual(len(exp.runs(x,name,3,np.random.default_rng(56))),3)

 def test_winning_reference_unmodified(self):
  pol=load_constraint("RF-T007",allow_trial=True)
  obj=json.loads(exp.REFERENCE.read_text())
  m=exp.src.Evaluator(pol,17,"cv1_input_tip").summary(np.array(obj["vector"]))
  self.assertLess(abs(m["worst_IL_db"]-0.8173655897607699),2e-3)

if __name__=="__main__":
 unittest.main()

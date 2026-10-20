"""EXP-057 source and topology graph regression; no full numeric search."""
import json
import sys
import unittest
from pathlib import Path

import numpy as np
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"experiments/chatgpt_topology_search/runs/EXP-057"))
sys.path.insert(0,str(ROOT/"src"))
import sweep_from_exp055 as run
from lpf.constraint_versions import load_constraint
from lpf.slsqp_budget import STANDARD_SLSQP_BUDGET

class TestExp057(unittest.TestCase):
 def test_source_winner_reproduces(self):
  pol=load_constraint("RF-T007",allow_trial=True)
  saved=json.loads(run.SOURCE.read_text(encoding="utf-8"))
  x=np.array(saved["vector"],float)
  self.assertEqual(x.shape,(29,))
  ev=run.src.Evaluator(pol,17,run.CV1)
  m=ev.summary(x)
  self.assertAlmostEqual(m["worst_IL_db"],run.REF_IL,places=6)
  self.assertGreaterEqual(m["min_H2_db"],30)
  self.assertGreaterEqual(m["min_H3_db"],30)
  self.assertEqual(run.src.capacitor_edges(run.CV1),
    ((0,1),(4,-1),(1,2),(0,3),(3,-1),(0,3),(1,2),(3,-1)))
  self.assertEqual(run.src.Q_C.tolist(),[80,80,40,40,35,35,35,40])

 def test_graphs_distinct_connected_and_base_restored(self):
  self.assertEqual(len(run.GRAPHS),10)
  self.assertEqual(len({tuple(sorted(tuple(sorted(e)) for e in v)) for v in run.GRAPHS.values()}),10)
  self.assertEqual(run.src.L_EDGES,run.GRAPHS["control_exp055"])
  for edges in run.GRAPHS.values():
   run.validate_graph(edges)
  for bad in [((0,1),(1,0),(1,4),(1,2)),((0,1),(0,1),(1,4),(1,2)),
              ((0,1),(1,2),(2,0),(1,4))]:
   with self.assertRaises(ValueError):
    run.validate_graph(bad)

 def test_staged_budget_and_starts(self):
  self.assertEqual(STANDARD_SLSQP_BUDGET.as_dict()["primary"],{"coarse":240,"fine":120})
  self.assertEqual(STANDARD_SLSQP_BUDGET.as_dict()["recovery"],{"coarse":500,"fine":280})
  old=np.array(json.loads(run.SOURCE.read_text())["vector"],float)
  ss=run.starts(old,2,np.random.default_rng(20261077))
  self.assertEqual(len(ss),2)
  self.assertTrue(np.array_equal(ss[0],old))
  lowhigh=run.src.bounds(run.CV1)
  self.assertTrue(np.all(ss[1]>=lowhigh[:,0]) and np.all(ss[1]<=lowhigh[:,1]))

if __name__=="__main__":
 unittest.main()

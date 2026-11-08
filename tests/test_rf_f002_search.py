"""RF-F002/RF-T004 topology search: placement freedom and current bounds."""
import sys
import unittest
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "experiments" / "matching_limit"))

from lpf.constraint_versions import load_constraint
from lpf.circuit import solve
from lpf.independent import solve_gain
from p4_batch import bounds_for, settings_for


@unittest.skip('RF-F002 and RF-T004 are historical and cannot be loaded for execution')
class HistoricalPolicySearchTests(unittest.TestCase):
    def test_actual_series_only_path_instantiates_in_six_settings(self):
        # Fixed L path terminates at node 3. Series C completes path 3-to-2.
        graph=(4, ((1,3,"LQP02HV"),))
        for cid, allow in (("RF-F002",False), ("RF-T004",True)):
            policy=load_constraint(cid,allow_trial=allow)
            layout={"edges":((3,2),(3,0)), "roles":("series",None)}
            x=np.asarray([2.0]+[.5,.2]*6)
            configs=settings_for(graph,x,np.eye(1),variable_layout=layout,
                                 resolved_policy=policy,require_explicit_series=True)
            for cfg in configs.values():
                self.assertEqual(cfg["capacitors"][0].q, 50)
                self.assertAlmostEqual(cfg["capacitors"][0].value, 0.5e-12)
                primary=solve(700e6,**cfg)
                self.assertAlmostEqual(primary["gain"], solve_gain(700e6,**cfg),
                                       delta=1e-10)

    def test_historical_search_bounds(self):
        graph=(4,((1,3,"PCB_L"),(3,2,"LQP02HV")))
        for cid,allow,cap in (("RF-F002",False,2),("RF-T004",True,3)):
            policy=load_constraint(cid,allow_trial=allow)
            bounds=bounds_for(graph,variable_count=cap,resolved_policy=policy)
            self.assertEqual(bounds[0],(.3,2.0))
            self.assertTrue(all(value==(0.0,1.5) for value in bounds[2:]))



if __name__ == "__main__":
    unittest.main()

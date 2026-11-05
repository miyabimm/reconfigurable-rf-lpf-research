import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from lpf.circuit import Branch,solve
from lpf.validate import validate_couplings
from lpf.constraint_versions import load_constraint

class CircuitTests(unittest.TestCase):
    def test_direct(self):
        r=solve(700e6,1,1,1,load_ohms=50+0j)
        self.assertAlmostEqual(r['gain'],1,places=12)
        self.assertAlmostEqual(r['power_residual'],0,places=12)
    def test_series(self):
        r=solve(700e6,2,1,2,inductors=[Branch(1,2,3e-9,25)])
        self.assertGreater(r['il_db'],0)
        self.assertLess(abs(r['power_residual']),1e-12)
    def test_coupled(self):
        r=solve(700e6,3,1,3,
            inductors=[Branch(1,2,2e-9,25),Branch(2,3,2e-9,25)],
            capacitors=[Branch(2,0,1e-12,80)],coupling=[[1,.4],[.4,1]])
        self.assertLess(abs(r['power_residual']),1e-12)
    def test_policy(self):
        self.assertEqual(validate_couplings([[1,.1],[.1,1]],['chip','chip'],[0,1],[(0,1)],
                                            resolved_policy=load_constraint('RF-F003')),[])
        self.assertTrue(validate_couplings([[1,.4],[.4,1]],['chip','chip'],[0,1],[]))
        self.assertTrue(validate_couplings([[1,.7],[.7,1]],['pcb','pcb'],[]))

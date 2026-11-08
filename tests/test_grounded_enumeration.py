"""Grounded-circuit MNA check independent of the retired matching enumerator."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
sys.path.insert(0, str(ROOT / 'experiments' / 'matching_limit'))
from instantiate_graph import build_grounded_settings
from lpf.circuit import solve


class GroundedMnaTests(unittest.TestCase):
    def test_shunt_cap_and_series_inductor(self):
        settings = build_grounded_settings((3, ((1, 2, 'LQP02'), (2, 0, 'GJM01'))))
        result = solve(700e6, **settings['B71'])
        self.assertGreater(result['gain'], 0)
        self.assertLess(abs(result['power_residual']), 1e-10)


if __name__ == '__main__':
    unittest.main()

"""Small, fixed matching-only graph-to-MNA numerical reference.

This is a bounded regression on a known circuit, not evidence of optimal
matching loss or full-LPF harmonic compliance.
"""
import math
import sys
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from lpf.legacy_graph_builder import build_grounded_settings
from lpf.circuit import solve
from lpf.evaluate import CASES
from lpf.independent import solve_gain


class MatchingReferenceRegression(unittest.TestCase):
    def test_grounded_graph_six_setting_analytical_reference(self):
        # 50-ohm source -> 1.8nH Q25 series L -> 60-j40-ohm load;
        # 0.5pF Q80 fixed shunt capacitor across the load.
        graph = (3, ((1, 2, "LQP02"), (2, 0, "GJM01")))
        settings = build_grounded_settings(
            graph, [1.8e-9, 0.5e-12], caps=np.zeros((6, 2)))
        self.assertEqual(set(settings), set(CASES))
        expected_il = {800e6: 0.5243664040495912,
                       1000e6: 0.5100971607067548}
        for case in CASES:
            for f_hz, il_reference in expected_il.items():
                params = settings[case]
                result = solve(f_hz, **params)
                independent = solve_gain(f_hz, **params)
                self.assertAlmostEqual(result["gain"], independent, delta=1e-10)
                self.assertAlmostEqual(result["il_db"], il_reference, delta=1e-9)
                self.assertLess(abs(result["power_residual"]), 1e-12)

    def test_analytical_reference_is_not_derived_from_mna(self):
        f_hz = 800e6
        w = 2 * math.pi * f_hz
        z_l = w * 1.8e-9 / 25 + 1j * w * 1.8e-9
        y_cap = w * 0.5e-12 / (1 / 80 - 1j)
        load = 60 - 40j
        y_total = 1 / load + y_cap
        v_out = 1 / (1 + (50 + z_l) * y_total)
        gain = abs(v_out) ** 2 * (1 / load).real * (4 * 50)
        il = -10 * math.log10(gain)
        self.assertAlmostEqual(il, 0.5243664040495912, delta=1e-12)


if __name__ == "__main__":
    unittest.main()

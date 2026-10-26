"""Historical graph builder import compatibility and independent MNA parity."""
import sys
import unittest
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "experiments" / "matching_limit"))

import instantiate_graph as old
from lpf import legacy_graph_builder as shared
from lpf.circuit import solve
from lpf.evaluate import CASES
from lpf.independent import solve_gain
from lpf.constraint_versions import load_constraint


class SharedGraphBuilderTests(unittest.TestCase):
    def test_all_legacy_builder_entrypoints_delegate_to_shared_core(self):
        for name in ("branch_q", "check_graph", "build_settings",
                     "build_grounded_settings", "_fixed_parts", "_build_settings"):
            with self.subTest(name=name):
                self.assertIs(getattr(old, name), getattr(shared, name))
        for name in ("Q", "DEFAULT", "AREA_THIRDS", "CAP_TYPES"):
            self.assertIs(getattr(old, name), getattr(shared, name))

    def test_historical_grounded_network_is_six_setting_and_independently_verified(self):
        graph = (3, ((1, 2, "LQP02"), (2, 0, "GJM01")))
        policy = load_constraint("RF-F003")
        values = (1.8e-9, 0.5e-12)
        states = shared.build_grounded_settings(
            graph, values, caps=np.zeros((6, 2)), resolved_policy=policy
        )
        self.assertEqual(set(states), set(CASES))
        expected = {800e6: 0.5243664040495912,
                    1000e6: 0.5100971607067548}
        for case in CASES:
            with self.subTest(case=case):
                self.assertEqual(states[case], old.build_grounded_settings(
                    graph, values, caps=np.zeros((6, 2)), resolved_policy=policy
                )[case])
                for f_hz, expected_db in expected.items():
                    main = solve(f_hz, **states[case])
                    independent = solve_gain(f_hz, **states[case])
                    self.assertAlmostEqual(main["gain"], independent, delta=1e-10)
                    self.assertAlmostEqual(main["il_db"], expected_db, delta=1e-9)
                    self.assertLess(abs(main["power_residual"]), 1e-12)

    def test_old_component_area_limits_not_misrepresented_as_rf_f003(self):
        graph = (2, ((0, 1, "LQP02HV"),) * 7)
        self.assertEqual(7.0, shared.check_graph(graph))
        with self.assertRaisesRegex(ValueError, "explicit LQP02HV/HQ"):
            shared.check_graph((2, ((0, 1, "LQP02"),)),
                               require_explicit_series=True)


if __name__ == "__main__":
    unittest.main()

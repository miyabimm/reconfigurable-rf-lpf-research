"""Phase 2 policy-scoped variable-C search API and historical import parity."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "experiments" / "matching_limit"))

from lpf.constraint_versions import load_constraint
from lpf.variable_c_layouts import (
    enumerate_variable_c_layouts as shared_layouts,
    inductor_types as shared_inductor_types,
)
from search_space import (
    enumerate_variable_c_layouts as legacy_layouts,
    inductor_types as legacy_inductor_types,
)


class SharedVariableCLayoutTests(unittest.TestCase):
    def setUp(self):
        self.graph = (5, ((1, 3, "LQP02HV"), (3, 2, "LQP02HQ"),
                          (3, 4, "LQP02HV")))

    def test_old_imports_are_thin_facades(self):
        self.assertIs(legacy_layouts, shared_layouts)
        self.assertIs(legacy_inductor_types, shared_inductor_types)

    def test_series_labels_remain_explicit_for_new_searches(self):
        self.assertEqual(shared_inductor_types("HV"),
                         ("LQP01", "LQP02HV", "PCB_L", "GJM01"))
        self.assertNotIn("LQP02", shared_inductor_types("both"))
        self.assertIn("LQP02", shared_inductor_types())  # historical only
        with self.assertRaises(ValueError):
            shared_inductor_types("unknown")

    def test_f001_legacy_trial_shapes_and_deterministic_cap(self):
        for id in ("RF-F001", "RF-T001", "RF-T002"):
            with self.subTest(id=id):
                policy = load_constraint(id, allow_trial=id.startswith("RF-T"))
                all_rows = shared_layouts(self.graph, policy)
                self.assertTrue(all_rows)
                self.assertEqual(all_rows, legacy_layouts(self.graph, policy))
                limit = min(3, len(all_rows))
                capped = shared_layouts(self.graph, policy, max_layouts=limit)
                self.assertEqual(len(capped), limit)
                self.assertEqual(capped, shared_layouts(self.graph, policy,
                                                       max_layouts=limit))

    def test_formal_and_t008_never_exceed_two_variable_branches(self):
        for id in ("RF-F003", "RF-T008"):
            with self.subTest(id=id):
                policy = load_constraint(id, allow_trial=id.startswith("RF-T"))
                layouts = shared_layouts(self.graph, policy, max_layouts=8)
                self.assertTrue(layouts)
                self.assertLessEqual(len(layouts), 8)
                self.assertTrue(all(1 <= len(row["edges"]) <= 2 for row in layouts))
                self.assertTrue(all(len(set(map(tuple, row["edges"]))) ==
                                    len(row["edges"]) for row in layouts))
                self.assertEqual(layouts, legacy_layouts(self.graph, policy,
                                                        max_layouts=8))

    def test_invalid_cap_rejected(self):
        with self.assertRaises(ValueError):
            shared_layouts(self.graph, load_constraint("RF-F003"), max_layouts=0)


if __name__ == "__main__":
    unittest.main()

"""Curated research catalog regression tests (no RF solver execution)."""
import unittest
from pathlib import Path

from scripts.audit_research_catalog import (
    ROOT, _path, check_threshold,
)


class ResearchCatalogTests(unittest.TestCase):
    def test_strict_raw_harmonic_threshold_cannot_use_solver_tolerance(self):
        result = check_threshold(
            "strict_finite_grid", 35.0, 34.9999999958, 35.01, "formal")
        self.assertTrue(result)

    def test_tolerance_only_is_not_strict_or_robust_feasibility(self):
        self.assertEqual([], check_threshold(
            "tolerance_only", 30.0, 29.9999999969, 29.9999999987, "formal"))
        self.assertTrue(check_threshold(
            "tolerance_only", 30.0, 29.999, 30.1, "formal"))
        self.assertTrue(check_threshold(
            "tolerance_only", 35.0, 35.01, 35.02, "formal"))

    def test_historical_candidate_cannot_be_relabelled_formal(self):
        self.assertTrue(check_threshold(
            "historical_only", 35.0, 35.1, 35.2, "formal"))
        self.assertTrue(check_threshold(
            "strict_finite_grid", 35.0, 35.1, 35.2, "historical"))

    def test_path_escape_rejected(self):
        for p in ("/tmp/dummy.json", "../README.md", "data/../README.md"):
            with self.subTest(path=p):
                with self.assertRaises(ValueError):
                    _path(ROOT, p)


if __name__ == "__main__":
    unittest.main()

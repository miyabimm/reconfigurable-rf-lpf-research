"""Curated research catalog regression tests (no RF solver execution)."""
import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.audit_research_catalog import (
    ROOT, _path, check_threshold,
)


class ResearchCatalogTests(unittest.TestCase):
    def test_legacy_imports_and_cli_failure_contract_are_preserved(self):
        from scripts import audit_research_catalog as legacy
        from lpf.cli import audit_research_catalog as implementation
        for name in ('audit_catalog', 'check_threshold', '_json', '_csv', '_path', '_source_metrics', 'main'):
            with self.subTest(name=name):
                self.assertIs(getattr(legacy, name), getattr(implementation, name))
        self.assertEqual(legacy.ROOT, ROOT)
        with tempfile.TemporaryDirectory(prefix='catalog-audit-fixture-') as temp:
            self.assertEqual(legacy.audit_catalog(Path(temp)), implementation.audit_catalog(Path(temp)))
            self.assertIn('Cannot load catalog/registry:', legacy.audit_catalog(Path(temp))[0])
        with patch.object(implementation, 'audit_catalog', return_value=[]), contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertIsNone(legacy.main())
            self.assertIn('PASS: curated research checkpoint paths', out.getvalue())
        with patch.object(implementation, 'audit_catalog', return_value=['fixture mismatch']):
            with self.assertRaisesRegex(SystemExit, 'FAILED research catalog:'):
                legacy.main()

    def test_results_audit_legacy_import_and_entrypoint_are_preserved(self):
        from scripts import audit_results as legacy
        from lpf.cli import audit_results as implementation
        self.assertIs(legacy, implementation)
        with tempfile.TemporaryDirectory(prefix='results-audit-fixture-') as temp:
            with patch.object(legacy, 'ROOT', Path(temp)):
                self.assertEqual(implementation.ROOT, Path(temp))
        with patch.object(implementation, 'audit', return_value=[]) as audit, \
                contextlib.redirect_stdout(io.StringIO()) as out:
            legacy.main()
            audit.assert_called_once_with(detail=True)
            self.assertIn('PASS: active policy, bands, candidates', out.getvalue())
        with patch.object(implementation, 'audit', return_value=['synthetic mismatch']):
            with self.assertRaisesRegex(SystemExit, 'FAILED:'):
                legacy.main()

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

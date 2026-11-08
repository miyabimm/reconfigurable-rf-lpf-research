"""Condition-isolated Pareto tests; historical storage-inventory tests retired."""
import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from scripts.report_research_pareto import dominates, make_report


class ParetoRegressions(unittest.TestCase):
    def test_entrypoints_keep_import_cli_and_fixture_output_contract(self):
        from scripts import report_research_pareto as legacy
        from lpf.cli import report_research_pareto as implementation
        for name in ('main', 'dominates', 'make_report', 'as_csv', 'as_markdown', '_rows'):
            with self.subTest(name=name):
                self.assertIs(getattr(legacy, name), getattr(implementation, name))
        root = Path(__file__).resolve().parents[1]
        self.assertEqual(legacy.ROOT, root)
        env = dict(os.environ, PYTHONPATH=str(root/'src'))
        script = [sys.executable, str(root/'scripts/report_research_pareto.py')]
        module = [sys.executable, '-m', 'lpf.cli.report_research_pareto']
        with tempfile.TemporaryDirectory(prefix='pareto-cli-fixture-') as temp:
            for cwd in (root, temp):
                for args in (['--help'], [], ['--unknown']):
                    with self.subTest(cwd=cwd, args=args):
                        a, b = (subprocess.run(entry + args, cwd=cwd, env=env,
                                               capture_output=True, text=True, timeout=30)
                                for entry in (script, module))
                        self.assertEqual((a.returncode, a.stdout, a.stderr),
                                         (b.returncode, b.stdout, b.stderr))
            # Only synthetic reports are written into the disposable fixture.
            out = Path(temp)
            summary = dict(candidate_count=0, comparison_group_count=0, groups=[], catalog_path='fixture',
                           formal_strict_rf_f002_il0p3_met=False, formal_strict_rf_f003_il0p3_met=False)
            argv = ['report_research_pareto.py', '--csv', str(out/'report.csv'),
                    '--summary', str(out/'summary.json'), '--markdown', str(out/'report.md')]
            with patch.object(implementation, 'make_report', return_value=([], summary)) as report, patch.object(
                    sys, 'argv', argv), contextlib.redirect_stdout(io.StringIO()) as output:
                legacy.main()
            report.assert_called_once_with(catalog_path='data/research_candidate_register.csv')
            self.assertIn('source-restricted Pareto 0 candidates, 0 groups', output.getvalue())
            self.assertEqual((out/'report.csv').read_text(), implementation.as_csv([]))
            self.assertEqual(json.loads((out/'summary.json').read_text()), summary)
            self.assertEqual((out/'report.md').read_text(), implementation.as_markdown(summary))

    def test_domination_requires_no_worse_area_and_il(self):
        a = {"chip_area_units": 6, "worst_il_db": 0.4}
        b = {"chip_area_units": 6, "worst_il_db": 0.5}
        c = {"chip_area_units": 8, "worst_il_db": 0.3}
        self.assertTrue(dominates(a, b))
        self.assertFalse(dominates(a, c))
        self.assertFalse(dominates(c, a))
        self.assertFalse(dominates(a, a))

    def test_register_groups_cannot_promote_trial_to_formal(self):
        view, summary = make_report()
        self.assertEqual(14, summary["candidate_count"])
        self.assertEqual(8, summary["comparison_group_count"])
        self.assertFalse(summary["formal_strict_rf_f002_il0p3_met"])
        by_id = {r["catalog_id"]: r for r in view}
        recovered = by_id["EXP017-LQW4-H30-NEAR"]
        self.assertEqual("formal", recovered["constraint_class"])
        self.assertEqual("RF-F002", recovered["constraint_id"])
        self.assertEqual("false", recovered["il_0p30_met_on_recorded_grid"])
        trial = by_id["EXP018-C13.667"]
        self.assertEqual("trial", trial["constraint_class"])
        self.assertEqual("RF-T004", trial["constraint_id"])
        self.assertEqual("true", trial["il_0p30_met_on_recorded_grid"])
        nominal = by_id["EXP-041-35DB-STAGE"]
        self.assertEqual("tolerance_only", nominal["threshold_classification"])
        self.assertEqual("false", nominal["il_0p30_met_on_recorded_grid"])
        same_group = [r for r in view if r["comparison_key"] ==
                      "RF-F002_full_lpf_35_strict_finite_grid"]
        self.assertEqual(2, len(same_group))
        self.assertTrue(all(r["pareto_within_group"] == "true" for r in same_group))
        old = [r for r in view if r["constraint_class"] == "historical"]
        self.assertEqual(1, sum(r["pareto_within_group"] == "true" for r in old))


if __name__ == "__main__":
    unittest.main()

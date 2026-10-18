"""Verify the lightweight Phase 2 CI trigger and the absence of heavy default audits.

Deep numerical validation and full-suite testing remain available as manual
commands; the everyday CI is intentionally a small research smoke gate.
"""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class Phase2WorkflowSchedulingTests(unittest.TestCase):
    def test_scoped_main_and_pr_smoke_with_manual_dispatch(self):
        body = (ROOT / ".github/workflows/audit.yml").read_text(encoding="utf-8")
        self.assertIn("name: Phase 2 smoke (lightweight)", body)
        self.assertIn("on:\n  push:\n    branches:\n      - main\n    paths:", body)
        self.assertIn("  pull_request:\n    paths:", body)
        self.assertIn("  workflow_dispatch:", body)
        self.assertIn("      - 'src/**'", body)
        self.assertIn("      - 'data/**'", body)
        self.assertIn("cancel-in-progress: ${{ github.event_name == 'pull_request' }}", body)
        self.assertIn('python -m unittest discover -s tests -p "$test_file" -v', body)
        self.assertIn("test_rf_f003_t005.py", body)
        self.assertIn("test_phase2_candidate_catalog.py", body)
        self.assertNotIn("unittest discover -s tests -v", body)
        self.assertNotIn("verify_exp017_recovered_mna.py", body)
        self.assertNotIn("audit_branch_retention.py", body)


if __name__ == "__main__":
    unittest.main()

"""Current Phase 2 documentation entrypoint guardrails."""
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import verify_phase2_cleanup_w1_links as links

ROOT = Path(__file__).resolve().parents[1]


class Phase2CurrentStatusTests(unittest.TestCase):
    def test_current_roadmap_identifies_active_development_gates(self):
        roadmap = (ROOT / "project/roadmap.md").read_text(encoding="utf-8")
        for target in ("campaign_workflow.md", "diagnostics/README.md",
                       "instructions.md", "../rf/constraints/registry.json",
                       "../rf/bands.csv"):
            self.assertIn(f"]({target})", roadmap)
            self.assertTrue((ROOT / "project" / target).is_file(), target)
        instructions = (ROOT / "project/instructions.md").read_text(encoding="utf-8")
        self.assertIn("rf/constraints/registry.json", instructions)
        self.assertIn("Phase 2", roadmap)

    def test_active_link_checker_rejects_broken_roadmap_link(self):
        known = links.tracked()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            for name in links.ACTIVE_ENTRYPOINTS:
                destination = root / name
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT / name, destination)
            with patch.object(links, "ROOT", root):
                issues, _ = links.all_links(links.ACTIVE_ENTRYPOINTS, known)
                self.assertEqual([], issues)
                roadmap = root / "project/roadmap.md"
                text = roadmap.read_text(encoding="utf-8")
                self.assertIn("](campaign_workflow.md)", text)
                roadmap.write_text(text.replace("](campaign_workflow.md)", "](missing-campaign.md)"), encoding="utf-8")
                issues, _ = links.all_links(links.ACTIVE_ENTRYPOINTS, known)
                self.assertTrue(any(issue[0] == "project/roadmap.md" and
                                    issue[2] == "missing-campaign.md" and
                                    issue[3] == "missing" for issue in issues), issues)

    def test_campaign_guide_entrypoints_and_diagnostic_inventory(self):
        """Keep one current entrypoint without orphaning Issue evidence."""
        guide = ROOT / "project/campaign_workflow.md"
        index = ROOT / "project/diagnostics/README.md"
        self.assertTrue(guide.is_file())
        self.assertIn("project/campaign_workflow.md", (ROOT / "README.md").read_text())
        self.assertIn("(campaign_workflow.md)", (ROOT / "project/README.md").read_text())
        inventory = index.read_text()
        for path in (ROOT / "project/diagnostics").iterdir():
            if path.is_file() and path.name != "README.md":
                self.assertIn(f"({path.name})", inventory, path.name)
        # Local Markdown targets in the new entrypoints must survive sparse checkout.
        import re
        for page in (guide, index):
            for target in re.findall(r"\]\(([^)]+)\)", page.read_text()):
                if "://" not in target:
                    self.assertTrue((page.parent / target.split("#")[0]).exists(), target)


if __name__ == "__main__":
    unittest.main()

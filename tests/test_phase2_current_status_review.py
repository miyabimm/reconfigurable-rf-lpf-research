"""Current Phase 2 documentation entrypoint guardrails."""
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ci import verify_phase2_cleanup_w1_links as links

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

    def test_project_documents_mode_requires_no_rf_or_dependencies_and_catches_deleted_target(self):
        with tempfile.TemporaryDirectory(prefix='issue371-doc-audit-') as temp:
            root = Path(temp)
            (root/'ci').mkdir()
            (root/'project').mkdir()
            shutil.copyfile(ROOT/'ci/verify_phase2_cleanup_w1_links.py',
                            root/'ci/verify_phase2_cleanup_w1_links.py')
            (root/'project/note.md').write_text('[target](target.md)\n')
            (root/'project/target.md').write_text('target\n')
            subprocess.run(['git', 'init', '-q', str(root)], check=True)
            subprocess.run(['git', '-C', str(root), 'add', '.'], check=True)
            command = [sys.executable, '-S', str(root/'ci/verify_phase2_cleanup_w1_links.py'),
                       '--project-documents']
            good = subprocess.run(command, cwd=root, capture_output=True, text=True, check=True)
            self.assertEqual(json.loads(good.stdout)['markdown_files'], 2)
            subprocess.run(['git', '-C', str(root), 'mv', 'project/target.md',
                            'project/renamed.md'], check=True)
            bad = subprocess.run(command, cwd=root, capture_output=True, text=True)
            self.assertNotEqual(bad.returncode, 0)
            self.assertIn('target.md', bad.stderr)

    def test_document_audit_checks_nested_destinations_and_angle_references(self):
        with tempfile.TemporaryDirectory(prefix='issue371-nested-links-') as temp:
            root = Path(temp)
            (root/'ci').mkdir()
            (root/'project').mkdir()
            shutil.copyfile(ROOT/'ci/verify_phase2_cleanup_w1_links.py',
                            root/'ci/verify_phase2_cleanup_w1_links.py')
            note = root/'project/note.md'
            note.write_text('[nested](file(one).md)\n[![icon](ok.png)](outer(two).md)\n')
            (root/'project/file(one').write_text('misleading existing prefix')
            (root/'project/ok.png').write_text('fixture')
            subprocess.run(['git', 'init', '-q', str(root)], check=True)
            subprocess.run(['git', '-C', str(root), 'add', '.'], check=True)
            command = [sys.executable, '-S', str(root/'ci/verify_phase2_cleanup_w1_links.py'),
                       '--project-documents']
            bad = subprocess.run(command, cwd=root, capture_output=True, text=True)
            self.assertNotEqual(bad.returncode, 0, bad.stdout)
            self.assertIn('file(one).md', bad.stderr)
            self.assertIn('outer(two).md', bad.stderr)
            (root/'project/file(one).md').write_text('synthetic')
            (root/'project/outer(two).md').write_text('synthetic')
            (root/'project/space file.md').write_text('synthetic')
            note.write_text(note.read_text() + '[ref]: <space file.md> "title"\n')
            subprocess.run(['git', '-C', str(root), 'add', '.'], check=True)
            subprocess.run(command, cwd=root, capture_output=True, text=True, check=True)
            subprocess.run(['git', '-C', str(root), 'mv', 'project/outer(two).md',
                            'project/renamed.md'], check=True)
            bad = subprocess.run(command, cwd=root, capture_output=True, text=True)
            self.assertNotEqual(bad.returncode, 0)
            self.assertIn('outer(two).md', bad.stderr)
            note.write_text('[x](' * 1000 + '\n')
            complex_link = subprocess.run(command, cwd=root, capture_output=True, text=True)
            self.assertNotEqual(complex_link.returncode, 0)
            self.assertIn('complexity limit', complex_link.stderr)

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
        # Local Markdown targets in the current entrypoints must resolve.
        import re
        for page in (guide, index):
            for target in re.findall(r"\]\(([^)]+)\)", page.read_text()):
                if "://" not in target:
                    self.assertTrue((page.parent / target.split("#")[0]).exists(), target)


if __name__ == "__main__":
    unittest.main()

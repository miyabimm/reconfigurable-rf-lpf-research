"""Guard the single-source cutover; archived EXP files are never rewritten."""
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASELINE = "c7968d185d5dd3d94cad47d2e1c08f2e327b5d42"


class CanonicalSourceAliasesTests(unittest.TestCase):
    def test_old_rf_paths_are_links_to_rf_not_independent_copies(self):
        old_paths = [
            "data/bands.csv",
            "data/design_constraints.json",
            "data/constraints/registry.json",
            *(f"data/constraints/formal/RF-F{i:03d}.json" for i in range(1, 4)),
            *(f"data/constraints/trial/RF-T{i:03d}.json" for i in range(1, 9)),
            "data/parasitics/circuit1_ant_coupler_0_6ghz.s2p",
            "data/parasitics/circuit2_poc_through_0_6ghz.s2p",
        ]
        for source in old_paths:
            with self.subTest(source=source):
                path = ROOT / source
                self.assertTrue(path.is_symlink(), source)
                expected = ("rf/constraints/formal/RF-F003.json"
                            if source == "data/design_constraints.json"
                            else "rf/" + source.removeprefix("data/"))
                self.assertEqual(path.resolve(), (ROOT / expected).resolve())
                self.assertTrue(path.is_file())
                # Registry is mutable: its active ID may change with approval.
                if source != "data/constraints/registry.json":
                    original_blob = subprocess.check_output(
                        ["git", "rev-parse", f"{BASELINE}:{source}"],
                        cwd=ROOT, text=True).strip()
                    current_blob = subprocess.check_output(
                        ["git", "hash-object", source],
                        cwd=ROOT, text=True).strip()
                    self.assertEqual(original_blob, current_blob)

    def test_old_active_docs_are_links_and_instructions_only_redirect(self):
        docs = {
            "docs/roadmap.md": "project/roadmap.md",
            "docs/specification.md": "project/specification.md",
            "docs/methods.md": "project/methods.md",
            "docs/results.md": "project/results.md",
            "docs/slsqp_iteration_policy.md": "project/slsqp_iteration_policy.md",
            "docs/governance/phase2_experiment_storage_policy.md": "project/experiment_storage_policy.md",
        }
        for source, target in docs.items():
            with self.subTest(source=source):
                path = ROOT / source
                self.assertTrue(path.is_symlink(), source)
                self.assertEqual(path.resolve(), (ROOT / target).resolve())
        old_instructions = ROOT / "docs/chatgpt_project_instructions.md"
        self.assertFalse(old_instructions.is_symlink())
        self.assertIn("project/instructions.md", old_instructions.read_text())
        self.assertNotIn("## 研究証拠と結果管理", old_instructions.read_text())


if __name__ == "__main__":
    unittest.main()

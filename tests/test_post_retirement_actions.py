"""Contract checks for post-retirement GitHub Actions and legacy provenance links."""
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class PostRetirementActionsTests(unittest.TestCase):
    def test_experiment_number_is_registry_validated_not_hard_coded(self):
        yaml = (ROOT / ".github/workflows/reserve_experiment_number.yml").read_text(
            encoding="utf-8"
        )
        registry = json.loads(
            (ROOT / "data/constraints/registry.json").read_text(encoding="utf-8")
        )
        self.assertEqual("RF-F003", registry["active_formal_id"])
        self.assertEqual("study_authorized", registry["trial"]["RF-T008"]["state"])
        self.assertIn("constraint_id:", yaml)
        self.assertIn('type: string', yaml)
        self.assertNotIn("type: choice", yaml)
        self.assertNotIn("      options:", yaml)
        self.assertIn("scripts/reserve_experiment_number.py", yaml)

    def test_legacy_exp004_note_points_to_immutable_history_not_missing_action(self):
        note = ROOT / "actions/workflows/lpf-target040.yml"
        self.assertTrue(note.is_file())
        self.assertFalse(note.is_symlink())
        content = note.read_text(encoding="utf-8")
        self.assertIn("NOT a GitHub Actions workflow", content)
        self.assertIn(
            "git show 055b222c79c73c7fbeacb19383f21c1da0625195:"
            ".github/workflows/lpf-target040.yml", content
        )
        self.assertFalse((ROOT / ".github/workflows/lpf-target040.yml").exists())


if __name__ == "__main__":
    unittest.main()

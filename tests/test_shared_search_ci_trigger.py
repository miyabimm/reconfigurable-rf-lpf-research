"""Exercise CI change detection on an isolated, multi-commit Git history."""
import subprocess
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/shared_search_ci_trigger.sh"


class SharedSearchTriggerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.git("init", "-q", "-b", "main")
        self.git("config", "user.name", "Fixture")
        self.git("config", "user.email", "fixture@example.invalid")
        self.commit("README.md", "base")
        self.base = self.git("rev-parse", "HEAD")
        self.git("update-ref", "refs/remotes/origin/main", self.base)

    def git(self, *args):
        return subprocess.run(["git", *args], cwd=self.root, check=True,
                              capture_output=True, text=True).stdout.strip()

    def commit(self, path, content):
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        self.git("add", path)
        self.git("commit", "-qm", content)

    def trigger(self, event, before, head="HEAD"):
        return subprocess.run(["bash", str(SCRIPT), event, before, head], cwd=self.root,
                              check=True, capture_output=True, text=True).stdout.strip()

    def test_push_compares_all_commits_and_pr_uses_merge_base(self):
        self.commit("src/lpf/checkpoint_io.py", "shared dependency")
        self.commit("README.md", "unrelated final commit")
        head = self.git("rev-parse", "HEAD")
        self.assertEqual("run", self.trigger("push", self.base, head))
        self.assertEqual("run", self.trigger("pull_request", "", head))
        self.assertEqual("skip", self.trigger("push", self.git("rev-parse", "HEAD^"), head))

    def test_unknown_history_and_manual_run_are_conservative(self):
        self.commit("README.md", "unrelated")
        head = self.git("rev-parse", "HEAD")
        self.assertEqual("skip", self.trigger("push", self.base, head))
        for before in ("0" * 40, "f" * 40, ""):
            with self.subTest(before=before):
                self.assertEqual("run", self.trigger("push", before, head))
        self.assertEqual("run", self.trigger("workflow_dispatch", "", head))
        # A force push or unrelated before is not a safe incremental range.
        self.assertEqual("run", self.trigger("push", head, self.base))
        self.git("update-ref", "-d", "refs/remotes/origin/main")
        self.assertEqual("run", self.trigger("pull_request", "", head))


if __name__ == "__main__":
    unittest.main()

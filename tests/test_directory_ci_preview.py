"""Real-Git tests for the unwired, mixed-directory-safe CI preview."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from ci import directory_preview as preview


class DirectoryPreviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='issue371-directory-preview-')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.git('init', '-q', '-b', 'main')
        self.git('config', 'user.name', 'fixture')
        self.git('config', 'user.email', 'fixture@example.invalid')
        for path in ('README.md', 'project/note.md', 'rf/README.md', 'src/README.md',
                     'tests/test_existing.py', 'data/README.md',
                     'experiments/EXP-050/README.md', 'ci/README.md'):
            self.write(path, 'original contents for ' + path + '\n')
        self.git('add', '.')
        self.git('commit', '-qm', 'base')
        self.base = self.git('rev-parse', 'HEAD')
        old = os.getcwd()
        os.chdir(self.root)
        self.addCleanup(os.chdir, old)

    def git(self, *args):
        return subprocess.check_output(['git', '-C', str(self.root), *args], text=True).strip()

    def write(self, name, text):
        path = self.root/name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)

    def commit(self):
        self.git('add', '-A')
        self.git('commit', '-qm', 'change')
        return self.git('rev-parse', 'HEAD')

    def plan(self, head=None, event='pull_request', base=None):
        return preview.preview(event, base or self.base, head or self.git('rev-parse', 'HEAD'), 'main')

    def test_root_only_and_each_directory(self):
        for path, classes, full in (
                ('README.md', [], False), ('rf/README.md', ['INPUT'], False),
                ('src/README.md', ['CODE'], False), ('tests/test_existing.py', ['CODE'], False),
                ('experiments/EXP-050/README.md', ['EXP'], False),
                ('project/note.md', [], True), ('data/README.md', [], True),
                ('ci/README.md', [], True), ('pyproject.toml', [], True),
                ('unknown/README.md', [], True)):
            with self.subTest(path=path):
                self.git('reset', '--hard', self.base)
                self.write(path, 'modified\n')
                self.commit()
                actual = self.plan()
                self.assertEqual(actual['classes'], classes, actual)
                self.assertEqual(actual['full'], full, actual)
                self.assertTrue(actual['changed_tests_complete'])

    def test_union_and_changed_test(self):
        self.write('rf/README.md', 'changed')
        self.write('experiments/EXP-050/README.md', 'changed')
        self.write('tests/test_new.py', 'import unittest\n')
        self.commit()
        for event in ('pull_request', 'push'):
            result = self.plan(event=event)
            self.assertFalse(result['full'], result)
            self.assertEqual(result['classes'], ['INPUT', 'EXP', 'CODE'])
            self.assertEqual(result['changed_tests'], ['tests/test_new.py'])

    def test_delete_and_cross_directory_rename(self):
        self.git('rm', 'rf/README.md')
        self.commit()
        result = self.plan()
        self.assertFalse(result['full'], result)
        self.assertEqual(result['classes'], ['INPUT'])
        self.assertEqual(result['changes'][0]['status'], 'D')
        self.git('reset', '--hard', self.base)
        self.git('mv', 'rf/README.md', 'src/moved.md')
        self.commit()
        result = self.plan()
        self.assertFalse(result['full'], result)
        self.assertEqual(result['classes'], ['INPUT', 'CODE'])
        self.assertTrue(result['changes'][0]['status'].startswith('R'), result)

    def test_symlink_mode_and_unsafe_diff_retain_changed_test(self):
        (self.root/'rf/README.md').unlink()
        (self.root/'rf/README.md').symlink_to('../README.md')
        self.write('tests/test_new.py', 'import unittest\n')
        self.commit()
        result = self.plan()
        self.assertTrue(result['full'])
        self.assertTrue(result['changed_tests_complete'])
        self.assertEqual(result['changed_tests'], ['tests/test_new.py'])
        self.git('reset', '--hard', self.base)
        (self.root/'src/README.md').chmod(0o755)
        self.commit()
        self.assertTrue(self.plan()['full'])

    def test_copy_is_conservative_and_push_includes_all_commits(self):
        original = (self.root/'rf/README.md').read_text()
        self.write('src/copy.md', original)
        self.commit()
        self.write('tests/test_new.py', 'import unittest\n')
        self.commit()
        result = self.plan(event='push')
        self.assertTrue(result['full'], result)
        self.assertTrue(any(x['status'].startswith('C') for x in result['changes']), result)
        self.assertEqual(result['changed_tests'], ['tests/test_new.py'])
        self.assertEqual(result['classes'], ['INPUT', 'CODE'])

    def test_head_mismatch_history_failure_and_manual_full(self):
        self.write('src/README.md', 'changed')
        self.commit()
        for args in (('push', self.base, self.base, 'main'),
                     ('push', 'f'*40, self.git('rev-parse', 'HEAD'), 'main'),
                     ('push', self.base, self.git('rev-parse', 'HEAD'), 'other')):
            result = preview.preview(*args)
            self.assertTrue(result['full'], result)
            self.assertFalse(result['changed_tests_complete'])
        with patch.object(preview, 'git', side_effect=subprocess.CalledProcessError(1, 'git')):
            self.assertTrue(self.plan()['full'])
        self.assertTrue(preview.preview('workflow_dispatch', None, None, None)['full'])

    def test_pr_uses_merge_base_push_requires_ancestor(self):
        self.git('checkout', '-qb', 'other')
        self.write('project/note.md', 'base branch change')
        base = self.commit()
        self.git('checkout', '-q', 'main')
        self.write('rf/README.md', 'head branch change')
        head = self.commit()
        result = self.plan(head=head, base=base)
        self.assertEqual(result['classes'], ['INPUT'])
        self.assertFalse(result['full'], result)
        self.assertTrue(self.plan(head=head, base=base, event='push')['full'])


if __name__ == '__main__':
    unittest.main()

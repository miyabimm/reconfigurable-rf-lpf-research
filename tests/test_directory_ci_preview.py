"""Real-Git tests for the unwired, mixed-directory-safe CI preview."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from ci import check_changed_ledger as ledger_check
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
                     'experiments/chatgpt_topology_search/runs/EXP-050/README.md', 'ci/README.md'):
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
                ('experiments/chatgpt_topology_search/runs/EXP-050/README.md', ['EXP'], False),
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
        self.write('experiments/chatgpt_topology_search/runs/EXP-050/README.md', 'changed')
        self.write('tests/test_new.py', 'import unittest\n')
        self.commit()
        for event in ('pull_request', 'push'):
            result = self.plan(event=event)
            self.assertFalse(result['full'], result)
            self.assertEqual(result['classes'], ['INPUT', 'EXP', 'CODE'])
            self.assertEqual(result['changed_tests'], ['tests/test_new.py'])
            self.assertEqual(result['comparison'], dict(base=self.base, head=self.git('rev-parse', 'HEAD')))

    def test_nested_changed_tests_are_identified_and_unsafe_names_are_incomplete(self):
        self.write('tests/nested/test_child.py',
                   'import unittest\nclass Case(unittest.TestCase):\n def test_ok(self): pass\n')
        self.write('tests/nested/worker_test.py', 'import unittest\n')
        self.commit()
        result = self.plan()
        self.assertEqual(result['changed_tests'], ['tests/nested/test_child.py',
                                                   'tests/nested/worker_test.py'])
        self.assertTrue(result['changed_tests_complete'], result)
        run = subprocess.run([os.sys.executable, '-m', 'unittest', 'discover',
                              '-s', 'tests/nested', '-p', 'test_child.py'],
                             cwd=self.root, capture_output=True, text=True, check=True)
        self.assertIn('Ran 1 test', run.stderr)
        self.write('tests/nested/test_unsafe-name.py', 'import unittest\n')
        self.commit()
        result = self.plan()
        self.assertTrue(result['full'], result)
        self.assertFalse(result['changed_tests_complete'], result)
        self.assertTrue(any('unexecutable changed test' in reason for reason in result['reasons']))

    def test_changed_test_runner_executes_nested_and_rejects_stale_or_empty(self):
        source = Path(__file__).resolve().parents[1]/'ci/run_changed_tests.py'
        shutil.copyfile(source, self.root/'ci/run_changed_tests.py')
        self.write('tests/nested/test_child.py',
                   'import unittest\nclass Case(unittest.TestCase):\n def test_ok(self): pass\n')
        self.write('tests/nested/test_empty.py', 'import unittest\n')
        head = self.commit()
        runner = [os.sys.executable, str(self.root/'ci/run_changed_tests.py'), '--head', head]
        good = subprocess.run(runner + ['tests/nested/test_child.py'], cwd=self.root,
                              text=True, capture_output=True, check=True)
        self.assertIn('Ran 1 test', good.stderr)
        empty = subprocess.run(runner + ['tests/nested/test_empty.py'], cwd=self.root,
                               text=True, capture_output=True)
        self.assertNotEqual(empty.returncode, 0)
        self.assertIn('no discoverable tests', empty.stderr)
        bad_head = subprocess.run([*runner[:-1], '0'*40, 'tests/nested/test_child.py'],
                                  cwd=self.root, text=True, capture_output=True)
        self.assertNotEqual(bad_head.returncode, 0)
        self.write('tests/nested/test_child.py', 'changed after commit\n')
        dirty = subprocess.run(runner + ['tests/nested/test_child.py'], cwd=self.root,
                               text=True, capture_output=True)
        self.assertNotEqual(dirty.returncode, 0)
        self.assertIn('differs from HEAD', dirty.stderr)
        invalid = subprocess.run(runner + ['tests/../nested/test_child.py'], cwd=self.root,
                                 text=True, capture_output=True)
        self.assertNotEqual(invalid.returncode, 0)
        self.git('restore', 'tests/nested/test_child.py')
        (self.root/'tests/test_link.py').symlink_to('nested/test_child.py')
        self.write('tests/test_executable.py', 'import unittest\n')
        (self.root/'tests/test_executable.py').chmod(0o755)
        head = self.commit()
        runner = [os.sys.executable, str(self.root/'ci/run_changed_tests.py'), '--head', head]
        for path in ('tests/test_link.py', 'tests/test_executable.py'):
            with self.subTest(path=path):
                denied = subprocess.run(runner + [path], cwd=self.root,
                                        text=True, capture_output=True)
                self.assertNotEqual(denied.returncode, 0)

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

    def test_changed_experiment_ids_and_unresolved_ledger_scope(self):
        exp = 'experiments/chatgpt_topology_search/runs/EXP-050/manifest.json'
        other = 'experiments/matching_limit/runs/EXP-051/manifest.json'
        self.write(exp, '{"state":"planned"}')
        self.write(other, '{"state":"planned"}')
        self.commit()
        result = self.plan()
        self.assertEqual(result['changed_experiments'], ['EXP-050', 'EXP-051'])
        self.assertTrue(result['experiment_scope_complete'])
        self.git('mv', exp, 'experiments/chatgpt_topology_search/runs/EXP-052.json')
        self.commit()
        result = self.plan()
        self.assertEqual(result['changed_experiments'], ['EXP-051'])
        self.assertFalse(result['experiment_scope_complete'])
        self.write('data/experiment_index.csv', 'experiment_id\nEXP-050\n')
        self.commit()
        result = self.plan()
        self.assertTrue(result['full'])
        self.assertFalse(result['experiment_scope_complete'])

    def seed_ledgers(self):
        header = ('experiment_id,constraint_class,constraint_id,effective_constraint_sha256,'
                  'objective,execution_status,numerical_validation,independent_validation,manifest,purpose\n')
        index = header + 'EXP-050,trial,RF-F003,sha,full_lpf,planned,not_run,not_run,path,"quoted, note"\n'
        rows = ['experiment_id,state,owner,request_id,purpose,constraint_id,reserved_at_utc,origin']
        rows += [f'EXP-{i:03d},{"legacy_gap_retired" if i in (18, 19) else "legacy_recorded"},,,,,,'
                 for i in range(1, 42)]
        registry = '\n'.join(rows) + '\n'
        self.write('data/experiment_index.csv', index)
        self.write('data/experiment_number_registry.csv', registry)
        self.base = self.commit()
        return index, registry

    def test_ledger_row_diff_extracts_ids_without_changing_full_policy(self):
        index, registry = self.seed_ledgers()
        self.write('data/experiment_index.csv', index.replace('planned', 'running'))
        self.write('data/experiment_number_registry.csv', registry +
                   'EXP-042,reserved,tester,key-042,purpose,RF-F003,2026-10-15T08:00:00Z,main\n')
        self.commit()
        result = self.plan()
        self.assertTrue(result['full'])  # data/ still has RF compatibility inputs
        self.assertTrue(result['experiment_scope_complete'], result)
        self.assertEqual(result['changed_experiments'], ['EXP-042', 'EXP-050'])
        self.assertEqual(result['removed_ledger_experiments'], [])

    def test_changed_ledger_check_validates_target_identity_and_reservation_only(self):
        index, registry = self.seed_ledgers()
        indexed = ('EXP-042,formal,RF-F003,sha,full_lpf,planned,not_run,not_run,'
                   'experiments/chatgpt_topology_search/runs/EXP-042/manifest.json,purpose\n')
        index = index.splitlines(keepends=True)[0] + indexed
        registry += ('EXP-042,reserved,tester,key-042,purpose,RF-F003,2026-10-15T08:00:00Z,main\n'
                     'EXP-043,reserved,tester,key-043,purpose,RF-F003,2026-10-15T08:00:00Z,main\n')
        self.write('data/experiment_index.csv', index)
        self.write('data/experiment_number_registry.csv', registry)
        result = ledger_check.check(self.root, ['EXP-043', 'EXP-042'])
        self.assertEqual([row['experiment_id'] for row in result], ['EXP-042', 'EXP-043'])
        self.assertEqual([row['index_present'] for row in result], [True, False])
        for ids in ([], ['EXP-042', 'EXP-042'], ['EXP-044'], ['../EXP-042']):
            with self.subTest(ids=ids), self.assertRaises(ValueError):
                ledger_check.check(self.root, ids)
        for bad in (index.replace('RF-F003', 'RF-T008'),
                    index.replace('EXP-042/manifest.json', 'EXP-043/manifest.json'),
                    index + indexed):
            with self.subTest(bad=bad[-100:]):
                self.write('data/experiment_index.csv', bad)
                with self.assertRaises(ValueError):
                    ledger_check.check(self.root, ['EXP-042'])
        self.write('data/experiment_index.csv', index)
        self.write('data/experiment_number_registry.csv', registry + registry.splitlines(keepends=True)[-1])
        with self.assertRaises(ValueError):
            ledger_check.check(self.root, ['EXP-042'])

    def test_ledger_duplicate_bad_header_and_removed_row_fail_closed_or_report(self):
        index, _ = self.seed_ledgers()
        row = index.splitlines(keepends=True)[1]
        for bad in (index + row, index.replace('experiment_id', 'wrong_header', 1),
                    index + '"broken\n'):
            with self.subTest(bad=bad[-30:]):
                self.git('reset', '--hard', self.base)
                self.write('data/experiment_index.csv', bad)
                self.commit()
                result = self.plan()
                self.assertTrue(result['full'])
                self.assertFalse(result['experiment_scope_complete'], result)
                self.assertTrue(any('ledger comparison unavailable' in r for r in result['reasons']))
        self.git('reset', '--hard', self.base)
        self.write('data/experiment_index.csv', index.splitlines(keepends=True)[0])
        self.commit()
        result = self.plan()
        self.assertTrue(result['full'])
        self.assertTrue(result['experiment_scope_complete'], result)
        self.assertEqual(result['removed_ledger_experiments'], ['EXP-050'])
        self.assertEqual(result['changed_experiments'], ['EXP-050'])

    def test_experiment_rename_identifies_both_old_and_new_ids(self):
        old = 'experiments/chatgpt_topology_search/runs/EXP-050/manifest.json'
        new = 'experiments/chatgpt_topology_search/runs/EXP-051/manifest.json'
        self.write(old, '{"state":"planned"}')
        self.base = self.commit()
        (self.root/new).parent.mkdir(parents=True)
        self.git('mv', old, new)
        self.commit()
        result = self.plan()
        self.assertEqual(result['changed_experiments'], ['EXP-050', 'EXP-051'])
        self.assertTrue(result['experiment_scope_complete'])
        self.assertEqual(result['classes'], ['EXP'])

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
        self.assertEqual(result['comparison'], dict(base=self.base, head=head))
        self.assertFalse(result['full'], result)
        self.assertTrue(self.plan(head=head, base=base, event='push')['full'])


if __name__ == '__main__':
    unittest.main()

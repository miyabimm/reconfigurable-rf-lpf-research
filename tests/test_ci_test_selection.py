"""Real Git comparisons and workflow contracts for the impact selector."""
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import select_ci_tests as selector


class SelectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='ci-selection-test-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.git('init', '-q', '-b', 'main')
        self.git('config', 'user.email', 'test@example.com')
        self.git('config', 'user.name', 'Test')
        for path in ('README.md', 'rf/bands.csv', 'src/lpf/search/starts.py',
                     'src/lpf/search/worker.py', 'src/lpf/search/gates.py',
                     'project/experiment_storage_policy.md', '.github/workflows/audit.yml',
                     'src/lpf/search/proposals.py',
                     *(f'src/lpf/phase2_models/{name}.py' for name in (
                         'post_search_validation', 'post_search_journal', 'post_search_evidence',
                         'experiment_post_search', 'limited_candidate_evidence')),
                     'tests/test_issue309_rf_core.py', 'unknown.txt'):
            self.write(path, 'baseline\n')
        self.commit()
        self.base = self.head()

    def git(self, *args):
        return subprocess.check_output(['git', *args], cwd=self.root, stderr=subprocess.PIPE, text=True).strip()

    def write(self, path, text):
        file = self.root / path
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(text)

    def commit(self):
        self.git('add', '-A')
        self.git('commit', '-qm', 'fixture')

    def head(self):
        return self.git('rev-parse', 'HEAD')

    def plan(self, event='pull_request', base=None, head=None, ref='main'):
        with patch.object(selector.storage, 'classify', return_value=False):
            old = os.getcwd()
            try:
                os.chdir(self.root)
                return selector.plan(event, base or self.base, head or self.head(), ref)
            finally:
                os.chdir(old)

    def test_responsibility_examples(self):
        examples = {
            'README.md': {'DOC'}, 'rf/bands.csv': {'RF'},
            'src/lpf/search/starts.py': {'OPT'}, 'src/lpf/search/worker.py': {'RUN', 'STORE'},
            'src/lpf/search/gates.py': {'GATE'}, 'project/experiment_storage_policy.md': {'STORE'},
        }
        for path, expected in examples.items():
            with self.subTest(path=path):
                self.git('reset', '--hard', self.base)
                self.write(path, 'changed\n')
                self.commit()
                result = self.plan()
                self.assertFalse(result['full'], result)
                self.assertEqual(set(result['classes']), expected)
        self.git('reset', '--hard', self.base)
        self.write('README.md', 'changed\n')
        self.write('src/lpf/search/starts.py', 'changed\n')
        self.commit()
        self.assertEqual(set(self.plan()['classes']), {'DOC', 'OPT'})

    def test_test_changes_unknown_and_ci_fail_closed(self):
        for path, full in [('tests/test_issue309_rf_core.py', False),
                           ('tests/test_unregistered.py', True),
                           ('.github/workflows/audit.yml', True), ('unknown.txt', True)]:
            with self.subTest(path=path):
                self.git('reset', '--hard', self.base)
                self.git('clean', '-fdq')
                self.write(path, 'changed\n')
                self.commit()
                result = self.plan()
                self.assertEqual(result['full'], full, result)
                if path.startswith('tests/'):
                    self.assertIn(path, result['changed_tests'])

    def test_push_all_commits_and_diverged_pr(self):
        self.write('src/lpf/search/starts.py', 'first\n')
        self.commit()
        self.write('README.md', 'second\n')
        self.commit()
        head = self.head()
        self.assertEqual(set(self.plan('push')['classes']), {'DOC', 'OPT'})
        self.git('checkout', '-qb', 'advanced', self.base)
        self.write('unknown.txt', 'base only\n')
        self.commit()
        advanced = self.head()
        self.git('checkout', '-q', 'main')
        self.assertEqual(set(self.plan(base=advanced, head=head)['classes']), {'DOC', 'OPT'})
        self.assertTrue(self.plan('push', base=advanced, head=head)['full'])

    def test_bad_comparison_and_modes(self):
        self.write('README.md', 'changed\n')
        self.commit()
        for kwargs in ({'base': 'f' * 40}, {'head': 'a' * 40}, {'ref': 'other'}, {'event': 'other'}):
            self.assertTrue(self.plan(**kwargs)['full'])
        self.git('reset', '--hard', self.base)
        self.git('mv', 'README.md', 'moved.md')
        self.commit()
        self.assertTrue(self.plan()['full'])
        self.git('reset', '--hard', self.base)
        self.git('update-index', '--chmod=+x', 'README.md')
        self.git('commit', '-qm', 'mode')
        self.assertTrue(self.plan()['full'])

    def test_delete_or_rename_cannot_hide_new_test(self):
        self.git('mv', 'README.md', 'renamed.md')
        self.write('tests/test_new_contract.py', 'changed\n')
        self.commit()
        result = self.plan()
        self.assertTrue(result['full'])
        self.assertIn('tests/test_new_contract.py', result['changed_tests'])

    def test_sparse_history_comparison(self):
        self.write('src/lpf/search/starts.py', 'changed\n')
        self.commit()
        self.git('sparse-checkout', 'init', '--cone')
        self.git('sparse-checkout', 'set', 'src')
        self.assertFalse((self.root / 'rf').exists())
        result = self.plan()
        self.assertEqual(result['classes'], ['OPT'])
        self.assertFalse(result['full'])
        self.git('sparse-checkout', 'disable')

    def test_suite_boundaries(self):
        self.assertIn('test_phase2_branch_mna.py', selector.SUITES['RF'])
        self.assertIn('test_issue317_fixed_worker.py', selector.SUITES['RUN'])
        self.assertNotIn('test_issue317_fixed_worker.py', selector.SUITES['GATE'])
        self.assertNotIn('test_issue325_campaign.py', selector.SUITES['GATE'])
        self.assertIn('test_issue325_campaign_gates.py', selector.SUITES['GATE'])
        self.assertIn('test_issue325_campaign_gates.py', selector.SUITES['STORE'])
        self.assertTrue(any('FixedWorkerTests' in name for name in selector.RF_RUN_BOUNDARY))
        self.assertEqual(selector.path_classes('project/instructions.md'), {'FULL'})
        self.assertEqual(selector.path_classes('project/specification.md'), {'RF'})
        self.assertEqual(selector.path_classes('src/lpf/phase2_models/branch_mna.py'), {'RF'})
        self.assertEqual(selector.path_classes('rf/unknown.txt'), {'FULL'})
        self.assertEqual(selector.path_classes('src/lpf/rf_core/new.py'), {'FULL'})

    def test_reviewed_source_changes_select_direct_regressions(self):
        examples = [
            *((f'src/lpf/phase2_models/{name}.py', {'RF', 'STORE'},
               'test_phase2_post_search_validation.py', None) for name in (
                   'post_search_validation', 'post_search_journal', 'post_search_evidence',
                   'experiment_post_search', 'limited_candidate_evidence')),
            ('src/lpf/search/proposals.py', {'RUN', 'GATE'},
             'test_issue325_campaign.py', 'test_issue325_campaign'),
            ('rf/bands.csv', {'RF'}, 'test_issue313_preflight.py', 'test_issue313_preflight'),
        ]
        for path, expected, normal_test, sparse_test in examples:
            with self.subTest(path=path):
                self.git('reset', '--hard', self.base)
                self.write(path, 'changed\n')
                self.commit()
                result = self.plan()
                self.assertFalse(result['full'], result)
                self.assertEqual(set(result['classes']), expected)
                for sparse, test in ((False, normal_test), (True, sparse_test)):
                    if test is None:
                        continue
                    with self.subTest(sparse=sparse), patch.object(Path, 'is_file', return_value=True), \
                         patch.dict(os.environ, {'GITHUB_STEP_SUMMARY': ''}), \
                         patch('builtins.print'), patch.object(selector.subprocess, 'run') as run:
                        selector.execute(result, sparse)
                    commands = [call.args[0] for call in run.call_args_list]
                    self.assertTrue(any(test in command for command in commands), commands)

    def test_strict_storage_fast_path_does_not_run_campaign(self):
        selected = dict(classes=['STORE'], full=False, reasons=[], changed_tests=[], storage_only=True)
        with patch.object(selector.subprocess, 'run') as run:
            selector.execute(selected, False)
        run.assert_not_called()

    def test_classifier_exception_selects_full(self):
        self.write('README.md', 'changed\n')
        self.commit()
        old = os.getcwd()
        try:
            os.chdir(self.root)
            with patch.object(selector.storage, 'classify', side_effect=RuntimeError('broken')):
                result = selector.plan('pull_request', self.base, self.head(), 'main')
            self.assertTrue(result['full'])
            self.assertIn('broken', result['reasons'][0])
        finally:
            os.chdir(old)

    def test_unregistered_changed_test_is_executed_in_full(self):
        self.write('tests/test_unregistered.py', 'changed\n')
        self.commit()
        result = self.plan()
        self.assertTrue(result['full'])
        self.assertEqual(result['changed_tests'], ['tests/test_unregistered.py'])
        old = os.getcwd()
        try:
            os.chdir(self.root)
            # Stop at the first invocation and inspect the actual selected units
            # without running the heavyweight suite in this fixture.
            with patch('builtins.print') as output, patch.object(selector.subprocess, 'run', side_effect=RuntimeError('stop')):
                with self.assertRaisesRegex(RuntimeError, 'stop'):
                    selector.execute(result, False)
            self.assertIn('test_unregistered.py', str(output.call_args_list))
        finally:
            os.chdir(old)


class WorkflowTests(unittest.TestCase):
    def test_triggers_and_shared_selector(self):
        for filename, job in (('audit.yml', 'smoke'), ('pi-sparse-rf.yml', 'sparse-rf')):
            wf = yaml.safe_load((ROOT / '.github/workflows' / filename).read_text())
            # PyYAML 1.1 interprets `on` as True.
            triggers = wf.get('on', wf.get(True))
            self.assertIn('pull_request', triggers)
            self.assertFalse(triggers['pull_request'])
            self.assertIn('workflow_dispatch', triggers)
            steps = wf['jobs'][job]['steps']
            checkout = next(x for x in steps if x.get('uses', '').startswith('actions/checkout@'))
            self.assertEqual(checkout['with']['fetch-depth'], 0)
            if job == 'sparse-rf':
                self.assertIn('sparse-checkout', checkout['with'])
                self.assertNotIn('filter', checkout['with'])
            step = next(x for x in steps if x.get('name', '').startswith('Classify complete'))
            self.assertIn('scripts/select_ci_tests.py', step['run'])
            self.assertNotIn('if', step)


if __name__ == '__main__':
    unittest.main()

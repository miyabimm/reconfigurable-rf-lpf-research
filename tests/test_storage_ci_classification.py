"""Real Git fixtures: only the narrow, audited G4 change can skip regressions."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/classify_storage_ci.py'
RUN = 'experiments/chatgpt_topology_search/runs/EXP-050'
HEADER = ('experiment_id,constraint_class,constraint_id,effective_constraint_sha256,'
          'objective,execution_status,numerical_validation,independent_validation,manifest,purpose\n')


def row(exp, status):
    return f'{exp},trial,RF-F003,sha,full_lpf,{status},not_run,not_run,path,purpose\n'


class ClassificationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.git('init', '-q', '-b', 'main')
        self.git('config', 'user.email', 'test@example.com')
        self.git('config', 'user.name', 'Test')
        rows = ['experiment_id,state,owner,request_id,purpose,constraint_id,reserved_at_utc,origin']
        for n in range(1, 51):
            if n <= 41:
                state = 'legacy_gap_retired' if n in (18, 19) else 'legacy_recorded'
                rows.append(f'EXP-{n:03d},{state},,,,,,')
            else:
                rows.append(f'EXP-{n:03d},reserved,test,req-{n},purpose,RF-F003,2026-01-01T00:00:00Z,main')
        self.write('data/experiment_number_registry.csv', '\n'.join(rows) + '\n')
        self.write('data/experiment_index.csv', HEADER + row('EXP-049', 'old') + row('EXP-050', 'planned'))
        self.write(f'{RUN}/storage_record.json', json.dumps({'experiment_id': 'EXP-050',
                   'policy': 'phase2-git-only-v1', 'stage': 'planned'}))
        self.write(f'{RUN}/manifest.json', '{"planned":true}')
        self.write(f'{RUN}/existing.json', '{"old":true}')
        self.write('experiments/chatgpt_topology_search/runs/EXP-049/old.json', '{"history":true}')
        self.commit()
        self.base = self.head()

    def git(self, *args):
        return subprocess.check_output(['git', *args], cwd=self.root, stderr=subprocess.PIPE).decode().strip()

    def write(self, path, text):
        dest = self.root / path
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(text)

    def commit(self):
        self.git('add', '-A')
        self.git('commit', '-qm', 'fixture')

    def head(self):
        return self.git('rev-parse', 'HEAD')

    def classify(self, event='pull_request', base=None, head=None, base_ref='main'):
        env = dict(os.environ, CI_EVENT=event, CI_BASE=base or self.base,
                   CI_HEAD=head or self.head(), CI_BASE_REF=base_ref)
        return subprocess.check_output([sys.executable, str(SCRIPT)], cwd=self.root, env=env, text=True).strip()

    def storage(self):
        self.write(f'{RUN}/run_summary.json', '{"new":"evidence"}')
        self.write(f'{RUN}/manifest.json', '{"planned":false}')

    def test_storage_only_pr_and_multi_commit_push(self):
        self.storage()
        self.commit()
        self.assertEqual('storage_only=true', self.classify())
        self.write(f'{RUN}/checkpoints/candidate.json', '{"candidate":123}')
        self.commit()
        self.assertEqual('storage_only=true', self.classify('push'))

    def test_g4_index_update_and_insert_pr_and_push(self):
        for add in (False, True):
            with self.subTest(add=add):
                self.git('reset', '--hard', self.base)
                if add:
                    self.write('data/experiment_index.csv', HEADER + row('EXP-049', 'old'))
                    self.commit()
                    baseline = self.head()
                else:
                    baseline = self.base
                self.storage()
                self.write('data/experiment_index.csv', HEADER + row('EXP-049', 'old') + row('EXP-050', 'complete'))
                self.commit()
                for event in ('pull_request', 'push'):
                    self.assertEqual('storage_only=true', self.classify(event, base=baseline))

    def test_index_other_rows_header_reorder_and_invalid_rejected(self):
        for contents in (
            HEADER + row('EXP-049', 'changed') + row('EXP-050', 'complete'),
            HEADER + row('EXP-049', 'old').replace('purpose', '"purpose"') + row('EXP-050', 'complete'),
            HEADER.replace('purpose', 'other') + row('EXP-049', 'old') + row('EXP-050', 'complete'),
            HEADER + row('EXP-050', 'complete') + row('EXP-049', 'old'),
            HEADER + row('EXP-050', 'complete'),
            HEADER + row('EXP-049', 'old') + row('EXP-050', 'complete') + row('EXP-050', 'duplicate'),
            HEADER + row('EXP-049', 'old') + 'EXP-050,"broken\n',
            HEADER + row('EXP-049', 'old') + row('EXP-050', 'complete') + row('EXP-051', 'extra'),
        ):
            with self.subTest(contents=contents):
                self.git('reset', '--hard', self.base)
                self.git('clean', '-fdq')
                self.storage()
                self.write('data/experiment_index.csv', contents)
                self.commit()
                for event in ('pull_request', 'push'):
                    self.assertEqual('storage_only=false', self.classify(event))

    def test_quoted_multiline_and_unicode_other_record_is_preserved(self):
        other = row('EXP-049', 'old').replace('purpose', '"first\nsecond\u0085third"')
        self.write('data/experiment_index.csv', HEADER + other + row('EXP-050', 'planned'))
        self.commit()
        baseline = self.head()
        self.storage()
        self.write('data/experiment_index.csv', HEADER + other + row('EXP-050', 'complete'))
        self.commit()
        self.assertEqual('storage_only=true', self.classify(base=baseline))
        self.write('data/experiment_index.csv', HEADER + other.replace('third', 'changed') + row('EXP-050', 'complete'))
        self.commit()
        self.assertEqual('storage_only=false', self.classify('push', base=baseline))

    def test_index_only_and_index_with_code_use_full_suite(self):
        for mixed in (False, True):
            with self.subTest(mixed=mixed):
                self.git('reset', '--hard', self.base)
                self.git('clean', '-fdq')
                self.write('data/experiment_index.csv', HEADER + row('EXP-049', 'old') + row('EXP-050', 'complete'))
                if mixed:
                    self.storage()
                    self.write('src/worker.py', 'mixed code')
                self.commit()
                self.assertEqual('storage_only=false', self.classify())
                self.assertEqual('storage_only=false', self.classify('push'))

    def test_pr_merge_base_and_non_fast_forward_push(self):
        self.storage()
        self.commit()
        head = self.head()
        self.git('checkout', '-q', '-b', 'other', self.base)
        self.write('other.txt', 'base moved')
        self.commit()
        advanced = self.head()
        self.git('checkout', '-q', 'main')
        self.assertEqual('storage_only=true', self.classify(base=advanced, head=head))
        self.assertEqual('storage_only=false', self.classify('push', base=advanced, head=head))

    def test_prior_commit_cannot_be_hidden_on_push(self):
        self.write('src/worker.py', 'change')
        self.commit()
        self.storage()
        self.commit()
        self.assertEqual('storage_only=false', self.classify('push'))

    def test_mixed_and_unknown_changes_fall_back(self):
        for path in ('src/worker.py', 'rf/bands.csv', '.github/workflows/audit.yml',
                     'project/experiment_storage_policy.md', 'data/unrelated.json',
                     'data/experiment_index.csv', 'unknown.file',
                     'experiments/chatgpt_topology_search/runs/EXP-049/old.json',
                     f'{RUN}/existing.json', f'{RUN}/script.py'):
            with self.subTest(path=path):
                self.git('reset', '--hard', self.base)
                self.git('clean', '-fdq')
                self.storage()
                self.write(path, 'changed')
                self.commit()
                self.assertEqual('storage_only=false', self.classify())
                self.assertEqual('storage_only=false', self.classify('push'))

    def test_delete_rename_copy_and_extra_exp_fall_back(self):
        for kind in ('delete', 'rename', 'copy', 'extra'):
            with self.subTest(kind=kind):
                self.git('reset', '--hard', self.base)
                self.git('clean', '-fdq')
                self.storage()
                if kind == 'delete':
                    (self.root / f'{RUN}/existing.json').unlink()
                elif kind == 'rename':
                    self.git('mv', f'{RUN}/existing.json', f'{RUN}/renamed.json')
                elif kind == 'copy':
                    self.write(f'{RUN}/copied.json', '{"old":true}')
                else:
                    self.write('experiments/chatgpt_topology_search/runs/EXP-051/new.json', '{}')
                self.commit()
                self.assertEqual('storage_only=false', self.classify())

    def test_missing_history_event_head_and_finalized_base(self):
        self.storage()
        self.commit()
        self.assertEqual('storage_only=false', self.classify(base_ref='feature'))
        for event, base, head in [('workflow_dispatch', self.base, self.head()),
                                  ('push', '0' * 40, self.head()),
                                  ('push', 'f' * 40, self.head()),
                                  ('pull_request', self.base, 'a' * 40),
                                  ('push', self.head(), self.base)]:
            with self.subTest(event=event, base=base, head=head):
                self.assertEqual('storage_only=false', self.classify(event, base, head))
        self.git('reset', '--hard', self.base)
        self.write(f'{RUN}/storage_record.json', json.dumps({'experiment_id': 'EXP-050',
                   'policy': 'phase2-git-only-v1', 'stage': 'complete'}))
        self.commit()
        self.base = self.head()
        self.storage()
        self.commit()
        self.assertEqual('storage_only=false', self.classify())

    def test_large_blob_and_symlink_fall_back(self):
        for kind in ('large', 'symlink'):
            with self.subTest(kind=kind):
                self.git('reset', '--hard', self.base)
                self.git('clean', '-fdq')
                path = self.root / f'{RUN}/new.json'
                if kind == 'large':
                    path.write_text('x' * 10_000_001)
                else:
                    path.symlink_to('existing.json')
                self.commit()
                self.assertEqual('storage_only=false', self.classify())

    def test_large_diff_falls_back(self):
        for n in range(1001):
            self.write(f'{RUN}/checkpoints/c{n}.json', str(n))
        self.commit()
        self.assertEqual('storage_only=false', self.classify())


class WorkflowContractTests(unittest.TestCase):
    def test_required_job_and_unconditional_audit(self):
        workflow = yaml.safe_load((SCRIPT.parent.parent / '.github/workflows/audit.yml').read_text())
        steps = workflow['jobs']['smoke']['steps']
        by_name = {step.get('name'): step for step in steps}
        audit = by_name['Verify future EXP storage policy (read only)']
        self.assertNotIn('if', audit)
        self.assertEqual('python scripts/audit_new_experiment_storage.py audit', audit['run'])
        for name in ('Check classifier fail-closed behavior', 'Check experiment reservation and provenance'):
            self.assertNotIn('if', by_name[name])
        reservation = by_name['Check experiment reservation and provenance']['run']
        for test in ('test_experiment_number_reservation.py', 'test_experiment_provenance.py',
                     'test_new_experiment_storage.py'):
            self.assertIn(test, reservation)
        classify = by_name['Classify complete event diff and run selected tests']
        self.assertEqual('python scripts/select_ci_tests.py', classify['run'])
        self.assertNotIn('if', classify)
        self.assertIn('github.event.pull_request.base.sha || github.event.before', classify['env']['CI_BASE'])
        self.assertIn('github.event.pull_request.head.sha || github.sha', classify['env']['CI_HEAD'])


if __name__ == '__main__':
    unittest.main()

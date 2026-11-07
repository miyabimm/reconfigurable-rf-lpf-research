"""G0/G1 with an isolated real Git origin; no real reservation or RF run."""
import copy
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import test_issue325_campaign as campaign_tests
from lpf.search import gates
from lpf.search.plan import ROOT
from lpf.search.storage import atomic
from lpf.rf_core.model import RFEvaluator
from scripts.experiment_id_registry import PATH, as_csv, next_reservation


class CampaignGateTests(unittest.TestCase):
    setUp = campaign_tests.CampaignTests.setUp
    setup_model = campaign_tests.CampaignTests.setup_model
    setup_campaign = campaign_tests.CampaignTests.setup_campaign

    def git(self, *args):
        return subprocess.check_output(['git', '-C', str(self.repo), *args], stderr=subprocess.PIPE)

    def commit(self, message='fixture'):
        self.git('add', '.')
        self.git('commit', '-qm', message)

    def publish(self):
        self.git('push', '-q', 'origin', 'HEAD:main')

    def fixture(self, cid='RF-F003'):
        plan, _, _, _ = self.setup_campaign(cid=cid)
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        base = Path(tmp.name)
        self.repo = base/'work'
        self.repo.mkdir()
        self.git('init', '-q', '-b', 'main')
        self.git('config', 'user.name', 'Fixture')
        self.git('config', 'user.email', 'fixture@example.invalid')
        subprocess.check_call(['git', 'init', '--bare', '-q', str(base/'origin.git')])
        self.git('remote', 'add', 'origin', str(base/'origin.git'))
        shutil.copytree(ROOT/'rf', self.repo/'rf')
        for name in ('src/fixture.py', 'scripts/run_rf_search.py', 'pyproject.toml', 'uv.lock'):
            path = self.repo/name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('# isolated source bytes\n')
        (self.repo/'experiments').mkdir()
        rows = [dict(experiment_id=f'EXP-{n:03d}',
                     state='legacy_gap_retired' if n in (18, 19) else 'legacy_recorded',
                     owner='', request_id='', purpose='', constraint_id='', reserved_at_utc='', origin='fixture')
                for n in range(1, 50)]
        rows, self.ident, _ = next_reservation(rows, owner='fixture', purpose='Campaign fixture',
            constraint_id=cid, request_id='issue325-fixture', reserved_at_utc='2026-11-07T00:00:00Z')
        ledger = self.repo/PATH
        ledger.parent.mkdir(parents=True)
        ledger.write_text(as_csv(rows))
        atomic(self.repo/'data/phase2_git_storage_budget.json', dict(thresholds=dict(
            individual_new_file_soft_bytes=131072, individual_new_file_hard_bytes=1048576,
            new_experiment_curated_soft_bytes=10000000)))
        self.commit('fake main reservation and inputs')
        self.publish()
        self.plan = plan
        self.kw = dict(root=self.repo, owner='fixture', request_id='issue325-fixture')
        self.selection = dict(top_k=1, retain=['best', 'topology_diversity', 'representative_failure'],
            rule='Retain topology diversity and representative failures in addition to best.',
            estimated_curated_bytes=10000)
        return plan

    def prepare(self):
        return gates.prepare_campaign(self.plan, self.ident, purpose='Campaign fixture',
                                      selection=self.selection, **self.kw)

    def verify(self):
        return gates.campaign_preflight(self.plan, self.ident, **self.kw)

    def test_planned_commit_changes_head_not_approved_code_f003_and_trial(self):
        for cid in ('RF-F003', 'RF-T008'):
            with self.subTest(cid=cid), patch.object(RFEvaluator, 'evaluate') as forward:
                self.fixture(cid)
                approved = self.git('rev-parse', 'HEAD').decode().strip()
                prepared = self.prepare()
                self.assertFalse(prepared['execution_allowed'])
                self.commit('planned Campaign envelope, not future Jobs')
                # A local-only planned commit is insufficient.
                with self.assertRaises((ValueError, subprocess.CalledProcessError)):
                    self.verify()
                self.publish()
                report = self.verify()
                self.assertEqual(report['status'], 'preflight_ready')
                self.assertEqual(report['approved_source']['head'], approved)
                self.assertNotEqual(report['runtime_source']['head'], approved)
                self.assertEqual(report['approved_source']['files'], report['runtime_source']['files'])
                self.assertFalse(report['execution_allowed'])
                self.assertEqual(report['gates']['G2_G5'], 'not_ready')
                forward.assert_not_called()

    def test_g0_identity_sparse_missing_and_stale_remote_stop_before_write(self):
        self.fixture()
        with patch.object(RFEvaluator, 'evaluate') as forward:
            for updates in (dict(owner='wrong'), dict(request_id='wrong-request')):
                with self.assertRaisesRegex(ValueError, 'reservation identity'):
                    gates.prepare_campaign(self.plan, self.ident, purpose='Campaign fixture',
                        selection=self.selection, **dict(self.kw, **updates))
            self.git('config', 'core.sparseCheckout', 'true')
            with self.assertRaisesRegex(ValueError, 'sparse'):
                self.prepare()
            self.git('config', 'core.sparseCheckout', 'false')
            missing = self.repo/'data/phase2_git_storage_budget.json'
            raw = missing.read_bytes(); missing.unlink()
            with self.assertRaisesRegex(ValueError, 'Full checkout'):
                self.prepare()
            missing.write_bytes(raw)
            # Force a stale tracking ref explicitly: Git versions differ in
            # whether pushing to the origin's path also updates origin/main.
            old_main = self.git('rev-parse', 'origin/main').decode().strip()
            self.git('commit', '--allow-empty', '-qm', 'remote advance')
            self.publish()
            self.git('update-ref', 'refs/remotes/origin/main', old_main)
            self.assertNotEqual(self.git('rev-parse', 'origin/main'), self.git('rev-parse', 'HEAD'))
            with self.assertRaisesRegex(ValueError, 'stale'):
                self.prepare()
            forward.assert_not_called()
        self.assertFalse((self.repo/'experiments/chatgpt_topology_search/runs'/self.ident).exists())

    def test_changed_code_environment_plan_and_planned_bytes_rejected(self):
        self.fixture()
        self.prepare(); self.commit(); self.publish()
        initial = self.git('rev-parse', 'HEAD').decode().strip()
        with patch.object(RFEvaluator, 'evaluate') as forward:
            with patch.object(gates, 'source_identity', wraps=gates.source_identity) as source:
                changed = copy.deepcopy(gates.source_identity(self.repo))
                changed['environment']['python'] = '0.0.0'
                source.side_effect = None; source.return_value = changed
                with self.assertRaisesRegex(ValueError, 'source/environment'):
                    self.verify()
            path = self.repo/'src/fixture.py'
            path.write_text('# changed source\n')
            with self.assertRaisesRegex(ValueError, 'clean checkout'):
                self.verify()
            self.commit(); self.publish()
            with self.assertRaisesRegex(ValueError, 'source/environment'):
                self.verify()
            self.git('reset', '--hard', initial)
            # Use the local bare remote only; no real origin history is touched.
            self.git('push', '-q', '--force', 'origin', 'HEAD:main')
            run = self.repo/'experiments/chatgpt_topology_search/runs'/self.ident
            path = run/'manifest.json'
            manifest = json.loads(path.read_bytes())
            manifest['search_scope']['campaign']['plan_sha256'] = '0'*64
            atomic(path, manifest)
            self.commit(); self.publish()
            with self.assertRaisesRegex(ValueError, 'envelope'):
                self.verify()
            forward.assert_not_called()

    def test_unreserved_and_branch_only_reservations_rejected(self):
        from scripts.experiment_id_registry import read_ledger
        self.fixture()
        with patch.object(RFEvaluator, 'evaluate') as forward:
            with self.assertRaises(ValueError):
                gates.prepare_campaign(self.plan, 'EXP-051', purpose='Campaign fixture',
                    selection=self.selection, **self.kw)
            path = self.repo/PATH
            rows = read_ledger(path.read_text())
            rows, ident, _ = next_reservation(rows, owner='fixture', purpose='Campaign fixture',
                constraint_id='RF-F003', request_id='branch-only-fixture',
                reserved_at_utc='2026-11-07T00:00:00Z')
            path.write_text(as_csv(rows))
            self.commit('branch-only reservation')
            with self.assertRaises(ValueError):
                gates.prepare_campaign(self.plan, ident, purpose='Campaign fixture',
                    selection=self.selection, **dict(self.kw, request_id='branch-only-fixture'))
            forward.assert_not_called()

    def test_project_input_drift_remote_bytes_and_storage_gate(self):
        self.fixture()
        path = self.repo/'project/fixture.yaml'
        path.parent.mkdir()
        path.write_text('input: frozen\n')
        self.commit(); self.publish()
        self.prepare(); self.commit(); self.publish()
        initial = self.git('rev-parse', 'HEAD').decode().strip()
        run = self.repo/'experiments/chatgpt_topology_search/runs'/self.ident
        with patch.object(RFEvaluator, 'evaluate') as forward:
            path.write_text('input: changed\n')
            self.commit(); self.publish()
            with self.assertRaisesRegex(ValueError, 'code/input bytes'):
                self.verify()
            self.git('reset', '--hard', initial)
            self.git('push', '-q', '--force', 'origin', 'HEAD:main')
            record_path = run/'storage_record.json'
            record = json.loads(record_path.read_bytes())
            record['selection']['rule'] = ''
            atomic(record_path, record)
            self.commit()
            with self.assertRaisesRegex(ValueError, 'remote/HEAD byte mismatch'):
                self.verify()
            self.publish()
            with self.assertRaisesRegex(ValueError, 'selection rule'):
                self.verify()
            forward.assert_not_called()

    def test_storage_budget_drift_after_planned_commit_stops_preflight(self):
        self.fixture()
        self.prepare(); self.commit(); self.publish()
        self.assertEqual(self.verify()['status'], 'preflight_ready')
        path = self.repo/'data/phase2_git_storage_budget.json'
        budget = json.loads(path.read_bytes())
        budget['thresholds']['new_experiment_curated_soft_bytes'] += 1
        atomic(path, budget)
        self.commit('change only storage capacity policy'); self.publish()
        with patch.object(RFEvaluator, 'evaluate') as forward:
            with self.assertRaisesRegex(ValueError, 'code/input bytes'):
                self.verify()
            forward.assert_not_called()

    def test_storage_estimate_limit_at_prepare_and_preflight(self):
        for cid in ('RF-F003', 'RF-T008'):
            with self.subTest(cid=cid), patch.object(RFEvaluator, 'evaluate') as forward:
                self.fixture(cid)
                budget = json.loads((self.repo/'data/phase2_git_storage_budget.json').read_bytes())
                limit = budget['thresholds']['new_experiment_curated_soft_bytes']
                run = self.repo/'experiments/chatgpt_topology_search/runs'/self.ident
                self.selection['estimated_curated_bytes'] = limit+1
                with self.assertRaisesRegex(ValueError, 'estimate exceeds'):
                    self.prepare()
                self.assertFalse(run.exists())
                # The closed boundary remains legal, including planned commit's HEAD change.
                self.selection['estimated_curated_bytes'] = limit
                self.prepare(); self.commit(); self.publish()
                self.assertEqual(self.verify()['status'], 'preflight_ready')
                path = run/'storage_record.json'
                record = json.loads(path.read_bytes())
                self.assertIsNone(record['size_exception'])
                record['selection']['estimated_curated_bytes'] = limit+1
                atomic(path, record)
                self.commit('oversize estimate without exception'); self.publish()
                with self.assertRaisesRegex(ValueError, 'estimate exceeds'):
                    self.verify()
                # Reuse the existing recorded-exception contract, not a new approval API.
                record['size_exception'] = {}
                atomic(path, record)
                self.commit('invalid exception'); self.publish()
                with self.assertRaisesRegex(ValueError, 'owner approval'):
                    self.verify()
                record['size_exception'] = dict(approved_by='fixture',
                    approval_url='https://example.invalid/fixture', reason='Isolated test only')
                atomic(path, record)
                self.commit('fixture recorded exception'); self.publish()
                self.assertEqual(self.verify()['status'], 'preflight_ready')
                forward.assert_not_called()

    def test_existing_run_never_overwritten(self):
        self.fixture()
        self.prepare(); self.commit(); self.publish()
        run = self.repo/'experiments/chatgpt_topology_search/runs'/self.ident
        before = {p.name: p.read_bytes() for p in run.iterdir()}
        with self.assertRaisesRegex(ValueError, 'already exists'):
            self.prepare()
        self.assertEqual(before, {p.name: p.read_bytes() for p in run.iterdir()})

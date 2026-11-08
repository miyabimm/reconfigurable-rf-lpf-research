"""G0/G1 with isolated Git; fixture source is NOT the imported implementation.

Only ImportOriginTests exercise real Python import identity. Fixture tests below
explicitly replace that check to retain their G0/G3-G5 contract coverage.
"""
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
from lpf.experiment_id_registry import PATH, as_csv, next_reservation


verify_import_origins = gates._verify_import_origins


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

    def fixture(self, cid='RF-F003', *, independent=False):
        # Test-only: this fake Git repo contains src/fixture.py, not imported lpf.
        bypass = patch.object(gates, '_verify_import_origins', new=lambda root: None)
        bypass.start()
        self.addCleanup(bypass.stop)
        plan, self.definition, _, _ = self.setup_campaign(cid=cid, independent=independent)
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
        (self.repo/'.gitignore').write_text('/results/\n')
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
        from lpf.experiment_id_registry import read_ledger
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

    def formal_start(self, cid='RF-F003', *, independent=False):
        from lpf.search import campaign
        self.fixture(cid, independent=independent)
        self.prepare(); self.commit(); self.publish()
        snapshot = campaign.begin_campaign(self.plan, self.ident, **self.kw)
        return self.repo/'results'/self.ident, snapshot

    def formal_submit(self, snapshot, definition=None, name='p1'):
        import yaml
        from lpf.search import campaign
        proposal = campaign_tests.CampaignTests.proposal(self, definition or self.definition, snapshot, name)
        path = Path(self.raw.name)/'formal-proposal.yaml'
        path.write_text(yaml.safe_dump(proposal))
        return campaign.submit_campaign_proposal(self.plan, path, self.ident,
            solver_kind='fixture', **self.kw)

    def test_formal_sequential_jobs_use_distinct_specs_and_existing_science(self):
        from dataclasses import replace
        from lpf.search import campaign, worker
        from lpf.search.storage import sha
        for cid in ('RF-F003', 'RF-T008'):
            with self.subTest(cid=cid):
                output, snapshot = self.formal_start(cid, independent=True)
                changed = replace(self.definition, capacitor_placement=replace(
                    self.definition.capacitor_placement, fixed_edges=((2, -1), (2, -1), (1, 3))))
                with patch.object(worker, 'slsqp_minimize', side_effect=campaign_tests.worker_tests.FixedWorkerTests.fixture):
                    for i, definition in enumerate((self.definition, changed, self.definition)):
                        snapshot = self.formal_submit(snapshot, definition, f'p{i}')
                        durable = json.loads((output/'campaign.json').read_bytes())
                        self.assertEqual(len(durable['jobs']), i+1, durable['events'])
                        self.assertEqual(snapshot['snapshot']['status'], 'ready', durable.get('exit_reason'))
                state = json.loads((output/'campaign.json').read_bytes())
                self.assertEqual(len(state['topologies']), 2)
                self.assertEqual((state['requested'], state['completed'], state['reserved']), (1176, 1176, 0))
                self.assertEqual((state['independent_requested'], state['independent_completed']), (3, 3))
                for row in state['jobs']:
                    spec = worker.JobSpec(**row['spec'])
                    raw = json.loads((output/row['raw_path']).read_bytes())
                    self.assertEqual(spec.data['kind'], 'campaign_formal_job_v1')
                    self.assertEqual(spec.trial_id, self.ident)
                    self.assertEqual(raw['kind'], 'campaign_formal_raw_v1')
                    self.assertEqual(raw['gates']['G0_G1'], 'passed')
                    self.assertEqual(raw['gates']['G3_G5'], 'not_run')
                    self.assertEqual(sha(raw), row['raw_content_sha256'])
                    with self.assertRaisesRegex(ValueError, 'rejects formal'):
                        worker.execute_development_job(spec, output/'wrong.json', root=self.repo)
                self.assertEqual(state['preservation_audit'], 'not_run')
                with self.assertRaisesRegex(ValueError, 'system tmp outside checkout'):
                    campaign.submit_development_proposal(self.plan, Path(self.raw.name)/'formal-proposal.yaml',
                                                         output, root=self.repo)
                with self.assertRaises(FileExistsError):
                    campaign.begin_campaign(self.plan, self.ident, **self.kw)

    def test_formal_rechecks_g1_before_every_forward_and_keeps_unknown_cap(self):
        from lpf.search import worker
        output, snapshot = self.formal_start()
        actual_forward = RFEvaluator.evaluate
        calls = []
        def changed_after_forward(evaluator, vector):
            calls.append(1)
            result = actual_forward(evaluator, vector)
            (self.repo/'src/fixture.py').write_text('# changed during Job\n')
            return result
        with patch.object(worker, 'slsqp_minimize', side_effect=campaign_tests.worker_tests.FixedWorkerTests.fixture), \
                patch.object(RFEvaluator, 'evaluate', new=changed_after_forward):
            snapshot = self.formal_submit(snapshot)
        self.assertEqual(len(calls), 1)
        self.assertEqual(snapshot['snapshot']['status'], 'unknown')
        state = json.loads((output/'campaign.json').read_bytes())
        self.assertEqual(state['requested']+state['reserved'], state['jobs'][0]['cap'])
        self.assertGreater(state['reserved'], 0)
        with patch.object(RFEvaluator, 'evaluate') as forward:
            with self.assertRaisesRegex(ValueError, 'clean checkout'):
                self.formal_submit(snapshot, name='next')
            forward.assert_not_called()

    def test_worker_import_path_contamination_stops_before_forward_and_keeps_raw(self):
        import lpf
        from lpf.search import worker
        output, snapshot = self.formal_start()
        execute = worker.execute_campaign_job
        def contaminated(spec, path, **kw):
            # The parent already reserved the Job. Re-enable the production
            # check and contaminate only at the Worker boundary.
            with patch.object(gates, '_verify_import_origins', side_effect=lambda root: verify_import_origins(ROOT)), \
                    patch.object(lpf, '__path__', [str(ROOT/'src/lpf'), str(self.repo/'src')]):
                return execute(spec, path, **kw)
        with patch.object(worker, 'execute_campaign_job', side_effect=contaminated), \
                patch.object(RFEvaluator, 'evaluate') as forward:
            snapshot = self.formal_submit(snapshot)
            forward.assert_not_called()
        self.assertEqual(snapshot['snapshot']['status'], 'unknown')
        state = json.loads((output/'campaign.json').read_bytes())
        self.assertGreater(state['reserved'], 0)
        self.assertFalse((output/'job-000000.json').exists())
        self.assertIn('Campaign G1 import package path mismatch', state['exit_reason'])

    def test_formal_parent_reservation_and_output_redirect_rejected_before_forward(self):
        from lpf.search import worker, campaign
        output, snapshot = self.formal_start()
        execute = worker.execute_campaign_job
        def corrupt(spec, path, **kw):
            state = json.loads((output/'campaign.json').read_bytes())
            state['jobs'][-1]['reserved'] -= 1
            atomic(output/'campaign.json', state)
            return execute(spec, path, **kw)
        with patch.object(worker, 'execute_campaign_job', side_effect=corrupt), \
                patch.object(RFEvaluator, 'evaluate') as forward:
            snapshot = self.formal_submit(snapshot)
            forward.assert_not_called()
        self.assertEqual(snapshot['snapshot']['status'], 'unknown')
        self.assertFalse((output/'job-000000.json').exists())
        with patch.object(RFEvaluator, 'evaluate') as forward:
            with self.assertRaisesRegex(ValueError, 'unknown/stopped'):
                self.formal_submit(snapshot, name='next')
            forward.assert_not_called()
        # A symlink to any other EXP/raw directory cannot be used as this EXP.
        output.rename(output.with_name('preserved-raw'))
        output.symlink_to(output.with_name('preserved-raw'), target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'symlinks'):
            campaign.begin_campaign(self.plan, self.ident, **self.kw)

    def test_campaign_preservation_real_git_and_conditional_cleanup(self):
        from dataclasses import replace
        from lpf.search import preservation, worker
        for cid in ('RF-F003', 'RF-T008'):
            with self.subTest(cid=cid):
                output, snapshot = self.formal_start(cid, independent=True)
                # Isolated evidence checkout has a real, schema-correct index.
                from lpf.experiment_manifest import INDEX_FIELDS
                (self.repo/'data/experiment_index.csv').write_text(','.join(INDEX_FIELDS)+'\n')
                self.commit('fixture index')
                self.publish()
                # New planned runtime binding after index-only commit.
                shutil.rmtree(output)
                from lpf.search import campaign
                snapshot = campaign.begin_campaign(self.plan, self.ident, **self.kw)
                changed = replace(self.definition, capacitor_placement=replace(
                    self.definition.capacitor_placement, fixed_edges=((2, -1), (2, -1), (1, 3))))
                with patch.object(worker, 'slsqp_minimize', side_effect=campaign_tests.worker_tests.FixedWorkerTests.fixture):
                    for i, definition in enumerate((self.definition, changed, self.definition)):
                        snapshot = self.formal_submit(snapshot, definition, f'p{i}')
                stale = copy.deepcopy(snapshot)
                stale['based_on_state_sha256'] = '0'*64
                self.formal_submit(stale, name='rejected-stale')
                before = {p.name: p.read_bytes() for p in output.iterdir()}
                with patch.object(RFEvaluator, 'evaluate') as forward:
                    summary = preservation.curate_campaign(self.ident, root=self.repo)
                    self.assertEqual(summary['preservation_errors'], [])
                    self.assertEqual(summary['attempts']['attempted'], 3)
                    self.assertEqual(summary['attempts']['nonconverged'], 3)
                    from lpf.experiment_storage_audit import find_run
                    journal = json.loads((find_run(self.repo, self.ident)/'campaign_evidence.json').read_bytes())
                    self.assertEqual(journal['proposals'][-1]['event']['status'], 'rejected')
                    self.assertTrue(journal['proposals'][-1]['original_base64'])
                    self.assertGreaterEqual(summary['selected_candidate_count'], 2)
                    report = preservation.finalize_campaign(self.ident, root=self.repo)
                    self.assertEqual(report['stage'], 'complete')
                    self.assertTrue(report['committed_readback'])
                    self.assertEqual(report['independent_validation'], 'not_run')
                    kw = dict(root=self.repo, resume_needed=False, classification_complete=True)
                    with self.assertRaises((ValueError, subprocess.CalledProcessError)):
                        preservation.campaign_cleanup_eligibility(self.ident, **kw)
                    self.publish()
                    decision = preservation.campaign_cleanup_eligibility(self.ident, **kw)
                    self.assertTrue(decision['eligible'])
                    self.assertFalse(decision['deleted'])
                    self.assertEqual(set(before), {Path(p).name for p in decision['temporary_c']})
                    with self.assertRaises(ValueError):
                        preservation.campaign_cleanup_eligibility(self.ident, **(kw | {'resume_needed': True}))
                    (output/'unclassified.log').write_text('do not delete')
                    with self.assertRaisesRegex(ValueError, 'Raw changed'):
                        preservation.campaign_cleanup_eligibility(self.ident, **kw)
                    forward.assert_not_called()
                for name, raw in before.items():
                    self.assertEqual((output/name).read_bytes(), raw)

    def test_campaign_unknown_preservation_retains_reservation_and_raw(self):
        from lpf.search import preservation, worker
        from lpf.experiment_manifest import INDEX_FIELDS
        output, snapshot = self.formal_start()
        (self.repo/'data/experiment_index.csv').write_text(','.join(INDEX_FIELDS)+'\n')
        self.commit('index'); self.publish()
        shutil.rmtree(output)
        from lpf.search import campaign
        snapshot = campaign.begin_campaign(self.plan, self.ident, **self.kw)
        with patch.object(worker, 'execute_campaign_job', side_effect=OSError('worker lost')):
            self.formal_submit(snapshot)
        before = (output/'campaign.json').read_bytes()
        with patch.object(RFEvaluator, 'evaluate') as forward:
            summary = preservation.curate_campaign(self.ident, root=self.repo)
            self.assertTrue(summary['preservation_errors'])
            self.assertEqual(summary['attempts']['unknown'], 1)
            self.assertEqual(summary['attempts']['failed'], 0)
            with self.assertRaises(ValueError):
                preservation.finalize_campaign(self.ident, root=self.repo)
            with self.assertRaises(ValueError):
                preservation.campaign_cleanup_eligibility(self.ident, root=self.repo,
                    resume_needed=False, classification_complete=True)
            forward.assert_not_called()
        self.assertEqual((output/'campaign.json').read_bytes(), before)

    def test_campaign_missing_raw_and_git_readback_failure_remain_incomplete(self):
        from lpf.search import campaign, preservation, worker
        from lpf.experiment_manifest import INDEX_FIELDS
        from lpf.experiment_storage_audit import find_run
        for failure in ('missing_raw', 'proposal_escape', 'git_readback'):
            with self.subTest(failure=failure):
                output, snapshot = self.formal_start()
                (self.repo/'data/experiment_index.csv').write_text(','.join(INDEX_FIELDS)+'\n')
                self.commit('index'); self.publish()
                shutil.rmtree(output)
                snapshot = campaign.begin_campaign(self.plan, self.ident, **self.kw)
                with patch.object(worker, 'slsqp_minimize', side_effect=campaign_tests.worker_tests.FixedWorkerTests.fixture):
                    self.formal_submit(snapshot)
                if failure == 'missing_raw':
                    (output/'job-000000.json').unlink()
                elif failure == 'proposal_escape':
                    durable = json.loads((output/'campaign.json').read_bytes())
                    durable['events'][0]['input_path'] = '../../private-input.yaml'
                    atomic(output/'campaign.json', durable)
                before = {p.name: p.read_bytes() for p in output.iterdir()}
                summary = preservation.curate_campaign(self.ident, root=self.repo)
                if failure in ('missing_raw', 'proposal_escape'):
                    self.assertTrue(summary['preservation_errors'])
                    if failure == 'proposal_escape':
                        journal = json.loads((find_run(self.repo, self.ident)/'campaign_evidence.json').read_bytes())
                        self.assertIsNone(journal['proposals'][0]['original_base64'])
                    with self.assertRaises(ValueError):
                        preservation.finalize_campaign(self.ident, root=self.repo)
                else:
                    self.assertEqual(summary['preservation_errors'], [])
                    with patch('lpf.experiment_preservation.tracked_file', side_effect=ValueError('readback mismatch')):
                        with self.assertRaisesRegex(ValueError, 'readback mismatch'):
                            preservation.finalize_campaign(self.ident, root=self.repo)
                record = json.loads((find_run(self.repo, self.ident)/'storage_record.json').read_bytes())
                self.assertEqual(record['stage'], 'preservation_incomplete')
                self.assertEqual(record['git_readback'], 'not_run')
                self.assertEqual(before, {p.name: p.read_bytes() for p in output.iterdir()})
                with self.assertRaises(ValueError):
                    preservation.curate_campaign(self.ident, root=self.repo)

    def test_existing_run_never_overwritten(self):
        self.fixture()
        self.prepare(); self.commit(); self.publish()
        run = self.repo/'experiments/chatgpt_topology_search/runs'/self.ident
        before = {p.name: p.read_bytes() for p in run.iterdir()}
        with self.assertRaisesRegex(ValueError, 'already exists'):
            self.prepare()
        self.assertEqual(before, {p.name: p.read_bytes() for p in run.iterdir()})


class ImportOriginTests(unittest.TestCase):
    """Real imports in fresh processes, separate from the fake Git fixture."""

    def run_python(self, code, *args):
        import os
        import sys
        env = dict(os.environ, PYTHONPATH=str(ROOT/'src'))
        subprocess.run([sys.executable, '-c', code, str(ROOT), *map(str, args)],
                       cwd=ROOT, env=env, check=True, timeout=60)

    def test_real_imports_match_and_untrusted_paths_or_origins_stop(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.run_python('''
import sys, types
from pathlib import Path
from unittest.mock import patch
from importlib.machinery import ModuleSpec
import lpf, scripts
from lpf.search import gates
from lpf.rf_core.model import RFEvaluator
root, outside = map(Path, sys.argv[1:])
gates._verify_import_origins(root)  # actual lpf and namespace scripts
with patch.object(RFEvaluator, 'evaluate') as forward:
    for package in (lpf, scripts):
        with patch.object(package, '__path__', list(package.__path__) + [str(outside)]):
            try: gates._base(None, root, '', '', '')
            except ValueError as e: assert 'package path mismatch' in str(e), e
            else: raise AssertionError('foreign package path passed')
    link = outside / 'redirect'
    link.symlink_to(outside, target_is_directory=True)
    with patch.object(lpf, '__path__', [str(link)]):
        try: gates._base(None, root, '', '', '')
        except ValueError as e: assert 'package path mismatch' in str(e), e
        else: raise AssertionError('symlink escape passed')
    for name, origin in [('lpf.unknown', None), ('scripts.unknown', str(outside/'x.py'))]:
        module = types.ModuleType(name)
        module.__spec__ = ModuleSpec(name, loader=None, origin=origin)
        module.__file__ = origin
        with patch.dict(sys.modules, {name: module}):
            try: gates._base(None, root, '', '', '')
            except ValueError as e: assert 'import origin mismatch' in str(e), e
            else: raise AssertionError('unknown origin passed')
    forward.assert_not_called()
''', tmp)

    def test_identical_bytes_other_checkout_rejected_by_formal_entries(self):
        with tempfile.TemporaryDirectory() as tmp:
            other = Path(tmp)/'other'
            other.mkdir()
            for name in ('src', 'scripts'):
                shutil.copytree(ROOT/name, other/name, ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
            for name in ('pyproject.toml', 'uv.lock'):
                shutil.copy2(ROOT/name, other/name)
            def git(*args):
                subprocess.run(['git', '-C', str(other), *args], check=True, stdout=subprocess.DEVNULL)
            git('init', '-q', '-b', 'main')
            git('config', 'user.name', 'Fixture')
            git('config', 'user.email', 'fixture@example.invalid')
            git('add', '.')
            git('commit', '-qm', 'copied source')
            self.run_python('''
import sys
from pathlib import Path
from unittest.mock import patch
from lpf.search import gates, campaign
from lpf.search._job_evaluation import source_identity
from lpf.rf_core.model import RFEvaluator
root, other = map(Path, sys.argv[1:])
assert source_identity(root)['files'] == source_identity(other)['files']
gates._verify_import_origins(root)
with patch.object(RFEvaluator, 'evaluate') as forward:
    entries = [
        lambda: gates.prepare_campaign(None, 'EXP-999', owner='', request_id='', purpose='', selection={}, root=other),
        lambda: gates.campaign_preflight(None, 'EXP-999', owner='', request_id='', root=other),
        lambda: campaign.begin_campaign(None, 'EXP-999', owner='', request_id='', root=other),
        lambda: campaign.submit_campaign_proposal(None, 'missing.yaml', 'EXP-999', owner='', request_id='', root=other),
    ]
    for entry in entries:
        try: entry()
        except ValueError as e: assert 'Campaign G1 import' in str(e), e
        else: raise AssertionError('foreign checkout passed')
    forward.assert_not_called()
''', other)

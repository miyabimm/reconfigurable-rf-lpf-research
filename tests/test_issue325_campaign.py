"""Campaign submission contracts; isolated tmp, never a real EXP reservation."""
import copy
from dataclasses import asdict, replace
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import yaml

import test_issue315_fixed_stage as stage_tests
import test_issue317_fixed_worker as worker_tests
import test_issue319_parent_runner as parent_tests
from lpf.search import campaign
from lpf.search.plan import Plan
from lpf.search.preflight import freeze
from lpf.search.proposals import load_proposal, normalize_proposal
from lpf.search.storage import atomic, canonical, plain, sha
from lpf.rf_core.model import RFEvaluator


class CampaignTests(unittest.TestCase):
    setUp = stage_tests.FixedStageTests.setUp
    setup_model = stage_tests.FixedStageTests.setup_model

    def setup_campaign(self, max_topologies=2, max_rf_samples=10000, independent=False, cid='RF-F003'):
        plan, definition, policy, x = self.setup_model(cid)
        # Remove coupling slots so a single generated Sobol point is SPD without
        # repair/retry. Omitted pairs remain explicit zeros in the full matrix.
        definition = replace(definition, coupling_pairs=())
        config = plan.data['config']
        config['definition'] = None
        config['campaign'] = dict(max_topologies=max_topologies, max_rf_samples=max_rf_samples,
            structure=dict(max_nodes=8, max_fixed_capacitors=3, max_variable_capacitors=2,
                inductor_types=['LQP02HV', 'LQP02HQ', 'PCB_L'],
                fixed_c_types=['GJM01', 'PCB_PATTERN_C'], variable_roles=['shunt_to_ground', 'bridge'],
                allow_coupling=True, allow_ic_fixed=cid == 'RF-T008'),
            independent=dict(stage='terminal' if independent else 'not_run',
                max_candidates=1 if independent else 0, sample_indices=[0] if independent else []))
        config['anytime_samples'] = [56]
        frozen = freeze(config, campaign.ROOT)
        plan = Plan(canonical(frozen), sha(frozen))
        self.counter += 1
        output = Path(self.raw.name)/f'campaign-{self.counter}'
        snapshot = campaign.begin_development_campaign(plan, output)
        return plan, definition, output, snapshot

    def proposal(self, definition, snapshot, name='p1'):
        return dict(schema_version=1, proposal_id=name,
            based_on_state_sha256=snapshot['based_on_state_sha256'], reason='構造仮説（適合証拠ではない）',
            definition=plain(asdict(definition)))

    def submit(self, plan, output, proposal, text=None):
        path = Path(self.raw.name)/'proposal.yaml'
        path.write_text(yaml.safe_dump(proposal) if text is None else text)
        return campaign.submit_development_proposal(plan, path, output, solver_kind='fixture')

    @staticmethod
    def state(output):
        return json.loads((output/'campaign.json').read_bytes())

    def test_two_structures_then_same_structure_rejob_counts_and_reservations(self):
        plan, definition, output, snapshot = self.setup_campaign()
        self.assertEqual(snapshot['based_on_state_sha256'], sha(snapshot['snapshot']))
        changed = replace(definition, capacitor_placement=replace(definition.capacitor_placement,
            fixed_edges=((2, -1), (2, -1), (1, 3))))
        cap = plan.data['config']['arms'][0]['max_requested_samples']
        def worker(spec, path, **kw):
            durable = self.state(output)
            self.assertEqual(durable['status'], 'unknown')
            self.assertEqual(durable['reserved'], cap)
            self.assertEqual(durable['jobs'][-1]['status'], 'unknown')
            self.assertLessEqual(durable['requested']+durable['reserved'], 10000)
            return parent_tests.ParentRunnerTests.mock_result(spec, path, **kw)
        with patch.object(campaign.runner, 'execute_development_job', side_effect=worker) as call:
            for i, d in enumerate((definition, changed, definition)):
                snapshot = self.submit(plan, output, self.proposal(d, snapshot, f'p{i}'))
                self.assertEqual(snapshot['snapshot']['status'], 'ready', self.state(output)['events'])
            self.assertEqual(call.call_count, 3)
        state = self.state(output)
        self.assertEqual(len(state['topologies']), 2)
        self.assertEqual(len(state['jobs']), 3)
        self.assertEqual(state['requested'], 3*56)
        self.assertEqual(state['completed'], 3*56)
        self.assertEqual(state['reserved'], 0)
        self.assertTrue(all(j['released'] == cap-56 for j in state['jobs']))
        self.assertNotEqual(state['jobs'][0]['spec_sha256'], state['jobs'][2]['spec_sha256'])
        self.assertEqual(state['jobs'][0]['definition_sha256'], state['jobs'][2]['definition_sha256'])
        self.assertNotEqual(state['jobs'][0]['job_id'], state['jobs'][2]['job_id'])
        self.assertEqual(state['plan']['config']['definition'], None)
        for row in state['jobs']:
            raw = json.loads((output/row['raw_path']).read_bytes())
            self.assertEqual(row['raw_content_sha256'], sha(raw))
            self.assertEqual(row['spec_sha256'], sha(row['spec']))
            self.assertEqual(row['campaign_plan_sha256'], plan.sha256)
            self.assertEqual(row['start']['method'], 'scrambled_sobol_single_point')

    def test_real_rf_f003_and_explicit_trial_392_with_one_independent_spot(self):
        for cid in ('RF-F003', 'RF-T008'):
            plan, d, output, snapshot = self.setup_campaign(independent=True, cid=cid)
            with patch('lpf.search.worker.slsqp_minimize', side_effect=worker_tests.FixedWorkerTests.fixture):
                snapshot = self.submit(plan, output, self.proposal(d, snapshot))
            state = self.state(output)
            self.assertEqual(state['status'], 'ready', state['events'])
            self.assertEqual((state['requested'], state['completed']), (392, 392))
            self.assertEqual((state['independent_requested'], state['independent_completed']), (1, 1))
            raw = json.loads((output/state['jobs'][0]['raw_path']).read_bytes())
            self.assertEqual(raw['batches'][-1]['independent']['status'], 'pass')
            self.assertEqual(len(set(raw['grids']['terminal']['segment'])), 28)
            self.assertEqual(len(set(raw['grids']['terminal']['setting'])), 6)
            self.assertFalse(raw['rf_compliance_certified'])
            self.assertEqual(raw['dense']['status'], 'not_run')

    def test_safe_yaml_hashes_unknown_duplicates_nan_tags_and_bad_types(self):
        plan, definition, output, snapshot = self.setup_campaign()
        proposal = self.proposal(definition, snapshot)
        other = copy.deepcopy(proposal); other['reason'] = '別の理由'
        self.assertNotEqual(normalize_proposal(other)[2], normalize_proposal(proposal)[2])
        self.assertEqual(normalize_proposal(other)[3], normalize_proposal(proposal)[3])
        texts = [yaml.safe_dump(dict(proposal, solver='slp')),
            yaml.safe_dump(proposal)+'reason: duplicate\n',
            yaml.safe_dump(proposal).replace('schema_version: 1', 'schema_version: .nan'),
            '!!python/object/apply:os.system ["false"]',
            yaml.safe_dump(proposal).replace('proposal_id: p1', 'proposal_id: .inf')]
        invalid = copy.deepcopy(proposal); invalid['definition']['physical_order'][0] = True
        texts.append(yaml.safe_dump(invalid))
        invalid = copy.deepcopy(proposal); invalid['definition']['inductor_tree']['edges'][0] = [0, 99]
        texts.append(yaml.safe_dump(invalid))
        with patch.object(RFEvaluator, 'evaluate') as forward:
            for text in texts:
                self.submit(plan, output, proposal, text)
            forward.assert_not_called()
        state = self.state(output)
        self.assertFalse(state['jobs']); self.assertFalse(state['topologies'])
        self.assertEqual(len(state['events']), len(texts))
        self.assertTrue(all(e['status'] == 'rejected' for e in state['events']))
        for text, event in zip(texts, state['events']):
            self.assertEqual((output/event['input_path']).read_text(), text)
        path = Path(self.raw.name)/'reordered.yaml'
        path.write_text(yaml.safe_dump(proposal, sort_keys=False))
        self.assertEqual(normalize_proposal(load_proposal(path))[3], normalize_proposal(proposal)[3])

    def test_stale_role_envelope_topology_and_sample_caps_forward_zero(self):
        for failure in ('stale', 'role', 'role_audit', 'envelope', 'capacitor_count',
                        'topologies', 'samples', 'illegal_start'):
            plan, d, output, snapshot = self.setup_campaign(max_topologies=1,
                max_rf_samples=1 if failure == 'samples' else 10000)
            if failure == 'topologies':
                with patch.object(campaign.runner, 'execute_development_job', side_effect=parent_tests.ParentRunnerTests.mock_result):
                    snapshot = self.submit(plan, output, self.proposal(d, snapshot))
                d = replace(d, physical_order=(1, 0, 2, 3))
            proposal = self.proposal(d, snapshot, 'p2')
            if failure == 'stale': proposal['based_on_state_sha256'] = '0'*64
            if failure == 'role': proposal['definition']['variable_roles'][0] = 'series'
            if failure == 'role_audit': proposal['definition']['variable_roles'][1] = 'shunt_to_ground'
            if failure == 'capacitor_count':
                proposal['definition']['fixed_c_types'].append('GJM01')
                proposal['definition']['capacitor_placement']['fixed_edges'].append([3, -1])
            if failure == 'envelope': proposal['definition']['inductor_types'][0] = 'UNKNOWN'
            with patch.object(RFEvaluator, 'evaluate') as forward:
                if failure == 'illegal_start':
                    with patch.object(campaign.starts, 'generate_for_definition', side_effect=ValueError('illegal SPD/start')):
                        self.submit(plan, output, proposal)
                else:
                    self.submit(plan, output, proposal)
                forward.assert_not_called()
            state = self.state(output)
            self.assertEqual(state['events'][-1]['status'], 'rejected', (failure, state['events']))
            self.assertEqual(len(state['jobs']), int(failure == 'topologies'))

    def test_unknown_holds_reservation_stops_submissions_and_no_rerun(self):
        for fault in ('crash', 'raw', 'uncertain'):
            plan, d, output, snapshot = self.setup_campaign()
            cap = plan.data['config']['arms'][0]['max_requested_samples']
            def worker(spec, path, **kw):
                if fault == 'crash': raise RuntimeError('crash')
                result = parent_tests.ParentRunnerTests.mock_result(spec, path, **kw)
                if fault == 'raw': path.write_text('{}')
                else:
                    result['status'] = 'unknown'
                    atomic(path, result)
                return result
            with patch.object(campaign.runner, 'execute_development_job', side_effect=worker) as call:
                snapshot = self.submit(plan, output, self.proposal(d, snapshot))
                self.assertEqual(snapshot['snapshot']['status'], 'unknown')
                with self.assertRaisesRegex(ValueError, 'unknown/stopped'):
                    self.submit(plan, output, self.proposal(d, snapshot, 'next'))
                self.assertEqual(call.call_count, 1)
            state = self.state(output)
            self.assertEqual(state['requested']+state['reserved'], cap)
            self.assertEqual(len(state['topologies']), 1)
            self.assertEqual(state['jobs'][0]['released'], 0)
            with self.assertRaises(FileExistsError): campaign.begin_development_campaign(plan, output)

    def test_only_next_job_reserved_and_verified_unused_samples_reusable(self):
        plan, d, output, snapshot = self.setup_campaign(max_topologies=1, max_rf_samples=1556)
        self.assertEqual(snapshot['snapshot']['reserved'], 0)
        with patch.object(campaign.runner, 'execute_development_job',
                          side_effect=parent_tests.ParentRunnerTests.mock_result) as worker:
            snapshot = self.submit(plan, output, self.proposal(d, snapshot, 'first'))
            snapshot = self.submit(plan, output, self.proposal(d, snapshot, 'second'))
            snapshot = self.submit(plan, output, self.proposal(d, snapshot, 'third'))
            self.assertEqual(worker.call_count, 2)
        state = self.state(output)
        self.assertEqual(len(state['topologies']), 1)
        self.assertEqual(state['requested'], 112)
        self.assertEqual(state['events'][-1]['status'], 'rejected')
        self.assertIn('max_rf_samples', state['events'][-1]['rejection_reason'])
        # Reusing a mutable copy of an advisor input never changes the ledger.
        snapshot['snapshot']['remaining_rf_samples'] = 999999
        self.assertNotEqual(campaign.campaign_snapshot(output), snapshot)

    def test_prior_raw_proposal_and_cached_accounting_rechecked_before_next_job(self):
        for fault in ('raw', 'proposal', 'totals', 'job_cost', 'topologies'):
            plan, d, output, snapshot = self.setup_campaign()
            with patch.object(campaign.runner, 'execute_development_job',
                              side_effect=parent_tests.ParentRunnerTests.mock_result):
                snapshot = self.submit(plan, output, self.proposal(d, snapshot))
            state = self.state(output)
            if fault == 'raw':
                path = output/state['jobs'][0]['raw_path']
                path.write_bytes(path.read_bytes()+b' ')
            elif fault == 'proposal':
                path = output/state['events'][0]['input_path']
                path.write_bytes(path.read_bytes()+b'\n')
            else:
                if fault == 'totals': state['requested'] = 0
                if fault == 'job_cost': state['jobs'][0]['requested'] = 0
                if fault == 'topologies': state['topologies'] = []
                atomic(output/'campaign.json', state)
            with patch.object(RFEvaluator, 'evaluate') as forward:
                with self.assertRaises(ValueError):
                    self.submit(plan, output, self.proposal(d, snapshot, 'next'))
                forward.assert_not_called()

    def test_parent_save_failure_preserves_unknown_and_never_retries(self):
        for fail_at in ('reservation', 'import'):
            plan, d, output, snapshot = self.setup_campaign()
            calls = []
            real_atomic = campaign.atomic
            def save(path, value):
                if path == output/'campaign.json':
                    calls.append(value['status'])
                    if (fail_at == 'reservation' and value['status'] == 'unknown' or
                            fail_at == 'import' and value['status'] == 'ready'):
                        raise OSError('parent storage failure')
                return real_atomic(path, value)
            with patch.object(campaign, 'atomic', side_effect=save), patch.object(
                    campaign.runner, 'execute_development_job',
                    side_effect=parent_tests.ParentRunnerTests.mock_result) as worker:
                with self.assertRaisesRegex(OSError, 'parent storage failure'):
                    self.submit(plan, output, self.proposal(d, snapshot))
                self.assertEqual(worker.call_count, int(fail_at == 'import'))
            self.assertEqual(calls, ['unknown'] if fail_at == 'reservation' else ['unknown', 'ready'])
            durable = self.state(output)
            self.assertEqual(durable['status'], 'ready' if fail_at == 'reservation' else 'unknown')
            if fail_at == 'import':
                self.assertEqual(durable['reserved'], 1500)
                self.assertEqual(durable['requested'], 0)
                with self.assertRaisesRegex(ValueError, 'unknown/stopped'):
                    self.submit(plan, output, self.proposal(d, snapshot, 'next'))

    def test_source_plan_and_formal_gate_fail_before_forward(self):
        plan, d, output, snapshot = self.setup_campaign()
        with patch.object(RFEvaluator, 'evaluate') as forward:
            with self.assertRaisesRegex(ValueError, 'formal Campaign G0/G1'):
                campaign.run_campaign(plan, output)
            with patch.object(campaign, 'source_identity', return_value={'changed': True}):
                with self.assertRaisesRegex(ValueError, 'source mismatch'):
                    self.submit(plan, output, self.proposal(d, snapshot))
            with self.assertRaisesRegex(ValueError, 'Plan/source'):
                self.submit(replace(plan, sha256='0'*64), output, self.proposal(d, snapshot))
            forward.assert_not_called()
        self.assertFalse(self.state(output)['jobs'])


if __name__ == '__main__':
    unittest.main()

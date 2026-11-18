"""Small deterministic RF-T009 development fixtures; no formal EXP."""
import copy
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import yaml

from test_issue323_dependencies import make
from lpf.rf_core.model import RFEvaluator
from lpf.search import _development_runner as runner
from lpf.search._development_worker import DevelopmentWorker
from lpf.search.development_plan import COSTS
from lpf.search.plan import ROOT
from lpf.search.source import source_identity
from lpf.search.storage import plain, sha, vector_sha


class CommonRunnerTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix='issue448-test-')
        self.addCleanup(tmp.cleanup)
        self.out = Path(tmp.name)/'run'
        _, definition, _, bounds, x = make('RF-F003')
        self.box = plain(bounds)
        step = dict(name='coarse', solver='hybrid', objective='signed_margin_db', aggregation='sum',
                    points_per_interval=2, options=dict(max_search_forwards=2))
        self.cfg = dict(schema_version=1, rf=dict(constraint_id='RF-T009', allow_trial=True),
                        definition=plain(asdict(definition)), seeds=[23, 7], terminal_points=4,
                        arms=[dict(name=arm, steps=[copy.deepcopy(step)]) for arm in ('zeta', 'alpha')],
                        budget=dict(rf_samples=896, rf_forwards=12, independent_mna_samples=8))
        self.starts = {}
        for seed in self.cfg['seeds']:
            self.starts[str(seed)] = {}
            for i, arm in enumerate(self.cfg['arms']):
                vector = x.copy()
                vector[0] += (i + seed) * 0.001
                self.starts[str(seed)][arm['name']] = dict(vector=plain(vector), vector_sha256=vector_sha(vector))
        self.spots = {'terminal': [0], 'zeta/coarse': [0]}

    def launch(self):
        return runner.run(self.cfg, self.starts, self.out, root=ROOT, spot_checks=self.spots,
                          search_bounds=self.box, checkpoint_interval=1)

    def read(self, name):
        return json.loads((self.out/name).read_bytes())

    def assert_stopped(self):
        rows = self.read('run.json')['jobs']
        self.assertEqual([j['status'] for j in rows], ['unknown'] + ['not_started']*3)
        self.assertEqual(rows[0]['unknown'], rows[0]['reservation'])
        self.assertTrue(all(j['actual'] is None and j['released'] is None for j in rows))
        self.assertEqual([j['reservation']['rf_forwards'] for j in rows], [3]*4)
        self.assertFalse((self.out/'job-0002').exists())

    def test_freeze_once_and_seed_then_arm_for_unconverged_jobs(self):
        states = []
        initialize = DevelopmentWorker.__init__
        publish = runner.atomic_verified
        def observe(worker, *args, **kwargs):
            states.append(self.read('run.json'))
            initialize(worker, *args, **kwargs)
        with patch.object(runner, 'freeze_run', wraps=runner.freeze_run) as freeze, \
             patch.object(runner, 'atomic_verified', wraps=publish) as writes, \
             patch.object(DevelopmentWorker, '__init__', observe):
            state = self.launch()
        freeze.assert_called_once()
        self.assertEqual(writes.call_count, 9)
        self.assertEqual(state, self.read('run.json'))
        plan = self.read('plan.json')
        self.assertEqual(sha(plan), state['plan_sha256'])
        self.assertTrue({'gates', 'development_weighted_restart'}.isdisjoint(plan))
        self.assertEqual(plan['search_bounds'], self.box)
        self.assertEqual(plan['spot_checks'], self.spots)
        self.assertEqual(plan['checkpoint_interval'], 1)
        self.assertEqual(plan['rf_profile']['base_constraint_id'], 'RF-F003')
        self.assertEqual([(j['seed'], j['arm']) for j in state['jobs']],
                         [(23, 'zeta'), (23, 'alpha'), (7, 'zeta'), (7, 'alpha')])
        self.assertEqual(len(set(j['vector_sha256'] for j in plan['jobs'])), 4)
        for i, row in enumerate(state['jobs']):
            before = states[i]['jobs']
            self.assertEqual([r['status'] for r in before], ['completed']*i + ['unknown'] + ['not_started']*(3-i))
            self.assertEqual(before[i]['unknown'], before[i]['reservation'])
            self.assertEqual(row['status'], 'completed')
            self.assertEqual(row['scientific_status'], 'not_converged')
            self.assertEqual(row['unknown'], dict.fromkeys(COSTS, 0))
            for k in COSTS:
                self.assertEqual(row['actual'][k] + row['released'][k], row['reservation'][k])
            directory = self.out/row['raw_path']
            self.assertEqual(self.read(f"{row['job_id']}/input.json")['start'],
                             self.starts[str(row['seed'])][row['arm']])
            for name, info in row['raw'].items():
                contents = (directory/name).read_bytes()
                self.assertEqual(info, dict(bytes=len(contents), sha256=hashlib.sha256(contents).hexdigest()))
            result = self.read(f"{row['job_id']}/result.json")
            self.assertEqual(result['plan_sha256'], state['plan_sha256'])
            self.assertEqual(result['terminal']['candidates'][0]['vector'], result['steps'][-1]['solver_result']['x'])
            self.assertNotIn('terminal', row)

    def test_single_job_chains_three_steps_and_reconstructs_terminal_vector(self):
        from lpf.rf_core.coupled_lc import ParameterVectorSchema

        self.cfg['seeds'] = [23]
        self.cfg['arms'] = self.cfg['arms'][:1]
        self.cfg['terminal_points'] = 5
        self.cfg['budget'] = dict(rf_samples=1000, rf_forwards=12, independent_mna_samples=8)
        self.starts = {'23': {'zeta': self.starts['23']['zeta']}}
        self.spots = {'terminal': [0]}
        steps = self.cfg['arms'][0]['steps']
        for solver, aggregation in [('slp', 'signed_max'), ('slsqp', 'max')]:
            steps.append(dict(steps[0], name=solver, solver=solver, aggregation=aggregation,
                              options=dict(max_iterations=1, max_evaluations=2)))
        self.launch()
        result = self.read('job-0001/result.json')
        for previous, step in zip(result['steps'], result['steps'][1:]):
            self.assertEqual(vector_sha(previous['solver_result']['x']), step['input_vector_sha256'])
        terminal, = result['terminal']['candidates']
        self.assertEqual(terminal['vector'], result['steps'][-1]['solver_result']['x'])
        schema = ParameterVectorSchema(**result['parameter_schema'])
        values = schema.decode(terminal['vector'])
        self.assertEqual(len(values.capacitors_pf_by_setting), 6)
        self.assertEqual(vector_sha(schema.encode(values)), terminal['vector_sha256'])
        checkpoints = self.out/'job-0001/checkpoints'
        self.assertEqual({json.loads(p.read_bytes())['step'] for p in checkpoints.iterdir()},
                         {'coarse', 'slp', 'slsqp'})

    def test_initial_full_reservation_and_budgets_before_forward(self):
        observed = []
        publish = runner.atomic_verified
        def save(path, value):
            result = publish(path, value)
            observed.append(json.loads(path.read_bytes()))
            if len(observed) == 1:
                raise OSError('injected after initial ledger write')
            return result
        for cost in COSTS:
            with self.subTest(cost=cost), patch.object(RFEvaluator, 'evaluate') as forward:
                self.cfg['budget'][cost] -= 1
                with self.assertRaisesRegex(ValueError, cost):
                    self.launch()
                self.cfg['budget'][cost] += 1
                self.assertFalse(self.out.exists())
                forward.assert_not_called()
        with patch.object(runner, 'atomic_verified', side_effect=save), patch.object(RFEvaluator, 'evaluate') as forward:
            with self.assertRaisesRegex(OSError, 'initial ledger'):
                self.launch()
            forward.assert_not_called()
        self.assertEqual([row['status'] for row in observed[0]['jobs']], ['not_started']*4)
        for k in COSTS:
            self.assertEqual(sum(j['reservation'][k] for j in observed[0]['jobs']), self.cfg['budget'][k])

    def test_abnormal_jobs_stop_with_full_unknown(self):
        profile = runner.freeze_run(self.cfg, self.starts, root=ROOT, spot_checks=self.spots,
                                    search_bounds=self.box, checkpoint_interval=1)[2]
        source = source_identity(ROOT)
        save = runner._save_checkpoint
        real_job = runner._run_job
        def fail_raw(path, record):
            if path.name == 'result.json':
                raise OSError('raw storage unavailable')
            return save(path, record)
        def tamper(name):
            def job(*args):
                receipt = real_job(*args)
                path = args[-1]/name
                if name == 'checkpoints':
                    path = next(path.iterdir())
                path.write_bytes(b'{}\n')
                return receipt
            return job
        publish = runner.atomic_verified
        def parent_failure(path, state):
            result = publish(path, state)
            if state['jobs'][0]['status'] == 'completed':
                raise OSError('parent completion readback unavailable')
            return result
        def overrun(callback, x, *_args, **_kwargs):
            for _ in range(3):
                callback(x)
        def terminal_failure(*args, check_power=False):
            if check_power:
                raise ValueError('Terminal power STOP')
            return evaluate(*args, check_power=check_power)
        evaluate = RFEvaluator.evaluate
        from dataclasses import replace
        cases = [
            ('solver', patch('lpf.search._development_worker.hybrid_minimize', side_effect=ValueError('Solver STOP')), 'Solver STOP'),
            ('terminal', patch.object(RFEvaluator, 'evaluate', terminal_failure), 'Terminal power STOP'),
            ('audit', patch('lpf.rf_core.independent.evaluate_independent_response', side_effect=ValueError('MNA STOP')), 'MNA STOP'),
            ('cap', patch('lpf.search._development_worker.hybrid_minimize', side_effect=overrun), 'forward budget exhausted'),
            ('source', patch('lpf.search._development_worker.source_identity', side_effect=[source, {}]), 'Source/environment'),
            ('rf', patch('lpf.minimax_profile.load_minimax_profile', side_effect=[profile, replace(profile, fingerprint='changed')]), 'RF profile/base'),
            ('raw-write', patch.object(runner, '_save_checkpoint', side_effect=fail_raw), 'raw storage unavailable'),
            ('raw-edit', patch.object(runner, '_run_job', side_effect=tamper('result.json')), 'bytes changed'),
            ('receipt', patch.object(runner, '_run_job', side_effect=tamper('receipt.json')), 'Receipt bytes changed'),
            ('checkpoint', patch.object(runner, '_run_job', side_effect=tamper('checkpoints')), 'bytes changed'),
            ('parent', patch.object(runner, 'atomic_verified', side_effect=parent_failure), 'parent completion readback'),
        ]
        for name, failure, reason in cases:
            with self.subTest(name=name), failure:
                self.out = self.out.with_name(name)
                with self.assertRaisesRegex((ValueError, OSError), reason):
                    self.launch()
                self.assert_stopped()

    def test_input_rejections_and_single_job_cli(self):
        for cid in ('RF-F003', 'RF-T005', 'RF-T006', 'RF-T007', 'RF-T008'):
            with self.subTest(cid=cid), patch.object(RFEvaluator, 'evaluate') as forward:
                self.cfg['rf']['constraint_id'] = cid
                with self.assertRaisesRegex(ValueError, 'Unknown minimax profile'):
                    self.launch()
                self.assertFalse(self.out.exists())
                forward.assert_not_called()
        self.cfg['rf']['constraint_id'] = 'RF-T009'
        del self.starts['7']['alpha']
        with self.assertRaisesRegex(ValueError, 'Expected exactly'):
            self.launch()
        self.assertFalse(self.out.exists())
        self.cfg['seeds'] = [23]
        self.cfg['arms'] = self.cfg['arms'][:1]
        starts = {'23': {'zeta': self.starts['23']['zeta']}}
        config, path = (self.out.parent/name for name in ('config.yaml', 'starts.json'))
        config.write_text(yaml.safe_dump(self.cfg))
        path.write_text(json.dumps(starts))
        command = [sys.executable, str(ROOT/'scripts/run_rf_search.py'), 'develop', '--config', str(config),
                   '--starts', str(path), '--output', str(self.out), '--spot-checks', '{"terminal":[0]}']
        proc = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(proc.returncode, 4, proc.stderr)
        self.assertEqual(json.loads(proc.stdout)['status'], 'completed')
        self.assertEqual(len(self.read('run.json')['jobs']), 1)
        retry = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(retry.returncode, 2)
        self.assertIn('Fresh temporary', retry.stderr)

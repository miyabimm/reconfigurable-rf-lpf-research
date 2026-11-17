"""Selectionless development: bounded RF software checks, not a scientific EXP."""
import copy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import test_issue315_fixed_stage as stage_tests
from lpf.search import runner
from lpf.search.storage import atomic, vector_sha
from lpf.search.worker import freeze_development_job


class DevelopmentTerminalTests(unittest.TestCase):
    setUp = stage_tests.FixedStageTests.setUp
    setup_model = stage_tests.FixedStageTests.setup_model

    def prepare(self, solvers=('slsqp',), same_grid=False):
        def configure(c):
            c.pop('selection')
            c['anytime_samples'] = []
            template = c['arms'][0]['steps'][0]
            steps = []
            for i, solver in enumerate(solvers):
                step = copy.deepcopy(template)
                step.update(name=f'step{i}', solver=solver,
                            aggregation='signed_max' if solver == 'slp' else 'sum',
                            points_per_interval=4 if same_grid else 2,
                            max_requested_samples=1000,
                            options=({'max_search_forwards': 2} if solver == 'hybrid' else
                                     {'max_iterations': 1, 'max_evaluations': 4}))
                steps.append(step)
            c['arms'][0]['steps'] = steps
            c['arms'][0]['max_requested_samples'] = 1000 * len(steps) + 112
            c['max_trial_requested_samples'] = c['arms'][0]['max_requested_samples']
        plan, definition, policy, x = self.setup_model(mutate=configure)
        starts = {23: dict(vector=x.tolist(), vector_sha256=vector_sha(x))}
        self.counter += 1
        return plan, definition, policy, starts, Path(self.raw.name)/f'run{self.counter}'

    def test_real_solvers_and_multistep(self):
        for solvers in [('slsqp',), ('slp',), ('hybrid',), ('slsqp', 'hybrid')]:
            with self.subTest(solvers=solvers):
                args = self.prepare(solvers)
                state = runner.run_development(*args, spot_checks={'terminal': [0]})
                self.assertEqual(state['status'], 'completed', state.get('exit_reason'))
                row = state['jobs'][0]
                raw = json.loads((args[-1]/row['raw_path']).read_text())
                self.assertNotIn('selection', raw)
                self.assertNotIn('selection', raw['grids'])
                self.assertNotIn('selection_upper_reservation', args[0].data['costs']['jobs']['demo'])
                self.assertEqual(args[0].data['costs']['jobs']['demo']['terminal_fixed_reservation'], 112)
                self.assertEqual(len(raw['terminal']['candidates']), 1)
                self.assertEqual(raw['terminal']['candidates'][0]['vector_sha256'], raw['steps'][-1]['output_vector_sha256'])
                self.assertFalse(raw['batches'][-1]['assessment']['strict_feasible'])  # terminal FAIL is not a solver verdict
                self.assertEqual(raw['batches'][-1]['independent']['status'], 'pass')
                self.assertEqual(row['requested'], row['completed'])
                self.assertEqual(row['requested'], sum(b['requested'] for b in raw['batches']))
                for step in raw['steps']:
                    solver = step['settings']['solver']
                    key = 'best_fun' if solver == 'hybrid' else 'fun' if solver == 'slsqp' else 'objective'
                    self.assertAlmostEqual(step['output_objective'], step['solver_result'][key], places=12)
                    common = step['optimizer_result']
                    self.assertEqual(set(common), {'x', 'objective', 'converged', 'stop_reason', 'evaluations'})
                    self.assertEqual(vector_sha(common['x']), step['output_vector_sha256'])
                    self.assertEqual(common['objective'], step['output_objective'])
                    self.assertEqual(common['converged'], step['status'] == 'converged')
                    if common['stop_reason'] in ('evaluation_limit', 'evaluation_budget_exhausted'):
                        self.assertFalse(common['converged'])
                    search_batches = [b for b in raw['batches'] if b['stage'] == 'demo/' + step['name']]
                    self.assertGreater(len(search_batches), 0)
                    self.assertTrue(any(b['vector_sha256'] == step['output_vector_sha256'] for b in search_batches))
                for first, second in zip(raw['steps'], raw['steps'][1:]):
                    self.assertEqual(first['output_vector_sha256'], second['input_vector_sha256'])
                summary = runner.finalize_development(state, args[-1])
                self.assertNotIn('selection', summary['jobs'][0])
                self.assertEqual(summary['jobs'][0]['terminal'], raw['terminal'])

    def test_same_grid_terminal_and_window_readback(self):
        import numpy as np
        from lpf.search._window_evaluation import WindowJobEvaluation
        for debug in (False, True):
            with self.subTest(debug=debug):
                args = self.prepare(same_grid=True)
                with patch.object(runner, '_validate_development_output'), \
                     patch.object(WindowJobEvaluation, '_validate_checkpoint'):
                    state = runner.run_development(*args, storage_mode='window100',
                        debug_forward_history=debug, spot_checks={'terminal': [0]})
                    self.assertEqual(state['status'], 'completed', state.get('exit_reason'))
                    summary = runner.finalize_development(state, args[-1])
                self.assertNotIn('selection', summary['jobs'][0])
                envelope = json.loads((args[-1]/state['jobs'][0]['raw_path']).read_text())
                self.assertEqual(len(envelope['payload']['terminal']['candidates']), 1)
        args = self.prepare(same_grid=True)
        state = runner.run_development(*args, spot_checks={'demo/step0': [0], 'terminal': [0]})
        self.assertEqual(state['status'], 'completed', state.get('exit_reason'))
        raw = json.loads((args[-1]/state['jobs'][0]['raw_path']).read_text())
        terminal = raw['batches'][-1]
        search = next(b for b in raw['batches'] if b['stage'] == 'demo/step0' and
                      b['vector_sha256'] == terminal['vector_sha256'])
        for key in ('s_real', 's_imag', 'il_db', 'apl_db', 'in_rl_db', 'out_rl_db'):
            np.testing.assert_allclose(search['response'][key], terminal['response'][key], rtol=0, atol=1e-12)
        for key in ('strict_feasible', 'worst_il_db', 'max_violation_db', 'sum_violation_db', 'mandatory_g'):
            self.assertEqual(search['assessment'][key], terminal['assessment'][key])
        self.assertEqual(search['physical_checks'], terminal['physical_checks'])
        self.assertEqual(search['independent']['status'], 'pass')
        self.assertEqual(terminal['independent']['status'], 'pass')

    def test_old_plan_rejected(self):
        plan, d, p, x = self.setup_model()
        with self.assertRaisesRegex(ValueError, 'selectionless'):
            freeze_development_job(plan, d, p, 'demo', 23, x)

    def test_no_solver_forward_keeps_reservation(self):
        from test_issue317_fixed_worker import FixtureOutput
        args = self.prepare()
        def fake(callback, x, bounds, **kw):
            return FixtureOutput(x=x, success=False, nfev=0, stop_reason='fixture')
        with patch('lpf.search.worker.slsqp_minimize', side_effect=fake):
            state = runner.run_development(*args, solver_kind='fixture')
        self.assertEqual(state['status'], 'unknown')
        self.assertEqual(state['jobs'][0]['reserved'], state['jobs'][0]['cap'])

    def test_invalid_final_output_keeps_reservation(self):
        from test_issue317_fixed_worker import FixtureOutput
        args = self.prepare()
        def fake(callback, x, bounds, **kw):
            callback(x)
            bad = x.copy()
            bad[0] = -1
            return FixtureOutput(x=bad, success=False, nfev=1, stop_reason='fixture')
        with patch('lpf.search.worker.slsqp_minimize', side_effect=fake):
            state = runner.run_development(*args, solver_kind='fixture')
        self.assertEqual(state['status'], 'unknown')
        row = state['jobs'][0]
        self.assertEqual(row['released'], 0)
        self.assertGreater(row['reserved'], 0)
        raw = json.loads((args[-1]/row['raw_path']).read_text())
        self.assertEqual(raw['steps'][0]['status'], 'invalid_output')
        self.assertEqual(raw['terminal']['status'], 'not_run')

    def test_readback_rejects_optimizer_result_substitution(self):
        args = self.prepare()
        state = runner.run_development(*args)
        self.assertEqual(state['status'], 'completed', state.get('exit_reason'))
        row = state['jobs'][0]
        path = args[-1]/row['raw_path']
        raw = json.loads(path.read_text())
        raw['steps'][0]['optimizer_result']['objective'] += 1
        atomic(path, raw)
        from lpf.search.worker import JobSpec
        with self.assertRaisesRegex(ValueError, 'Optimizer result'):
            runner._development_readback(path, raw, JobSpec(**row['spec']))

    def test_readback_rejects_terminal_substitution(self):
        args = self.prepare()
        state = runner.run_development(*args)
        self.assertEqual(state['status'], 'completed', state.get('exit_reason'))
        row = state['jobs'][0]
        path = args[-1]/row['raw_path']
        raw = json.loads(path.read_text())
        raw['terminal']['candidates'][0]['vector_sha256'] = '0' * 64
        atomic(path, raw)
        from lpf.search.worker import JobSpec
        with self.assertRaisesRegex(ValueError, 'Terminal'):
            runner._development_readback(path, raw, JobSpec(**row['spec']))


if __name__ == '__main__':
    unittest.main()

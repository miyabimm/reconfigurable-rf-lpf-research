"""Tiny non-EXP CLI integration: real RF/solver, no dense or seed search."""
import contextlib
import copy
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

import yaml
import test_issue315_fixed_stage as stage_tests
from lpf.search import runner
from lpf.search.storage import atomic, canonical, vector_sha
from lpf.rf_core.model import RFEvaluator

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('rf_search_cli', ROOT/'scripts/run_rf_search.py')
cli = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cli)


class DevelopmentCLITests(unittest.TestCase):
    setUp = stage_tests.FixedStageTests.setUp
    setup_model = stage_tests.FixedStageTests.setup_model

    def prepare(self, two_arms=False):
        def tiny(c):
            c['anytime_samples'] = [56]
            first = c['arms'][0]['steps'][0]
            first['max_requested_samples'] = 56
            first['options'] = dict(max_iterations=1, max_evaluations=1)
            second = copy.deepcopy(first); second['name'] = 'fine'
            c['arms'][0]['steps'].append(second)
            if two_arms:
                other = copy.deepcopy(c['arms'][0]); other['name'] = 'other'
                c['arms'].append(other)
                c['max_trial_requested_samples'] = 3000
        plan, d, p, x = self.setup_model(mutate=tiny)
        starts = {23: dict(vector=x.tolist(), vector_sha256=vector_sha(x))}
        start_path = Path(self.raw.name)/'starts.json'
        atomic(start_path, {str(k): v for k, v in starts.items()})
        output = Path(self.raw.name)/'output'
        argv = ['develop', '--config', str(Path(self.sources.name)/'plan.yaml'),
                '--starts', str(start_path), '--output', str(output),
                '--spot-checks', '{"terminal":[0]}']
        return (plan, d, p, starts, output), argv

    def invoke(self, argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli.main(argv)
        return code, out.getvalue(), err.getvalue()

    def test_module_and_compatibility_entry_have_same_help_and_rejection(self):
        env = dict(os.environ, PYTHONPATH=str(ROOT/'src'))
        for args in (['--help'], ['preflight', '--config', 'unused.yaml']):
            results = [subprocess.run([sys.executable, *entry, *args], capture_output=True,
                                      text=True, timeout=30, env=env)
                       for entry in ([str(ROOT/'scripts/run_rf_search.py')],
                                     ['-m', 'lpf.cli.run_rf_search'])]
            self.assertEqual(results[0].returncode, results[1].returncode)
            # argparse derives its usage program name from the entry point.
            self.assertEqual(results[0].stdout, results[1].stdout)
            self.assertEqual(results[0].stderr, results[1].stderr)

    def test_retired_schema1_commands_rejected_without_output(self):
        for command in ('preflight', 'run'):
            with self.subTest(command=command):
                completed = subprocess.run([sys.executable, str(ROOT/'scripts/run_rf_search.py'),
                    command, '--config', 'unused.yaml'], capture_output=True, text=True, timeout=30)
                self.assertEqual(completed.returncode, 2)
                self.assertIn('invalid choice', completed.stderr)
                self.assertFalse(completed.stdout)

    def test_actual_cli_two_steps_solver_rf_and_summary(self):
        args, argv = self.prepare()
        # The real schema2 CLI must run without importing retired facades,
        # including imports hidden in a function or an import-time dependency.
        guarded_cli = '''
import importlib.abc, runpy, sys
class NoLegacy(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == 'lpf.phase2_models' or fullname.startswith('lpf.phase2_models.') or fullname == 'lpf.search._legacy_schema1':
            raise ImportError('schema2 imported legacy: ' + fullname)
sys.meta_path.insert(0, NoLegacy())
sys.argv = sys.argv[1:]
runpy.run_path(sys.argv[0], run_name='__main__')
'''
        completed = subprocess.run([sys.executable, '-c', guarded_cli,
                                    str(ROOT/'scripts/run_rf_search.py'), *argv],
                                   capture_output=True, text=True, timeout=60)
        self.assertEqual(completed.returncode, 4, completed.stderr)
        summary = json.loads(completed.stdout)
        saved = json.loads((args[-1]/'summary.json').read_text())
        self.assertEqual(summary, saved)
        self.assertEqual(summary['development_flow'], 'completed')
        self.assertFalse(summary['solver_converged'])
        self.assertFalse(summary['rf_compliance_certified'])
        self.assertEqual(summary['campaign']['requested'], 392)
        self.assertEqual(summary['campaign']['completed'], 392)
        self.assertEqual(summary['campaign']['independent_completed'], 1)
        self.assertEqual(summary['campaign']['reserved'], 0)
        self.assertEqual(summary['interval_count'], 28)
        self.assertEqual(summary['dense'], 'not_run')
        self.assertEqual(summary['gates'], dict(G0_G1='not_ready', G2_G5='not_ready'))
        parent_path = args[-1]/'run.json'
        self.assertEqual(summary['parent_raw_byte_sha256'], hashlib.sha256(parent_path.read_bytes()).hexdigest())
        job = summary['jobs'][0]
        raw_path = args[-1]/job['raw_path']
        raw = json.loads(raw_path.read_text())
        self.assertEqual(job['raw_byte_sha256'], hashlib.sha256(raw_path.read_bytes()).hexdigest())
        self.assertEqual(job['start_vector_sha256'], args[3][23]['vector_sha256'])
        self.assertEqual(len(job['solver_steps']), 2)
        self.assertEqual([s['status'] for s in job['solver_steps']], ['not_converged']*2)
        self.assertEqual([b['requested'] for b in raw['batches']], [56, 84, 56, 84, 112])
        self.assertEqual(raw['terminal']['status'], 'completed')
        self.assertEqual(job['selection']['status'], 'completed')
        self.assertEqual(job['anytime'][0]['status'], 'completed')
        self.assertEqual(job['independent_spots'][-1]['status'], 'pass')
        self.assertFalse(job['finite_grid'][-1]['strict_feasible'])
        for observed, batch in zip(job['finite_grid'], raw['batches']):
            self.assertEqual(observed['strict_feasible'], batch['assessment']['strict_feasible'])
            nominal = [r for r in batch['assessment']['rows'] if r['requirement']['level'] == 'nominal']
            self.assertEqual(observed['nominal_pass'], all(r['passed'] for r in nominal))
        for grid in raw['grids'].values():
            self.assertEqual(len(grid['interval_samples']), 28)
            self.assertEqual(set(grid['setting']), set(range(6)))
        self.assertEqual(summary['plan_sha256'], raw['plan_sha256'])
        self.assertEqual(summary['effective_constraint_sha256'], raw['policy_fingerprint'])
        self.assertEqual(summary['source_sha256'], raw['spec']['source_sha256'])
        before = parent_path.read_bytes()
        self.assertEqual(self.invoke(argv)[0], 2)  # no resume or rewrite
        self.assertEqual(parent_path.read_bytes(), before)

    def test_two_arms_and_zero_exit_is_not_a_scientific_pass(self):
        args, argv = self.prepare(two_arms=True)
        from test_issue317_fixed_worker import FixtureOutput
        import numpy as np
        def converged(residuals, x, bounds, **kw):
            # Synthetic convergence only; actual RF is still evaluated once.
            residuals(x)
            return FixtureOutput(np.array(x), success=True)
        with patch('lpf.search.worker.slsqp_minimize', side_effect=converged):
            code, out, err = self.invoke(argv)
        self.assertEqual(code, 0, err)
        summary = json.loads(out)
        self.assertEqual(summary['campaign']['requested'], 784)
        self.assertEqual(summary['trials']['seed23']['initial_reservation'], 3000)
        self.assertTrue(summary['solver_converged'])
        self.assertFalse(summary['rf_compliance_certified'])
        self.assertTrue(all(not j['finite_grid'][-1]['strict_feasible'] for j in summary['jobs']))

    def test_illegal_start_sha_seed_budget_definition_and_production_before_forward(self):
        args, argv = self.prepare()
        start_path = Path(argv[argv.index('--starts')+1])
        original = json.loads(start_path.read_text())
        bads = [{}, {'24': original['23']},
                {'23': dict(original['23'], vector_sha256='0'*64)}]
        invalid = copy.deepcopy(original); invalid['23']['vector'][0] = -1
        invalid['23']['vector_sha256'] = vector_sha(invalid['23']['vector']); bads.append(invalid)
        with patch.object(RFEvaluator, 'evaluate') as forward:
            for bad in bads:
                atomic(start_path, bad)
                self.assertEqual(self.invoke(argv)[0], 2)
                self.assertFalse(args[-1].exists())
            start_path.write_text('{"23":{},"23":{}}')
            self.assertEqual(self.invoke(argv)[0], 2)
            atomic(start_path, original)
            config_path = Path(argv[argv.index('--config')+1])
            cfg = yaml.safe_load(config_path.read_text())
            for mutation in (lambda c: c.update(max_trial_requested_samples=1),
                             lambda c: c['definition'].update(source_sha256='0'*64)):
                changed = copy.deepcopy(cfg); mutation(changed)
                config_path.write_text(yaml.safe_dump(changed))
                self.assertEqual(self.invoke(argv)[0], 2)
                self.assertFalse(args[-1].exists())
            self.assertEqual(self.invoke(argv+['--mode', 'production'])[0], 3)
            forward.assert_not_called()

    def test_final_readback_faults_and_save_failure_stop_without_rewrite(self):
        # Single bounded run; subsequent fault injections do not forward again.
        args, argv = self.prepare()
        state = runner.run_development(*args, spot_checks={'terminal': [0]})
        parent = args[-1]/'run.json'
        raw = args[-1]/state['jobs'][0]['raw_path']
        parent_bytes, raw_bytes = parent.read_bytes(), raw.read_bytes()
        with patch.object(RFEvaluator, 'evaluate') as forward:
            for path in (parent, raw):
                path.write_bytes(path.read_bytes()+b' ')
                with self.assertRaises(ValueError): runner.finalize_development(state, args[-1])
                path.write_bytes(parent_bytes if path == parent else raw_bytes)
            raw.unlink()
            with self.assertRaises(OSError): runner.finalize_development(state, args[-1])
            raw.write_bytes(raw_bytes)
            with patch.object(runner, 'atomic', side_effect=OSError('disk full')) as save:
                with self.assertRaises(OSError): runner.finalize_development(state, args[-1])
                self.assertEqual(save.call_count, 1)
            forward.assert_not_called()
        self.assertEqual(parent.read_bytes(), parent_bytes)
        self.assertEqual(raw.read_bytes(), raw_bytes)
        self.assertFalse((args[-1]/'summary.json').exists())

    def test_budget_stop_is_reconciled_not_implementation_or_rf_pass(self):
        args, argv = self.prepare()
        from test_issue317_fixed_worker import FixedWorkerTests
        # Two callbacks want two full grids; the explicit step cap permits one.
        with patch('lpf.search.worker.slsqp_minimize', side_effect=FixedWorkerTests.fixture):
            code, out, err = self.invoke(argv)
        self.assertEqual(code, 4, err)
        summary = json.loads(out)
        self.assertEqual(summary['development_flow'], 'completed')
        self.assertEqual(summary['jobs'][0]['worker_status'], 'budget_exhausted')
        self.assertEqual(summary['jobs'][0]['terminal']['status'], 'not_run')
        self.assertEqual(summary['campaign']['requested'], 140)  # 56 search + 84 anytime
        self.assertEqual(summary['campaign']['requested'], summary['campaign']['completed'])
        self.assertEqual(summary['campaign']['reserved'], 0)
        self.assertFalse(summary['rf_compliance_certified'])

    def test_cli_parent_save_failure_is_stop_and_never_retried(self):
        args, argv = self.prepare()
        with patch.object(runner, 'atomic', side_effect=OSError('disk full')) as save, \
             patch.object(runner, 'execute_development_job') as worker:
            code, out, err = self.invoke(argv)
        self.assertEqual(code, 2)
        self.assertIn('disk full', err)
        self.assertEqual(save.call_count, 1)
        worker.assert_not_called()
        self.assertFalse((args[-1]/'summary.json').exists())

    def test_unknown_interrupt_cli_stop(self):
        args, argv = self.prepare()
        with patch.object(runner, 'execute_development_job', side_effect=KeyboardInterrupt()) as call:
            code, out, err = self.invoke(argv)
        self.assertEqual(code, 2, err)
        self.assertEqual(call.call_count, 1)
        summary = json.loads(out)
        self.assertEqual(summary['development_flow'], 'stopped')
        self.assertEqual(summary['campaign']['reserved'], 1500)
        self.assertEqual(summary['jobs'][0]['status'], 'unknown')
        self.assertEqual(summary['jobs'][0]['requested'], 0)
        self.assertFalse(summary['solver_converged'])


if __name__ == '__main__':
    unittest.main()

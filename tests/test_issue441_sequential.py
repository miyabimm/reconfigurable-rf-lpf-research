"""Small development-only sequential and checkpoint contracts."""
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import test_issue435_weighted_development as fixtures
from lpf.search._development_runner import _weighted_plan
from lpf.search._development_worker import DevelopmentWorker
from lpf.search.component_constraints import physical_bounds
from lpf.search.plan import ROOT
from lpf.search.runner import run_weighted_development, _weighted_strict_winner
from lpf.search.storage import canonical, vector_sha
from lpf.optimizers.hybrid import HybridResult, LocalRun
from lpf.search.starts import generate_for_definition
from lpf.rf_core import build_rf_model


class SequentialTests(unittest.TestCase):
    setUp = fixtures.WeightedTests.setUp
    setup_model = fixtures.WeightedTests.setup_model
    inputs = fixtures.WeightedTests.inputs

    def prepared(self, n=3):
        config, _, definition, policy, x = self.inputs()
        c = yaml.safe_load(config.read_text())
        c['seeds'] = [23, 24]
        config.write_text(yaml.safe_dump(c))
        model = build_rf_model(definition, policy)
        box = [list(pair) for pair in physical_bounds(definition, model.schema, policy)]
        plan = _weighted_plan(config, ROOT, 'demo', n, search_bounds=box)
        starts = {seed: dict(vector=x.tolist(), vector_sha256=vector_sha(x)) for seed in c['seeds']}
        return plan, definition, policy, x, box, starts

    def test_sequential_parent_and_per_job_budget(self):
        plan, d, p, x, box, starts = self.prepared()
        def early(fun, z, **kwargs):
            value = fun(z)
            return SimpleNamespace(x=z, fun=value, success=True, status=0, message='success', nit=0)
        output = Path(self.raw.name)/'sequence'
        with patch('lpf.optimizers.hybrid.minimize', side_effect=early):
            summary = run_weighted_development(plan, d, p, starts, output, root=ROOT,
                                               spot_checks={'terminal': [0, 111]})
        self.assertEqual(summary['status'], 'completed', summary.get('exit_reason'))
        self.assertEqual([r['seed'] for r in summary['jobs']], [23, 24])
        for row in summary['jobs']:
            self.assertEqual(row['requested'], 3*70+84+476)
            self.assertEqual(row['local_run_count'], 3)
            self.assertNotIn('local_runs', row)
            self.assertEqual(set(row['best']), {'vector_sha256', 'objective_j'})
            self.assertEqual(set(row['terminal']['assessment']), {'strict_feasible', 'worst_il_db'})
            job = output/row['raw_path']
            self.assertEqual(len(json.loads((job/'result.json').read_text())['steps'][0]['solver_result']['runs']), 3)
            checkpoint = json.loads((job/'checkpoints'/'000001.json').read_text())
            self.assertEqual(checkpoint['forward_count'], 3)
            self.assertEqual(checkpoint['restart_count'], 2)
            self.assertEqual(row['terminal']['independent']['status'], 'pass')
        with self.assertRaises(ValueError):
            run_weighted_development(plan, d, p, starts, output, root=ROOT)

    def test_weighted_plan_rejects_old_solver_options(self):
        plan, d, p, x, box, starts = self.prepared(3)
        config = Path(self.sources.name)/'plan.yaml'
        c = yaml.safe_load(config.read_text())
        c['arms'][0]['steps'][0]['options'] = dict(maxiter=3, max_restarts=0,
                                                   max_evaluations=3, restart_sigma=.1)
        config.write_text(yaml.safe_dump(c))
        with self.assertRaisesRegex(ValueError, 'omit step options'):
            _weighted_plan(config, ROOT, 'demo', 3, search_bounds=box)

    def test_configurable_checkpoint_interval_is_frozen_and_saved(self):
        plan, d, p, x, box, starts = self.prepared(5)
        config = Path(self.sources.name)/'plan.yaml'
        plan = _weighted_plan(config, ROOT, 'demo', 5,
                              search_bounds=box, checkpoint_interval_forwards=2)
        self.assertEqual(plan.data['development_weighted_restart']['checkpoint_interval_forwards'], 2)
        def early(fun, z, **kwargs):
            value = fun(z)
            return SimpleNamespace(x=z, fun=value, success=True, status=0, message='success', nit=0)
        output = Path(self.raw.name)/'interval'
        with patch('lpf.optimizers.hybrid.minimize', side_effect=early):
            summary = run_weighted_development(plan, d, p, starts, output, root=ROOT)
        self.assertEqual(summary['status'], 'completed', summary.get('exit_reason'))
        job = output/summary['jobs'][0]['raw_path']
        rows = [json.loads(p.read_text()) for p in sorted((job/'checkpoints').glob('*.json'))]
        self.assertEqual([r['forward_count'] for r in rows], [2, 4, 5])
        self.assertEqual(json.loads((job/'input.json').read_text())['checkpoint_interval_forwards'], 2)
        for invalid in (0, -1, True, 1.5):
            with self.assertRaises(ValueError):
                _weighted_plan(config, ROOT, 'demo', 5,
                               search_bounds=box, checkpoint_interval_forwards=invalid)

    def test_terminal_strict_then_il_not_j(self):
        def row(name, strict, il, j):
            return dict(job_id=name, status='completed', best=dict(vector_sha256=name, objective_j=j),
                        terminal=dict(assessment=dict(strict_feasible=strict, worst_il_db=il)))
        rows = [row('fail', False, .1, 0), row('strict-high-il', True, .9, .1),
                row('strict-low-il', True, .8, 99)]
        self.assertEqual(_weighted_strict_winner(rows), 'strict-low-il')
        self.assertIsNone(_weighted_strict_winner(rows[:1]))

    def test_cli_explicit_starts(self):
        plan, d, p, x, box, starts = self.prepared(2)
        config = Path(self.sources.name)/'plan.yaml'
        start_file = Path(self.raw.name)/'starts.json'
        start_file.write_text(json.dumps(starts))
        box_file = Path(self.raw.name)/'box.json'
        box_file.write_text(json.dumps(box))
        output = Path(self.raw.name)/'cli-sequential'
        proc = subprocess.run([sys.executable, str(ROOT/'scripts/run_rf_search.py'), 'develop',
                               '--config', str(config), '--output', str(output), '--starts', str(start_file),
                               '--objective-mode', 'weighted_violation', '--max-search-forwards', '2',
                               '--checkpoint-interval-forwards', '1',
                               '--search-bounds', str(box_file)], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 4, proc.stderr)
        summary = json.loads((output/'summary.json').read_text())
        self.assertEqual(summary['status'], 'completed')
        self.assertEqual([r['seed'] for r in summary['jobs']], [23, 24])
        self.assertEqual(summary['jobs'][0]['start']['vector_sha256'], vector_sha(x))
        job = output/summary['jobs'][0]['raw_path']
        self.assertEqual([json.loads(p.read_text())['forward_count']
                          for p in sorted((job/'checkpoints').glob('*.json'))], [1, 2])

    def test_worker_readback_tampering_stops_with_unknown(self):
        from lpf.search._development_runner import run_prepared_weighted_job
        plan, d, p, x, box, starts = self.prepared(2)
        output = Path(self.raw.name)/'tampered'
        def tamper(*args, **kwargs):
            result = run_prepared_weighted_job(*args, **kwargs)
            path = Path(args[6])/'result.json'
            path.write_text(path.read_text() + ' ')
            return result
        with patch('lpf.search._development_runner.run_prepared_weighted_job', side_effect=tamper):
            summary = run_weighted_development(plan, d, p, starts, output, root=ROOT)
        self.assertEqual(summary['status'], 'unknown')
        self.assertIn('byte mismatch', summary['exit_reason'])
        self.assertEqual(summary['jobs'][0]['reserved'], 2*70+84+476)
        self.assertEqual(summary['jobs'][1]['status'], 'not_started')

    def test_selection_vector_mismatch_stops_even_with_matching_file(self):
        from lpf.search._development_runner import run_prepared_weighted_job
        plan, d, p, x, box, starts = self.prepared(2)
        output = Path(self.raw.name)/'bad-selection'
        def tamper(*args, **kwargs):
            result = run_prepared_weighted_job(*args, **kwargs)
            result['selection']['ranked'][0]['vector'][0] += .01
            (Path(args[6])/'result.json').write_text(canonical(result) + '\n')
            return result
        with patch('lpf.search._development_runner.run_prepared_weighted_job', side_effect=tamper):
            summary = run_weighted_development(plan, d, p, starts, output, root=ROOT)
        self.assertEqual(summary['status'], 'unknown')
        self.assertIn('best/selection/terminal mismatch', summary['exit_reason'])
        self.assertEqual(summary['jobs'][0]['reserved'], 2*70+84+476)

    def test_exact_multiple_and_interruption_preserve_checkpoint(self):
        plan, d, p, x, box, starts = self.prepared(1000)
        for interrupted in (False, True):
            path = Path(self.raw.name)/('interrupt' if interrupted else 'exact')
            worker = DevelopmentWorker(plan, d, p, 'demo', 23, x, vector_sha(x), root=ROOT,
                checkpoint=path, checkpoint_interval=1000, search_bounds=box,
                objective_mode='weighted_violation')
            evaluation = worker.evaluate(x)
            def solver(callback, start, bounds, **kw):
                with patch('lpf.search._worker_next.MinimalWorker._evaluate', return_value=evaluation):
                    for _ in range(1000):
                        residual = callback(x)
                if interrupted:
                    raise RuntimeError('interrupted')
                score = float(np.sum(residual * residual))
                run = LocalRun(x.tolist(), score, x.tolist(), score, False, None, 'budget', 0, 1000)
                return HybridResult([run], x.tolist(), score, 1000, 'evaluation_budget_exhausted',
                                    23, 1000, 1000, .1)
            with patch('lpf.search._worker_next.hybrid_minimize', side_effect=solver):
                if interrupted:
                    with self.assertRaisesRegex(RuntimeError, 'interrupted'):
                        worker.run()
                else:
                    self.assertEqual(worker.run()['status'], 'search_budget_exhausted')
            checkpoints = sorted(path.glob('*.json'))
            self.assertEqual(len(checkpoints), 1)
            self.assertEqual(json.loads(checkpoints[0].read_text())['forward_count'], 1000)

    def test_stop_preserves_unknown_reservation_and_no_retry(self):
        plan, d, p, x, box, starts = self.prepared()
        output = Path(self.raw.name)/'stopped'
        with patch('lpf.search._development_runner.run_prepared_weighted_job', side_effect=RuntimeError('failure')) as run:
            summary = run_weighted_development(plan, d, p, starts, output, root=ROOT)
        self.assertEqual(run.call_count, 1)
        self.assertEqual(summary['status'], 'unknown')
        self.assertEqual([r['status'] for r in summary['jobs']], ['unknown', 'not_started'])
        self.assertEqual(summary['jobs'][0]['reserved'], 3*70+84+476)
        self.assertEqual(summary['campaign']['unknown_cost_upper_bound'], 3*70+84+476)
        self.assertEqual(json.loads((output/'run.json').read_text())['status'], 'unknown')

    def test_sobol_subbox_and_illegal_box(self):
        plan, d, p, x, box, starts = self.prepared()
        box[0] = [x[0]-.01, x[0]+.01]
        point = generate_for_definition(d, p, 23, bounds=box)
        self.assertEqual(point['vector_sha256'], vector_sha(point['vector']))
        self.assertGreaterEqual(point['vector'][0], box[0][0])
        self.assertLessEqual(point['vector'][0], box[0][1])
        bad = [pair[:] for pair in box]
        bad[0][0] = -1.
        with self.assertRaises(ValueError):
            generate_for_definition(d, p, 23, bounds=bad)

    def test_issue441_recommended_box_is_physical_subset(self):
        from lpf.constraint_versions import load_constraint
        from lpf.search.component_constraints import validate_search_box
        from lpf.search.proposals import definition_from_data
        d = definition_from_data(json.loads((ROOT/'project/diagnostics/issue361/definition.json').read_text()))
        p = load_constraint('RF-T008', root=ROOT, allow_trial=True)
        hard = physical_bounds(d, build_rf_model(d, p).schema, p)
        box = json.loads((ROOT/'project/diagnostics/issue441/recommended_box.json').read_text())
        validate_search_box(box, hard)
        self.assertEqual(box[:4], [[.4, 20.]]*4)
        self.assertEqual(box[4:7], [[.1, 5.]]*3)
        self.assertEqual(box[7:], [list(pair) for pair in hard[7:]])

    def test_periodic_checkpoint_even_without_improvement(self):
        plan, d, p, x, box, starts = self.prepared(2001)
        worker = DevelopmentWorker(plan, d, p, 'demo', 23, x, vector_sha(x), root=ROOT,
                                   checkpoint=Path(self.raw.name)/'checkpoints',
                                   checkpoint_interval=1000, search_bounds=box,
                                   objective_mode='weighted_violation')
        worker._activate('demo/' + worker.step['name'])
        evaluation = worker.evaluate(x)
        worker._running = True
        worker.forward_count = worker.saved_count = 0
        worker.saved_sha = worker.best = worker.best_key = worker.solver_best = None
        with patch('lpf.search._worker_next.MinimalWorker._evaluate', return_value=evaluation):
            for _ in range(2001):
                worker._evaluate(x)
        worker._save_best()
        paths = sorted(worker.path.glob('*.json'))
        rows = [json.loads(path.read_text()) for path in paths]
        self.assertEqual([r['forward_count'] for r in rows], [1000, 2000, 2001])
        self.assertEqual(len({r['best']['vector_sha256'] for r in rows}), 1)


if __name__ == '__main__':
    unittest.main()

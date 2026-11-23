"""TRF development integration and fail-closed accounting; no formal EXP."""
import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from lpf.optimizers.least_squares import least_squares_local, to_optimizer_result
from lpf.rf_core.model import RFEvaluator
from lpf.search import _development_runner as runner
from lpf.search.plan import ROOT
from lpf.search.storage import sha


class TRFTests(unittest.TestCase):
    def setUp(self):
        self.cfg = json.loads((ROOT/'project/diagnostics/issue470/config.json').read_text())
        self.starts = json.loads((ROOT/'project/diagnostics/issue470/starts.json').read_text())
        step = self.cfg['arms'][0]['steps'][0]
        step.update(solver='trf', aggregation='sum', options={'max_evaluations': 3})
        self.cfg['budget'] = dict(rf_samples=70*3+476, rf_forwards=4, independent_mna_samples=5)
        self.spots = {'baseline/search': [0], 'terminal': [0, 111]}

    def freeze(self):
        return runner.freeze_run(self.cfg, self.starts, root=ROOT, spot_checks=self.spots,
                                 search_bounds=None, checkpoint_interval=1)

    def test_plan_and_invalid_options(self):
        plan = self.freeze()[0]
        self.assertEqual(plan.sha256, self.freeze()[0].sha256)
        self.assertEqual(plan.sha256, sha(plan.data))
        self.assertEqual(plan.data['jobs'][0]['reservation'], self.cfg['budget'])
        self.assertEqual(plan.data['config']['arms'][0]['steps'][0]['effective_options'], {'max_evaluations': 3})
        step = self.cfg['arms'][0]['steps'][0]
        for update in [dict(aggregation='max'), dict(objective='wrong'),
                       dict(options={'max_evaluations': 3, 'restart_sigma': .1}),
                       dict(options={'max_evaluations': 3, 'batch_fd': True})] + [
                           dict(options={'max_evaluations': n}) for n in (0, -1, True, 1.5, '3')]:
            original = copy.deepcopy(step)
            step.update(update)
            with self.subTest(update=update), self.assertRaises(ValueError): self.freeze()
            step.clear(); step.update(original)

    def test_callback_cache_best_and_classification(self):
        seen = []
        def evaluate(x): return np.array([x[0]-.2]), np.array([[1.]])
        def fake(fun, z0, *, jac, **kwargs):
            from types import SimpleNamespace
            a, b = np.array([.2]), np.array([.8])
            ra = fun(a); jac(a); rb = fun(b); jac(b)
            return SimpleNamespace(x=b, fun=rb, status=0, success=False, message='limit', nfev=7, njev=2, optimality=1.)
        with patch('lpf.optimizers.least_squares.least_squares', side_effect=fake):
            result = least_squares_local(evaluate, [.5], [(0,1)], objective_callback=lambda x, f: seen.append((x, f)))
        self.assertEqual(len(seen), 2)
        self.assertEqual(result.best_objective, seen[0][1])
        selected = to_optimizer_result(result)
        np.testing.assert_array_equal(selected.x, [.2])
        self.assertEqual(selected.stop_reason, 'evaluation_limit')
        self.assertEqual(selected.evaluations, 2)
        self.assertEqual(result.nfev, 7)  # Never infer RF calls from SciPy's counter.
        from dataclasses import replace
        self.assertEqual(to_optimizer_result(replace(result, status=-1)).stop_reason, 'solver_failure')
        fixed = least_squares_local(evaluate, [0.], [(0,0)], objective_callback=lambda x, f: seen.append((x, f)))
        self.assertEqual(to_optimizer_result(fixed).stop_reason, 'all_variables_fixed')
        self.assertTrue(fixed.success)
        with self.assertRaisesRegex(RuntimeError, 'observer'):
            least_squares_local(evaluate, [.5], [(0,1)], objective_callback=lambda x, f: (_ for _ in ()).throw(RuntimeError('observer')))
        with self.assertRaises(ValueError):
            least_squares_local(lambda x: ([float('nan')], [[1]]), [.5], [(0,1)], objective_callback=lambda x, f: self.fail('invalid notification'))
        def invalid(fun, z0, *, jac, **kwargs):
            from types import SimpleNamespace
            fun(z0)
            return SimpleNamespace(x=z0, fun=[float('nan')], status=1, success=True, message='', nfev=1, njev=1)
        with patch('lpf.optimizers.least_squares.least_squares', side_effect=invalid), self.assertRaisesRegex(ValueError, 'Invalid SciPy'):
            least_squares_local(evaluate, [.5], [(0,1)])

    def test_run_and_stop(self):
        with tempfile.TemporaryDirectory(prefix='issue503-test-') as tmp:
            out = Path(tmp)/'run'
            state = runner.run(self.cfg, self.starts, out, root=ROOT, spot_checks=self.spots,
                               checkpoint_interval=1, rf_cache_mode='both')
            row = state['jobs'][0]
            self.assertEqual(row['status'], 'completed')
            result = json.loads((out/'job-0001/result.json').read_text())
            step = result['steps'][0]; details = step['trf_details']
            self.assertEqual(step['rf_cache_mode'], 'off')
            self.assertEqual(step['forward_count'], details['sensitivity_evaluations'])
            self.assertEqual(details['computed_samples'], step['forward_count']*70)
            self.assertEqual(details['requested_samples'], details['computed_samples'])
            self.assertEqual(step['solver_result']['x'], details['best_x'])
            self.assertEqual(step['solver_result']['objective'], details['best_objective'])
            terminal = result['terminal']['candidates'][0]
            self.assertEqual(terminal['vector'], details['best_x'])
            self.assertEqual(set(terminal['response']['grid']['setting']), set(range(6)))
            self.assertEqual(set(terminal['response']['grid']['segment']), set(range(28)))
            self.assertEqual(terminal['independent']['status'], 'pass')
            self.assertEqual(step['independent']['status'], 'pass')
            self.assertEqual(terminal['external_passivity'], 'checked_on_terminal_grid')
            self.assertEqual(terminal['power_balance'], 'checked_on_terminal_grid')
            self.assertEqual(row['actual'], dict(rf_forwards=step['forward_count']+1,
                             rf_samples=step['forward_count']*70+476, independent_mna_samples=step['forward_count']+2))
            for k in row['actual']:
                self.assertEqual(row['actual'][k]+row['released'][k], row['reservation'][k])
            receipt = json.loads((out/'job-0001/receipt.json').read_text())
            for name, info in receipt['files'].items():
                blob = (out/'job-0001'/name).read_bytes()
                self.assertEqual(info['sha256'], hashlib.sha256(blob).hexdigest())
            checkpoints = sorted((out/'job-0001/checkpoints').iterdir())
            self.assertGreaterEqual(len(checkpoints), step['forward_count'])
            last = json.loads(checkpoints[-1].read_text())['observation']
            self.assertEqual(last['vector'], details['best_x'])
            self.assertEqual(last['objective'], details['best_objective'])
            failout = Path(tmp)/'fail'
            with patch.object(RFEvaluator, 'evaluate_with_il_jacobian', side_effect=ValueError('injected')) as call:
                with self.assertRaisesRegex(ValueError, 'injected'):
                    runner.run(self.cfg, self.starts, failout, root=ROOT, spot_checks=self.spots, checkpoint_interval=1)
                self.assertEqual(call.call_count, 1)
            self.assertEqual(json.loads((failout/'run.json').read_text())['jobs'][0]['status'], 'unknown')
            self.assertFalse((failout/'job-0001/receipt.json').exists())
            self.assertFalse(json.loads((failout/'job-0001/failure.json').read_text())['retry_allowed'])

    def test_new_options_reach_scipy_and_terminal(self):
        self.cfg['arms'][0]['steps'][0]['options'].update(ftol=None, x_scale='jac')
        self.assertEqual(self.freeze()[0].data['config']['arms'][0]['steps'][0]['effective_options'],
                         {'max_evaluations': 3, 'ftol': None, 'x_scale': 'jac'})
        with tempfile.TemporaryDirectory(prefix='issue507-run-') as tmp:
            out = Path(tmp)/'run'
            runner.run(self.cfg, self.starts, out, root=ROOT, spot_checks=self.spots, checkpoint_interval=1)
            result = json.loads((out/'job-0001/result.json').read_text())
            step = result['steps'][0]
            self.assertIsNotNone(step['trf_details']['optimality'])
            self.assertEqual(step['solver_options']['x_scale'], 'jac')
            self.assertIsNone(step['solver_options']['ftol'])
            self.assertEqual(result['terminal']['candidates'][0]['vector'], step['trf_details']['best_x'])
            self.assertEqual(result['terminal']['candidates'][0]['independent']['status'], 'pass')

    def test_budget_stops_before_extra_rf_and_invalid_counts_stop(self):
        self.cfg['arms'][0]['steps'][0]['options']['max_evaluations'] = 1
        with tempfile.TemporaryDirectory(prefix='issue503-budget-') as tmp:
            def overrun(callback, x, bounds, **kwargs):
                callback(x)
                callback(x)
            actual = RFEvaluator.evaluate_with_il_jacobian
            calls = []
            def count(evaluator, vector):
                calls.append(vector)
                return actual(evaluator, vector)
            with patch('lpf.search._development_worker.least_squares_local', side_effect=overrun), \
                 patch.object(RFEvaluator, 'evaluate_with_il_jacobian', count):
                out = Path(tmp)/'overrun'
                with self.assertRaisesRegex(ValueError, 'budget exhausted'):
                    runner.run(self.cfg, self.starts, out, root=ROOT, spot_checks=self.spots, checkpoint_interval=1)
            self.assertEqual(len(calls), 1)
            self.assertEqual(json.loads((out/'run.json').read_text())['jobs'][0]['status'], 'unknown')
            from dataclasses import replace
            def wrong_counts(*args, **kwargs):
                return replace(least_squares_local(*args, **kwargs), computed_samples=0)
            with patch('lpf.search._development_worker.least_squares_local', side_effect=wrong_counts):
                out = Path(tmp)/'badcounts'
                with self.assertRaisesRegex(ValueError, 'accounting mismatch'):
                    runner.run(self.cfg, self.starts, out, root=ROOT, spot_checks=self.spots, checkpoint_interval=1)
            self.assertFalse((out/'job-0001/receipt.json').exists())

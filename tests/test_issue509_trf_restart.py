"""Opt-in TRF restart accounting and previous-terminal perturbation."""
import json
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from test_issue503_trf_runner import TRFTests
from lpf.optimizers.least_squares import least_squares_local
from lpf.search import _development_runner as runner
from lpf.search.plan import ROOT


class RestartTests(TRFTests):
    def test_restarts_follow_last_final_not_best(self):
        step = self.cfg['arms'][0]['steps'][0]
        step['options']['restart_sigma'] = .1
        calls = []
        def fake(callback, x, bounds, **kwargs):
            calls.append((np.array(x).copy(), kwargs['max_evaluations']))
            result = least_squares_local(callback, x, bounds, **{**kwargs, 'max_evaluations': 1})
            # First local endpoint is deliberately distinct from its observed best.
            final = np.array(bounds, dtype=float)[:, 1] if len(calls) == 1 else result.x
            return replace(result, x=final, success=len(calls) == 1, status=1 if len(calls) == 1 else 0)
        with tempfile.TemporaryDirectory(prefix='issue509-test-') as tmp:
            with patch('lpf.search._development_worker.least_squares_local', side_effect=fake):
                out = Path(tmp)/'run'
                runner.run(self.cfg, self.starts, out, root=ROOT, spot_checks=self.spots, checkpoint_interval=1)
            result = json.loads((out/'job-0001/result.json').read_text())
        row = result['steps'][0]
        bounds = np.asarray(result['search_bounds'])
        lo, width = bounds[:, 0], bounds[:, 1]-bounds[:, 0]
        free = width > 0
        expected = lo.copy()
        expected[free] = np.clip(lo[free] + np.clip(1 + np.random.default_rng(result['seed']).normal(0, .1, free.sum()), 0, 1)*width[free], lo[free], bounds[free, 1])
        np.testing.assert_array_equal(calls[1][0], expected)
        self.assertEqual([x[1] for x in calls], [3, 2])
        self.assertEqual(row['local_runs'], 2)
        self.assertEqual(row['restart_count'], 1)
        self.assertEqual(row['forward_count'], 2)
        self.assertEqual(sum(r['sensitivity_evaluations'] for r in row['local_run_details']), 2)
        self.assertEqual(row['stop_reason'], 'evaluation_limit')
        self.assertFalse(row['converged'])
        self.assertEqual(row['solver_result']['objective'], min(r['best_objective'] for r in row['local_run_details']))
        self.assertEqual(result['terminal']['candidates'][0]['vector'], row['solver_result']['x'])

    def test_invalid_sigma(self):
        options = self.cfg['arms'][0]['steps'][0]['options']
        for value in (0, -1, True, '0.1', float('nan'), float('inf')):
            options['restart_sigma'] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.freeze()

    def test_budget_exhaustion_and_fail_closed(self):
        self.cfg['arms'][0]['steps'][0]['options']['restart_sigma'] = .1
        def single(callback, x, bounds, **kwargs):
            result = least_squares_local(callback, x, bounds, **{**kwargs, 'max_evaluations': 1})
            return replace(result, success=True, status=1)
        with tempfile.TemporaryDirectory(prefix='issue509-budget-') as tmp:
            with patch('lpf.search._development_worker.least_squares_local', side_effect=single):
                out = Path(tmp)/'run'
                runner.run(self.cfg, self.starts, out, root=ROOT, spot_checks=self.spots, checkpoint_interval=1)
            row = json.loads((out/'job-0001/result.json').read_text())['steps'][0]
            self.assertEqual((row['forward_count'], row['local_runs'], row['restart_count']), (3, 3, 2))
            self.assertEqual(row['stop_reason'], 'evaluation_budget_exhausted')
            self.assertFalse(row['converged'])
            with patch('lpf.search._development_worker.least_squares_local', side_effect=RuntimeError('STOP')) as solver:
                with self.assertRaisesRegex(RuntimeError, 'STOP'):
                    runner.run(self.cfg, self.starts, Path(tmp)/'failed', root=ROOT, spot_checks=self.spots, checkpoint_interval=1)
                self.assertEqual(solver.call_count, 1)

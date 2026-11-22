"""Hybrid workers use SciPy's own probes, with group-based accounting."""
import unittest
import sys
import json
import tempfile
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from lpf.optimizers.hybrid import hybrid_minimize


class BatchFDTest(unittest.TestCase):
    def run_mode(self, batch, limit=200, aggregation='sum'):
        observations, batches, runs = [], [], []

        def residual(x):
            return np.array([x[0] - .25, x[1] - .4, .1])

        def residual_batch(xs):
            batches.append([x.copy() for x in xs])
            return [residual(x) for x in xs]

        out = hybrid_minimize(residual, [.8, .7], [(0, 1), (0, 1)], seed=3,
                              max_evaluations=limit, restart_sigma=.1, batch_fd=batch,
                              residuals_batch=residual_batch, aggregation=aggregation,
                              objective_callback=lambda x, f: observations.append((x.copy(), f)),
                              local_run_callback=runs.append)
        return out, observations, batches, runs

    def test_path_and_group_budget(self):
        for aggregation in ('sum', 'max'):
            a, ao, _, ar = self.run_mode(False, 90, aggregation)
            b, bo, batches, br = self.run_mode(True, 90, aggregation)
            self.assertTrue(any(len(x) == 2 for x in batches))
            common = min(len(ao), len(bo))
            np.testing.assert_allclose([x for x, _ in ao[:common]], [x for x, _ in bo[:common]], atol=1e-12)
            np.testing.assert_allclose([f for _, f in ao[:common]], [f for _, f in bo[:common]], atol=1e-12)
            self.assertEqual(a.evaluations, 90)
            self.assertGreaterEqual(b.evaluations, 90)
            self.assertLessEqual(b.evaluations, 91)
            self.assertEqual(sum(r.nfev for r in br), b.evaluations)
            self.assertEqual(sum(r.nfev for r in ar), a.evaluations)

    def test_partial_remaining_and_fixed(self):
        out, obs, batches, _ = self.run_mode(True, 2)
        self.assertEqual(out.evaluations, 3)
        self.assertEqual(len(obs), 3)
        self.assertEqual(len(batches[0]), 2)
        seen = []
        out = hybrid_minimize(lambda x: [1.], [.5] * 25, [(0, 1)] * 25, seed=0,
                              max_evaluations=11, restart_sigma=.1, batch_fd=True,
                              residuals_batch=lambda xs: (seen.append(len(xs)) or [[1.]] * len(xs)))
        self.assertEqual(seen, [25])
        self.assertEqual(out.evaluations, 26)
        out = hybrid_minimize(lambda x: [1], [1], [(1, 1)], seed=0,
                              max_evaluations=1, restart_sigma=.1, batch_fd=True,
                              residuals_batch=lambda xs: self.fail('fixed must not batch'))
        self.assertEqual(out.evaluations, 1)
        self.assertEqual(out.stop_reason, 'all_coordinates_fixed')

    def test_deep_objective_regions_and_callback_failure(self):
        from lpf.timing import TimerCollector
        timer = TimerCollector()
        out = hybrid_minimize(lambda x: [1.], [.5, .5], [(0, 1)] * 2, seed=0,
                              max_evaluations=2, restart_sigma=.1, batch_fd=True,
                              residuals_batch=lambda xs: [[1.]] * len(xs), _timing=(timer, 's'))
        regions = timer.snapshot()
        self.assertEqual(regions['s/batch/vectors']['count'], 1)
        for name in ('s/objective/value', 's/objective/state'):
            self.assertEqual(regions[name]['count'], out.evaluations)
            self.assertEqual(regions[name]['failed'], 0)
        timer = TimerCollector()
        def fail(*args):
            raise RuntimeError('checkpoint failed')
        with self.assertRaisesRegex(RuntimeError, 'checkpoint failed'):
            hybrid_minimize(lambda x: [1.], [.5], [(0, 1)], seed=0,
                            max_evaluations=2, restart_sigma=.1, group_callback=fail,
                            _timing=(timer, 's'))
        self.assertEqual(timer.snapshot()['s/objective/state']['failed'], 1)
        self.assertEqual(timer.snapshot()['s/objective/group_callback']['failed'], 1)
        timer = TimerCollector()
        out = hybrid_minimize(lambda x: [float('nan')], [.5], [(0, 1)], seed=0,
                              max_evaluations=2, restart_sigma=.1, _timing=(timer, 's'))
        self.assertEqual(out.stop_reason, 'invalid_residual')
        self.assertEqual(timer.snapshot()['s/objective/value']['failed'], 1)
        self.assertNotIn('s/objective/state', timer.snapshot())

    def test_failure_preserves_prior_observations(self):
        observed = []
        def batch(xs):
            return iter(([.5], ValueError('injected')))
        with self.assertRaisesRegex(ValueError, 'injected'):
            hybrid_minimize(lambda x: [1], [.5, .5], [(0, 1)] * 2, seed=0,
                            max_evaluations=10, restart_sigma=.1, batch_fd=True,
                            residuals_batch=batch,
                            objective_callback=lambda x, f: observed.append((x, f)))
        self.assertEqual(len(observed), 2)


class RFWorkerBatchTest(unittest.TestCase):
    def test_reservation_receipt_and_checkpoint_boundaries(self):
        from lpf.search.development_plan import freeze_run
        from lpf.search import _development_runner as runner
        from lpf.rf_core.model import RFEvaluator
        from unittest.mock import patch

        root = Path(__file__).resolve().parents[1]
        config = json.loads((root/'project/diagnostics/issue470/config.json').read_text())
        starts = json.loads((root/'project/diagnostics/issue470/starts.json').read_text())
        step = config['arms'][0]['steps'][0]
        step['options'].update(batch_fd=True, partial_fd=False, max_search_forwards=2)
        # 25 free coordinates: reserve 2 + 24 Search and one Terminal.
        config['budget'] = dict(rf_samples=70*26 + 476, rf_forwards=27, independent_mna_samples=2)
        args = dict(root=root, spot_checks={'terminal': [0, 57]}, search_bounds=None,
                    checkpoint_interval=1)
        compiled = freeze_run(config, starts, **args)
        self.assertEqual(compiled[0].data['jobs'][0]['reservation']['rf_forwards'], 27)
        config['budget']['rf_forwards'] = 26
        with self.assertRaisesRegex(ValueError, 'reserve'):
            freeze_run(config, starts, **args)
        config['budget']['rf_forwards'] = 27
        calls = []
        original = RFEvaluator.evaluate_batch
        def wrapped(evaluator, xs):
            calls.append(len(xs))
            return original(evaluator, xs)
        with tempfile.TemporaryDirectory(prefix='issue482-test-') as tmp, patch.object(RFEvaluator, 'evaluate_batch', wrapped):
            for mode in ('lk', 'response', 'both'):
                output = Path(tmp)/mode
                runner.run(config, starts, output, rf_cache_mode=mode, **args)
                result = json.loads((output/'job-0001/result.json').read_text())
                self.assertEqual(calls.pop(), 25)
                self.assertEqual(result['costs']['search_forwards'], 26)
                self.assertEqual(result['ledger']['rf_forwards']['completed'], 27)
                checkpoints = sorted((json.loads(p.read_text()) for p in (output/'job-0001/checkpoints').glob('*.json')),
                                     key=lambda c: c['sequence'])
                self.assertTrue(all(c['forward_count'] in (1, 26) for c in checkpoints))
                self.assertEqual(checkpoints[-1]['observation']['vector_sha256'], result['terminal']['candidates'][0]['vector_sha256'])

    def test_consume_clock_stops_before_yield(self):
        from lpf.search import _development_runner as runner, _development_worker as worker
        from unittest.mock import patch
        root = Path(__file__).resolve().parents[1]
        cfg = json.loads((root/'project/diagnostics/issue470/config.json').read_text())
        starts = json.loads((root/'project/diagnostics/issue470/starts.json').read_text())
        cfg['arms'][0]['steps'][0]['options'].update(batch_fd=True, partial_fd=False, max_search_forwards=2)
        clock = [0]
        def tick():
            clock[0] += 1
            return clock[0]
        original = worker.hybrid_minimize
        def instrument(*args, **kwargs):
            progress = kwargs['progress_callback']
            def pause(*args):
                clock[0] += 1_000_000  # time spent outside consume, including generator suspension
                return progress(*args)
            kwargs['progress_callback'] = pause
            return original(*args, **kwargs)
        with tempfile.TemporaryDirectory(prefix='issue491-clock-') as tmp, \
             patch.object(worker, 'perf_counter_ns', tick), \
             patch.object(worker, 'hybrid_minimize', instrument):
            base = Path(tmp)
            runner.run(cfg, starts, base/'run', root=root, spot_checks={'terminal': [0, 111]},
                       checkpoint_interval=1, timing_output=base/'timing.json', timing_level='deep')
            regions = json.loads((base/'timing.json').read_text())['jobs'][0]['regions']
            row = regions['baseline/search/batch/consume']
            self.assertEqual((row['count'], row['wall_ns'], row['failed']), (25, 25, 0))
            self.assertGreater(regions['baseline/search/checkpoint']['count'], 0)

    def test_rf_failure_replay_and_checkpoint(self):
        from lpf.search.development_plan import freeze_run
        from lpf.search._development_worker import DevelopmentWorker
        from lpf.search.source import source_identity
        from lpf.rf_core.model import RFEvaluator
        from lpf.rf_core.numerical_diagnostics import CircuitNumericalError
        from lpf.timing import TimerCollector
        from unittest.mock import patch

        root = Path(__file__).resolve().parents[1]
        cfg = json.loads((root/'project/diagnostics/issue470/config.json').read_text())
        starts = json.loads((root/'project/diagnostics/issue470/starts.json').read_text())
        cfg['arms'][0]['steps'][0]['options'].update(batch_fd=True, partial_fd=False, max_search_forwards=2)
        compiled = freeze_run(cfg, starts, root=root, spot_checks={'terminal': [0, 111]},
                              search_bounds=None, checkpoint_interval=1000)
        original = RFEvaluator.evaluate
        count = 0
        def scalar(ev, x, **kwargs):
            nonlocal count
            count += 1
            if count == 3:
                raise CircuitNumericalError('injected', 'probe failure', sample_index=7)
            return original(ev, x, **kwargs)
        with tempfile.TemporaryDirectory(prefix='issue482-stop-') as tmp:
            timer = TimerCollector()
            worker = DevelopmentWorker(compiled, 0, source_identity(root), root=root,
                                       checkpoint=Path(tmp)/'checkpoints', timer=timer, timing_level='deep')
            with patch.object(RFEvaluator, 'evaluate_batch', side_effect=ValueError('batch failure')), \
                 patch.object(RFEvaluator, 'evaluate', scalar):
                with self.assertRaises(CircuitNumericalError) as error:
                    worker.run()
            self.assertEqual(error.exception.sample_index, 7)
            self.assertEqual(worker.forward_count, 3)
            regions = timer.snapshot()
            self.assertEqual(regions['baseline/search/batch/vectors']['count'], 1)
            self.assertNotIn('baseline/search/batch/consume', regions)  # scalar replay
            self.assertEqual(regions['baseline/search/objective/value']['count'], 2)
            files = list((Path(tmp)/'checkpoints').glob('*.json'))
            self.assertEqual(len(files), 1)
            checkpoint = json.loads(files[0].read_text())
            self.assertEqual(checkpoint['forward_count'], 3)
            self.assertTrue(np.isfinite(checkpoint['observation']['objective']))


if __name__ == '__main__':
    unittest.main()

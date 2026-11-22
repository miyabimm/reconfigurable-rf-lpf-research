"""Partial RF probes preserve full-grid semantics and transactional replay."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

from test_issue307_constraints import make
from test_issue309_rf_core import grid
from lpf.rf_core.model import EvaluationGrid, RFEvaluator
from lpf.rf_core.numerical_diagnostics import CircuitNumericalError
from lpf.search.plan import validate_solver


class PartialBatchTest(unittest.TestCase):
    def setUp(self):
        policy, _, self.model, self.bounds, self.x = make('RF-T008')
        self.grid = grid(policy)

    def test_mixed_candidates_and_missing_interleaved_settings(self):
        # Arbitrary, non-contiguous rows, with settings deliberately omitted.
        idx = np.flatnonzero(np.isin(self.grid.setting, [0, 2, 4]))[::-1]
        g = EvaluationGrid(self.grid.frequency_hz[idx], self.grid.setting[idx], self.grid.segment[idx])
        schema = self.model.schema
        start = schema.vector_length - 6 * schema.n_variable
        xs = np.tile(self.x, (9, 1))
        for i in range(6):
            xs[i, start + i * schema.n_variable] += .001
        xs[6, 0] += .001
        xs[7, schema.n_inductors] += .001
        xs[8, start] += .001; xs[8, start + schema.n_variable] += .001
        mask = np.ones((len(xs), len(g.setting)), bool)
        for i in range(6): mask[i] = g.setting == i
        for mode in ('off', 'lk', 'response', 'both'):
            with self.subTest(mode=mode):
                ev = self.model.evaluator(g, cache_mode=mode)
                base = ev.evaluate(self.x)
                before = ev.cache_stats['computed_samples']
                actual = ev.evaluate_partial_batch(xs, base, mask)
                expected = self.model.evaluator(g).evaluate_batch(xs)
                for a, b in zip(actual, expected):
                    for key in ('s', 'il_db', 'apl_db', 'in_rl_db', 'out_rl_db'):
                        np.testing.assert_array_equal(getattr(a, key), getattr(b, key))
                        self.assertFalse(getattr(a, key).flags.writeable)
                if mode in ('off', 'lk'):
                    self.assertEqual(ev.cache_stats['computed_samples'] - before, mask.sum())

    def test_empty_selection_and_response_delegation(self):
        ev = self.model.evaluator(self.grid, cache_mode='lk')
        base = ev.evaluate(self.x)
        before = ev.cache_stats['computed_samples']
        result = ev.evaluate_partial_batch([self.x], base, np.zeros((1, len(self.grid.setting)), bool))
        self.assertEqual(ev.cache_stats['computed_samples'], before)
        np.testing.assert_array_equal(result[0].s, base.s)
        for mode in ('response', 'both'):
            ev = self.model.evaluator(self.grid, cache_mode=mode)
            base = ev.evaluate(self.x)
            with patch.object(RFEvaluator, 'evaluate_batch', autospec=True, wraps=RFEvaluator.evaluate_batch) as delegated:
                ev.evaluate_partial_batch([self.x], base, np.zeros((1, len(self.grid.setting)), bool))
                self.assertEqual(delegated.call_count, 1)

    def test_failure_replay_and_no_speculative_lru(self):
        ev = self.model.evaluator(self.grid, cache_mode='lk')
        base = ev.evaluate(self.x)
        bad = self.x.copy(); bad[self.model.schema.n_inductors + self.model.schema.n_fixed] = 2
        nan = self.x.copy(); nan[0] = np.nan
        before = list(ev._lk_cache)
        with self.assertRaises(CircuitNumericalError) as err:
            ev.evaluate_partial_batch([bad, nan], base, np.ones((2, len(self.grid.setting)), bool))
        self.assertEqual(err.exception.code, 'mutual_not_spd')
        self.assertEqual(list(ev._lk_cache), before)
        from lpf.rf_core.coupled_lc import CoupledLCTopology
        def fail(*args, **kwargs):
            raise CircuitNumericalError('node_nonfinite', 'injected', sample_index=3)
        with patch.object(RFEvaluator, '_compute_batch', side_effect=ValueError('injected')), \
             patch.object(CoupledLCTopology, 'port_admittance', fail):
            with self.assertRaises(CircuitNumericalError) as err:
                ev.evaluate_partial_batch([self.x], base, np.zeros((1, len(self.grid.setting)), bool))
        self.assertEqual((err.exception.code, err.exception.sample_index), ('node_nonfinite', 3))
        self.assertEqual(list(ev._lk_cache), before)

    def test_late_failure_stages_lru_until_replay(self):
        from lpf.rf_core import model as rf_model
        from lpf.rf_core.coupled_lc import CoupledLCTopology
        ev = self.model.evaluator(self.grid, cache_mode='lk')
        base = ev.evaluate(self.x)
        changed = self.x.copy(); changed[0] += .01
        before = list(ev._lk_cache)
        computed_before = ev.cache_stats['computed_samples']
        cascade = rf_model._cascade
        calls = 0
        def injected(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise ValueError('late speculative failure')
            return cascade(*args, **kwargs)
        def scalar_fail(*args, **kwargs):
            raise CircuitNumericalError('node_nonfinite', 'replay', sample_index=7)
        with patch.object(rf_model, '_cascade', side_effect=injected), \
             patch.object(CoupledLCTopology, 'port_admittance', side_effect=scalar_fail):
            with self.assertRaises(CircuitNumericalError) as err:
                ev.evaluate_partial_batch([changed], base, np.ones((1, len(self.grid.setting)), bool))
        self.assertEqual((err.exception.code, err.exception.sample_index), ('node_nonfinite', 7))
        self.assertEqual(list(ev._lk_cache), before)
        # Both the speculative selected samples and full scalar replay count.
        self.assertEqual(ev.cache_stats['computed_samples'] - computed_before, 2 * len(self.grid.setting))

    def test_options(self):
        from lpf.search.development_plan import solver_options
        step = dict(solver='hybrid', aggregation='sum', options=dict(max_search_forwards=2))
        validate_solver(step)
        self.assertEqual((solver_options(step)['batch_fd'], solver_options(step)['partial_fd']), (True, True))
        step['options']['partial_fd'] = True
        validate_solver(step)  # batch_fd defaults to True
        for value in (1, 'true'):
            step['options']['partial_fd'] = value
            with self.assertRaises(ValueError): validate_solver(step)
        step['options'].update(batch_fd=False, partial_fd=True)
        with self.assertRaises(ValueError): validate_solver(step)
        step['options']['partial_fd'] = False
        validate_solver(step)
        self.assertEqual((solver_options(step)['batch_fd'], solver_options(step)['partial_fd']), (False, False))
        step['options'].pop('partial_fd')
        self.assertFalse(solver_options(step)['partial_fd'])
        step['options']['batch_fd'] = True
        step['options']['partial_fd'] = False
        validate_solver(step)
        self.assertEqual((solver_options(step)['batch_fd'], solver_options(step)['partial_fd']), (True, False))

    def test_default_plan_reserves_batch_group(self):
        from lpf.search.development_plan import freeze_run
        root = Path(__file__).resolve().parents[1]
        config = json.loads((root/'project/diagnostics/issue470/config.json').read_text())
        starts = json.loads((root/'project/diagnostics/issue470/starts.json').read_text())
        options = config['arms'][0]['steps'][0]['options']
        args = dict(root=root, spot_checks={'terminal': [0, 111]},
                    search_bounds=None, checkpoint_interval=1000)
        # The old exact 1000-forward reservation is insufficient for default batched FD.
        with self.assertRaisesRegex(ValueError, 'reserve'):
            freeze_run(config, starts, **args)
        config['budget'] = dict(rf_samples=70*1024+476, rf_forwards=1025, independent_mna_samples=2)
        plan = freeze_run(config, starts, **args)[0].data
        step = plan['config']['arms'][0]['steps'][0]
        self.assertEqual((step['effective_options']['batch_fd'], step['effective_options']['partial_fd']),
                         (True, True))
        self.assertEqual(step['batch_forward_cap'], 1024)
        self.assertEqual(plan['jobs'][0]['reservation']['rf_forwards'], 1025)
        # Explicit opt-out keeps the historical scalar reservation.
        options['batch_fd'] = False
        config['budget'] = dict(rf_samples=70*1000+476, rf_forwards=1001, independent_mna_samples=2)
        scalar = freeze_run(config, starts, **args)[0].data
        scalar_opts = scalar['config']['arms'][0]['steps'][0]['effective_options']
        self.assertEqual((scalar_opts['batch_fd'], scalar_opts['partial_fd']), (False, False))
        self.assertNotIn('batch_forward_cap', scalar['config']['arms'][0]['steps'][0])

    def test_real_runner_probes_and_receipt(self):
        from lpf.search import _development_runner as runner
        root = Path(__file__).resolve().parents[1]
        config = json.loads((root/'project/diagnostics/issue470/config.json').read_text())
        starts = json.loads((root/'project/diagnostics/issue470/starts.json').read_text())
        config['arms'][0]['steps'][0]['options'].update(batch_fd=True, partial_fd=True, max_search_forwards=2)
        config['budget'] = dict(rf_samples=70*26 + 476, rf_forwards=27, independent_mna_samples=2)
        args = dict(root=root, spot_checks={'terminal': [0, 57]}, search_bounds=None, checkpoint_interval=1)
        seen = []
        original = RFEvaluator.evaluate_partial_batch
        def capture(ev, xs, base, mask):
            result = original(ev, xs, base, mask)
            expected = ev.model.evaluator(ev.grid).evaluate_batch(xs)
            for a, b in zip(result, expected):
                for name in ('s', 'il_db', 'apl_db', 'in_rl_db', 'out_rl_db'):
                    np.testing.assert_array_equal(getattr(a, name), getattr(b, name))
            seen.append((np.asarray(mask).sum(), len(xs), np.asarray(mask).sum(axis=1).tolist()))
            return result
        with tempfile.TemporaryDirectory(prefix='issue484-test-') as tmp, patch.object(RFEvaluator, 'evaluate_partial_batch', capture):
            output = Path(tmp)/'run'
            runner.run(config, starts, output, rf_cache_mode='lk', **args)
            result = json.loads((output/'job-0001/result.json').read_text())
            self.assertEqual(result['costs']['search_forwards'], 26)
            self.assertEqual(result['ledger']['rf_forwards']['completed'], 27)
            self.assertEqual(result['terminal']['status'], 'completed')
        self.assertEqual(seen[0][:2], (1050, 25))
        self.assertEqual(sum(n < 70 for n in seen[0][2]), 12)

    def test_worker_failure_replay_preserves_checkpoint_and_charge(self):
        from lpf.search.development_plan import freeze_run
        from lpf.search._development_worker import DevelopmentWorker
        from lpf.search.source import source_identity
        root = Path(__file__).resolve().parents[1]
        config = json.loads((root/'project/diagnostics/issue470/config.json').read_text())
        starts = json.loads((root/'project/diagnostics/issue470/starts.json').read_text())
        config['arms'][0]['steps'][0]['options'].update(batch_fd=True, partial_fd=True, max_search_forwards=2)
        compiled = freeze_run(config, starts, root=root, spot_checks={'terminal': [0, 111]},
                              search_bounds=None, checkpoint_interval=1000)
        original = RFEvaluator.evaluate
        count = 0
        def scalar(ev, x, **kwargs):
            nonlocal count
            count += 1
            if count == 3:
                raise CircuitNumericalError('injected', 'probe failure', sample_index=7)
            return original(ev, x, **kwargs)
        with tempfile.TemporaryDirectory(prefix='issue484-stop-') as tmp:
            w = DevelopmentWorker(compiled, 0, source_identity(root), root=root, checkpoint=Path(tmp)/'checkpoints')
            with patch.object(RFEvaluator, 'evaluate_partial_batch', side_effect=ValueError('batch failure')), \
                 patch.object(RFEvaluator, 'evaluate', scalar):
                with self.assertRaises(CircuitNumericalError) as err:
                    w.run()
            self.assertEqual((err.exception.code, err.exception.sample_index), ('injected', 7))
            self.assertEqual(w.forward_count, 3)
            files = list((Path(tmp)/'checkpoints').glob('*.json'))
            self.assertEqual(len(files), 1)
            self.assertEqual(json.loads(files[0].read_text())['forward_count'], 3)

    def test_runner_trajectory_and_accounting(self):
        from lpf.search import _development_runner as runner, _development_worker as worker_module
        root = Path(__file__).resolve().parents[1]
        config = json.loads((root/'project/diagnostics/issue470/config.json').read_text())
        starts = json.loads((root/'project/diagnostics/issue470/starts.json').read_text())
        config['budget'] = dict(rf_samples=70*104+476, rf_forwards=105, independent_mna_samples=2)
        args = dict(root=root, spot_checks={'terminal': [0, 57]}, search_bounds=None, checkpoint_interval=1)
        original = worker_module.hybrid_minimize
        traces, results, checkpoints = [], [], []
        with tempfile.TemporaryDirectory(prefix='issue484-path-') as tmp:
            for partial in (False, True):
                config['arms'][0]['steps'][0]['options'].update(batch_fd=True, partial_fd=partial, max_search_forwards=80)
                seen = []
                def capture(*a, **kw):
                    progress = kw['progress_callback']
                    def observe(x, f, improved):
                        seen.append((x.tolist(), f, improved))
                        progress(x, f, improved)
                    kw['progress_callback'] = observe
                    return original(*a, **kw)
                output = Path(tmp)/str(partial)
                with patch.object(worker_module, 'hybrid_minimize', capture):
                    runner.run(config, starts, output, rf_cache_mode='lk', **args)
                traces.append(seen)
                results.append(json.loads((output/'job-0001/result.json').read_text()))
                checkpoints.append([(c['forward_count'], c['observation']) for c in
                    (json.loads(p.read_text()) for p in sorted((output/'job-0001/checkpoints').glob('*.json')))])
        self.assertEqual(traces[0], traces[1])
        self.assertGreater(len(traces[0]), 26)
        self.assertEqual(checkpoints[0], checkpoints[1])
        for key in ('costs', 'ledger', 'terminal'):
            self.assertEqual(results[0][key], results[1][key])
        for key in ('solver_result', 'local_run_details', 'forward_count', 'requested_samples'):
            self.assertEqual(results[0]['steps'][0][key], results[1]['steps'][0][key])


if __name__ == '__main__': unittest.main()

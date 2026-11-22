"""Batch deep timing is opt-in, transactional, and restores hooks on failure."""
import unittest
from unittest.mock import patch

import numpy as np

from test_issue307_constraints import make
from test_issue309_rf_core import grid
from lpf.rf_core import model, coupled_lc
from lpf.search._rf_deep_timing import search_rf_timing
from lpf.timing import TimerCollector


class BatchTimingTests(unittest.TestCase):
    def setUp(self):
        policy, _, self.model, _, self.x = make('RF-T008')
        self.grid = grid(policy)

    def test_partial_batch_and_nested_scalar_delegation(self):
        for mode in ('lk', 'response'):
            with self.subTest(mode=mode):
                ev = self.model.evaluator(self.grid, cache_mode=mode)
                base = ev.evaluate(self.x)
                mask = np.ones((2, len(self.grid.setting)), dtype=bool)
                expected = ev.evaluate_partial_batch([self.x, self.x], base, mask)
                timer = TimerCollector()
                with search_rf_timing(timer, 'search'):
                    actual = ev.evaluate_partial_batch([self.x, self.x], base, mask)
                for a, b in zip(actual, expected):
                    for name in ('s', 'il_db', 'apl_db', 'in_rl_db', 'out_rl_db'):
                        np.testing.assert_array_equal(getattr(a, name), getattr(b, name))
                rows = timer.snapshot()
                if mode == 'lk':
                    for name in ('decode_lk', 'select', 'stamp', 'schur_solve', 'schur_update', 'y_to_s', 'output'):
                        self.assertEqual(rows['search/rf/batch/' + name]['count'], 1)
                        self.assertEqual(rows['search/rf/batch/' + name]['failed'], 0)
                    self.assertEqual(rows['search/rf/batch']['count'], 1)
                    self.assertEqual(rows['search/rf/batch/decode']['count'], 1)
                    self.assertNotIn('search/rf/batch/matrices', rows)  # warm L/k cache
                    self.assertEqual(rows['search/rf/cascade']['count'], 2)
                    self.assertEqual(rows['search/rf/power_response']['count'], 1)
                    self.assertNotIn('search/rf/decode', rows)
                    self.assertNotIn('search/rf/matrices', rows)
                    self.assertFalse(any('/rf/matrices/' in key for key in rows))
                else:
                    # Partial -> batch -> scalar delegation must not multiply counts.
                    self.assertEqual(rows['search/rf/decode']['count'], 2)
                    self.assertFalse(any('/batch/' in key for key in rows))
                self.assertIsNone(model._deep_timing)
                self.assertIsNone(coupled_lc._deep_timing)

    def test_batch_misses_and_scalar_matrices_are_separate(self):
        ev = self.model.evaluator(self.grid, cache_mode='lk')
        changed = self.x.copy(); changed[0] += .01
        timer = TimerCollector()
        with search_rf_timing(timer, 'search'):
            ev.evaluate(self.x)  # scalar cache miss
            ev.evaluate_batch([self.x, changed, changed])  # hit, miss, staged hit
            ev.evaluate_batch([changed, self.x])  # two hits
        rows = timer.snapshot()
        self.assertEqual(rows['search/rf/matrices']['count'], 1)
        self.assertEqual(rows['search/rf/batch/matrices']['count'], 1)
        self.assertEqual(rows['search/rf/batch/decode']['count'], 2)
        self.assertEqual(ev.cache_stats['lk_misses'], 2)
        self.assertEqual(ev.cache_stats['lk_hits'], 4)
        self.assertGreaterEqual(rows['search/rf/batch/decode_lk']['wall_ns'],
                                rows['search/rf/batch/decode']['wall_ns'] +
                                rows['search/rf/batch/matrices']['wall_ns'])
        self.assertFalse(any('/rf/batch/matrices/' in key for key in rows))
        self.assertEqual(rows['search/rf/batch/matrices']['failed'], 0)

    def test_handled_batch_failure_replays_scalar_without_double_counts(self):
        ev = self.model.evaluator(self.grid, cache_mode='lk')
        ev.evaluate(self.x)  # first batch solve is Schur, then replay uses cache
        timer = TimerCollector()
        original_solve = np.linalg.solve
        calls = 0
        def fail_once(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise np.linalg.LinAlgError('injected')
            return original_solve(*args, **kwargs)
        with search_rf_timing(timer, 'search'):
            with patch.object(np.linalg, 'solve', side_effect=fail_once):
                actual = ev.evaluate_batch([self.x, self.x])
        self.assertEqual(len(actual), 2)
        rows = timer.snapshot()
        self.assertEqual(rows['search/rf/batch']['failed'], 1)
        self.assertEqual(rows['search/rf/batch/schur_solve']['failed'], 1)
        self.assertEqual(rows['search/rf/batch/decode']['count'], 1)
        self.assertNotIn('search/rf/batch/matrices', rows)
        self.assertEqual(rows['search/rf/decode']['count'], 2)
        self.assertEqual(rows['search/rf/power_response']['count'], 2)
        self.assertIsNone(model._deep_timing)
        self.assertIsNone(coupled_lc._deep_timing)

    def test_plain_batch_uses_no_rf_clock(self):
        ev = self.model.evaluator(self.grid, cache_mode='lk')
        base = ev.evaluate(self.x)
        with patch.object(model, 'perf_counter_ns', side_effect=AssertionError('clock used')):
            ev.evaluate_partial_batch([self.x], base, np.ones((1, len(self.grid.setting)), bool))

    def test_batch_decode_failure_is_recorded(self):
        ev = self.model.evaluator(self.grid, cache_mode='lk')
        timer = TimerCollector()
        with patch.object(coupled_lc.ParameterVectorSchema, 'decode_batch', side_effect=RuntimeError('decode injected')):
            with self.assertRaisesRegex(RuntimeError, 'decode injected'):
                with search_rf_timing(timer, 'search'):
                    ev.evaluate_batch([self.x, self.x])
        rows = timer.snapshot()
        self.assertEqual(rows['search/rf/batch/decode']['failed'], 1)
        self.assertEqual(rows['search/rf/batch/decode_lk']['failed'], 1)
        self.assertNotIn('search/rf/decode', rows)
        self.assertIsNone(model._deep_timing)
        self.assertIsNone(coupled_lc._deep_timing)

    def test_schur_failure_is_recorded(self):
        ev = self.model.evaluator(self.grid, cache_mode='lk')
        ev.evaluate(self.x)  # warm the L/k cache so the first solve is Schur
        timer = TimerCollector()
        with self.assertRaisesRegex(RuntimeError, 'schur'):
            with search_rf_timing(timer, 'search'):
                with patch.object(np.linalg, 'solve', side_effect=RuntimeError('schur')):
                    ev.evaluate_batch([self.x])
        rows = timer.snapshot()
        self.assertEqual(rows['search/rf/batch/schur_solve']['failed'], 1)
        self.assertEqual(rows['search/rf/batch']['failed'], 1)
        self.assertIsNone(model._deep_timing)
        self.assertIsNone(coupled_lc._deep_timing)

    def test_failure_and_restoration(self):
        ev = self.model.evaluator(self.grid, cache_mode='lk')
        original = (model.RFEvaluator.evaluate, model.RFEvaluator.evaluate_batch,
                    model.RFEvaluator.evaluate_partial_batch, model._cascade)
        timer = TimerCollector()
        with self.assertRaisesRegex(RuntimeError, 'injected'):
            with search_rf_timing(timer, 'search'):
                with patch.object(np.linalg, 'solve', side_effect=RuntimeError('injected')):
                    ev.evaluate_batch([self.x])
        rows = timer.snapshot()
        self.assertEqual(rows['search/rf/batch/decode_lk']['failed'], 1)
        self.assertEqual(rows['search/rf/batch/matrices']['failed'], 1)
        self.assertEqual(rows['search/rf/batch']['failed'], 1)
        self.assertEqual(original, (model.RFEvaluator.evaluate, model.RFEvaluator.evaluate_batch,
                                    model.RFEvaluator.evaluate_partial_batch, model._cascade))
        self.assertIsNone(model._deep_timing)
        self.assertIsNone(coupled_lc._deep_timing)
        before = timer.snapshot()
        ev.evaluate_batch([self.x])
        self.assertEqual(before, timer.snapshot())


if __name__ == '__main__':
    unittest.main()

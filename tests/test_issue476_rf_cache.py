"""Evaluator-local RF caches: exact results, isolation and failure semantics."""
import unittest
from unittest.mock import patch

import numpy as np

from test_issue307_constraints import make
from test_issue309_rf_core import grid
from lpf.rf_core.coupled_lc import CoupledLCTopology
from lpf.rf_core.numerical_diagnostics import CircuitNumericalError


class RFCacheTests(unittest.TestCase):
    def setUp(self):
        policy, _, self.model, _, self.x = make('RF-T008')
        # Interleave all settings, retaining all 28 distinct intervals.
        original = grid(policy)
        order = np.argsort(original.setting % 2, kind='stable')
        from lpf.rf_core import EvaluationGrid
        self.grid = EvaluationGrid(original.frequency_hz[order], original.setting[order], original.segment[order])

    def assert_response_equal(self, a, b):
        for name in ('s', 'il_db', 'apl_db', 'in_rl_db', 'out_rl_db'):
            np.testing.assert_array_equal(getattr(a, name), getattr(b, name), err_msg=name)

    def test_modes_and_partial_hits(self):
        m, x, s = self.model, self.x, self.model.schema
        variants = [x.copy(), x.copy(), x.copy(), x.copy(), x.copy()]
        start = s.n_inductors + s.n_fixed + s.n_coupling + s.n_ic_fixed
        variants[2][start + 2*s.n_variable] += .01  # only setting 2
        variants[3][s.n_inductors] += .01  # shared fixed C
        variants[4][0] += .01  # L
        baseline = m.evaluator(self.grid)
        expected = [baseline.evaluate(v) for v in variants]
        for mode in ('off', 'lk', 'response', 'both'):
            with self.subTest(mode=mode):
                evaluator = m.evaluator(self.grid, cache_mode=mode)
                for v, reference in zip(variants, expected):
                    self.assert_response_equal(evaluator.evaluate(v), reference)
                stats = evaluator.cache_stats
                self.assertEqual(stats['computed_samples'], 5*len(self.grid.setting) if mode in ('off', 'lk') else
                                 3*len(self.grid.setting) + np.count_nonzero(self.grid.setting == 2))
                if mode in ('response', 'both'):
                    self.assertEqual(stats['response_hits'], 11)
                    self.assertEqual(stats['response_misses'], 19)
                if mode in ('lk', 'both'):
                    self.assertGreater(stats['lk_hits'], 0)
                # Power checking must bypass both caches.
                self.assert_response_equal(evaluator.evaluate(x, check_power=True), baseline.evaluate(x, check_power=True))
                self.assertEqual(m.evaluator(self.grid, cache_mode=mode).cache_stats['response_hits'], 0)

    def test_failure_not_cached_and_original_sample_index(self):
        evaluator = self.model.evaluator(self.grid, cache_mode='both')
        evaluator.evaluate(self.x)
        s = self.model.schema
        x = self.x.copy()
        start = s.n_inductors + s.n_fixed + s.n_coupling + s.n_ic_fixed
        x[start + 3*s.n_variable] += .01
        expected_index = int(np.flatnonzero(self.grid.setting == 3)[0])
        original = CoupledLCTopology.port_admittance

        def fail(topology, values, omega, setting, **kwargs):
            idx = np.flatnonzero(setting == 3)
            if len(idx):
                raise CircuitNumericalError('node_nonfinite', 'test', sample_index=int(idx[0]))
            return original(topology, values, omega, setting, **kwargs)

        with patch.object(CoupledLCTopology, 'port_admittance', fail):
            for _ in range(2):
                with self.assertRaises(CircuitNumericalError) as caught:
                    evaluator.evaluate(x)
                self.assertEqual((caught.exception.code, caught.exception.sample_index), ('node_nonfinite', expected_index))
        self.assertEqual(evaluator.cache_stats['response_misses'], 8)
        self.assert_response_equal(evaluator.evaluate(x), self.model.evaluator(self.grid).evaluate(x))
        bad = x.copy()
        bad[s.n_inductors + s.n_fixed] = 2.
        for _ in range(2):
            with self.assertRaises(CircuitNumericalError) as caught:
                evaluator.evaluate(bad)
            self.assertEqual(caught.exception.code, 'mutual_not_spd')
        bad[0] = np.nan
        with self.assertRaises(ValueError): evaluator.evaluate(bad)

    def test_distribution_on_incomplete_grid_and_deep_timing(self):
        from lpf.rf_core import EvaluationGrid
        from lpf.search._rf_deep_timing import search_rf_timing
        from lpf.timing import TimerCollector
        mask = np.isin(self.grid.setting, (0, 2))
        grid = EvaluationGrid(self.grid.frequency_hz[mask], self.grid.setting[mask], self.grid.segment[mask])
        evaluator = self.model.evaluator(grid, cache_mode='both', cache_diagnostics=True)
        timer = TimerCollector()
        s = self.model.schema
        changed = self.x.copy()
        start = s.n_inductors + s.n_fixed + s.n_coupling + s.n_ic_fixed
        changed[start + 2*s.n_variable] += .01
        with search_rf_timing(timer, 'search'):
            for x in (self.x, self.x, changed):
                self.assert_response_equal(evaluator.evaluate(x), self.model.evaluator(grid).evaluate(x))
        dist = evaluator.cache_stats['response_distribution']
        self.assertEqual(dist, {'all_miss': {'forwards': 1, 'computed_samples': len(grid.setting)},
                                'all_hit': {'forwards': 1, 'computed_samples': 0},
                                'partial_hit': {'forwards': 1, 'computed_samples': int(np.sum(grid.setting == 2))}})
        regions = timer.snapshot()
        for name in ('lk_lookup', 'response_lookup', 'missing_select', 'missing_compute', 'store', 'assemble'):
            self.assertIn('search/rf/cache/' + name, regions)
        with patch('lpf.rf_core.model.perf_counter_ns', side_effect=AssertionError('clock called')):
            evaluator.evaluate(changed)  # plain: no additional clock calls

    def test_numerical_stop_modes_and_cached_result_ownership(self):
        original_solve = np.linalg.solve

        def singular_two_port(a, b):
            if a.ndim == 3 and a.shape[-2:] == (2, 2):
                raise np.linalg.LinAlgError('injected singular Y-to-S')
            return original_solve(a, b)

        schema = self.model.schema
        for mode in ('off', 'lk', 'response', 'both'):
            with self.subTest(mode=mode):
                evaluator = self.model.evaluator(self.grid, cache_mode=mode)
                x = self.x.copy()
                first = evaluator.evaluate(x)
                saved_s = first.s.copy()
                x[0] += .01
                np.testing.assert_array_equal(first.s, saved_s)
                self.assertFalse(first.s.flags.writeable)
                bad = self.x.copy()
                bad[schema.n_inductors + schema.n_fixed] = 2.
                with self.assertRaises(CircuitNumericalError) as caught:
                    evaluator.evaluate(bad)
                self.assertEqual(caught.exception.code, 'mutual_not_spd')
                bad[0] = np.nan
                with self.assertRaises(ValueError): evaluator.evaluate(bad)
                with patch('numpy.linalg.solve', side_effect=singular_two_port):
                    # x changes L, preventing response hits in this failure check.
                    with self.assertRaises(CircuitNumericalError) as caught:
                        evaluator.evaluate(x)
                    self.assertEqual(caught.exception.code, 's_singular')
                self.assert_response_equal(evaluator.evaluate(self.x), first)

    def test_capacity(self):
        e = self.model.evaluator(self.grid, cache_mode='both')
        for i in range(17):
            x = self.x.copy(); x[0] += i * .001
            e.evaluate(x)
        self.assertEqual(len(e._lk_cache), 16)
        self.assertTrue(all(len(cache) == 16 for cache in e._response_cache))
        misses = e.cache_stats['lk_misses']
        e.evaluate(self.x)
        self.assertEqual(e.cache_stats['lk_misses'], misses + 1)


if __name__ == '__main__':
    unittest.main()

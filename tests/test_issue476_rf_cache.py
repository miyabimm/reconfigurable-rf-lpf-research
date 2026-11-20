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

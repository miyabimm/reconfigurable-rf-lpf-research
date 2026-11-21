"""Candidate-batch equivalence, ordering, and transactional failures."""
import unittest
from unittest.mock import patch
import numpy as np

from test_issue307_constraints import make
from test_issue309_rf_core import grid
from lpf.rf_core.numerical_diagnostics import CircuitNumericalError


class BatchTests(unittest.TestCase):
    def setUp(self):
        policy, _, self.model, self.bounds, self.x = make('RF-T008')
        self.grid = grid(policy)

    def test_equivalence_and_cache(self):
        variants = [self.x.copy() for _ in range(5)]
        variants[1][self.model.schema.n_inductors] += .01
        variants[2][-1] += .01
        variants[3][0] += .01
        expected = [self.model.evaluator(self.grid).evaluate(v) for v in variants]
        for mode in ('off', 'lk', 'response', 'both'):
            with self.subTest(mode=mode):
                ev = self.model.evaluator(self.grid, cache_mode=mode)
                actual = ev.evaluate_batch(variants)
                self.assertIsInstance(actual, tuple)
                for a, b in zip(actual, expected):
                    self.assertIs(a.grid, self.grid)
                    for name in ('s', 'il_db', 'apl_db', 'in_rl_db', 'out_rl_db'):
                        np.testing.assert_allclose(getattr(a, name), getattr(b, name), rtol=1e-12, atol=1e-12)
                        self.assertFalse(getattr(a, name).flags.writeable)
                if mode == 'lk':
                    self.assertEqual((ev.cache_stats['lk_hits'], ev.cache_stats['lk_misses']), (3, 2))
                if mode in ('off', 'lk'):
                    self.assertEqual(ev.cache_stats['computed_samples'], 5*len(self.grid.setting))

    def test_bad_input_and_ordered_failure(self):
        ev = self.model.evaluator(self.grid, cache_mode='lk')
        for invalid in ([], self.x, np.array([self.x], complex), np.array([self.x], bool), np.empty((0, len(self.x)))):
            with self.assertRaises(ValueError): ev.evaluate_batch(invalid)
        bad = self.x.copy()
        bad[self.model.schema.n_inductors + self.model.schema.n_fixed] = 2
        nan = self.x.copy(); nan[0] = np.nan
        with self.assertRaises(CircuitNumericalError) as caught:
            ev.evaluate_batch([self.x, bad, nan])
        self.assertEqual(caught.exception.code, 'mutual_not_spd')
        self.assertEqual(len(ev._lk_cache), 1)
        self.assertEqual(ev.cache_stats['lk_lookups'], 2)
        self.assertEqual(ev.cache_stats['lk_computations'], 2)
        self.assertEqual(ev.cache_stats['computed_samples'], len(self.grid.setting))

    def test_other_schemas_and_lru(self):
        for cid in ('RF-F003', 'RF-T007'):
            policy, _, model, _, x = make(cid)
            g = grid(policy)
            variants = [x.copy(), x.copy()]
            variants[1][-1] += .01
            batch = model.evaluator(g, cache_mode='lk').evaluate_batch(variants)
            for a, v in zip(batch, variants):
                b = model.evaluator(g).evaluate(v, check_power=True)
                np.testing.assert_allclose(a.s, b.s, rtol=1e-12, atol=1e-12)
        variants = []
        for i in list(range(17)) + [0, 16]:
            x = self.x.copy(); x[0] += .001*i
            variants.append(x)
        scalar = self.model.evaluator(self.grid, cache_mode='lk')
        batch = self.model.evaluator(self.grid, cache_mode='lk')
        for x in variants: scalar.evaluate(x)
        batch.evaluate_batch(variants)
        self.assertEqual(scalar.cache_stats, batch.cache_stats)
        self.assertEqual(list(scalar._lk_cache), list(batch._lk_cache))

    def test_boundaries_and_singular_solve(self):
        variants = [self.x.copy()]
        # C endpoints are valid even when they are zero in a different policy.
        for index in (self.model.schema.n_inductors, len(self.x)-1):
            for endpoint in self.bounds[index]:
                x = self.x.copy(); x[index] = endpoint
                variants.append(x)
        ev = self.model.evaluator(self.grid, cache_mode='lk')
        expected = [self.model.evaluator(self.grid).evaluate(x) for x in variants]
        for a, b in zip(ev.evaluate_batch(variants), expected):
            np.testing.assert_allclose(a.s, b.s, rtol=1e-12, atol=1e-12)
        original = np.linalg.solve
        def singular(a, b):
            if a.shape[-2:] == (2, 2):
                raise np.linalg.LinAlgError('injected Y-to-S singularity')
            return original(a, b)
        ev = self.model.evaluator(self.grid, cache_mode='lk')
        with patch('numpy.linalg.solve', side_effect=singular):
            with self.assertRaises(CircuitNumericalError) as caught:
                ev.evaluate_batch(variants)
        self.assertEqual(caught.exception.code, 's_singular')
        self.assertEqual(len(ev._lk_cache), 0)

    def test_failure_replay_original_sample_index(self):
        ev = self.model.evaluator(self.grid, cache_mode='lk')
        from lpf.rf_core.coupled_lc import CoupledLCTopology
        original = CoupledLCTopology.port_admittance
        def fail(t, values, omega, setting, **kwargs):
            if values.inductances_nh[0] != self.x[0]:
                raise CircuitNumericalError('node_nonfinite', 'injected', sample_index=3)
            return original(t, values, omega, setting, **kwargs)
        changed = self.x.copy(); changed[0] += .01
        # Force the batch to fail late; scalar replay gives the true index.
        with patch('lpf.rf_core.model.power_response', side_effect=ValueError('batch failure')):
            # Scalar also uses power_response, so test the ordered fallback separately below.
            with self.assertRaises(ValueError): ev.evaluate_batch([self.x, changed])
        self.assertEqual(len(ev._lk_cache), 0)
        with patch.object(type(ev), '_compute_batch', side_effect=ValueError('batch failure')), patch.object(CoupledLCTopology, 'port_admittance', fail):
            with self.assertRaises(CircuitNumericalError) as caught:
                ev.evaluate_batch([self.x, changed])
        self.assertEqual((caught.exception.code, caught.exception.sample_index), ('node_nonfinite', 3))
        self.assertEqual(len(ev._lk_cache), 1)


if __name__ == '__main__': unittest.main()

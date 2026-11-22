"""Batch extraction matches scalar decode, including ordered failure replay."""
import unittest
from unittest.mock import patch

import numpy as np

from test_issue307_constraints import make
from test_issue309_rf_core import grid
from lpf.rf_core.coupled_lc import ParameterVectorSchema


class BatchDecodeTests(unittest.TestCase):
    def test_schema_layout_and_float_conversion(self):
        for schema in (ParameterVectorSchema(2, 1, 1, 1, 2, (0.5,)),
                       ParameterVectorSchema(1, 0, 0, 0, 0)):
            x = np.arange(1, 1 + 3 * schema.vector_length, dtype=np.float32).reshape(3, -1)
            L, k, C = schema.decode_batch(x)
            self.assertEqual(C.shape, (3, 6, schema.capacitor_count))
            self.assertEqual(C.dtype, np.float64)
            for i, row in enumerate(x):
                v = schema.decode(row)
                np.testing.assert_array_equal(L[i], v.inductances_nh)
                np.testing.assert_array_equal(k[i], v.coupling_k)
                np.testing.assert_array_equal(C[i], v.capacitors_pf_by_setting)

    def test_bitwise_reference_batch_and_masks(self):
        policy, _, model, _, x = make('RF-T008')
        g = grid(policy)
        variants = np.array([x, x, x, x])
        variants[1, -1] += .01
        variants[2, 0] += .01
        variants[3, 0] += .01
        def old_decode(schema, vectors):
            values = [schema.decode(row) for row in vectors]
            return (np.asarray([v.inductances_nh for v in values]),
                    np.asarray([v.coupling_k for v in values]),
                    np.asarray([v.capacitors_pf_by_setting for v in values]))
        for mode in ('off', 'lk'):
            for partial in (False, True):
                with self.subTest(mode=mode, partial=partial):
                    ev1 = model.evaluator(g, cache_mode=mode)
                    ev2 = model.evaluator(g, cache_mode=mode)
                    base1, base2 = ev1.evaluate(x), ev2.evaluate(x)
                    mask = np.ones((len(variants), len(g.setting)), bool)
                    if partial:
                        mask[1, ::2] = False
                        mask[2, 1::2] = False
                    def run(ev, base):
                        return ev.evaluate_partial_batch(variants, base, mask)
                    with patch.object(ParameterVectorSchema, 'decode_batch', old_decode):
                        expected = run(ev1, base1)
                    actual = run(ev2, base2)
                    for a, b in zip(actual, expected):
                        for name in ('s', 'il_db', 'apl_db', 'in_rl_db', 'out_rl_db'):
                            np.testing.assert_array_equal(getattr(a, name), getattr(b, name))
                    self.assertEqual(ev1.cache_stats, ev2.cache_stats)
                    self.assertEqual(list(ev1._lk_cache), list(ev2._lk_cache))

    def test_dtype_shape_and_extreme_values_replay(self):
        policy, _, model, _, x = make('RF-T008')
        g = grid(policy)
        ev = model.evaluator(g, cache_mode='lk')
        for invalid in (np.array([x], dtype=complex), np.array([x], dtype=bool),
                        np.array([x], dtype=str), np.array([x[:-1]]), x):
            with self.assertRaisesRegex(ValueError, 'Expected real numeric vectors'):
                ev.evaluate_batch(invalid)
        for value in (np.finfo(float).max, -np.finfo(float).max):
            bad = x.copy()
            bad[model.schema.n_inductors + model.schema.n_fixed] = value
            batch = model.evaluator(g, cache_mode='lk')
            scalar = model.evaluator(g, cache_mode='lk')
            with np.errstate(over='ignore', invalid='ignore'):
                with self.assertRaises(Exception) as a:
                    batch.evaluate_batch([x, bad])
                with self.assertRaises(Exception) as b:
                    scalar.evaluate(x)
                    scalar.evaluate(bad)
            self.assertEqual((type(a.exception), str(a.exception)),
                             (type(b.exception), str(b.exception)))
            self.assertEqual(batch.cache_stats, scalar.cache_stats)
            self.assertEqual(list(batch._lk_cache), list(scalar._lk_cache))
        # Float32 and integer inputs follow the scalar float64 coercion.
        for vectors in (np.array([x, x], dtype=np.float32),
                        np.array([x, x], dtype=np.int64)):
            try:
                expected = [model.evaluator(g).evaluate(row) for row in vectors]
            except ValueError:
                with self.assertRaises(ValueError):
                    model.evaluator(g).evaluate_batch(vectors)
            else:
                actual = model.evaluator(g).evaluate_batch(vectors)
                for a, b in zip(actual, expected):
                    np.testing.assert_allclose(a.s, b.s, rtol=1e-12, atol=1e-12)

    def test_ordered_failures_match_scalar_and_cache(self):
        policy, _, model, _, x = make('RF-T008')
        g = grid(policy)
        schema = model.schema
        invalids = []
        for index, value in ((0, np.nan), (0, np.inf), (0, 0.), (0, -1.),
                             (schema.n_inductors, -1.),
                             (schema.n_inductors + schema.n_fixed, 2.),
                             (-1, -1.)):
            bad = x.copy(); bad[index] = value; invalids.append(bad)
        for bad in invalids:
            for mode in ('off', 'lk'):
                with self.subTest(value=bad, mode=mode):
                    batch = model.evaluator(g, cache_mode=mode)
                    scalar = model.evaluator(g, cache_mode=mode)
                    vectors = [x, bad, x]
                    with self.assertRaises(Exception) as a:
                        batch.evaluate_batch(vectors)
                    with self.assertRaises(Exception) as b:
                        for row in vectors:
                            scalar.evaluate(row)
                    self.assertEqual(type(a.exception), type(b.exception))
                    self.assertEqual(str(a.exception), str(b.exception))
                    self.assertEqual(batch.cache_stats, scalar.cache_stats)
                    self.assertEqual(list(batch._lk_cache), list(scalar._lk_cache))


if __name__ == '__main__':
    unittest.main()

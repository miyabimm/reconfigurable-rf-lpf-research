"""Issue #235: mock solver only; no real SLSQP optimization."""
from functools import partial
from types import SimpleNamespace
from unittest.mock import patch
import unittest

import numpy as np

from test_phase2_problem_seed import make, seed
from test_phase2_staged_optimization import status
from lpf.phase2_models.normalized_epigraph import NormalizedEpigraph
from lpf.phase2_models.problem_seed import VectorBox, vector_fingerprint
from lpf.phase2_models.sampled_epigraph import SampledEpigraph
from lpf.phase2_models.staged_optimization import run_c1_staged, scipy_slsqp_stage


class NormalizationTests(unittest.TestCase):
    def test_roundtrip_full_vector_objective_and_28_interval_grid(self):
        for n in (3, 4):
            p, physical = make('RF-T008', n)
            if n == 3:
                physical[6] = 0.  # fixed nominal-zero non-neighbor coupling
            for points in (2, 3):
                p = SampledEpigraph(p.circuit, points)
                x = np.array(seed(p, physical)['vector'])
                wrapped = NormalizedEpigraph(p)
                z = wrapped.to_normalized(x)
                back = wrapped.to_physical(z)
                np.testing.assert_allclose(back, x, rtol=2e-15, atol=2e-15)
                self.assertEqual(z[-1], x[-1])
                self.assertEqual(len(z), p.circuit.schema.vector_length + 1)
                self.assertEqual(wrapped.objective(z), p.objective(x))
                np.testing.assert_allclose(wrapped.residuals(z), p.residuals(x), atol=2e-10)
                self.assertIs(wrapped.physical.evaluator, p.evaluator)
                self.assertEqual(len(set(p.evaluator.setting)), 6)
                self.assertEqual(len(set(p.evaluator.segment)), 28)
                self.assertEqual(len(p.evaluator.f), 28 * points)
                self.assertEqual(p.mandatory_stop_db, 30.)
                self.assertEqual(p.policy_fingerprint,
                    'e682165c72d3a8b9f1384a2529f71bacfebfc9d17164d4af5af879e4a138b532')
                for i in np.flatnonzero(wrapped.fixed):
                    self.assertEqual(z[i], 0.)
                    self.assertEqual(wrapped.box.bounds[i], (0., 0.))
                    invalid = z.copy()
                    invalid[i] = 1e-6
                    with self.assertRaises(ValueError):
                        wrapped.to_physical(invalid)

    def test_invalid_box_open_lower_spd_and_vectors_fail_closed(self):
        p, physical = make('RF-T008', 4)
        x = np.array(seed(p, physical)['vector'])
        wrapped = NormalizedEpigraph(p)
        z = wrapped.to_normalized(x)
        for bad in (z[:-1], np.r_[z, 0.], np.full_like(z, np.nan),
                    np.full_like(z, np.inf)):
            with self.assertRaises(ValueError):
                wrapped.to_physical(bad)
        for i, value in ((0, -1e-6), (0, 1.000001), (4, -1e-6)):
            bad = z.copy()
            bad[i] = value
            with self.assertRaises(ValueError):
                wrapped.residuals(bad)
        # A decoder/SPD failure is propagated, never converted into finite RF
        # residuals or claimed convergence, even for a box-interior input.
        with patch.object(type(p.circuit), 'validate_components',
                          side_effect=ValueError('full inductance matrix not SPD')):
            with self.assertRaisesRegex(ValueError, 'not SPD'):
                wrapped.to_physical(z)
        bad = x.copy()
        bad[6:9] = -.9
        with self.assertRaises(ValueError):
            wrapped.to_normalized(bad)
        with patch.object(p, 'box', VectorBox(((None, 1.),) + p.box.bounds[1:], ())):
            with self.assertRaises(ValueError):
                NormalizedEpigraph(p)

    def test_opt_in_mock_stages_preserve_physical_records_and_v2(self):
        p, x = make('RF-T008', 4)
        p = SampledEpigraph(p.circuit, 2)
        initial = seed(p, x)
        for codes, budgets in (([0, 0], [240, 120]),
                               ([8, 0, 0, 0], [240, 120, 240, 120]),
                               ([9, 0, 0, 0], [240, 120, 500, 280]),
                               ([4, 9], [240, 120])):
            records = []
            for coordinates in ('physical', 'normalized'):
                calls = []
                def fake_minimize(fun, vector, **kw):
                    # Evaluate the actual RF callback, but never optimize it.
                    self.assertTrue(np.isfinite(fun(vector)))
                    self.assertTrue(np.all(np.isfinite(kw['constraints'][0]['fun'](vector))))
                    calls.append(kw['options']['maxiter'])
                    state = status(codes[len(calls)-1])
                    return SimpleNamespace(x=vector.copy(), **state)
                with patch('lpf.phase2_models.staged_optimization.minimize',
                           side_effect=fake_minimize):
                    record = run_c1_staged(p.circuit, initial, coarse_points=2,
                        fine_points=3, optimize_stage=partial(scipy_slsqp_stage,
                            coordinates=coordinates, finite_difference_eps=1e-6),
                        source_provenance={'kind': 'synthetic_mock', 'source_sha': 'fixture'})
                self.assertEqual(calls, budgets)
                self.assertEqual(record['seed'], initial)
                self.assertEqual(record['validation']['independent_mna'], 'not_run')
                self.assertEqual(record['validation']['power_balance'], 'not_run')
                self.assertTrue(record['candidate_promotion_blocked'])
                for stage in record['stage_calls']:
                    self.assertEqual(stage['input_vector_sha256'],
                                     vector_fingerprint(stage['input_vector']))
                    config = stage['status']['coordinate_configuration']
                    self.assertEqual(config['coordinates'], coordinates)
                    self.assertEqual(config['finite_difference_eps'], 1e-6)
                    self.assertEqual(stage['status']['status'], codes[stage['call_index']])
                records.append(record)
            a, b = records
            self.assertEqual(a['grids'], b['grids'])
            self.assertEqual(a['numerical_state'], b['numerical_state'])
            self.assertEqual(a['controller']['recovery_cause'], b['controller']['recovery_cause'])
            for left, right in zip(a['stage_calls'], b['stage_calls']):
                np.testing.assert_allclose(left['output_vector'], right['output_vector'], atol=2e-14)
                np.testing.assert_allclose(left['observation']['sampled_rf']['residuals_db'],
                                           right['observation']['sampled_rf']['residuals_db'], atol=2e-10)

    def test_invalid_normalized_solver_output_aborts_and_options_are_explicit(self):
        p, x = make('RF-T008', 4)
        initial = seed(p, x)
        def invalid(fun, z, **kwargs):
            self.assertEqual(kwargs['options'], {'maxiter': 240, 'eps': 1e-5})
            self.assertEqual(kwargs['bounds'][-1], (None, None))
            z[4] = -1e-6  # below the closed GJM bound; no repair
            return SimpleNamespace(x=z, **status(0))
        with patch('lpf.phase2_models.staged_optimization.minimize', side_effect=invalid) as solver:
            result = run_c1_staged(p.circuit, initial, coarse_points=1, fine_points=2,
                optimize_stage=partial(scipy_slsqp_stage, coordinates='normalized',
                                       finite_difference_eps=1e-5))
        self.assertEqual(solver.call_count, 1)
        self.assertEqual(result['numerical_state'], 'failed')
        self.assertIn('coordinate box', result['exception']['message'])
        for kwargs in ({'coordinates': 'typo'}, {'finite_difference_eps': 0},
                       {'finite_difference_eps': np.nan}):
            with self.assertRaises(ValueError):
                scipy_slsqp_stage(p, initial['vector'], 240, None, **kwargs)


if __name__ == '__main__':
    unittest.main()

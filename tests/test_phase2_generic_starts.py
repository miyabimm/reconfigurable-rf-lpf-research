"""Issue #248: synthetic bounded transformations, no solver or scientific EXP."""
from dataclasses import replace
import unittest
from unittest.mock import patch

import numpy as np
from test_phase2_problem_seed import make
from lpf.phase2_models.sampled_epigraph import SampledEpigraph
from lpf.phase2_models.multistart import generate_starts, run_multistart_preview
from lpf.phase2_models.generic_starts import multiplier_interval, transform_candidate
from lpf.phase2_models.start_selection import StartSelectionError


def mock_il(e, x):
    return np.choose(e.role, [x[0], 30., np.nextafter(30., 0.)])


class GenericStartsTests(unittest.TestCase):
    def fixture(self, n=3):
        p, x = make('RF-T008', n)
        if n == 3:
            x[6] = 0.
        return SampledEpigraph(p.circuit, 2), x

    def generate(self, p, x, **kw):
        return generate_starts(p, x, seed=23, selection='rf_pareto',
            candidate_pool='physical_transform', **kw)

    def test_topology_independent_deterministic_pool_and_legacy(self):
        for n in (3, 4):
            p, x = self.fixture(n)
            with patch.object(type(p.evaluator), 'il', mock_il):
                a = self.generate(p, x, max_initial_samples=952)
                b = self.generate(p, x, max_initial_samples=952)
                old = generate_starts(p, x, seed=23, selection='rf_pareto')
                legacy = generate_starts(p, x, seed=23)
            self.assertEqual(a['starts'], b['starts'])
            ra, ro = a['selection_report'], old['selection_report']
            self.assertEqual(ra['cost']['RF_forward_calls'], 17)
            self.assertEqual(ra['cost']['frequency_samples_completed'], 952)
            self.assertEqual(ra['cost']['frequency_samples_requested'], 952)
            self.assertEqual(a['starts'][0]['vector'], x.tolist())
            self.assertEqual([r['vector_sha256'] for r in ra['candidates'][5:]],
                             [r['vector_sha256'] for r in ro['candidates'][5:]])
            self.assertEqual(ro['baseline_prefix_vector_sha256'],
                             [s['vector_sha256'] for s in legacy['starts']])
            for slot, row in enumerate(ra['candidates'][1:5]):
                source = np.array(ro['candidates'][slot+1]['vector'])
                new = np.array(row['vector'])
                self.assertEqual(row['source_vector_sha256'], ro['candidates'][slot+1]['vector_sha256'])
                self.assertEqual(row['pool_index'], slot)
                self.assertEqual(row['cost']['RF_forward_calls'], 1)
                detail = p.circuit.validate_components(new)
                self.assertGreater(detail['min_L_eigenvalue_H'], 0)
                nf, nk = p.circuit.schema.n_fixed, p.circuit.schema.n_coupling
                if slot < 2:
                    d = row['transform']
                    np.testing.assert_allclose(new[:n], source[:n] * d['lambda_L'])
                    np.testing.assert_array_equal(new[n+nf:n+nf+nk], source[n+nf:n+nf+nk])
                    ci = list(range(n, n+nf)) + list(range(n+nf+nk, len(x)))
                    np.testing.assert_allclose(new[ci], source[ci] * d['mu_C'])
                    self.assertAlmostEqual(d['lambda_L'], d['alpha']/d['beta'])
                    self.assertAlmostEqual(d['mu_C'], 1/(d['alpha']*d['beta']))
                else:
                    start = len(x) - 12  # two variable branches, six settings
                    np.testing.assert_array_equal(new[:start], source[:start])
                    self.assertEqual(row['transform']['rho'], .5)
                    inv = 1 / np.square(row['transform']['representative_frequencies_mhz'])
                    trend = (inv - min(inv)) / np.ptp(inv)
                    np.testing.assert_allclose(new[start:].reshape(6, 2),
                        .5 * source[start:].reshape(6, 2) + .5 * 3 * trend[:, None])
                    for s, f in enumerate(row['transform']['representative_frequencies_mhz']):
                        self.assertIn(f, p.evaluator.f[(p.evaluator.setting == s) & (p.evaluator.role == 0)])
            # CPU/wall variations cannot change synthetic run identity.
            ids = []
            def capture(*args, **kwargs):
                ids.append(kwargs['run_id'])
                raise RuntimeError('captured')
            with patch.object(type(p.evaluator), 'il', mock_il), patch(
                    'lpf.phase2_models.multistart.make_synthetic_plan', side_effect=capture):
                for generated in (a, b):
                    with self.assertRaisesRegex(RuntimeError, 'captured'):
                        run_multistart_preview(p.circuit, generated, None,
                            optimize_stage=None, historical_benchmarks=[])
            self.assertEqual(ids[0], ids[1])

    def test_intervals_zeros_fixed_dimensions_open_bounds_and_no_variable(self):
        self.assertEqual(multiplier_interval([0., 2.], [(0., 3.), (1., 4.)], [False, False]), (.5, 2., False))
        self.assertEqual(multiplier_interval([2.], [(2., 2.)], [False]), (1., 1., False))
        with self.assertRaisesRegex(ValueError, 'Zero value'):
            multiplier_interval([0.], [(0., 3.)], [True])
        p, x = self.fixture()
        # GJM zero is not deleted: allowed ONLY by the existing exploration gate.
        x[3] = 0.
        with patch.object(type(p.evaluator), 'il', mock_il):
            with self.assertRaises(StartSelectionError) as cm:
                self.generate(p, x)
            self.assertEqual(cm.exception.report['cost']['RF_forward_calls'], 0)
            a = self.generate(p, x, for_exploration=True)
        self.assertTrue(a['candidate_promotion_blocked'])
        self.assertEqual(a['starts'][0]['vector'][3], 0.)
        # No epsilon: a multiplier sampled at an open zero boundary is rejected.
        bounds = list(p.box.bounds)
        bounds[0] = (0., bounds[0][1])
        bounds[1] = (0., bounds[1][1])
        bounds[2] = (0., bounds[2][1])
        p.box = replace(p.box, bounds=tuple(bounds), open_lower=(0, 1, 2))
        with self.assertRaisesRegex(ValueError, 'open boundary'):
            transform_candidate(p, x, np.zeros(len(x)), 0, {})
        # Fixed/zero vector produces an explicit duplicate rejection, no repair.
        p.box = replace(p.box, bounds=tuple((v, v) for v in x) + ((None, None),), open_lower=())
        with self.assertRaisesRegex(ValueError, 'duplicates source'):
            transform_candidate(p, x, np.full(len(x), .5), 0, {})
        d = p.circuit.definition
        d = replace(d, capacitor_placement=replace(d.capacitor_placement,
            variable_edges=(), ic_fixed_edges=()), variable_roles=())
        from lpf.phase2_models.api import build_nominal_circuit
        p = SampledEpigraph(build_nominal_circuit(p.circuit.resolved_policy, d), 2)
        x = np.array([2., 2., 2., 1., .1, .02, 0.])
        with patch.object(type(p.evaluator), 'il', mock_il):
            a = self.generate(p, x)
        rows = a['selection_report']['candidates']
        for row in rows[3:5]:
            self.assertIn('No variable C', row['exception'])
            self.assertEqual(row['cost']['RF_forward_calls'], 0)
        self.assertEqual(a['selection_report']['cost']['RF_forward_calls'], 15)
        self.assertEqual(len(rows[5:]), 12)

    def test_rejections_and_fail_closed_partial_cost(self):
        p, x = self.fixture()
        with patch.object(type(p.evaluator), 'il', mock_il):
            with self.assertRaises(StartSelectionError) as cm:
                self.generate(p, x, max_initial_samples=56)
        self.assertEqual(cm.exception.report['cost']['frequency_samples_requested'], 56)
        self.assertIn('budget exhausted', cm.exception.report['exception'])
        for bad in (RuntimeError('forward failed'), np.full(56, np.nan)):
            def forward(e, vector):
                if isinstance(bad, Exception):
                    raise bad
                return bad
            with patch.object(type(p.evaluator), 'il', forward):
                with self.assertRaises(StartSelectionError) as cm:
                    self.generate(p, x)
            self.assertEqual(cm.exception.report['status'], 'failed')
        # Illegal transformed vector is discarded, retained wide slots still evaluated.
        def illegal(problem, vector, unit, slot, metadata):
            y = np.array(vector)
            y[0] = -1.
            return y
        with patch.object(type(p.evaluator), 'il', mock_il), patch(
                'lpf.phase2_models.generic_starts.transform_candidate', side_effect=illegal):
            a = self.generate(p, x)
        r = a['selection_report']
        self.assertEqual(r['cost']['RF_forward_calls'], 13)
        self.assertTrue(all(row['reason'] == 'rejected' for row in r['candidates'][1:5]))
        # Existing SPD validator rechecks both source and transformed candidates.
        original = type(p.circuit).validate_components
        def spd(c, vector, **kw):
            if vector[0] > 20:
                raise ValueError('Full inductance matrix is non-positive-definite or ill-conditioned')
            return original(c, vector, **kw)
        with patch.object(type(p.evaluator), 'il', mock_il), patch.object(
                type(p.circuit), 'validate_components', spd):
            a = self.generate(p, x)
        self.assertGreater(a['selection_report']['cost']['spd_rejections'], 0)
        fixed = tuple((float(v), float(v)) for v in x) + ((None, None),)
        p.box = replace(p.box, bounds=fixed, open_lower=())
        with patch.object(type(p.evaluator), 'il', mock_il):
            with self.assertRaisesRegex(StartSelectionError, 'Insufficient legal') as cm:
                self.generate(p, x)
        self.assertEqual(cm.exception.report['cost']['RF_forward_calls'], 1)
        self.assertEqual(len(cm.exception.report['candidates']), 17)


if __name__ == '__main__':
    unittest.main()

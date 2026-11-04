"""Small finite-grid regressions; no optimization or historical EXP imports."""
import sys
from pathlib import Path
import unittest

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from lpf.constraint_versions import load_constraint
from lpf.phase2_models.api import CircuitDefinition, build_nominal_circuit
from lpf.phase2_models.circuit_layout import CapacitorPlacement, InductorTree
from lpf.phase2_models.sampled_epigraph import SampledEpigraph
from lpf.phase2_models.numerical_diagnostics import CircuitNumericalError


def circuit(policy_id):
    definition = CircuitDefinition(
        inductor_tree=InductorTree(4, ((0, 1), (1, 2), (1, 3))),
        inductor_types=("LQP02HV",) * 3,
        physical_order=(0, 1, 2),
        coupling_pairs=((0, 1), (1, 2), (0, 2)),
        capacitor_placement=CapacitorPlacement(4, ((1, -1),), (), ()),
        fixed_c_types=("PCB_PATTERN_C",), variable_roles=(),
    )
    return build_nominal_circuit(load_constraint(policy_id, allow_trial=True), definition)


class SampledEpigraphTests(unittest.TestCase):
    def test_grid_roles_and_signs_all_trials(self):
        for policy_id in ("RF-T005", "RF-T007", "RF-T008"):
            with self.subTest(policy_id=policy_id):
                c = circuit(policy_id)
                p = SampledEpigraph(c, 2)
                x = np.array([2., 3., 4., .1, .01, -.02, .01, 7.])
                il = p.evaluator.il(x[:-1])
                expected = np.where(p.evaluator.role == 0, 7 - il, il - 30)
                np.testing.assert_allclose(p.residuals(x), expected)
                self.assertEqual(p.objective(x), 7.)
                self.assertEqual(len(p.residuals(x)), 56)
                self.assertEqual(set(p.evaluator.segment), set(range(28)))
                self.assertEqual(set(p.evaluator.setting), set(range(6)))
                self.assertEqual(set(p.evaluator.role), {0, 1, 2})
                self.assertEqual(p.policy_fingerprint, c.policy_fingerprint)
                # Numerical derivative dimensions, without running SLSQP.
                eps = 1e-6
                jac = np.column_stack([(p.residuals(x + np.eye(len(x))[i]*eps)
                                        - p.residuals(x))/eps for i in range(len(x))])
                self.assertEqual(jac.shape, (56, len(x)))
                np.testing.assert_allclose(jac[:, -1], p.evaluator.role == 0, atol=1e-8)

    def test_explicit_segment_frequencies_preserve_uniform_grid_and_roles(self):
        c = circuit("RF-T008")
        base = SampledEpigraph(c, 3)
        extra = SampledEpigraph(c, 3, extra_frequencies=((0, 670.5), (2, 1350.5)))
        for seg in range(28):
            a = base.evaluator.segment == seg
            b = extra.evaluator.segment == seg
            np.testing.assert_array_equal(extra.evaluator.f[b][:3], base.evaluator.f[a])
            self.assertTrue(np.all(extra.evaluator.role[b] == base.evaluator.role[a][0]))
            self.assertTrue(np.all(extra.evaluator.setting[b] == base.evaluator.setting[a][0]))
        x = np.array([2., 3., 4., .1, .01, -.02, .01, 7.])
        values = extra.evaluator.il(x[:-1])
        np.testing.assert_allclose(extra.residuals(x), np.where(
            extra.evaluator.role == 0, x[-1] - values, values - 30))
        for invalid in (((0, 670.5), (0, 670.5)), ((0, 663.),),
                        ((0, 700.),), ((28, 1.),), ((0, float('nan')),)):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                SampledEpigraph(c, 3, extra_frequencies=invalid)

    def test_opt_in_working_thresholds_and_selected_settings(self):
        c = circuit("RF-T008")
        x = np.array([2., 3., 4., .1, .01, -.02, .01, 7.])
        for threshold in (None, 10., 20., 25., 28., 30.005):
            p = SampledEpigraph(c, 2, settings=("B8", "B13+B14"),
                                working_stop_db=threshold)
            self.assertEqual(set(p.evaluator.setting), {3, 5})
            self.assertEqual(len(set(p.evaluator.segment)), 12)
            self.assertEqual(len(p.evaluator.f), 24)
            il, role = p.evaluator.il(x[:-1]), p.evaluator.role
            expected = (x[-1] - il[role == 0] if threshold is None else
                        np.where(role == 0, x[-1] - il, il - threshold))
            np.testing.assert_allclose(p.residuals(x), expected)
            self.assertEqual(p.mandatory_stop_db, 30.)
        from lpf.phase2_models.evaluation_cost import SampleBudgetCost
        meter = SampleBudgetCost(24)
        p = SampledEpigraph(c, 2, settings=("B8",), working_stop_db=None)
        meter.epigraph(p).residuals(x)
        self.assertEqual(meter.frequency_samples_requested, 8)
        for settings in ((), ("B8", "B8"), ("unknown",), "B8"):
            with self.subTest(settings=settings), self.assertRaises(ValueError):
                SampledEpigraph(c, 2, settings=settings)
        for threshold in (-1, float("nan"), float("inf"), True, "10"):
            with self.subTest(threshold=threshold), self.assertRaises(ValueError):
                SampledEpigraph(c, 2, working_stop_db=threshold)
        with self.assertRaises(ValueError):
            SampledEpigraph(c, 2, search_guard=True, working_stop_db=30.)
        with self.assertRaises(ValueError):
            SampledEpigraph(c, 2, settings=("B8",), extra_frequencies=((0, 670.5),))

    def test_gjm_search_box_and_diagnostic_stop(self):
        from test_phase2_problem_seed import make, seed
        from lpf.phase2_models.evaluation_cost import SampleBudgetCost
        from lpf.phase2_models.staged_optimization import run_c1_continuation
        p, physical = make('RF-T008', 4)
        base = SampledEpigraph(p.circuit, 2)
        limited = SampledEpigraph(p.circuit, 2, gjm_search_max_pf=10)
        self.assertEqual(base.box.bounds[4], (0., 100.))
        self.assertEqual(limited.box.bounds[4], (0., 10.))
        self.assertEqual(base.box.bounds[:4] + base.box.bounds[5:],
                         limited.box.bounds[:4] + limited.box.bounds[5:])
        definition = CircuitDefinition(
            InductorTree(5, ((0, 1), (1, 3), (1, 4), (1, 2))),
            ('LQP02HV',) * 4, (0, 1, 3, 2), ((0, 1), (1, 3), (3, 2)),
            CapacitorPlacement(5, ((0, 1), (4, -1), (1, 2), (3, -1)),
                               ((0, 3), (1, 2)), ((0, 3), (1, 2))),
            ('GJM01', 'GJM01', 'GJM01', 'PCB_PATTERN_C'), ('bridge', 'bridge'))
        three = build_nominal_circuit(load_constraint('RF-T008', allow_trial=True), definition)
        default_box = SampledEpigraph(three, 2).box
        narrow_box = SampledEpigraph(three, 2, gjm_search_max_pf=10).box
        self.assertEqual([i for i, (a, b) in enumerate(zip(default_box.bounds, narrow_box.bounds))
                          if a != b], [4, 5, 6])
        self.assertEqual(narrow_box.bounds[4:7], ((0., 10.),) * 3)
        self.assertEqual(default_box.open_lower, narrow_box.open_lower)
        for invalid in (0, -1, 101, float('nan'), True, '10'):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                SampledEpigraph(p.circuit, 2, gjm_search_max_pf=invalid)
        for invalid in (0., 11.):
            vector = physical.copy()
            vector[4] = invalid
            with self.subTest(seed=invalid), self.assertRaises(ValueError):
                seed(limited, vector)
        vector = physical.copy()
        vector[-1] = 4.
        with self.assertRaisesRegex(ValueError, 'clipping is forbidden'):
            seed(limited, vector)
        with self.assertRaisesRegex(ValueError, 'Jitter'):
            seed(limited, physical, jitter_fraction=.01)
        start = seed(base, physical)
        source = {'kind': 'synthetic', 'git_head': 'a' * 40,
                  'dirty_patch_sha256': 'b' * 64, 'input_source_sha256': 'c' * 64}
        seen = []
        def optimizer(problem, vector, maxiter, target):
            seen.append(problem.box.bounds[4])
            return vector, dict(success=True, status=0, message='ok', nit=1, nfev=1)
        args = dict(method='D', cost_meter=SampleBudgetCost(100000),
                    source_provenance=source, optimize_stage=optimizer,
                    record_sink=lambda snapshot: None, gjm_search_max_pf=10,
                    stop_after='all_20.0')
        clipped = dict(start, changes=[{'index': 4, 'kind': 'clip'}])
        with self.assertRaisesRegex(ValueError, 'must not be clipped or jittered'):
            run_c1_continuation(p.circuit, clipped, **args)
        result = run_c1_continuation(p.circuit, start, **args)
        self.assertEqual(result['state'], 'diagnostic_end_at_20db')
        self.assertEqual(result['stages'][-1]['label'], 'all_20.0')
        self.assertIsNone(result['final_exchange'])
        self.assertGreater(len(seen), 2)
        self.assertTrue(all(hi <= 10 for _, hi in seen))
        def illegal(problem, vector, maxiter, target):
            vector[4] = 11.
            return vector, dict(success=True, status=0, message='ok', nit=1, nfev=1)
        args.update(cost_meter=SampleBudgetCost(100000), optimize_stage=illegal)
        result = run_c1_continuation(p.circuit, start, **args)
        self.assertEqual(result['state'], 'failed')
        call = result['stages'][0]['record']['stage_calls'][0]
        self.assertEqual(call['output_vector'][4], 11.)
        self.assertEqual(call['observation']['box']['state'], 'fail')
        self.assertNotEqual(result['last_valid_vector'][4], 11.)
        def status4_at_20(problem, vector, maxiter, target):
            code = 4 if problem.search_stop_db == 20. else 0
            return vector, dict(success=code == 0, status=code, message='status', nit=1, nfev=1)
        args.update(cost_meter=SampleBudgetCost(100000), optimize_stage=status4_at_20)
        result = run_c1_continuation(p.circuit, start, **args)
        self.assertEqual(result['state'], 'failed')
        self.assertEqual(result['stages'][-1]['label'], 'all_20.0')
        self.assertEqual(len(result['stages'][-1]['record']['stage_calls']), 1)
        self.assertEqual(result['stages'][-1]['record']['stage_calls'][0]['status']['status'], 4)
        self.assertIsNone(result['final_exchange'])
        args.update(cost_meter=SampleBudgetCost(0), optimize_stage=optimizer)
        self.assertEqual(run_c1_continuation(p.circuit, start, **args)['state'], 'budget_exhausted')

    def test_working_staged_reseeds_and_fails_closed_on_illegal_output(self):
        from test_phase2_problem_seed import make, seed
        from lpf.phase2_models.evaluation_cost import SampleBudgetCost
        from lpf.phase2_models.staged_optimization import run_c1_staged
        p, physical = make("RF-T008", 4)
        p = SampledEpigraph(p.circuit, 2)
        start = seed(p, physical)
        warm = list(start['vector'])
        warm[-1] = 999.
        calls = []
        def optimizer(problem, vector, maxiter, target):
            calls.append(vector.copy())
            self.assertEqual(problem.settings, ('B8',))
            self.assertIsNone(problem.search_stop_db)
            self.assertEqual(problem.box.bounds[0], (physical[0], physical[0]))
            return vector, dict(success=True, status=0, message='ok', nit=1, nfev=1)
        kwargs = dict(coarse_points=2, fine_points=3, warm_start_vector=warm,
                      working_configuration=dict(settings=['B8'], stop_db=None, fixed_indices=[0]),
                      cost_meter=SampleBudgetCost(10000))
        record = run_c1_staged(p.circuit, start, optimize_stage=optimizer, **kwargs)
        self.assertEqual(record['numerical_state'], 'converged')
        self.assertEqual(len(calls), 2)
        selected = SampledEpigraph(p.circuit, 2, settings=('B8',), working_stop_db=None)
        expected = max(selected.evaluator.il(physical)[selected.evaluator.role == 0])
        self.assertAlmostEqual(calls[0][-1], expected)
        self.assertIsNone(record['stage_calls'][0]['observation']['sampled_rf']['h2_min_residual_db'])
        def illegal(problem, vector, maxiter, target):
            vector[0] += 1.
            return vector, dict(success=True, status=0, message='ok', nit=1, nfev=1)
        kwargs['cost_meter'] = SampleBudgetCost(10000)
        record = run_c1_staged(p.circuit, start, optimize_stage=illegal, **kwargs)
        self.assertEqual(record['numerical_state'], 'failed')
        self.assertEqual(len(record['stage_calls']), 1)

    def test_continuation_methods_and_budget_stop_with_mock_optimizer(self):
        from test_phase2_problem_seed import make, seed
        from lpf.phase2_models.evaluation_cost import SampleBudgetCost
        from lpf.phase2_models.staged_optimization import run_c1_continuation
        p, physical = make('RF-T008', 4)
        p = SampledEpigraph(p.circuit, 2)
        start = seed(p, physical)
        source = {'kind': 'synthetic', 'git_head': 'a' * 40,
                  'dirty_patch_sha256': 'b' * 64, 'input_source_sha256': 'c' * 64}
        def optimizer(problem, vector, maxiter, target):
            return vector, dict(success=True, status=0, message='ok', nit=1, nfev=1)
        for method in ('A', 'B', 'C', 'D'):
            with self.subTest(method=method):
                result = run_c1_continuation(p.circuit, start, method=method,
                    cost_meter=SampleBudgetCost(100000), source_provenance=source,
                    optimize_stage=optimizer, record_sink=lambda snapshot: None)
                self.assertEqual(result['state'], 'completed')
                labels = [item['label'] for item in result['stages']]
                self.assertEqual([label for label in labels if label.startswith('all_')],
                                 ([] if method in ('A', 'C') else
                                  (['all_il_only'] if method == 'B' else []) +
                                  ['all_10.0', 'all_20.0', 'all_25.0', 'all_28.0']))
                if method in ('C', 'D'):
                    self.assertEqual(result['b8_initial_zero_vector'][-3:-1], [0., 0.])
                    self.assertEqual(labels[0], 'B8_il_only')
                    self.assertEqual(labels[1], 'adjust_B71')
                    all_bands = next(item for item in result['stages'] if
                                     item['label'].startswith('bands_') and
                                     'B13+B14' in item['label'])
                    self.assertEqual(len(all_bands['record']['working_configuration']['settings']), 6)
                    self.assertNotIn(len(physical)-1, all_bands['record']['working_configuration']['fixed_indices'])
                self.assertEqual(result['final_exchange']['stop_db'], 30.005)
                self.assertFalse(result['rf_compliance_certified'])
        result = run_c1_continuation(p.circuit, start, method='B',
            cost_meter=SampleBudgetCost(0), source_provenance=source,
            optimize_stage=optimizer, record_sink=lambda snapshot: None)
        self.assertEqual(result['state'], 'budget_exhausted')
        self.assertEqual(result['last_valid_vector'], list(start['vector']))
        from lpf.phase2_models.evaluation_cost import SampleBudgetExceeded
        def interrupted_fine(problem, vector, maxiter, target):
            if problem.points_per_interval == 3:
                raise SampleBudgetExceeded('mock budget')
            vector[0] += 0.1
            return vector, dict(success=True, status=0, message='ok', nit=1, nfev=1)
        result = run_c1_continuation(p.circuit, start, method='B',
            cost_meter=SampleBudgetCost(10000), source_provenance=source,
            optimize_stage=interrupted_fine, record_sink=lambda snapshot: None)
        self.assertEqual(result['state'], 'budget_exhausted')
        self.assertAlmostEqual(result['last_valid_vector'][0], physical[0] + 0.1)
        def nonconverged(problem, vector, maxiter, target):
            return vector, dict(success=False, status=4, message='failed', nit=1, nfev=1)
        result = run_c1_continuation(p.circuit, start, method='B',
            cost_meter=SampleBudgetCost(10000), source_provenance=source,
            optimize_stage=nonconverged, record_sink=lambda snapshot: None)
        self.assertEqual(result['state'], 'not_converged')
        self.assertEqual(len(result['stages']), 1)
        self.assertIsNone(result['final_exchange'])
        snapshots = []
        def illegal_final(problem, vector, maxiter, target):
            vector[0] = -1.
            return vector, dict(success=True, status=0, message='bad', nit=1, nfev=1)
        result = run_c1_continuation(p.circuit, start, method='A',
            cost_meter=SampleBudgetCost(10000), source_provenance=source,
            optimize_stage=illegal_final, record_sink=snapshots.append)
        self.assertEqual(result['state'], 'failed')
        self.assertEqual(len(result['final_stage']['stage_calls']), 1)
        self.assertEqual(result['final_stage']['numerical_state'], 'failed')
        self.assertTrue(any(row.get('final_stage', {}).get('stage_calls') for row in snapshots))
        self.assertEqual(result['last_valid_vector'], list(start['vector']))
        def broken_sink(_):
            raise OSError('storage unavailable')
        with self.assertRaises(Exception):
            run_c1_continuation(p.circuit, start, method='A',
                cost_meter=SampleBudgetCost(10000), source_provenance=source,
                optimize_stage=optimizer, record_sink=broken_sink)
        def late_failure(snapshot):
            if snapshot.get('final_stage', {}).get('stage_calls'):
                raise OSError('late storage failure')
        with self.assertRaisesRegex(Exception, 'record sink failed'):
            run_c1_continuation(p.circuit, start, method='A',
                cost_meter=SampleBudgetCost(10000), source_provenance=source,
                optimize_stage=optimizer, record_sink=late_failure)

    def test_scipy_fixed_coordinate_with_synthetic_problem(self):
        from types import SimpleNamespace
        from lpf.phase2_models.problem_seed import VectorBox
        from lpf.phase2_models.staged_optimization import scipy_slsqp_stage
        problem = SimpleNamespace(
            box=VectorBox(((1., 1.), (0., 5.), (None, None)), ()),
            objective=lambda v: v[-1],
            residuals=lambda v: np.array([v[-1] - (v[1] - 2.) ** 2 - 1.]))
        output, status = scipy_slsqp_stage(problem, [1., 0., 5.], 30, None)
        self.assertTrue(status['success'])
        self.assertEqual(output[0], 1.)
        self.assertAlmostEqual(output[1], 2., places=3)
        self.assertAlmostEqual(output[2], 1., places=4)
        self.assertGreaterEqual(problem.residuals(output)[0], -1e-6)

    def test_invalid_vectors_and_non_spd(self):
        p = SampledEpigraph(circuit("RF-T005"), 1)
        x = np.array([2., 3., 4., .1, .01, -.02, .01, 7.])
        for invalid in (x[:-1], np.r_[x[:-1], np.nan]):
            with self.assertRaises(ValueError):
                p.residuals(invalid)
        x[4:7] = (-.9, -.9, -.9)
        with self.assertRaises(CircuitNumericalError):
            p.residuals(x)

    def test_independent_instances_and_policy_copy(self):
        a = SampledEpigraph(circuit("RF-T005"), 1)
        b = SampledEpigraph(circuit("RF-T007"), 2)
        x = np.array([2., 3., 4., .1, .01, -.02, .01, 7.])
        before = a.residuals(x)
        b.residuals(x)
        a.circuit.resolved_policy["evaluation"]["full_phase2"]["minimum_h2_h3_db"] = 0
        np.testing.assert_array_equal(a.residuals(x), before)
        self.assertEqual(a.mandatory_stop_db, 30)


if __name__ == "__main__":
    unittest.main()

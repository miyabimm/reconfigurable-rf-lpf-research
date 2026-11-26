"""Independent finite differences for Issue #499 nodal sensitivities."""
import unittest
import json
from pathlib import Path
from unittest.mock import patch
import numpy as np

from test_issue307_constraints import make
from test_issue309_rf_core import grid


class NodalSensitivityTests(unittest.TestCase):
    def test_undefined_transmission_and_spd_fail_closed(self):
        from lpf.rf_core.numerical_diagnostics import CircuitNumericalError
        _, _, model, _, x = make('RF-T008')
        evaluator = model.evaluator(grid(model.resolved_policy))
        bad = x.copy()
        bad[model.schema.n_inductors + model.schema.n_fixed] = 10
        with self.assertRaises(CircuitNumericalError) as normal:
            evaluator.evaluate(bad)
        with self.assertRaises(CircuitNumericalError) as sensitivity:
            evaluator.evaluate_with_il_jacobian(bad)
        self.assertEqual(normal.exception.code, 'mutual_not_spd')
        self.assertEqual(sensitivity.exception.code, normal.exception.code)
        zeros = np.zeros_like(evaluator.pre)
        with patch('lpf.rf_core.model._cascade', return_value=zeros):
            with self.assertRaises(CircuitNumericalError) as failure:
                evaluator.evaluate_with_il_jacobian(x)
            self.assertEqual(failure.exception.code, 'sensitivity_zero_transmission')

    def test_packed_sensitivity_solves_fail_closed(self):
        from lpf.rf_core.numerical_diagnostics import CircuitNumericalError
        _, _, model, _, x = make('RF-T008')
        evaluator = model.evaluator(grid(model.resolved_policy))
        solve = np.linalg.solve
        # Y-to-S and power-wave sensitivity solves, with all directions packed
        # into 2*p RHS columns. The Schur sensitivity solve no longer exists.
        for failing, behavior in ((1, 'raise'), (2, 'raise'), (1, 'nan'), (2, 'nan')):
            calls = []
            def injected(a, b):
                if a.ndim == 3 and b.ndim == 3 and b.shape[-1] == 2*len(x):
                    calls.append(a.shape)
                    if len(calls) == failing:
                        if behavior == 'raise':
                            raise np.linalg.LinAlgError('injected')
                        result = solve(a, b)
                        result[...] = np.nan
                        return result
                return solve(a, b)
            with self.subTest(failing=failing, behavior=behavior), patch('numpy.linalg.solve', side_effect=injected):
                with self.assertRaises(CircuitNumericalError) as failure:
                    evaluator.evaluate_with_il_jacobian(x)
                self.assertEqual(failure.exception.code,
                    'sensitivity_nonfinite' if behavior == 'nan' else 'sensitivity_solve_failed')
                self.assertEqual(len(calls), failing if behavior == 'raise' else 2)

    def test_forward_schur_failure_and_sample_index(self):
        from lpf.rf_core.numerical_diagnostics import CircuitNumericalError
        _, _, model, _, x = make('RF-T008')
        evaluator = model.evaluator(grid(model.resolved_policy))
        solve = np.linalg.solve
        for mode in ('singular', 'nonfinite'):
            def injected(a, b):
                # The first three-dimensional solve is the forward Schur solve.
                if a.ndim == 3:
                    if mode == 'singular':
                        raise np.linalg.LinAlgError('injected')
                    result = solve(a, b)
                    result[3] = np.nan
                    return result
                return solve(a, b)
            with self.subTest(mode=mode), patch('numpy.linalg.solve', side_effect=injected):
                with self.assertRaises(CircuitNumericalError) as failure:
                    evaluator.evaluate_with_il_jacobian(x)
                self.assertEqual(failure.exception.code,
                    'schur_solve_failed' if mode == 'singular' else 'schur_nonfinite')
                if mode == 'nonfinite':
                    self.assertEqual(failure.exception.sample_index, 3)

    def test_external_response_and_all_columns(self):
        policy, _, model, _, x = make('RF-T008')
        x[10], x[13] = .03, -.04
        x[-12:] = np.linspace(.4, 2.4, 12)
        evaluator = model.evaluator(grid(policy))
        response, jac = evaluator.evaluate_with_il_jacobian(x)
        expected = evaluator.evaluate(x)
        for name in ('s', 'il_db', 'apl_db', 'in_rl_db', 'out_rl_db'):
            np.testing.assert_allclose(getattr(response, name), getattr(expected, name), rtol=1e-12, atol=1e-12)
        for j in range(len(x)):
            h = 1e-5 * max(1., abs(x[j]))
            plus, minus = x.copy(), x.copy()
            plus[j] += h
            minus[j] -= h
            fd = (evaluator.evaluate(plus).il_db - evaluator.evaluate(minus).il_db)/(2*h)
            np.testing.assert_allclose(jac[:, j], fd, rtol=1e-4, atol=1e-5, err_msg=f'column {j}')

    def test_t010_normalized_all_columns_on_search_grid(self):
        from lpf.search.development_plan import freeze_run
        from lpf.search.plan import grid_from_record
        from lpf.minimax_profile import _margin_parameters
        from lpf.minimax_profile import least_squares_residual_and_jacobian
        root = Path(__file__).resolve().parents[1]
        config = json.loads((root/'project/diagnostics/issue470/config.json').read_text())
        step = config['arms'][0]['steps'][0]
        step['solver'] = 'lbfgsb'
        step['options']['max_evaluations'] = step['options'].pop('max_search_forwards')
        starts = json.loads((root/'project/diagnostics/issue470/starts.json').read_text())
        config['arms'][0]['steps'][0]['options'].update(max_evaluations=100000, batch_fd=True, partial_fd=True)
        config['budget'] = dict(rf_samples=70*(100000+24)+476, rf_forwards=100025, independent_mna_samples=2)
        plan, _, profile, model, _ = freeze_run(config, starts, root=root,
            spot_checks={'terminal': [0,111]}, search_bounds=None, checkpoint_interval=1000)
        evaluator = model.evaluator(grid_from_record(plan.data['grids']['baseline/search']))
        self.assertEqual(len(evaluator.grid.setting), 70)
        bounds = np.asarray(plan.data['search_bounds'])
        width = bounds[:, 1]-bounds[:, 0]
        x0 = np.asarray(starts['1013']['baseline']['vector'])
        threshold, direction = _margin_parameters(profile, evaluator.grid)
        for x in (x0, x0 + width * np.linspace(-.001, .001, len(x0))):
            response, jac = evaluator.evaluate_with_il_jacobian(x)
            original = evaluator.evaluate(x)
            for name in ('s', 'il_db', 'apl_db', 'in_rl_db', 'out_rl_db'):
                np.testing.assert_allclose(getattr(response, name), getattr(original, name), rtol=1e-12, atol=1e-12)
            residual, rjac = least_squares_residual_and_jacobian(profile, response, jac)
            margin = direction * (response.il_db-threshold)
            self.assertGreater(np.min(np.abs(margin)), 1e-5)
            for h in (1e-6, 3e-6):
                for j in range(len(x)):
                    plus, minus = x.copy(), x.copy()
                    plus[j] += h*width[j]; minus[j] -= h*width[j]
                    a, b = evaluator.evaluate(plus), evaluator.evaluate(minus)
                    fd = (a.il_db-b.il_db)/(2*h)
                    np.testing.assert_allclose(jac[:,j]*width[j], fd, rtol=1e-4, atol=1e-5, err_msg=f'h={h} column={j}')
                    fm = direction*fd
                    np.testing.assert_allclose(direction*jac[:,j]*width[j], fm, rtol=1e-4, atol=1e-5)
                    ra = np.sqrt(2)*np.maximum(direction*(a.il_db-threshold), 0)
                    rb = np.sqrt(2)*np.maximum(direction*(b.il_db-threshold), 0)
                    np.testing.assert_allclose(rjac[:,j]*width[j], (ra-rb)/(2*h), rtol=1e-4, atol=1e-5)
        # Individually move each coordinate near its nearest bound; other
        # coordinates remain at the valid seed. Two-point inward difference.
        for j in range(len(x0)):
            x = x0.copy()
            low = (x0[j]-bounds[j, 0]) < (bounds[j, 1]-x0[j])
            sign = 1 if low else -1
            x[j] = bounds[j, 0 if low else 1] + sign*1e-5*width[j]
            response, jac = evaluator.evaluate_with_il_jacobian(x)
            h = 1e-6
            x1, x2 = x.copy(), x.copy()
            x1[j] += sign*h*width[j]; x2[j] += sign*2*h*width[j]
            fd = sign*(-3*response.il_db + 4*evaluator.evaluate(x1).il_db - evaluator.evaluate(x2).il_db)/(2*h)
            np.testing.assert_allclose(jac[:,j]*width[j], fd, rtol=1e-4, atol=1e-5, err_msg=f'boundary column={j}')

    def test_physical_units_all_columns_and_setting_zeros(self):
        _, _, model, _, x = make('RF-T008')
        x[10], x[13] = .03, -.04
        x[-12:] = np.linspace(.4, 2.4, 12)
        topology, schema = model.topology, model.schema
        omega = 2 * np.pi * np.linspace(.8e9, 3e9, 6)
        settings = np.arange(6)
        values = model.decode(x)
        y, jac = topology.node_admittance_with_jacobian(values, schema, omega, settings)
        np.testing.assert_array_equal(y, topology.node_admittance(values, omega, settings))
        for j in range(len(x)):
            h = 1e-5 * max(1., abs(x[j]))
            plus, minus = x.copy(), x.copy()
            plus[j] += h
            minus[j] -= h
            fd = (topology.node_admittance(model.decode(plus), omega, settings)
                  - topology.node_admittance(model.decode(minus), omega, settings)) / (2*h)
            np.testing.assert_allclose(jac[:, j], fd, rtol=1e-7, atol=1e-10, err_msg=f'column {j}')
        start = len(x) - 6 * schema.n_variable
        for s in range(6):
            np.testing.assert_array_equal(jac[settings != s, start+s*schema.n_variable:start+(s+1)*schema.n_variable], 0)


if __name__ == '__main__':
    unittest.main()

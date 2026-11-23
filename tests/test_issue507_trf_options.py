"""Issue 507: strict options and unchanged TRF defaults."""
import copy
import unittest
from unittest.mock import patch
import numpy as np

from lpf.search.plan import validate_solver
from lpf.optimizers.least_squares import least_squares_local


class OptionsTests(unittest.TestCase):
    def test_validation(self):
        step = dict(solver='trf', aggregation='sum', objective='signed_margin_db', options={'max_evaluations': 5})
        for ftol in (None, 1e-8):
            for scale in (1.0, 'jac'):
                test = copy.deepcopy(step)
                test['options'].update(ftol=ftol, x_scale=scale)
                validate_solver(test)
        for key, values in {'ftol': [0, -1, float('nan'), float('inf'), True, '1'],
                            'x_scale': [0, 2, True, [1.0], 'JAC', None],
                            'xtol': [1e-8], 'gtol': [1e-8], 'unknown': [1]}.items():
            for value in values:
                test = copy.deepcopy(step)
                test['options'][key] = value
                with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                    validate_solver(test)

    def test_options_and_defaults(self):
        def evaluate(x):
            return np.array([x[0]-.2, 2*(x[1]-.8)]), np.array([[1., 0., 0.], [0., 2., 0.]])
        from scipy.optimize import least_squares
        results = []
        for options in ({}, {'ftol': 1e-8, 'x_scale': 1.0},
                        {'ftol': None, 'x_scale': 'jac'}):
            with patch('lpf.optimizers.least_squares.least_squares', wraps=least_squares) as call:
                result = least_squares_local(evaluate, [.5, .5, 3], [(0, 1), (0, 1), (3, 3)], **options)
                self.assertEqual(call.call_args.kwargs['ftol'], options.get('ftol', 1e-8))
                self.assertEqual(call.call_args.kwargs['x_scale'], options.get('x_scale', 1.0))
            self.assertTrue(result.success)
            self.assertGreaterEqual(result.optimality, 0)
            results.append(result)
        np.testing.assert_array_equal(results[0].x, results[1].x)
        self.assertEqual(results[0].objective, results[1].objective)
        self.assertEqual(results[0].nfev, results[1].nfev)
        self.assertEqual(results[0].status, results[1].status)

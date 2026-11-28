"""TRF staged controls are opt-in and retain exact restart accounting."""
from dataclasses import replace
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from lpf.optimizers.trf import _trf_local, trf_minimize
from lpf.search.plan import validate_solver
from lpf.search.development_plan import solver_options


class StagedTRFTests(unittest.TestCase):
    def test_best_center_and_default_last(self):
        def evaluate(x):
            return np.array([x[0]]), np.array([[1.]])
        def run(center):
            starts = []
            def local(callback, x, bounds, **kwargs):
                starts.append(np.array(x))
                r = _trf_local(callback, x, bounds, **{**kwargs, 'max_evaluations': 1})
                return replace(r, x=np.array([.9]), success=len(starts) == 1,
                               status=1 if len(starts) == 1 else 0)
            opts = {} if center is None else {'restart_center': center}
            with patch('lpf.optimizers.trf._trf_local', side_effect=local):
                trf_minimize(evaluate, [.2], [(0., 1.)], seed=2, max_evaluations=2,
                             restart_sigma=.1, ftol=1e-6, x_scale=1., **opts)
            return starts[1][0]
        noise = np.random.default_rng(2).normal(0, .1)
        self.assertAlmostEqual(run(None), .9 + noise)
        self.assertAlmostEqual(run('last'), .9 + noise)
        self.assertAlmostEqual(run('best'), .2 + noise)

    def test_target_budget_boundary_and_failure(self):
        def evaluate(x):
            return np.array([x[0]]), np.array([[1.]])
        def run(status, target, limit=1, sigma=.1):
            def local(callback, x, bounds, **kwargs):
                r = _trf_local(callback, x, bounds, **kwargs)
                return replace(r, success=status > 0, status=status)
            with patch('lpf.optimizers.trf._trf_local', side_effect=local):
                return trf_minimize(evaluate, [.2], [(0., 1.)], seed=0, max_evaluations=limit,
                                    restart_sigma=sigma, ftol=1e-6, x_scale=1., target_objective=target)
        reached = run(0, .03)
        self.assertEqual(reached.stop_reason, 'target_reached')
        self.assertFalse(reached.converged)
        self.assertEqual(run(0, .01).stop_reason, 'evaluation_budget_exhausted')
        self.assertEqual(run(-1, .03).stop_reason, 'solver_failure')
        self.assertEqual(run(1, .03, sigma=None).stop_reason, 'target_reached')
        self.assertTrue(run(1, .03, sigma=None).converged)

    def test_options_validation_and_legacy_effective_options(self):
        step = dict(solver='trf', aggregation='sum', objective='signed_margin_db',
                    options=dict(max_evaluations=3))
        before = solver_options(step)
        self.assertNotIn('target_objective', before)
        self.assertNotIn('restart_center', before)
        for key, values in [('target_objective', [-1, True, float('inf'), '1']),
                            ('restart_center', ['other', None, True])]:
            for value in values:
                step['options'][key] = value
                with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                    validate_solver(step)
            del step['options'][key]
        step['options'].update(restart_center='best', target_objective=0.)
        validate_solver(step)
        self.assertEqual(solver_options(step)['restart_center'], 'best')
        self.assertEqual(solver_options(step)['target_objective'], 0.)


if __name__ == '__main__':
    unittest.main()

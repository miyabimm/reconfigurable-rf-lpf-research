"""Solver-native result adaptation; synthetic deterministic callbacks only."""
from dataclasses import replace
from pathlib import Path
import sys
import unittest

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from lpf.optimizers.hybrid import hybrid_minimize
from lpf.optimizers.result import optimizer_result
from lpf.optimizers.slp import slp_minimize
from lpf.optimizers.slsqp import slsqp_minimize


class OptimizerResultTests(unittest.TestCase):
    def test_distinct_objectives_return_observed_pairs(self):
        for solver in ('slsqp', 'slp', 'hybrid'):
            with self.subTest(solver=solver):
                seen = {}
                observed = {}
                def observe(x, objective):
                    observed[tuple(x)] = objective
                def callback(x):
                    # Signed SLP uses a different objective from squared solvers.
                    r = np.array([x[0] - .4, .1 - x[0]])
                    seen[tuple(x)] = float(np.max(r) if solver == 'slp' else np.sum(r*r))
                    return r
                if solver == 'slsqp':
                    native = slsqp_minimize(callback, [.6], [(0., 1.)], max_iterations=3, max_evaluations=20,
                                            objective_callback=observe)
                elif solver == 'slp':
                    native = slp_minimize(callback, [.6], [(0., 1.)], aggregation='signed_max',
                                          max_iterations=3, max_evaluations=20, objective_callback=observe)
                else:
                    native = hybrid_minimize(callback, [.6], [(0., 1.)], seed=1,
                                             max_evaluations=20, restart_sigma=.1, objective_callback=observe)
                result = optimizer_result(native)
                self.assertIn(result.x, seen)
                self.assertAlmostEqual(result.objective, seen[result.x])
                self.assertEqual(result.objective, observed[result.x])
                self.assertEqual(set(seen), set(observed))
                self.assertGreater(result.evaluations, 0)
                self.assertFalse(hasattr(result, 'violation'))
                self.assertFalse(hasattr(result, 'rf_margin_db'))
                if result.stop_reason in ('evaluation_limit', 'evaluation_budget_exhausted'):
                    self.assertFalse(result.converged)

    def test_missing_and_nonfinite_results_stop(self):
        native = hybrid_minimize(lambda x: [x[0]], [.5], [(0., 1.)], seed=0,
                                 max_evaluations=2, restart_sigma=.1)
        for broken in (replace(native, best_x=None), replace(native, best_fun=None),
                       replace(native, best_fun=float('nan')), replace(native, best_x=[float('inf')]),
                       replace(native, nfev=0), replace(native, stop_reason='invalid_residual')):
            with self.subTest(broken=broken), self.assertRaises(ValueError):
                optimizer_result(broken)


if __name__ == '__main__':
    unittest.main()

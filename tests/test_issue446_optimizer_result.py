"""Direct solver result contracts; synthetic deterministic callbacks only."""
from dataclasses import asdict
from pathlib import Path
import sys
import unittest

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from lpf.optimizers.hybrid import hybrid_minimize
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
                result = native  # The solver itself provides the common fields.
                key = tuple(result.x)
                self.assertIn(key, seen)
                self.assertAlmostEqual(result.objective, seen[key])
                self.assertEqual(result.objective, observed[key])
                self.assertEqual({'x', 'objective', 'converged', 'stop_reason', 'evaluations'}, set(asdict(result)))
                self.assertEqual(set(seen), set(observed))
                self.assertGreater(result.evaluations, 0)
                for key in ('violation', 'max_violation', 'rf_margin_db', 'fun', 'best_fun', 'best_x', 'runs'):
                    self.assertFalse(hasattr(result, key), key)
                if result.stop_reason in ('evaluation_limit', 'evaluation_budget_exhausted'):
                    self.assertFalse(result.converged)

    def test_constraint_callbacks_are_in_native_counts(self):
        for solver in ('slsqp', 'slp'):
            with self.subTest(solver=solver):
                calls = {'objective': 0, 'constraint': 0}
                seen = {}
                def objective(x):
                    calls['objective'] += 1
                    seen[tuple(x)] = (x[0] - .4)**2
                    return np.array([x[0] - .4])
                def constraint(x):
                    calls['constraint'] += 1
                    return np.array([x[0]])
                fn = slsqp_minimize if solver == 'slsqp' else slp_minimize
                result = fn(objective, [.6], [(0., 1.)], constraints=constraint,
                            max_iterations=2, max_evaluations=8)
                self.assertGreater(calls['constraint'], 0)
                self.assertEqual(result.evaluations, sum(calls.values()))
                self.assertAlmostEqual(result.objective, seen[tuple(result.x)])
                if result.stop_reason in ('evaluation_limit', 'evaluation_budget_exhausted'):
                    self.assertFalse(result.converged)

    def test_invalid_first_callback_exposes_no_candidate_and_never_converges(self):
        result = hybrid_minimize(lambda x: [float('nan')], [.5], [(0., 1.)], seed=0,
                                 max_evaluations=2, restart_sigma=.1)
        self.assertIsNone(result.x)
        self.assertIsNone(result.objective)
        self.assertFalse(result.converged)
        self.assertEqual(result.stop_reason, 'invalid_residual')
        self.assertEqual(result.evaluations, 1)


if __name__ == '__main__':
    unittest.main()

"""Deterministic callback-only frequency exchange tests; no SLSQP or EXP."""
import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from lpf.phase2_models.evaluation_cost import SampleBudgetCost
from lpf.phase2_models.frequency_exchange import FrequencyExchangeError, run_frequency_exchange


class Circuit:
    def validate_components(self, x):
        if len(x) != 1:
            raise ValueError('bad vector')


class Samples:
    def __init__(self, points, fn):
        self.f, self.fn = points, fn
    def il(self, vector):
        return [self.fn(p, vector) for p in self.f]


class ExchangeTests(unittest.TestCase):
    segments = [(2, 2, 30., 34.), (0, 0, 10., 14.), (1, 1, 20., 24.)]

    def invoke(self, fn, *, inner=None, budget=1000, **kwargs):
        calls = []
        def solver(circuit, vector, extras, meter):
            calls.append(extras)
            if inner:
                return inner(circuit, vector, extras, meter)
            return vector, {'numerical_state': 'converged'}
        def scan(circuit, vector, points, meter):
            return meter.forward(Samples(points, fn), vector)
        result = run_frequency_exchange(Circuit(), [1., 1.], self.segments,
            inner=solver, scan=scan, cost_meter=SampleBudgetCost(budget),
            scan_points=5, **kwargs)
        return result, calls

    def test_interior_ties_signs_and_stall(self):
        def values(point, _):
            seg, f = point
            if seg == 0:
                return 2. if f in (11., 13.) else 1.
            if seg == 1:
                return 29. if f == 21. else 31.
            return 31.
        result, calls = self.invoke(values, max_additions=2)
        self.assertEqual(calls, [(), ((0, 11.), (0, 13.)),
                                 ((0, 11.), (0, 13.), (1, 21.))])
        self.assertEqual(result['stop_reason'], 'stalled_existing_constraint')
        self.assertEqual(result['rounds'][0]['positive_violations'],
                         [[1., 0, 11.], [1., 0, 13.], [1., 1, 21.]])
        self.assertFalse(result['rounds'][0]['scan_strict30'])
        self.assertEqual(result['evaluation_cost']['frequency_samples_requested'], 60)
        self.assertFalse(result['rf_compliance_certified'])

    def test_no_violation_stall_limit_and_budget(self):
        clean = lambda p, x: 1. if p[0] == 0 else 30.
        result, calls = self.invoke(clean)
        self.assertEqual(result['stop_reason'], 'scan_no_new_violation')
        self.assertEqual(len(calls), 1)
        existing = lambda p, x: 2. if p == (0, 10.) else (1. if p[0] == 0 else 31.)
        self.assertEqual(self.invoke(existing)[0]['stop_reason'], 'stalled_existing_constraint')
        interior = lambda p, x: 2. if p == (0, 11.) else (1. if p[0] == 0 else 31.)
        self.assertEqual(self.invoke(interior, max_rounds=1)[0]['stop_reason'], 'max_rounds')
        result, _ = self.invoke(clean, budget=15)
        self.assertEqual(result['stop_reason'], 'budget_exhausted')
        self.assertEqual(result['evaluation_cost']['frequency_samples_requested'], 15)

    def test_real_c1_adapter_with_mock_solver_and_shared_meter(self):
        from test_phase2_problem_seed import make, seed
        from lpf.phase2_models.frequency_exchange_c1 import run_c1_frequency_exchange
        problem, x = make('RF-T008', 4)
        # The production contract fixes coarse=2 and derives t from that grid.
        from lpf.phase2_models.sampled_epigraph import SampledEpigraph
        coarse = SampledEpigraph(problem.circuit, 2)
        start = seed(coarse, x)
        stages = []
        def optimizer(p, vector, maxiter, target):
            stages.append((p.points_per_interval, maxiter))
            return vector, dict(success=True, status=0, message='ok', nit=1, nfev=1)
        meter = SampleBudgetCost(10000)
        result = run_c1_frequency_exchange(problem.circuit, start, cost_meter=meter,
                                           optimize_stage=optimizer, max_rounds=1)
        self.assertEqual(stages, [(2, 240), (3, 120)])
        self.assertEqual(result['stop_reason'], 'max_rounds')
        self.assertEqual(meter.frequency_samples_requested, 476 * 2 + 56 + 56 + 84)
        self.assertEqual(result['final_validation'], 'not_run')

    def test_callback_failure_and_bad_scan_fail_closed(self):
        def bad(*args):
            raise RuntimeError('failed')
        with self.assertRaises(FrequencyExchangeError) as error:
            self.invoke(lambda p, x: 30., inner=bad)
        self.assertEqual(error.exception.trace['stop_reason'], 'failed')
        with self.assertRaises(FrequencyExchangeError):
            self.invoke(lambda p, x: np.nan)
        with self.assertRaises(FrequencyExchangeError):
            self.invoke(lambda p, x: 30., inner=lambda *args: (np.array([1., 1.]),
                                                      {'numerical_state': 'failed'}))


if __name__ == '__main__':
    unittest.main()

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))

from lpf.timing import TimerCollector


class TimerCollectorTests(unittest.TestCase):
    def test_nested_inclusive_and_independent(self):
        one, two = TimerCollector(), TimerCollector()
        with patch('lpf.timing.perf_counter_ns', side_effect=[10, 20, 25, 40, 50, 65]):
            with one.measure('solver'):
                with one.measure('forward'):
                    pass
            with two.measure('solver'):
                pass
        self.assertEqual(one.snapshot()['solver']['wall_ns'], 30)
        self.assertEqual(one.snapshot()['forward']['wall_ns'], 5)
        self.assertEqual(two.snapshot()['solver']['wall_ns'], 15)
        self.assertNotIn('forward', two.snapshot())

    def test_worker_solver_wrapper_preserves_results_and_calls(self):
        from lpf.search.worker import _timed_solver
        timer = TimerCollector()
        calls = []
        def solver(value, *, option):
            calls.append((value, option))
            return value + option
        for name in ('hybrid', 'slsqp', 'slp'):
            self.assertEqual(_timed_solver(None, name, solver, 2, option=3), 5)
            self.assertEqual(_timed_solver(timer, name, solver, 2, option=3), 5)
        self.assertEqual(calls, [(2, 3)] * 6)
        self.assertEqual({name: row['count'] for name, row in timer.snapshot().items()},
                         {'hybrid': 1, 'slsqp': 1, 'slp': 1})

    def test_failure_and_snapshot_are_independent(self):
        timer = TimerCollector()
        with self.assertRaisesRegex(ValueError, 'bad'):
            with timer.measure('forward'):
                raise ValueError('bad')
        row = timer.snapshot()['forward']
        self.assertEqual((row['count'], row['failed']), (1, 1))
        row['count'] = 99
        self.assertEqual(timer.snapshot()['forward']['count'], 1)


if __name__ == '__main__':
    unittest.main()

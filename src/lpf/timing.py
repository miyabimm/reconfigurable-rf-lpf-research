"""Small opt-in inclusive wall-clock accumulator, independent of RF and solvers."""
from contextlib import contextmanager
from time import perf_counter_ns


class TimerCollector:
    """Accumulate inclusive durations without retaining per-call events.

    Each collector belongs to one job. Nested regions overlap and must not be
    summed as a breakdown of total time. A failed region is counted separately.
    """
    def __init__(self):
        self._regions = {}

    @contextmanager
    def measure(self, name):
        start = perf_counter_ns()
        failed = False
        try:
            yield
        except BaseException:
            failed = True
            raise
        finally:
            elapsed = perf_counter_ns() - start
            row = self._regions.setdefault(name, {'count': 0, 'wall_ns': 0, 'failed': 0})
            row['count'] += 1
            row['wall_ns'] += elapsed
            row['failed'] += int(failed)

    def snapshot(self):
        return {name: {**row, 'mean_wall_ns': row['wall_ns'] / row['count']}
                for name, row in self._regions.items()}

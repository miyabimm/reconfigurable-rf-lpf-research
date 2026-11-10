"""Small opt-in inclusive wall-clock accumulator, independent of RF and solvers."""
from contextlib import contextmanager
from functools import wraps
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
            self.add(name, elapsed, failed=failed)

    def add(self, name, wall_ns, *, failed=False):
        row = self._regions.setdefault(name, {'count': 0, 'wall_ns': 0, 'failed': 0})
        row['count'] += 1
        row['wall_ns'] += wall_ns
        row['failed'] += int(failed)

    def call(self, name, function, *args, **kwargs):
        with self.measure(name):
            return function(*args, **kwargs)

    def snapshot(self):
        return {name: {**row, 'mean_wall_ns': row['wall_ns'] / row['count']}
                for name, row in self._regions.items()}


def timed_method(name):
    """Instrument an existing method only when its owner has a collector."""
    def decorate(function):
        @wraps(function)
        def wrapped(self, *args, **kwargs):
            timer = getattr(self, 'timer', None)
            if timer is None:
                return function(self, *args, **kwargs)
            return timer.call(name, function, self, *args, **kwargs)
        return wrapped
    return decorate


def timed_call(timer, name, function, *args, **kwargs):
    if timer is None:
        return function(*args, **kwargs)
    return timer.call(name, function, *args, **kwargs)

"""Opt-in in-process cost counters; no cache, RF arithmetic or solver policy.

A forward call means entry to evaluator.il, including failures. Requested
samples are charged before entry; completed samples only after return. Early
failures have no invented count of partially solved frequencies. Counters count
check/callback events, not unique physical candidates. Not thread-safe.
"""
from contextlib import contextmanager
from copy import copy
from dataclasses import asdict, dataclass
import time


def _spd_error(exc):
    # Existing component validator uses ValueError; forward uses a typed code.
    return (getattr(exc, 'code', None) == 'mutual_not_spd' or
            str(exc) == 'Full inductance matrix is non-positive-definite or ill-conditioned')


@dataclass
class EvaluationCost:
    RF_forward_calls: int = 0
    frequency_samples_requested: int = 0
    frequency_samples_completed: int = 0
    forward_failures: int = 0
    component_checks: int = 0
    component_rejections: int = 0
    spd_rejections: int = 0
    box_rejections: int = 0
    role_rejections: int = 0
    cache_hits: int = 0
    solver_objective_calls: int = 0
    solver_constraint_calls: int = 0
    wall_seconds: float = 0.
    cpu_seconds: float = 0.

    def snapshot(self):
        return asdict(self)

    @contextmanager
    def timed(self):
        """Whole measured operation, including cache/checks and solver overhead."""
        wall, cpu = time.perf_counter(), time.process_time()
        try:
            yield
        finally:
            self.wall_seconds += time.perf_counter() - wall
            self.cpu_seconds += time.process_time() - cpu

    def forward(self, evaluator, vector):
        self.RF_forward_calls += 1
        self.frequency_samples_requested += len(evaluator.f)
        try:
            result = evaluator.il(vector)
        except BaseException as exc:
            self.forward_failures += 1
            self.spd_rejections += int(_spd_error(exc))
            raise
        self.frequency_samples_completed += len(evaluator.f)
        return result

    def components(self, circuit, vector, *, allow_absent_gjm=False):
        self.component_checks += 1
        try:
            if allow_absent_gjm:
                return circuit.validate_components(vector, allow_absent_gjm=True)
            return circuit.validate_components(vector)
        except BaseException as exc:
            self.component_rejections += 1
            self.spd_rejections += int(_spd_error(exc))
            raise

    def callback(self, function, *, constraint=False):
        def measured(vector):
            if constraint:
                self.solver_constraint_calls += 1
            else:
                self.solver_objective_calls += 1
            return function(vector)
        return measured

    def epigraph(self, problem):
        """Private shallow view: do not mutate the caller's C1 problem/circuit.

        NormalizedEpigraph's existing component checks pass through this view.
        No additional validation is inserted into the physical SLSQP path.
        """
        measured = copy(problem)
        measured.evaluator = _ForwardView(problem.evaluator, self)
        measured.circuit = _CircuitView(problem.circuit, self)
        return measured


class _ForwardView:
    def __init__(self, original, cost):
        self.original, self.cost = original, cost

    def __getattr__(self, name):
        return getattr(self.original, name)

    def il(self, vector):
        return self.cost.forward(self.original, vector)


class _CircuitView:
    def __init__(self, original, cost):
        self.original, self.cost = original, cost

    def __getattr__(self, name):
        return getattr(self.original, name)

    def validate_components(self, vector, *, allow_absent_gjm=False):
        return self.cost.components(
            self.original, vector, allow_absent_gjm=allow_absent_gjm)

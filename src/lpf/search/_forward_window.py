"""Arithmetic for the opt-in development forward reservation (no I/O).

A window must be persisted and read back by its caller before any forward.
This module does not implement a runner, recovery, or permission to release an
uncertain reservation. Sample counts, not optimizer iterations, are charged.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class ForwardWindow:
    first_forward: int  # zero based, inclusive
    forward_count: int
    samples_per_forward: int

    @property
    def end_forward(self):
        return self.first_forward + self.forward_count

    @property
    def reserved_samples(self):
        return self.forward_count * self.samples_per_forward


def reserve_forward_window(*, first_forward, samples_per_forward, step_remaining,
                           job_remaining, trial_remaining, job_reserved,
                           trial_reserved):
    """Calculate at most 100 full forwards without invading inactive allocations.

    All remaining amounts include the current allocation; job_reserved and
    trial_reserved are the portions held for other allocations/jobs. Return
    None if not even one full grid fits. The returned window is only a plan:
    it is not authorization to evaluate until durable persistence and readback.
    """
    values = (first_forward, step_remaining, job_remaining, trial_remaining,
              job_reserved, trial_reserved)
    if any(type(v) is not int or v < 0 for v in values):
        raise ValueError('Expected nonnegative integer counts and reservations')
    if type(samples_per_forward) is not int or samples_per_forward <= 0:
        raise ValueError('Expected positive integer samples per forward')
    available = min(step_remaining, job_remaining - job_reserved,
                    trial_remaining - trial_reserved)
    if available < 0:
        raise ValueError('Existing reservations exceed remaining budget')
    count = min(100, available // samples_per_forward)
    if not count:
        return None
    return ForwardWindow(first_forward, count, samples_per_forward)

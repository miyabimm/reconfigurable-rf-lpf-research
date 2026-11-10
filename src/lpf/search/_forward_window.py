"""Arithmetic for the opt-in development forward reservation (no I/O).

A window must be persisted and read back by its caller before any forward.
This module does not implement a runner, recovery, or permission to release an
uncertain reservation. Sample counts, not optimizer iterations, are charged.
"""
from dataclasses import dataclass
from pathlib import Path
import os

from lpf.timing import timed_method
from .storage import atomic_verified


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


class ForwardJournal:
    """Pre-reserved development windows. The caller owns RF and candidate data.

    The checkpoint is authoritative only after verified readback. In-flight work
    and every unconfirmed forward remain covered by the *entire* durable window.
    A failed verification, persistence or evaluation permanently stops this
    object; there is deliberately no restore, retry, or reservation release API.
    """
    def __init__(self, path, *, identity, validate_inputs, snapshot, budget):
        self.path = Path(path)
        self.identity = identity
        self.validate_inputs = validate_inputs
        self.snapshot = snapshot
        self.budget = budget
        self.forward_count = self.requested = self.completed = 0
        self.inflight = False
        self.window = None
        self.checkpoint_number = 0
        self.write_calls = self.written_bytes = self.read_calls = self.read_bytes = 0
        self.failed = False
        self.started = False
        self.last_record = None

    def _stop_on_error(self, operation):
        if self.failed:
            raise RuntimeError('STOP: journal failed; no retry')
        try:
            return operation()
        except BaseException:
            self.failed = True
            raise

    @timed_method('window_checkpoint_save')
    def _save(self, *, reserve):
        if self.inflight:
            raise RuntimeError('Cannot confirm an in-flight forward')
        self.validate_inputs()
        window = reserve_forward_window(first_forward=self.forward_count, **self.budget()) if reserve else None
        lower = dict(forwards=self.forward_count, requested=self.requested, completed=self.completed)
        upper = dict(forwards=self.forward_count + (window.forward_count if window else 0),
                     requested=self.requested + (window.reserved_samples if window else 0),
                     completed=self.completed + (window.reserved_samples if window else 0))
        previous = (self.last_record['confirmed'] if self.last_record is not None else
                    dict(forwards=0, requested=0, completed=0))
        record = dict(kind='development_forward_window_v1', identity=self.identity,
                      checkpoint_number=self.checkpoint_number + 1, confirmed=lower,
                      previous_confirmed=previous,
                      previous_uncertain_upper=(self.last_record['uncertain_upper'] if self.last_record is not None else previous),
                      uncertain_upper=upper, window=None if window is None else dict(
                          first_forward=window.first_forward, end_forward=window.end_forward,
                          samples_per_forward=window.samples_per_forward,
                          reserved_samples=window.reserved_samples),
                      io_before=dict(write_calls=self.write_calls, written_bytes=self.written_bytes,
                                     read_calls=self.read_calls, read_bytes=self.read_bytes),
                      payload=self.snapshot())
        measured = atomic_verified(self.path, record)
        self.write_calls += measured['write_calls']
        self.written_bytes += measured['written_bytes']
        self.read_calls += measured['read_calls']
        self.read_bytes += measured['read_bytes']
        self.window = window
        self.checkpoint_number += 1
        self.last_record = record
        return window

    def start(self):
        def operation():
            if self.started:
                raise RuntimeError('Journal already started')
            # Claim the name exclusively; no existing raw, even an empty one,
            # is ever overwritten or interpreted as a retryable fresh run.
            fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            os.close(fd)
            self.started = True
            return self._save(reserve=True)
        return self._stop_on_error(operation)

    def begin_forward(self):
        def operation():
            if not self.started or self.inflight or self.window is None:
                raise RuntimeError('STOP: no persisted forward window')
            if not self.window.first_forward <= self.forward_count < self.window.end_forward:
                raise RuntimeError('STOP: persisted window exhausted')
            self.inflight = True
            self.requested += self.window.samples_per_forward
        return self._stop_on_error(operation)

    def complete_forward(self):
        def operation():
            if not self.inflight:
                raise RuntimeError('No forward in flight')
            self.completed += self.window.samples_per_forward
            self.forward_count += 1
            self.inflight = False
            if self.forward_count == self.window.end_forward:
                self._save(reserve=True)
        return self._stop_on_error(operation)

    def boundary(self, *, reserve):
        """Confirm a partial window at a successful state/step/job boundary."""
        def operation():
            if not self.started or self.inflight:
                raise RuntimeError('Cannot confirm an unstarted/in-flight window')
            return self._save(reserve=reserve)
        return self._stop_on_error(operation)

    def abort(self, reason=None):
        """Save diagnostics if possible, without changing the durable bounds.

        If input verification or saving fails, the previous reservation is
        left authoritative and no second save is attempted.
        """
        if self.failed:
            return
        self.failed = True
        if self.last_record is None:
            return
        self.validate_inputs()
        record = dict(self.last_record, checkpoint_number=self.checkpoint_number+1,
            io_before=dict(write_calls=self.write_calls, written_bytes=self.written_bytes,
                           read_calls=self.read_calls, read_bytes=self.read_bytes),
            termination=dict(status='unknown', reason=reason))
        measured = atomic_verified(self.path, record)
        self.write_calls += measured['write_calls']
        self.written_bytes += measured['written_bytes']
        self.read_calls += measured['read_calls']
        self.read_bytes += measured['read_bytes']
        self.checkpoint_number += 1
        self.last_record = record

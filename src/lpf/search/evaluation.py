"""All forwards, legality checks, sample budgets and durable legal observations."""
import time
import numpy as np
from .starts import validate
from .performance import harmonic_limit_db
from .storage import plain, vector_sha
from .validation import score


class BudgetExceeded(RuntimeError):
    pass


class Evaluation:
    def __init__(self, circuit, bounds, maximum, *, backend='rf', sink=None,
                 milestones=()):
        if maximum < 476:
            raise ValueError('Job must reserve terminal 28*17 samples')
        if backend not in ('rf', 'fixture'):
            raise ValueError('Unknown forward backend')
        self.circuit, self.bounds = circuit, bounds
        self.maximum, self.backend, self.sink = maximum, backend, sink
        self.mandatory = float(harmonic_limit_db(circuit.resolved_policy))
        self.requested = self.completed = self.failures = 0
        self.reserve = 476
        self.grids, self.ledger, self.scans = {}, [], []
        self.last = None
        self.stage_requested = 0
        self.stage_max = maximum
        self.milestones = list(milestones)

    def grid(self, points):
        if points not in self.grids:
            e = self.circuit.forward_evaluator(points)
            if (len(e.f) != 28 * points or set(e.setting) != set(range(6)) or
                    set(e.segment) != set(range(28)) or set(e.role) != {0, 1, 2} or
                    any(sum(e.segment == i) != points for i in range(28))):
                raise ValueError('Incomplete RF grid/settings/roles')
            self.grids[points] = e
        return self.grids[points]

    def begin_stage(self, maximum):
        # Solver and selection only; anytime and terminal use the job budget.
        self.stage_requested, self.stage_max = 0, maximum

    def snapshot(self):
        return plain({'frequency_samples_requested': self.requested,
                      'frequency_samples_completed': self.completed,
                      'failed_forwards': self.failures, 'terminal_reserved': self.reserve,
                      'stage_requested': self.stage_requested, 'stage_max': self.stage_max,
                      'cache': 'none', 'backend': self.backend, 'ledger': self.ledger,
                      'last_legal_observation': self.last, 'anytime17': self.scans,
                      'pending_anytime_samples': self.milestones})

    def checkpoint(self):
        if self.sink:
            self.sink(self.snapshot())

    def forward(self, vector, points, stage, *, terminal=False, scan=False, on_completed=None):
        x = validate(self.circuit, vector, self.bounds)
        n = 28 * points
        if terminal and (points != 17 or self.reserve != 476):
            raise ValueError('Invalid terminal reservation')
        ceiling = self.maximum if terminal else self.maximum - self.reserve
        if (self.requested + n > ceiling or
                (not scan and not terminal and self.stage_requested + n > self.stage_max)):
            raise BudgetExceeded('Next full forward batch exceeds requested-sample budget')
        if terminal:
            self.reserve = 0
        e = self.grid(points)
        row = {'stage': stage, 'points_per_interval': points,
               'requested': n, 'completed': 0, 'status': 'unknown',
               'vector_sha256': vector_sha(x)}
        self.requested += n
        if not scan and not terminal:
            self.stage_requested += n
        self.ledger.append(row)
        self.checkpoint()  # unknown in-flight cost survives kill
        wall, cpu = time.monotonic(), time.process_time()
        try:
            if self.backend == 'rf':
                il = np.asarray(e.il(x), float)
            else:
                # Deliberately artificial, never RF performance evidence.
                il = np.where(e.role == 0, .4 + 1e-4 * float(np.dot(x, x)), 31.)
            if il.shape != (n,):
                raise ValueError('Unexpected forward sample count')
            s = score(il, e.role, self.mandatory)
            self.completed += n
            row.update(completed=n, status='completed')
            extrema = {}
            for role, label in ((0, 'pass'), (1, 'H2'), (2, 'H3')):
                ids = np.flatnonzero(e.role == role)
                i = ids[np.argmax(il[ids]) if role == 0 else np.argmin(il[ids])]
                extrema[label] = {'setting_index': int(e.setting[i]),
                                  'segment': int(e.segment[i]), 'frequency_mhz': float(e.f[i]),
                                  'il_db': float(il[i])}
            self.last = {'vector': x.tolist(), 'vector_sha256': vector_sha(x),
                         'stage': stage, 'points_per_interval': points, 'score': s,
                         'extrema': extrema,
                         'physical_checks': 'closed_box/components/role/full_L_SPD_passed',
                         'completed_at_requested_samples': self.requested}
        except BaseException as exc:
            self.failures += 1
            row.update(status='interrupted' if isinstance(exc, KeyboardInterrupt) else 'failed',
                       error=f'{type(exc).__name__}: {exc}')
            raise
        finally:
            row.update(wall_seconds=time.monotonic() - wall, cpu_seconds=time.process_time() - cpu)
            self.checkpoint()
        # Selection must persist the completed score even if the subsequent
        # anytime scan fails or exhausts its separate job budget.
        if on_completed is not None:
            on_completed(il)
        if not terminal and not scan:
            while self.milestones and self.requested >= self.milestones[0]:
                milestone = self.milestones.pop(0)
                observed = self.last['vector']
                entry = {'milestone': milestone, 'status': 'unknown'}
                self.scans.append(entry)
                try:
                    self.forward(observed, 17, 'anytime17', scan=True)
                    entry.update(status='completed', observation=self.last)
                except BaseException as exc:
                    entry.update(status='not_run' if isinstance(exc, BudgetExceeded) else 'failed',
                                 reason=f'{type(exc).__name__}: {exc}')
                    raise
                finally:
                    self.checkpoint()
        return il

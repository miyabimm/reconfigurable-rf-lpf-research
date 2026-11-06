"""All forwards, legality checks, sample budgets and durable legal observations."""
from dataclasses import asdict
from pathlib import Path
import tempfile
import time

import numpy as np

from .starts import validate
from .performance import harmonic_limit_db
from .storage import plain, vector_sha
from .validation import score

from lpf.constraint_versions import load_constraint, rf_input_file
from lpf.rf_core.model import build_rf_model
from .component_constraints import validate_values
from .performance import compile_requirements, evaluate_requirements, grid_fingerprint
from .preflight import freeze, check_next_batch
from .storage import atomic, sha


def raw_numbers(value):
    """Strict JSON: preserve exact +/-inf dB, never floor solver values."""
    value = plain(value)
    if isinstance(value, dict):
        return {k: raw_numbers(v) for k, v in value.items()}
    if isinstance(value, list):
        return [raw_numbers(v) for v in value]
    if isinstance(value, complex):
        return {'real': raw_numbers(value.real), 'imag': raw_numbers(value.imag)}
    if isinstance(value, float) and not np.isfinite(value):
        return {'nonfinite': '+inf' if value == np.inf else '-inf' if value == -np.inf else 'nan'}
    return value


class FixedStageEvaluation:
    """Development only: one process, one fixed Job/stage, no resume or solver.

    Every other stage and Job retains its full reservation. Selection, terminal,
    anytime and independent dense budgets are never released/executed here.
    Existing checkpoints (including unknown cost) must be investigated, not reset.
    Caller supplies a fresh path in a TemporaryDirectory outside the repository.
    """
    def __init__(self, plan, definition, approved_policy, arm, step, checkpoint, *, root=None):
        from .plan import ROOT
        self.root = Path(root or ROOT).resolve()
        self.path = Path(checkpoint).resolve()
        if (not self.path.is_relative_to(Path(tempfile.gettempdir()).resolve()) or
                self.path.is_relative_to(self.root)):
            raise ValueError('Development checkpoint must be in system temp outside repository')
        if self.path.exists():
            raise ValueError('Existing raw/unknown checkpoint: no automatic resume or retry')
        self.plan, self.definition = plan, definition
        self.policy = approved_policy
        self.arm, self.step = arm, step
        self.stage = f'{arm}/{step}'
        self.requested = self.completed = 0
        self.rows = []
        self.status, self.reason = 'ready', None
        self._contract()
        self.model = build_rf_model(definition, approved_policy)
        self.grid = plan.requested_grid(self.stage)
        self.requirements = compile_requirements(approved_policy,
            rf_input_file(self.root, approved_policy['bands_file']), self.data['config']['objective'])
        self.job = self.data['costs']['jobs'][arm]
        self.stage_cap = self.job['stages'][step]['upper_reservation']
        self.reserved = (self.job['total_upper_reservation'] - self.stage_cap)
        self.other_jobs = (self.data['costs']['trial_job_cap_reservation'] -
                           self.job['max_requested_samples'])
        self._checkpoint()

    def _contract(self):
        from lpf.constraint_versions import constraint_fingerprint
        d = self.plan.data
        if sha(d) != self.plan.sha256 or d['config']['schema_version'] != 2:
            raise ValueError('Plan SHA/schema mismatch')
        # Recompile read-only Stage 4A: checks definition source bytes, actual
        # bands/S2Ps, current approved RF, requirements, mode, every grid and cost.
        if sha(freeze(d['config'], self.root)) != self.plan.sha256:
            raise ValueError('Plan/current RF inputs, requirements or grid mismatch')
        ref = d['config']['definition']
        if ref is None:
            raise ValueError('Null definition is preflight-only')
        if sha(asdict(self.definition)) != ref['definition_sha256']:
            raise ValueError('CircuitDefinition/Plan mismatch')
        approved = load_constraint(d['config']['rf']['constraint_id'], root=self.root,
                                   allow_trial=d['config']['rf']['allow_trial'])
        if constraint_fingerprint(self.policy) != constraint_fingerprint(approved):
            raise ValueError('Approved policy/effective SHA mismatch')
        if self.step not in d['costs']['jobs'][self.arm]['stages']:
            raise ValueError('Unknown fixed stage')
        if hasattr(self, 'grid'):
            if grid_fingerprint(self.grid) != d['grids'][self.stage]['sha256']:
                raise ValueError('Runtime grid/Plan mismatch')
            if sha(asdict(self.requirements)) != sha(d['requirements']):
                raise ValueError('Runtime requirements/Plan mismatch')
            if (self.model.policy_fingerprint != constraint_fingerprint(approved) or
                    sha(asdict(self.model.definition)) != ref['definition_sha256']):
                raise ValueError('Runtime model/Plan mismatch')
        self.data = d

    def snapshot(self):
        return raw_numbers(dict(kind='stage4b_development_only', plan_sha256=self.plan.sha256,
            stage=self.stage, policy_id=self.model.policy_id,
            policy_fingerprint=self.model.policy_fingerprint,
            definition_sha256=sha(asdict(self.definition)),
            requirements_fingerprint=self.requirements.fingerprint,
            grid_sha256=grid_fingerprint(self.grid), grid=self.grid,
            requested=self.requested, completed=self.completed,
            reservations=dict(other_steps_selection_terminal_anytime=self.reserved,
                other_jobs=self.other_jobs, dense=self.data['costs']['dense']),
            remaining=dict(step=self.stage_cap-self.requested,
                job=self.job['max_requested_samples']-self.requested,
                trial=self.data['costs']['max_trial_requested_samples']-self.requested),
            status=self.status, reason=self.reason, batches=self.rows,
            gates=self.data['gates'], dense='not_run', continuous_band_proven=False,
            physical_q_srf_em_checked=False, rf_compliance_certified=False))

    def _checkpoint(self):
        try:
            atomic(self.path, self.snapshot())
        except BaseException:
            self.status = 'storage_failed'  # prohibit a second attempt in this object
            raise

    def evaluate(self, vector):
        if self.status != 'ready':
            raise RuntimeError('STOP: failed/stopped/unknown Job cannot retry')
        row = dict(stage=self.stage, grid_sha256=grid_fingerprint(self.grid),
                   requested=0, completed=0, status='rejected', phase='contract',
                   independent={'status': 'not_run', 'reason': 'not requested'})
        try:
            self._contract()
            # Copy the entire candidate before validation/forward, no silent repair.
            row['phase'] = 'physical_values'
            x = np.array(vector, copy=True)
            row['vector'] = x.tolist()
            if x.ndim == 1 and x.dtype.kind in 'fiu' and np.all(np.isfinite(x)):
                row['vector_sha256'] = vector_sha(x)
            physical = validate_values(self.definition, self.model.schema, x, self.policy)
            x = np.asarray(x, dtype=float)
            x.setflags(write=False)
            row.update(vector_sha256=vector_sha(x), physical_checks=physical)
            n = len(self.grid.frequency_hz)
            row['phase'] = 'budget'
            check_next_batch(n, step_remaining=self.stage_cap-self.requested,
                job_remaining=self.job['max_requested_samples']-self.requested,
                trial_remaining=self.data['costs']['max_trial_requested_samples']-self.requested,
                job_reserved=self.reserved, trial_reserved=self.reserved+self.other_jobs)
            row['phase'] = 'evaluator_setup'
            evaluator = self.model.evaluator(self.grid)
        except BaseException as exc:
            self.status, self.reason = 'stopped', f'{type(exc).__name__}: {exc}'
            row['reason'] = self.reason
            self.rows.append(row)
            self._checkpoint()
            raise
        row['remaining_before'] = self.snapshot()['remaining']
        row['reservations'] = self.snapshot()['reservations']
        self.requested += n
        row.update(requested=n, status='unknown', phase='forward',
                   remaining_after=self.snapshot()['remaining'])
        self.rows.append(row)
        self.status = 'unknown'
        self._checkpoint()  # durable full-batch charge BEFORE evaluate(x)
        try:
            response = evaluator.evaluate(x)
            # Preserve a complete response even if subsequent assessment fails.
            # Save every completed response metric, including complex external S.
            row['response'] = dict(s_real=response.s.real.tolist(), s_imag=response.s.imag.tolist(),
                **{k: getattr(response, k).tolist() for k in
                   ('il_db', 'apl_db', 'in_rl_db', 'out_rl_db')})
            row['phase'] = 'requirements'
            assessment = evaluate_requirements(response, self.requirements, requested_grid=self.grid)
            row['assessment'] = plain(assessment)
            row.update(status='completed', completed=n, phase='completed',
                       reason='forward_and_requirements_completed')
            self.completed += n
            self.status = 'ready'
        except BaseException as exc:
            self.status = 'interrupted' if isinstance(exc, KeyboardInterrupt) else 'failed'
            self.reason = f'{type(exc).__name__}: {exc}'
            row.update(status=self.status, reason=self.reason)
            raise
        finally:
            self._checkpoint()
        return dict(vector=x.copy(), vector_sha256=vector_sha(x), model=self.model,
                    assessment=assessment, plan_sha256=self.plan.sha256,
                    grid_sha256=grid_fingerprint(self.grid), batch_index=len(self.rows)-1)

    def spot_check(self, batch_index, sample_indices, *, atol=1e-9):
        """Independent MNA/passivity/power at named completed samples only.

        Separate audit sample counts, not a second primary RF forward. No
        whole-band PASS implied, and no retry after a failed/unknown audit.
        """
        from lpf.rf_core.independent import evaluate_independent_response
        row = self.rows[batch_index]
        ids = list(sample_indices)
        if (self.status != 'ready' or row['status'] != 'completed' or
                row['independent']['status'] != 'not_run' or
                not ids or len(set(ids)) != len(ids) or
                any(type(i) is not int or not 0 <= i < len(self.grid.frequency_hz) for i in ids) or
                not np.isfinite(atol) or atol <= 0):
            raise ValueError('Expected unverified completed batch and explicit unique sample indices')
        audit = dict(status='unknown', sample_indices=ids, requested=len(ids), completed=0,
                     absolute_tolerance=atol, samples=[], whole_band_checked=False)
        row['independent'] = audit
        self._checkpoint()
        try:
            self._contract()
            x = np.asarray(row['vector'], float)
            if vector_sha(x) != row['vector_sha256'] or row['grid_sha256'] != grid_fingerprint(self.grid):
                raise ValueError('Independent audit candidate/grid identity mismatch')
            for i in ids:
                ref = evaluate_independent_response(self.model, x,
                    float(self.grid.frequency_hz[i]), int(self.grid.setting[i]))
                s = np.array(row['response']['s_real'][i]) + 1j*np.array(row['response']['s_imag'][i])
                for key in ('s', 'il_db', 'apl_db', 'in_rl_db', 'out_rl_db'):
                    actual = s if key == 's' else row['response'][key][i]
                    if not np.allclose(actual, ref[key], rtol=0, atol=atol):
                        raise ValueError(f'Independent MNA mismatch: {key} sample {i}')
                independent_s = ref.pop('s')
                audit['samples'].append(dict(index=i, s_real=independent_s.real.tolist(),
                                             s_imag=independent_s.imag.tolist(), **ref))
                audit['completed'] += 1
                self._checkpoint()
            audit.update(status='pass', passivity='pass_at_samples', power_balance='pass_at_samples')
        except BaseException as exc:
            self.status, self.reason = 'failed', f'{type(exc).__name__}: {exc}'
            audit.update(status='failed', reason=self.reason)
            raise
        finally:
            self._checkpoint()
        return audit


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

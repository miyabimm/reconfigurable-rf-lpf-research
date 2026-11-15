"""Gate-free, single-process development worker; not a formal Job or resume API."""
import os
from numbers import Real
from pathlib import Path
import tempfile

import numpy as np

from lpf.optimizers.slsqp import slsqp_minimize
from lpf.optimizers.slp import slp_minimize
from ._worker_next import MinimalWorker
from .component_constraints import _check_vector_box, validate_search_box, validate_values
from .evaluation import raw_numbers
from .performance import (evaluate_requirements, grid_fingerprint, prepare_requirements,
                          summarize_mandatory)
from .storage import canonical, plain, vector_sha
from .validation import rank_candidates
from .worker import _development_options


def _save_checkpoint(path, payload):
    """Atomically publish a new event without replacing any existing path."""
    data = (canonical(raw_numbers(payload)) + '\n').encode()
    fd, name = tempfile.mkstemp(dir=path.parent, prefix='.' + path.name)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        # link is an atomic no-replace publication even if a path appears after
        # initialization. Both names are on the same temporary filesystem.
        os.link(name, path)
        os.unlink(name)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def _normalize_search_bounds(bounds):
    """Copy numeric pairs without accepting bools, strings, or ragged input."""
    try:
        box = np.asarray(bounds, dtype=object)
        if (box.ndim != 2 or box.shape[1] != 2 or
                any(isinstance(v, (bool, np.bool_)) or not isinstance(v, Real) for v in box.flat)):
            raise ValueError('Search bounds must be numeric pairs')
        box = np.asarray(box, dtype=float)
    except (TypeError, OverflowError) as exc:
        raise ValueError('Search bounds must be numeric pairs') from exc
    if not np.all(np.isfinite(box)):
        raise ValueError('Search bounds must be finite')
    return tuple(tuple(row) for row in box.tolist())


class DevelopmentWorker(MinimalWorker):
    """Execute a frozen Plan without formal storage, reservations, or recovery.

    The checkpoint is an append-only experimental best history, not solver state.
    A fresh directory in the system temporary directory is required.
    """
    @staticmethod
    def _validate_arm(chosen):
        if chosen is None or not chosen['steps']:
            raise ValueError('Plan arm with steps required')

    def __init__(self, plan, definition, policy, arm, seed, vector, expected_vector_sha,
                 *, root, checkpoint, checkpoint_interval=100, spot_checks=None, search_bounds=None):
        self.path = Path(checkpoint).resolve()
        root = Path(root).resolve()
        if (not self.path.is_relative_to(Path(tempfile.gettempdir()).resolve()) or
                self.path.is_relative_to(root) or self.path.exists()):
            raise ValueError('Fresh temporary checkpoint outside repository required')
        if type(checkpoint_interval) is not int or checkpoint_interval < 1:
            raise ValueError('Positive checkpoint interval required')
        if plan.data['config']['objective'] != 'full_lpf':
            raise ValueError('DevelopmentWorker requires all full-LPF intervals')
        self.plan, self.arm = plan, arm
        self.checkpoint_interval = checkpoint_interval
        self.spot_checks = {} if spot_checks is None else dict(spot_checks)
        self._running = False
        self._started = False
        super().__init__(plan, definition, policy, arm, seed, vector, expected_vector_sha, root=root)
        if search_bounds is not None:
            box = _normalize_search_bounds(search_bounds)
            validate_search_box(box, self._physical_bounds)
            _check_vector_box(self.x, box)
            self.bounds = box
        self.steps = next(a['steps'] for a in plan.data['config']['arms'] if a['name'] == arm)
        self._grids = {f"{arm}/{self.step['name']}":
                       (self.grid, self.evaluator, self.prepared_requirements)}
        valid = {f"{arm}/{s['name']}" for s in self.steps} | {'selection', 'terminal'}
        for stage, indices in self.spot_checks.items():
            if (stage not in valid or not isinstance(indices, list) or not indices or
                    len(set(indices)) != len(indices) or any(type(i) is not int or i < 0 or
                    i >= len(plan.requested_grid(stage).frequency_hz) for i in indices)):
                raise ValueError('Invalid independent spot checks')
        self.path.mkdir(exist_ok=False)
        self.checkpoint_sequence = 0

    def _activate(self, stage):
        if stage not in self._grids:
            grid = self.plan.requested_grid(stage)
            if grid_fingerprint(grid) != self.plan.data['grids'][stage]['sha256']:
                raise ValueError('Grid/Plan mismatch')
            self._grids[stage] = (grid, self.model.evaluator(grid),
                                  prepare_requirements(self.requirements, grid))
        self.stage = stage
        self.grid, self.evaluator, self.prepared_requirements = self._grids[stage]

    def _evaluate(self, vector):
        if self.bounds is not self._physical_bounds:
            _check_vector_box(vector, self.bounds)
        response, assessment = super()._evaluate(vector)
        if self._running:
            self.forward_count += 1
            self.independent = self._audit(vector, response, self.stage)
            metrics = summarize_mandatory(assessment, self.prepared_requirements)
            digest = vector_sha(vector)
            il = assessment['worst_il_db']
            if not np.isfinite(il) or il < 0 or np.isnan(metrics['max_violation_db']):
                raise ValueError('Invalid RF best metrics')
            key = ((0, il, digest) if metrics['strict_feasible'] else
                   (1, metrics['max_violation_db'], metrics['sum_violation_db'], il, digest))
            if self.best is None or key < self.best_key:
                validate_values(self.definition, self.model.schema, vector, self.policy, frozen_model=self.model)
                self.best_key = key
                self.best = dict(vector=plain(vector), vector_sha256=digest,
                                 worst_il_db=il, **metrics)
            if self.saved_sha is None or (self.forward_count - self.saved_count >= self.checkpoint_interval
                                         and self.best['vector_sha256'] != self.saved_sha):
                self._save_best()
        return response, assessment

    def _save_best(self):
        sequence = self.checkpoint_sequence + 1
        payload = dict(kind='development_temporary_best_v1', job_id=f'development-{self.arm}-{self.seed}',
                       sequence=sequence, arm=self.arm, step=self.step['name'], seed=self.seed,
                       plan_sha256=self.plan.sha256, policy_id=self.model.policy_id,
                       policy_fingerprint=self.model.policy_fingerprint,
                       rf_inputs=self.plan.data['rf_inputs'], grid_sha256=grid_fingerprint(self.grid),
                       requirements_fingerprint=self.requirements.fingerprint,
                       forward_count=self.forward_count, best=self.best)
        _save_checkpoint(self.path / f'{sequence:06d}.json', payload)
        self.checkpoint_sequence = sequence
        self.saved_sha, self.saved_count = self.best['vector_sha256'], self.forward_count

    def _objective(self, vector, *, square_root):
        _, a = self._evaluate(vector)
        value = a['worst_il_db']
        if not np.isfinite(value) or value < 0:
            raise ValueError('Squared-residual solver requires finite nonnegative worst IL; no floor')
        return np.array([np.sqrt(value) if square_root else value])

    def _constraints(self, vector):
        return np.asarray(self._evaluate(vector)[1]['mandatory_g'])

    def _audit(self, vector, response, stage):
        indices = self.spot_checks.get(stage)
        if not indices:
            return dict(status='not_run', reason='not requested')
        from lpf.rf_core.independent import evaluate_independent_response
        for i in indices:
            ref = evaluate_independent_response(self.model, vector, float(self.grid.frequency_hz[i]),
                                                int(self.grid.setting[i]))
            for key in ('s', 'il_db', 'apl_db', 'in_rl_db', 'out_rl_db'):
                if not np.allclose(getattr(response, key)[i], ref[key], rtol=0, atol=1e-9):
                    raise ValueError(f'Independent MNA mismatch: {key} sample {i}')
        return dict(status='pass', sample_indices=indices, passivity='pass_at_samples',
                    power_balance='pass_at_samples', whole_band_checked=False)

    def run(self):
        if self._started:
            raise RuntimeError('Worker cannot retry or resume')
        self._started = True
        validate_search_box(self.bounds, self._physical_bounds)
        _check_vector_box(self.x, self.bounds)
        x = self.x.copy()
        candidates, steps, invalid = [], [], []
        cfg = self.plan.data['config']
        for step in self.steps:
            self.step = step
            stage = f"{self.arm}/{step['name']}"
            self._activate(stage)
            self.forward_count, self.saved_count, self.saved_sha = 0, 0, None
            self.best = self.best_key = None
            self.independent = dict(status='not_run', reason='no successful forward')
            self._running = True
            try:
                opts = _development_options(step)
                if step['solver'] == 'hybrid':
                    from . import _worker_next
                    out = _worker_next.hybrid_minimize(self._solver_residuals, x, self.bounds,
                            seed=self.seed, aggregation=step['aggregation'], **opts)
                    found = [r.end_x for r in out.runs if r.end_x is not None]
                    if out.best_x is not None:
                        found.append(out.best_x)
                    next_x = out.best_x
                    success = bool(out.runs) and all(r.success for r in out.runs)
                    reason = out.stop_reason
                else:
                    solver = slsqp_minimize if step['solver'] == 'slsqp' else slp_minimize
                    out = solver(lambda v: self._objective(v, square_root=step['solver'] == 'slsqp'),
                                 x, self.bounds, constraints=self._constraints,
                                 aggregation=step['aggregation'], **opts)
                    next_x, success, found = out.x, out.success, [out.x]
                    reason = out.stop_reason if step['solver'] == 'slsqp' else out.slp.reason
                if reason.startswith('invalid_'):
                    raise ValueError(f'Solver numerical STOP: {reason}')
                if next_x is None:
                    raise ValueError('No solver output; no implicit retry')
                for v in found:
                    try:
                        _check_vector_box(v, self.bounds)
                        validate_values(self.definition, self.model.schema, v, self.policy, frozen_model=self.model)
                    except ValueError as exc:
                        invalid.append(dict(vector=plain(v), status='invalid', reason=str(exc)))
                        continue
                    candidates.append(plain(v))
                _check_vector_box(next_x, self.bounds)
                validate_values(self.definition, self.model.schema, next_x, self.policy, frozen_model=self.model)
                if self.best is not None and self.best['vector_sha256'] != self.saved_sha:
                    self._save_best()
                steps.append(dict(name=step['name'], solver=step['solver'], solver_result=raw_numbers(out),
                                  stop_reason=reason, converged=bool(success), forward_count=self.forward_count,
                                  rf_best=plain(self.best), independent=plain(self.independent)))
                x = np.asarray(next_x, dtype=float).copy()
            finally:
                self._running = False
        selection = dict(status='not_run', forward_count=0, ranked=[], excluded=invalid)
        assessed = []
        self._activate('selection')
        for i, (digest, vector) in enumerate(sorted({vector_sha(v): v for v in candidates}.items())):
            if i >= cfg['selection']['max_candidates']:
                selection['excluded'].append(dict(vector_sha256=digest, status='unrun', reason='max_candidates'))
                continue
            response, _ = self.evaluate(vector)
            selection['forward_count'] += 1
            assessment = evaluate_requirements(response, self.requirements, requested_grid=self.grid)
            keys = ('status', 'policy_id', 'policy_fingerprint', 'mode', 'requirements_fingerprint',
                    'grid_fingerprint', 'strict_feasible', 'worst_il_db', 'max_violation_db', 'sum_violation_db')
            compact = {key: assessment[key] for key in keys}
            assessed.append(dict(vector=vector, vector_sha256=digest, model=self.model, assessment=compact,
                                 independent=self._audit(vector, response, 'selection')))
            del assessment, response
        ranked = rank_candidates(assessed)
        selection['ranked'] = [raw_numbers({k: v for k, v in r.items() if k != 'model'}) for r in ranked['ranked']]
        selection['excluded'].extend(raw_numbers(ranked['excluded']))
        if candidates:
            selection['status'] = 'completed'
        terminal = dict(status='not_run', forward_count=0, candidates=[])
        self._activate('terminal')
        for row in ranked['ranked'][:cfg['selection']['top_k']]:
            response, _ = self.evaluate(row['vector'])
            terminal['forward_count'] += 1
            assessment = evaluate_requirements(response, self.requirements, requested_grid=self.grid)
            terminal['candidates'].append(raw_numbers(dict(vector_sha256=row['vector_sha256'],
                assessment=assessment, independent=self._audit(row['vector'], response, 'terminal'))))
        if terminal['candidates']:
            terminal['status'] = 'completed'
        return dict(kind='development_only', status='converged' if all(s['converged'] for s in steps)
                    else 'not_converged', steps=steps, selection=selection, terminal=terminal,
                    forward_count=sum(s['forward_count'] for s in steps) + selection['forward_count'] + terminal['forward_count'],
                    finite_grid_only=True, continuous_band_proven=False, rf_compliance_certified=False,
                    physical_q_srf_em_checked=False)

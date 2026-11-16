"""Gate-free, single-process development worker; not a formal Job or resume API."""
import os
import json
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
from .storage import canonical, plain, sha, vector_sha
from .validation import rank_candidates
from .worker import _development_options


WEIGHTED_OBJECTIVE = dict(mode='weighted_violation', formula='IL_weight*p^2 + H_weight*mean(h^2)',
                          p='max(0, worst_pass_IL_db - 0.30)',
                          h='max(0, 30.01 - attenuation_db)', IL_weight=1, H_weight=100,
                          nominal_harmonic_db=35, strict_harmonic_db=30,
                          note='development only; weights and margin attainment unverified')


def _weighted_residuals(response, assessment, prepared):
    intervals = prepared.requirements.intervals
    segments = [i.segment for i in intervals if i.region in ('H2', 'H3')]
    ix = np.flatnonzero(np.isin(prepared.grid.segment, segments))
    if not len(ix):
        raise ValueError('No harmonic samples')
    il = assessment['worst_il_db']
    attenuation = response.il_db[ix]
    if not np.isfinite(il) or il < 0 or np.any(np.isnan(attenuation)) or np.any(np.isneginf(attenuation)):
        raise ValueError('Invalid RF values for weighted objective')
    p = max(0., il - 0.30)
    h = np.maximum(0., 30.01 - attenuation)
    residuals = np.r_[p, np.sqrt(100. / len(ix)) * h]
    if not np.all(np.isfinite(residuals)):
        raise ValueError('Invalid weighted objective residuals')
    return residuals


def _harmonic_margin(response, prepared):
    segments = [i.segment for i in prepared.requirements.intervals if i.region in ('H2', 'H3')]
    indices = np.flatnonzero(np.isin(prepared.grid.segment, segments))
    if not len(indices):
        raise ValueError('No harmonic samples')
    minimum = float(np.min(response.il_db[indices]))
    if np.isnan(minimum) or np.isneginf(minimum):
        raise ValueError('Invalid harmonic attenuation')
    return dict(min_harmonic_attenuation_db=minimum, target_30_01=bool(minimum >= 30.01))


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
    def _verify_plan(self, plan, root):
        if not self.budget_restarts:
            return super()._verify_plan(plan, root)
        from .preflight import freeze
        data = plan.data
        base = {k: v for k, v in data.items() if k != 'development_weighted_restart'}
        if sha(data) != plan.sha256 or sha(freeze(data['config'], root)) != sha(base):
            raise ValueError('Plan/current RF inputs mismatch')

    @staticmethod
    def _validate_arm(chosen):
        if chosen is None or not chosen['steps']:
            raise ValueError('Plan arm with steps required')

    def __init__(self, plan, definition, policy, arm, seed, vector, expected_vector_sha,
                 *, root, checkpoint, checkpoint_interval=1000, spot_checks=None, search_bounds=None,
                 objective_mode=None, budget_restarts=False):
        if type(budget_restarts) is not bool or (budget_restarts and objective_mode != 'weighted_violation'):
            raise ValueError('Budget restarts require weighted development mode')
        self.budget_restarts = budget_restarts
        self.local_run_index = 0
        self.path = Path(checkpoint).resolve()
        root = Path(root).resolve()
        if (not self.path.is_relative_to(Path(tempfile.gettempdir()).resolve()) or
                self.path.is_relative_to(root) or self.path.exists()):
            raise ValueError('Fresh temporary checkpoint outside repository required')
        if type(checkpoint_interval) is not int or checkpoint_interval < 1:
            raise ValueError('Positive checkpoint interval required')
        if plan.data['config']['objective'] != 'full_lpf':
            raise ValueError('DevelopmentWorker requires all full-LPF intervals')
        if objective_mode not in (None, 'weighted_violation'):
            raise ValueError('Unknown development objective mode')
        self.objective_mode = objective_mode
        self.plan, self.arm = plan, arm
        self.checkpoint_interval = checkpoint_interval
        self.spot_checks = {} if spot_checks is None else dict(spot_checks)
        self.audit_samples = {}
        self._running = False
        self._started = False
        super().__init__(plan, definition, policy, arm, seed, vector, expected_vector_sha, root=root)
        if search_bounds is not None:
            box = _normalize_search_bounds(search_bounds)
            validate_search_box(box, self._physical_bounds)
            _check_vector_box(self.x, box)
            self.bounds = box
        self.steps = next(a['steps'] for a in plan.data['config']['arms'] if a['name'] == arm)
        if self.objective_mode:
            step = self.steps[0]
            opts = step['options']
            costs = plan.data['costs']['jobs'][arm]
            n = opts['max_search_forwards']
            if (len(plan.data['config']['arms']) != 1 or
                    (not budget_restarts and len(plan.data['config']['seeds']) != 1) or
                    plan.data['config']['anytime_samples'] != [] or
                    costs['stages'][step['name']]['upper_reservation'] != n * 70 or
                    costs['selection_upper_reservation'] != 84 or costs['terminal_fixed_reservation'] != 476 or
                    costs['total_upper_reservation'] != n * 70 + 84 + 476 or
                    plan.data['config']['rf'] != {'constraint_id': 'RF-T008', 'allow_trial': True} or
                    len(self.steps) != 1 or step['solver'] != 'hybrid' or step['aggregation'] != 'sum' or
                    step['points_per_interval'] != 2 or step.get('stop_points_per_interval') != 3 or
                    len(self.grid.frequency_hz) != 70 or
                    plan.data['config']['selection']['max_candidates'] != 1 or
                    plan.data['config']['selection']['top_k'] != 1 or
                    len(plan.requested_grid('selection').frequency_hz) != 84 or
                    len(plan.requested_grid('terminal').frequency_hz) != 476):
                raise ValueError('Invalid weighted development Plan')
            if budget_restarts:
                mode = plan.data.get('development_weighted_restart', {})
                expected = dict(checkpoint_interval_forwards=checkpoint_interval, search_bounds=plain(self.bounds),
                                search_bounds_sha256=sha(self.bounds), objective='weighted_violation',
                                start_method=mode.get('start_method'))
                if mode != expected or mode['start_method'] not in ('explicit', 'scrambled_sobol_single_point'):
                    raise ValueError('Budget restart settings/box do not match frozen Plan')
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
            if self.objective_mode:
                residuals = _weighted_residuals(response, assessment, self.prepared_requirements)
                score = float(np.sum(residuals * residuals))
                if not np.isfinite(score):
                    raise ValueError('Invalid weighted objective')
                key = (score, digest)
                if self.solver_best is None or score < self.solver_best[0]:
                    self.solver_best = (score, digest)
            else:
                key = ((0, il, digest) if metrics['strict_feasible'] else
                       (1, metrics['max_violation_db'], metrics['sum_violation_db'], il, digest))
            if self.best is None or key < self.best_key:
                validate_values(self.definition, self.model.schema, vector, self.policy, frozen_model=self.model)
                self.best_key = key
                self.best = dict(vector=plain(vector), vector_sha256=digest,
                                 worst_il_db=il, **metrics)
                if self.objective_mode:
                    self.best['objective_j'] = score
                if self.budget_restarts:
                    self.best.update(_harmonic_margin(response, self.prepared_requirements))
            if self.budget_restarts:
                if self.forward_count % self.checkpoint_interval == 0:
                    self._save_best()
            elif self.saved_sha is None or (self.forward_count - self.saved_count >= self.checkpoint_interval
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
        if self.budget_restarts:
            payload['local_run_index'] = self.local_run_index
            payload['restart_count'] = self.local_run_index
        target = self.path / f'{sequence:06d}.json'
        _save_checkpoint(target, payload)
        if self.objective_mode and canonical(json.loads(target.read_text())) != canonical(raw_numbers(payload)):
            raise ValueError('Checkpoint readback mismatch')
        self.checkpoint_sequence = sequence
        self.saved_sha, self.saved_count = self.best['vector_sha256'], self.forward_count

    def _residuals(self, evaluation):
        if self.objective_mode:
            return _weighted_residuals(*evaluation, self.prepared_requirements)
        return super()._residuals(evaluation)

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
        self.audit_samples[stage] = self.audit_samples.get(stage, 0) + len(indices)
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
            self.solver_best = None
            self.independent = dict(status='not_run', reason='no successful forward')
            self._running = True
            try:
                opts = _development_options(step)
                if step['solver'] == 'hybrid':
                    from . import _worker_next
                    extra = {}
                    if self.budget_restarts:
                        extra['run_callback'] = lambda index: setattr(self, 'local_run_index', index)
                    out = _worker_next.hybrid_minimize(self._solver_residuals, x, self.bounds,
                            seed=self.seed, aggregation=step['aggregation'], **opts, **extra)
                    found = [r.end_x for r in out.runs if r.end_x is not None]
                    if out.best_x is not None:
                        found.append(out.best_x)
                    next_x = out.best_x
                    if self.objective_mode:
                        if self.best is None or out.best_fun is None or out.best_x is None:
                            raise ValueError('No weighted best; no replacement or retry')
                        if out.nfev != self.forward_count or out.nfev > opts['max_evaluations']:
                            raise ValueError('Solver/Worker forward count mismatch')
                        if (self.best['objective_j'] != out.best_fun or self.solver_best !=
                                (out.best_fun, vector_sha(out.best_x))):
                            raise ValueError('Worker/Optimizer best objective/vector mismatch')
                        # Hybrid keeps the first equal score; Worker breaks exact ties by SHA.
                        found = [self.best['vector']]
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
                        if self.objective_mode:
                            raise ValueError('Invalid weighted best; no replacement') from exc
                        invalid.append(dict(vector=plain(v), status='invalid', reason=str(exc)))
                        continue
                    candidates.append(plain(v))
                _check_vector_box(next_x, self.bounds)
                validate_values(self.definition, self.model.schema, next_x, self.policy, frozen_model=self.model)
                if self.best is not None and (self.forward_count != self.saved_count if self.budget_restarts
                                              else self.best['vector_sha256'] != self.saved_sha):
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
            response, prepared_assessment = self.evaluate(vector)
            selection['forward_count'] += 1
            assessment = evaluate_requirements(response, self.requirements, requested_grid=self.grid)
            keys = ('status', 'policy_id', 'policy_fingerprint', 'mode', 'requirements_fingerprint',
                    'grid_fingerprint', 'strict_feasible', 'worst_il_db', 'max_violation_db', 'sum_violation_db')
            compact = {key: assessment[key] for key in keys}
            row = dict(vector=vector, vector_sha256=digest, model=self.model, assessment=compact,
                       independent=self._audit(vector, response, 'selection'))
            if self.objective_mode:
                residuals = _weighted_residuals(response, prepared_assessment, self.prepared_requirements)
                row['objective_j'] = float(np.sum(residuals * residuals))
                row['status'] = 'pass' if assessment['strict_feasible'] else 'fail'
            assessed.append(row)
            del assessment, response
        ranked = ({'ranked': assessed, 'excluded': []} if self.objective_mode else rank_candidates(assessed))
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
            terminal_row = dict(vector_sha256=row['vector_sha256'], assessment=assessment,
                                independent=self._audit(row['vector'], response, 'terminal'))
            if self.budget_restarts:
                terminal_row.update(_harmonic_margin(response, self.prepared_requirements))
            terminal['candidates'].append(raw_numbers(terminal_row))
        if terminal['candidates']:
            terminal['status'] = 'completed'
        result = dict(kind='development_only', status='converged' if all(s['converged'] for s in steps)
                    else 'not_converged', steps=steps, selection=selection, terminal=terminal,
                    forward_count=sum(s['forward_count'] for s in steps) + selection['forward_count'] + terminal['forward_count'],
                    finite_grid_only=True, continuous_band_proven=False, rf_compliance_certified=False,
                    physical_q_srf_em_checked=False)
        if self.budget_restarts:
            result['status'] = ('search_budget_exhausted' if steps[0]['stop_reason'] == 'evaluation_budget_exhausted'
                                else 'incomplete')
        if self.objective_mode:
            search_samples = steps[0]['forward_count'] * len(self.plan.requested_grid(f"{self.arm}/{self.step['name']}").frequency_hz)
            result['weighted_objective'] = WEIGHTED_OBJECTIVE
            result['weighted_objective_sha256'] = sha(WEIGHTED_OBJECTIVE)
            result['plan_sha256'] = self.plan.sha256
            result['best_tie_policy'] = ('exact J; Worker uses smallest SHA, Hybrid keeps first; '
                                         'different vectors are possible only for an exact tie')
            result['costs'] = dict(search_forwards=steps[0]['forward_count'], search_requested_samples=search_samples,
                                   search_completed_samples=search_samples,
                                   selection_requested_samples=selection['forward_count'] * 84,
                                   terminal_requested_samples=terminal['forward_count'] * 476,
                                   dense='not_run', independent_mna_samples_by_stage=self.audit_samples)
        return result

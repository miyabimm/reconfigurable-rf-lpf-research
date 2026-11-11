"""Opt-in development-only forward windows; never used by formal Campaigns."""
import numpy as np
from lpf.timing import timed_call, timed_method

from ._forward_window import ForwardJournal
from ._job_evaluation import FixedJobEvaluation
from .component_constraints import validate_values
from .performance import evaluate_requirements, prepare_requirements, summarize_mandatory
from .storage import plain, vector_sha
from .evaluation import raw_numbers


def _hybrid_observation(a, aggregation):
    """Record the exact unweighted Hybrid scalar without retaining mandatory_g."""
    from lpf.optimizers._objectives import aggregate, squared_terms
    invalid = dict(aggregation=aggregation, status='invalid', value=None,
                   il_term=None, violation_squared_sum=None, max_violation_squared=None)
    il = a['worst_il_db']
    if not np.isfinite(il) or il < 0:
        return invalid
    with np.errstate(over='ignore', invalid='ignore'):
        residuals = np.r_[np.sqrt(il), np.maximum(0., -np.asarray(a['mandatory_g'], dtype=float))]
        if not np.all(np.isfinite(residuals)):
            return invalid
        terms = squared_terms(residuals, None)
        value = aggregate(terms, aggregation)
        penalty = float(np.sum(terms[1:]))
        maximum = float(np.max(terms[1:], initial=0.))
    if not np.isfinite(value) or not np.isfinite(maximum):
        return invalid
    return dict(aggregation=aggregation, status='evaluated', value=value,
                il_term=float(terms[0]), violation_squared_sum=penalty if np.isfinite(penalty) else None,
                max_violation_squared=maximum)


def _compact_assessment(a):
    fields = ('status', 'policy_id', 'policy_fingerprint', 'mode', 'requirements_fingerprint',
              'grid_fingerprint', 'strict_feasible', 'worst_il_db', 'max_violation_db', 'sum_violation_db')
    compact = {key: a[key] for key in fields}
    if 'hybrid_objective' in a:
        compact['hybrid_objective'] = a['hybrid_objective']
    if 'nominal_pass' in a:
        compact['nominal_pass'] = a['nominal_pass']
    else:
        def nominal(row):
            req = row['requirement']
            return (req['level'] if isinstance(req, dict) else req.level) == 'nominal'
        compact['nominal_pass'] = all(row['passed'] for row in a['rows'] if nominal(row))
    return plain(compact)


class WindowJobEvaluation(FixedJobEvaluation):
    """Keep legacy scientific selection in memory; persist compact search rows."""
    def __init__(self, plan, definition, policy, arm, path, spec, *, root):
        if spec.data.get('kind') != 'development_only' or spec.data.get('storage_mode') != 'window100':
            raise ValueError('Window raw is development-only and must be frozen in JobSpec')
        self.journal = None
        self.cached_evaluator = None
        self.debug_history = spec.data['debug_forward_history']
        self.evidence_rows = []
        self.progress = {}
        self.scientific_best = {}
        super().__init__(plan, definition, policy, arm, path, spec, root=root)
        self.result['kind'] = 'development_window_raw_v1'
        chosen = next(a for a in self.data['config']['arms'] if a['name'] == arm)
        self.hybrid_stages = {f"{arm}/{step['name']}": step['aggregation']
                              for step in chosen['steps'] if step['solver'] == 'hybrid'}

    def _validate_checkpoint(self):
        from .runner import _validate_development_output
        _validate_development_output(self.path, self.root, 'window100')

    def _budget(self):
        inactive = sum(v-self.used(k) for k, v in self.allocations.items() if k != self.active)
        return dict(samples_per_forward=len(self.grid.frequency_hz),
            step_remaining=self.allocations[self.active]-self.used(self.active),
            job_remaining=self.job['max_requested_samples']-self.requested,
            trial_remaining=self.data['costs']['max_trial_requested_samples']-self.requested,
            job_reserved=inactive, trial_reserved=inactive+self.other_jobs)

    def used(self, allocation):
        return self.progress.get(allocation, {}).get('requested', 0)

    @property
    def search_requested(self):
        return sum(v['requested'] for k, v in self.progress.items() if k.startswith(self.arm+'/'))

    def snapshot(self):
        if not self.debug_history:
            original = self.rows
            self.rows = self.evidence_rows
            try:
                snapshot = super().snapshot()
            finally:
                self.rows = original
            snapshot['progress_by_allocation'] = plain(self.progress)
            snapshot['best_observed_by_stage'] = raw_numbers(self.scientific_best)
            snapshot['unsaved_window_results_may_be_lost'] = True
            return snapshot
        # Avoid serializing the complex RF responses for search observations.
        # Independent audits and all selection/terminal/anytime responses remain.
        original = self.rows
        compact_rows = []
        for row in original:
            if not row['stage'].startswith(self.arm+'/'):
                compact_rows.append(row)
                continue
            compact = dict(row)
            if not self.spec.data['spot_checks'].get(row['stage']):
                compact.pop('response', None)
            if 'assessment' in row:
                compact['assessment'] = _compact_assessment(row['assessment'])
            if 'physical_checks' in row:
                physical = row['physical_checks']
                compact['physical_checks'] = {k: physical[k] for k in
                    ('component_policy_pass', 'checked_settings', 'min_L_eigenvalue_H')}
            compact_rows.append(compact)
        self.rows = compact_rows
        try:
            snapshot = super().snapshot()
        finally:
            self.rows = original
        best = {}
        for index, row in enumerate(original):
            if row['status'] != 'completed' or not row['stage'].startswith(self.arm+'/'):
                continue
            a = row['assessment']
            key = ((0, a['worst_il_db'], row['vector_sha256']) if a['strict_feasible'] else
                   (1, a['max_violation_db'], a['sum_violation_db'], a['worst_il_db'], row['vector_sha256']))
            stage = row['stage']
            if stage not in best or key < best[stage][0]:
                best[stage] = (key, index)
        snapshot['best_observed_by_stage'] = {stage: dict(batch_index=index,
            vector=snapshot['batches'][index]['vector'], vector_sha256=original[index]['vector_sha256'],
            assessment=snapshot['batches'][index]['assessment']) for stage, (_, index) in best.items()}
        hybrid_best = {}
        for index, row in enumerate(original):
            if row['status'] != 'completed' or row['stage'] not in self.hybrid_stages:
                continue
            score = row['assessment']['hybrid_objective']
            if score['status'] != 'evaluated':
                continue
            stage = row['stage']
            if stage not in hybrid_best or score['value'] < hybrid_best[stage][0]:
                hybrid_best[stage] = (score['value'], index)
        snapshot['best_hybrid_observed_by_stage'] = {stage: dict(batch_index=index,
            vector=snapshot['batches'][index]['vector'], vector_sha256=original[index]['vector_sha256'],
            assessment=snapshot['batches'][index]['assessment']) for stage, (_, index) in hybrid_best.items()}
        snapshot['unsaved_window_results_may_be_lost'] = True
        return snapshot

    @timed_method('checkpoint')
    def _checkpoint(self):
        # Parent constructor calls this before allocations exist. No RF is
        # possible until activate() has persisted the first window.
        if self.journal is None:
            return
        try:
            self.journal.boundary(reserve=self.active is not None and self.status == 'ready')
        except BaseException:
            self.status = 'storage_failed'
            raise

    def activate(self, allocation, grid):
        if self.status != 'ready' or allocation not in self.allocations:
            raise RuntimeError('STOP: inactive/failed/unknown allocation')
        # An active partial window must be confirmed before changing its grid.
        # finish() already persisted the inactive state, so repeating that save
        # before reserving the next allocation adds no crash protection.
        if self.journal is not None and self.active is not None:
            self.journal.boundary(reserve=False)
        self.active, self.stage = allocation, grid
        self.grid = self.plan.requested_grid(grid)
        self.prepared_requirements = prepare_requirements(self.requirements, self.grid)
        # Construction interpolates the fixed preloaded S2Ps, never inside a forward.
        self.cached_evaluator = self.model.evaluator(self.grid)
        try:
            if self.journal is None:
                self.journal = ForwardJournal(self.path, identity=plain(self.spec),
                    validate_inputs=self._contract, snapshot=self.snapshot, budget=self._budget)
                self.journal.timer = getattr(self, 'timer', None)
                self.journal.start()
            else:
                self.journal.boundary(reserve=True)
        except BaseException:
            self.status = 'storage_failed'
            raise

    def _assess(self, vector):
        if self.status != 'ready' or self.journal is None:
            raise RuntimeError('STOP: failed/stopped/unknown Job cannot retry')
        row = dict(stage=self.stage, allocation=self.active, grid_sha256=self.prepared_requirements.grid_fingerprint,
                   requested=0, completed=0, status='rejected', phase='physical_values',
                   independent={'status': 'not_run', 'reason': 'not requested'})
        try:
            x = np.array(vector, copy=True)
            row['vector'] = x.tolist()
            if x.ndim == 1 and x.dtype.kind in 'fiu' and np.all(np.isfinite(x)):
                row['vector_sha256'] = vector_sha(x)
            physical = timed_call(getattr(self, 'timer', None), 'physical_validation', validate_values,
                                  self.definition, self.model.schema, x, self.policy, frozen_model=self.model)
            x = np.asarray(x, dtype=float)
            x.setflags(write=False)
            row.update(vector_sha256=vector_sha(x), physical_checks=physical)
            n = len(self.grid.frequency_hz)
            self._check_budget(n)
            self.journal.begin_forward()
        except BaseException as exc:
            self.status, self.reason = 'stopped', f'{type(exc).__name__}: {exc}'
            row['reason'] = self.reason
            row['batch_index'] = len(self.rows)
            self.rows.append(row)
            self.evidence_rows.append(row)
            if not self.journal.failed:
                self._checkpoint()
            raise
        self.requested += n
        progress = self.progress.setdefault(self.active, dict(forwards=0, requested=0, completed=0))
        progress['requested'] += n
        progress['forwards'] += 1
        row.update(requested=n, status='unknown', phase='forward', batch_index=len(self.rows))
        self.rows.append(row)
        if not self.stage.startswith(self.arm+'/') or self.spec.data['spot_checks'].get(self.stage):
            self.evidence_rows.append(row)
        try:
            response = timed_call(getattr(self, 'timer', None), 'rf_forward', self.cached_evaluator.evaluate, x)
            if not self.stage.startswith(self.arm+'/') or self.spec.data['spot_checks'].get(self.stage):
                row['response'] = dict(s_real=response.s.real.tolist(), s_imag=response.s.imag.tolist(),
                    **{k: getattr(response, k).tolist() for k in ('il_db', 'apl_db', 'in_rl_db', 'out_rl_db')})
            row['phase'] = 'requirements'
            search = self.stage.startswith(self.arm+'/')
            compact_search = search and not self.debug_history and not self.spec.data['spot_checks'].get(self.stage)
            if compact_search:
                assessment = timed_call(getattr(self, 'timer', None), 'requirements', evaluate_requirements,
                                        response, self.prepared_requirements)
                assessment.update(summarize_mandatory(assessment, self.prepared_requirements))
                row['assessment'] = {key: assessment[key] for key in
                                     ('worst_il_db', 'strict_feasible', 'max_violation_db', 'sum_violation_db')}
            else:
                assessment = timed_call(getattr(self, 'timer', None), 'requirements', evaluate_requirements,
                                        response, self.requirements, requested_grid=self.grid)
                row['assessment'] = _compact_assessment(assessment) if search else plain(assessment)
            if self.debug_history and self.stage in self.hybrid_stages:
                row['assessment']['hybrid_objective'] = _hybrid_observation(
                    assessment, self.hybrid_stages[self.stage])
            row.update(status='completed', completed=n, phase='completed', reason='forward_and_requirements_completed')
            self.completed += n
            progress['completed'] += n
            if self.stage.startswith(self.arm+'/') and not self.debug_history:
                a = assessment
                key = ((0, a['worst_il_db'], row['vector_sha256']) if a['strict_feasible'] else
                       (1, a['max_violation_db'], a['sum_violation_db'], a['worst_il_db'], row['vector_sha256']))
                previous = self.scientific_best.get(self.stage)
                if previous is None or key < previous['_key']:
                    detailed = (evaluate_requirements(response, self.requirements, requested_grid=self.grid)
                                if compact_search else a)
                    full = plain(detailed)
                    full['nominal_pass'] = _compact_assessment(detailed)['nominal_pass']
                    self.scientific_best[self.stage] = dict(_key=key, batch_index=row['batch_index'],
                        vector=row['vector'], vector_sha256=row['vector_sha256'], assessment=full,
                        physical_checks=physical, grid_sha256=row['grid_sha256'])
            self.journal.complete_forward()
        except BaseException as exc:
            self.reason = f'{type(exc).__name__}: {exc}'
            row.update(status='failed', reason=self.reason)
            self.status = 'storage_failed'  # parent must keep its full unknown cap
            self.journal.abort(self.reason)
            raise
        result = dict(vector=x.copy(), vector_sha256=vector_sha(x), model=self.model,
                      assessment=assessment, plan_sha256=self.plan.sha256,
                      grid_sha256=self.prepared_requirements.grid_fingerprint, batch_index=len(self.rows)-1)
        indices = self.spec.data['spot_checks'].get(self.stage)
        if indices:
            self.spot_check(result['batch_index'], indices)
        return result

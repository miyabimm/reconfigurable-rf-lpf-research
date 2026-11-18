"""RF-T009 Search→Terminal science for a single frozen Job."""
from dataclasses import asdict
import hashlib
import json
from pathlib import Path

import numpy as np

from lpf import minimax_profile
from lpf.minimax_profile import signed_margins, _margin_parameters
from lpf.optimizers.hybrid import hybrid_minimize
from lpf.optimizers.result import OptimizerResult
from lpf.optimizers.slp import slp_minimize
from lpf.optimizers.slsqp import slsqp_minimize
from lpf.rf_core.model import build_rf_model
from .plan import grid_from_record
from .source import source_identity
from .component_constraints import _check_vector_box, _validate_values_with_bounds
from .evaluation import raw_numbers
from .storage import _save_checkpoint, canonical, plain, sha, vector_sha


class DevelopmentWorker:
    """Run a frozen RF-T009 Job once. The caller owns durable reservation and raw."""

    def __init__(self, compiled, job_index, source, *, root, checkpoint):
        self.plan, self.definition, self.profile, self.model, self.physical_bounds = compiled
        self.data = self.plan.data
        if sha(self.data) != self.plan.sha256:
            raise ValueError('Frozen Plan SHA mismatch')
        cfg = self.data['config']
        job = self.data['jobs'][job_index]
        self.arm, self.seed = job['arm'], job['seed']
        self.steps = next(a['steps'] for a in cfg['arms'] if a['name'] == self.arm)
        self.root = root
        self.source = source
        self.source_sha256 = sha(source)
        self._verify_boundary()
        self.policy = json.loads(self.profile.base_json)
        self.physical_model = build_rf_model(self.definition, self.policy)
        if (sha(asdict(self.definition)) != sha(self.data['definition']) or
                plain(self.model.schema) != self.data['parameter_schema'] or
                self.profile.fingerprint != self.data['rf_profile']['effective_sha256']):
            raise ValueError('Frozen Plan/Job inputs mismatch')
        self.bounds = self.data['search_bounds']
        self.x = _check_vector_box(job['vector'], self.bounds).astype(float, copy=True)
        if vector_sha(self.x) != job['vector_sha256']:
            raise ValueError('Start vector SHA mismatch')
        self.x.setflags(write=False)
        self._physical(self.x)
        self.grids = {stage: grid_from_record(self.data['grids'][stage]) for stage in
                      [f"{self.arm}/{step['name']}" for step in self.steps] + ['terminal']}
        self.spot_checks = {stage: tuple(indices) for stage, indices in self.data['spot_checks'].items()
                            if stage in self.grids}
        self.path = Path(checkpoint)
        self.path.mkdir(exist_ok=False)
        self.checkpoint_interval = self.data['checkpoint_interval']
        self.checkpoint_files = {}
        self.audit_samples = {}
        self._started = False

    def _verify_boundary(self):
        if source_identity(self.root) != self.source:
            raise ValueError('Source/environment changed; no retry')
        if minimax_profile.load_minimax_profile('RF-T009', root=self.root, allow_trial=True) != self.profile:
            raise ValueError('RF profile/base/bands/S2P changed; no retry')
        ref = self.data['config']['definition']
        if 'path' in ref and hashlib.sha256((self.root/ref['path']).read_bytes()).hexdigest() != ref['source_sha256']:
            raise ValueError('Plan definition source changed; no retry')

    def _physical(self, vector):
        return _validate_values_with_bounds(self.definition, self.model.schema, vector, self.policy,
                                            self.physical_bounds, frozen_model=self.physical_model)

    def _audit(self, vector, response, stage):
        from lpf.rf_core.independent import evaluate_independent_response
        spots = []
        g = response.grid
        for i in self.spot_checks.get(stage, ()):
            ref = evaluate_independent_response(self.model, vector, float(g.frequency_hz[i]), int(g.setting[i]))
            for key in ('s', 'il_db', 'apl_db', 'in_rl_db', 'out_rl_db'):
                if not np.allclose(getattr(response, key)[i], ref[key], rtol=0, atol=1e-9):
                    raise ValueError(f'Independent MNA mismatch: {key} sample {i}')
            spots.append(dict(index=i, reference=ref))
        if not spots:
            return dict(status='not_run', reason='not requested')
        self.audit_samples[stage] = self.audit_samples.get(stage, 0) + len(spots)
        result = dict(status='pass', sample_indices=list(self.spot_checks[stage]),
                      passivity='pass_at_samples', power_balance='pass_at_samples', whole_band_checked=False)
        if stage == 'terminal':
            result['spots'] = spots
        return result

    def _forward(self, evaluator, vector, stage):
        terminal = stage == 'terminal'
        if self.forward_count >= self.forward_cap:
            raise ValueError(f'STOP: {"Terminal" if terminal else "Search"} RF forward budget exhausted')
        physical = None
        if terminal:
            _check_vector_box(vector, self.bounds)
            physical = self._physical(vector)
        self.forward_count += 1  # Charge before entering RF Core, even when it raises.
        # Search callbacks are bounded by the Optimizers. RF Core still checks
        # finite values, full L SPD and numerical failures on each evaluation.
        response = evaluator.evaluate(vector, check_power=True) if terminal else evaluator.evaluate(vector)
        if (response.grid is not evaluator.grid or response.policy_id != self.model.policy_id or
                response.policy_fingerprint != self.model.policy_fingerprint):
            raise ValueError('Response profile/grid mismatch')
        return response, physical, self._audit(vector, response, stage)

    def _checkpoint(self, step, stage, observation):
        payload = dict(kind='development_temporary_observation_v1', sequence=len(self.checkpoint_files) + 1,
                       arm=self.arm, step=step, seed=self.seed, plan_sha256=self.plan.sha256,
                       source_sha256=self.source_sha256, rf_profile=self.data['rf_profile'],
                       grid_sha256=self.data['grids'][stage]['sha256'],
                       forward_count=self.forward_count, observation=observation)
        target = self.path/f"{payload['sequence']:06d}.json"
        digest = _save_checkpoint(target, payload)
        data = target.read_bytes()
        if hashlib.sha256(data).hexdigest() != digest or canonical(json.loads(data)) != canonical(payload):
            raise ValueError('Checkpoint readback mismatch')
        self.checkpoint_files[target.name] = dict(bytes=len(data), sha256=digest)

    def _search(self, step, x):
        stage = f"{self.arm}/{step['name']}"
        evaluator = self.model.evaluator(self.grids[stage])
        threshold, direction = _margin_parameters(self.profile, evaluator.grid)
        opts = step['effective_options']
        self.forward_count, self.forward_cap = 0, opts['max_evaluations']
        saved = None
        independent = None

        def residuals(vector):
            nonlocal independent
            response, _, independent = self._forward(evaluator, vector, stage)
            residual = direction * (response.il_db - threshold)
            if not np.all(np.isfinite(residual)):
                raise ValueError('Nonfinite signed-margin Search residuals')
            return residual

        def observe(vector, objective):
            nonlocal saved
            if self.forward_count % self.checkpoint_interval == 0:
                digest = vector_sha(vector)
                self._checkpoint(step['name'], stage, dict(vector=plain(vector), vector_sha256=digest, objective=objective))
                saved = self.forward_count, digest, objective

        solver = step['solver']
        if solver == 'hybrid':
            out = hybrid_minimize(residuals, x, self.bounds, seed=self.seed,
                                  aggregation=step['aggregation'], objective_callback=observe, **opts)
        else:
            minimize = slsqp_minimize if solver == 'slsqp' else slp_minimize
            out = minimize(residuals, x, self.bounds, constraints=None, aggregation=step['aggregation'],
                           objective_callback=observe, **opts)
        if (not isinstance(out, OptimizerResult) or out.x is None or out.objective is None or
                not np.isfinite(out.objective) or type(out.evaluations) is not int or
                not 1 <= out.evaluations <= opts['max_evaluations'] or type(out.converged) is not bool or
                not isinstance(out.stop_reason, str) or not out.stop_reason or out.stop_reason.startswith('invalid_') or
                (out.converged and out.stop_reason in ('evaluation_limit', 'evaluation_budget_exhausted')) or
                not 1 <= self.forward_count <= self.forward_cap):
            raise ValueError('Invalid or missing Optimizer result; no replacement or retry')
        _check_vector_box(out.x, self.bounds)
        self._physical(out.x)
        digest = vector_sha(out.x)
        if saved != (self.forward_count, digest, out.objective):
            self._checkpoint(step['name'], stage, dict(vector=plain(out.x), vector_sha256=digest, objective=out.objective))
        return dict(name=step['name'], solver=solver, solver_options=opts, aggregation=step['aggregation'],
                    solver_result=raw_numbers(out), stop_reason=out.stop_reason, converged=out.converged,
                    forward_count=self.forward_count, requested_samples=self.forward_count * len(evaluator.grid.frequency_hz),
                    input_vector=plain(x), input_vector_sha256=vector_sha(x),
                    grid_sha256=self.data['grids'][stage]['sha256'], independent=independent), out.x

    def run(self):
        if self._started:
            raise RuntimeError('Worker cannot retry or resume')
        self._started = True
        x = self.x.copy()
        steps = []
        for step in self.steps:
            record, x = self._search(step, x.copy())
            steps.append(record)
        self.forward_count, self.forward_cap = 0, 1
        evaluator = self.model.evaluator(self.grids['terminal'])
        response, physical, independent = self._forward(evaluator, x, 'terminal')
        margin, margins = signed_margins(self.profile, evaluator.grid, response)
        terminal_row = raw_numbers(dict(vector=x, vector_sha256=vector_sha(x), physical=physical,
            terminal_signed_max_margin_db=margin, signed_margins_db=margins, performance_feasible=margin <= 0,
            response=response, independent=independent, external_passivity='checked_on_terminal_grid',
            power_balance='checked_on_terminal_grid', independent_power_balance='checked_at_independent_mna_spots'))
        self._verify_boundary()
        search_forwards = sum(s['forward_count'] for s in steps)
        return dict(kind='development_only', status='converged' if all(s['converged'] for s in steps) else 'not_converged',
            steps=steps, terminal=dict(status='completed', forward_count=1, candidates=[terminal_row]),
            forward_count=search_forwards + 1, plan=self.data, plan_sha256=self.plan.sha256,
            source=self.source, source_sha256=self.source_sha256, arm=self.arm, seed=self.seed,
            definition=plain(self.definition), parameter_schema=plain(self.model.schema),
            initial_vector=plain(self.x), initial_vector_sha256=vector_sha(self.x),
            search_bounds=plain(self.bounds), search_bounds_sha256=sha(self.bounds), rf_profile=self.data['rf_profile'],
            performance_profile=self.profile.profile, terminal_grid_sha256=self.data['grids']['terminal']['sha256'],
            solver_objective=dict(residual='signed_margin_db', slp='signed max [dB]',
                                  slsqp_hybrid='configured sum or max of squared residuals [dB^2]', weights='unit'),
            costs=dict(search_forwards=search_forwards, search_requested_samples=sum(s['requested_samples'] for s in steps),
                       terminal_forwards=1, terminal_requested_samples=len(evaluator.grid.frequency_hz),
                       independent_mna_samples_by_stage=self.audit_samples),
            finite_grid_only=True, continuous_band_proven=False, rf_compliance_certified=False,
            physical_q_srf_em_checked=False)

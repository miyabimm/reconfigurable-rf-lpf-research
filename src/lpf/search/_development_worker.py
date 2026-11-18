"""RF performance profile science Worker for development G2 only."""
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import tempfile

import numpy as np

from lpf.constraint_versions import constraint_fingerprint
from lpf.minimax_profile import load_minimax_profile, signed_margins, _margin_parameters
from lpf.optimizers.hybrid import hybrid_minimize
from lpf.optimizers.result import OptimizerResult
from lpf.optimizers.slp import slp_minimize
from lpf.optimizers.slsqp import slsqp_minimize
from lpf.rf_core.model import build_rf_model
from ._job_evaluation import source_identity
from .component_constraints import (_check_vector_box, _validate_values_with_bounds,
                                    physical_bounds, validate_search_box)
from .evaluation import raw_numbers
from .performance import grid_fingerprint
from .preflight import definition_sha, freeze
from .storage import _normalize_search_bounds, _save_checkpoint, canonical, plain, sha, vector_sha
from .worker import _development_options


class DevelopmentWorker:
    """Run a frozen RF-T009 Job once. The caller owns durable reservation and raw."""

    def __init__(self, plan, definition, policy, arm, seed, vector, expected_vector_sha,
                 *, root, checkpoint, checkpoint_interval=1000, spot_checks=None, search_bounds=None):
        data = plan.data
        cfg = data['config']
        if cfg['rf'] != {'constraint_id': 'RF-T009', 'allow_trial': True} or 'rf_profile' not in data:
            raise ValueError('STOP: DevelopmentWorker requires an explicit RF-T009 performance profile; legacy performance is unsupported')
        if (cfg['objective'] != 'full_lpf' or 'campaign' in cfg or 'selection' in cfg or cfg['anytime_samples']):
            raise ValueError('STOP: RF-T009 G2 requires a standalone Search→Terminal Plan')
        self.root = Path(root).resolve()
        self.source = source_identity(self.root)
        self.source_sha256 = sha(self.source)
        if sha(data) != plan.sha256 or sha(freeze(cfg, self.root)) != plan.sha256:
            raise ValueError('Plan/current RF inputs mismatch')
        self.profile = load_minimax_profile('RF-T009', root=self.root, allow_trial=True)
        if (self.profile.fingerprint != data['rf_profile']['effective_sha256'] or
                constraint_fingerprint(policy) != self.profile.base_sha256):
            raise ValueError('RF profile/physical base mismatch')
        if sha(asdict(definition)) != definition_sha(cfg['definition']):
            raise ValueError('Definition/Plan mismatch')
        steps = next((a['steps'] for a in cfg['arms'] if a['name'] == arm), None)
        if not steps:
            raise ValueError('Plan arm with steps required')
        if type(seed) is not int or seed not in cfg['seeds'] or vector_sha(vector) != expected_vector_sha:
            raise ValueError('Seed/start SHA mismatch')
        self.plan, self.data, self.arm, self.seed, self.steps = plan, data, arm, seed, steps
        self.definition = definition
        self.policy = json.loads(self.profile.base_json)
        self.physical_model = build_rf_model(definition, self.policy)
        self.model = self.profile.build_model(definition)
        self.physical_bounds = physical_bounds(definition, self.model.schema, self.policy)
        self.bounds = self.physical_bounds if search_bounds is None else _normalize_search_bounds(search_bounds)
        validate_search_box(self.bounds, self.physical_bounds)
        self.x = _check_vector_box(vector, self.bounds).astype(float, copy=True)
        self.x.setflags(write=False)
        self._physical(self.x)
        self.grids = {stage: plan.requested_grid(stage) for stage in
                      [f"{arm}/{step['name']}" for step in steps] + ['terminal']}
        if any(grid_fingerprint(g) != data['grids'][stage]['sha256'] for stage, g in self.grids.items()):
            raise ValueError('Grid/Plan mismatch')
        if not isinstance(spot_checks, dict) or not spot_checks.get('terminal'):
            raise ValueError('RF-T009 requires terminal MNA spots')
        self.spot_checks = {}
        for stage, indices in spot_checks.items():
            if (stage not in self.grids or not isinstance(indices, list) or not indices or
                    any(type(i) is not int or not 0 <= i < len(self.grids[stage].frequency_hz) for i in indices) or
                    len(set(indices)) != len(indices)):
                raise ValueError('Invalid independent spot checks')
            self.spot_checks[stage] = tuple(indices)
        self.path = Path(checkpoint).resolve()
        if (not self.path.is_relative_to(Path(tempfile.gettempdir()).resolve()) or
                self.path.is_relative_to(self.root) or self.path.exists()):
            raise ValueError('Fresh temporary checkpoint outside repository required')
        if type(checkpoint_interval) is not int or checkpoint_interval < 1:
            raise ValueError('Positive checkpoint interval required')
        self.path.mkdir(exist_ok=False)
        self.checkpoint_interval = checkpoint_interval
        self.checkpoint_files = {}
        self.audit_samples = {}
        self._started = False

    def _verify_boundary(self):
        if source_identity(self.root) != self.source:
            raise ValueError('Source/environment changed; no retry')
        if load_minimax_profile('RF-T009', root=self.root, allow_trial=True) != self.profile:
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
        _check_vector_box(vector, self.bounds)
        physical = self._physical(vector)
        if self.forward_count >= self.forward_cap:
            raise ValueError(f'STOP: {"Terminal" if stage == "terminal" else "Search"} RF forward budget exhausted')
        self.forward_count += 1  # Charge before entering RF Core, even when it raises.
        response = evaluator.evaluate(vector, check_power=True)
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
        opts = _development_options(step)
        self.forward_count, self.forward_cap = 0, opts['max_evaluations']
        pending, saved = None, None
        observed = set()
        independent = None

        def residuals(vector):
            nonlocal pending, independent
            if pending is not None:
                raise ValueError('Optimizer did not report its previous Search observation')
            response, _, independent = self._forward(evaluator, vector, stage)
            residual = direction * (response.il_db - threshold)
            if not np.all(np.isfinite(residual)):
                raise ValueError('Nonfinite signed-margin Search residuals')
            pending = vector_sha(vector)
            return residual

        def observe(vector, objective, *_):
            nonlocal pending, saved
            digest = vector_sha(vector)
            if digest != pending or not np.isfinite(objective):
                raise ValueError('Optimizer objective does not match Search observation')
            pending = None
            observed.add((digest, objective))
            if self.forward_count % self.checkpoint_interval == 0:
                self._checkpoint(step['name'], stage, dict(vector=plain(vector), vector_sha256=digest, objective=objective))
                saved = self.forward_count, digest, objective

        solver = step['solver']
        if solver == 'hybrid':
            out = hybrid_minimize(residuals, x, self.bounds, seed=self.seed,
                                  aggregation=step['aggregation'], progress_callback=observe, **opts)
        else:
            minimize = slsqp_minimize if solver == 'slsqp' else slp_minimize
            out = minimize(residuals, x, self.bounds, constraints=None, aggregation=step['aggregation'],
                           objective_callback=observe, **opts)
        if (not isinstance(out, OptimizerResult) or out.x is None or out.objective is None or
                not np.isfinite(out.objective) or type(out.evaluations) is not int or
                not 1 <= out.evaluations <= opts['max_evaluations'] or type(out.converged) is not bool or
                not isinstance(out.stop_reason, str) or not out.stop_reason or out.stop_reason.startswith('invalid_') or
                (out.converged and out.stop_reason in ('evaluation_limit', 'evaluation_budget_exhausted')) or pending is not None):
            raise ValueError('Invalid or missing Optimizer result; no replacement or retry')
        digest = vector_sha(out.x)
        if (digest, out.objective) not in observed:
            raise ValueError('Optimizer result not observed on Search grid')
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
            self._verify_boundary()
            record, x = self._search(step, x.copy())
            steps.append(record)
        self._verify_boundary()
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

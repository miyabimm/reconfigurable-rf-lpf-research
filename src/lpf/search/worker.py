"""Shared fixed-step science with distinct development and G1-bound formal entries."""
from dataclasses import dataclass
import json

from lpf.optimizers.slsqp import slsqp_minimize
from lpf.optimizers.hybrid import hybrid_minimize
from lpf.optimizers.slp import slp_minimize
from .storage import canonical, plain, sha, vector_sha


def freeze_development_job(plan, definition, policy, arm, seed, vector, *, root=None, spot_checks=None,
                           campaign_context=None, storage_mode='legacy', debug_forward_history=False):
    """Freeze one schema-2 development Job; this is NOT a G1 JobSpec."""
    if storage_mode not in ('legacy', 'window100'):
        raise ValueError('Unknown development storage mode')
    return _freeze_fixed_job(plan, definition, policy, arm, seed, vector, root=root,
        spot_checks=spot_checks, campaign_context=campaign_context, storage_mode=storage_mode,
        debug_forward_history=debug_forward_history)


def freeze_campaign_job(plan, definition, policy, arm, seed, vector, *, root,
                        spot_checks, campaign_context, formal_binding):
    """Freeze a distinct formal Job after read-only G0/G1 revalidation."""
    from .gates import verify_campaign_binding
    verify_campaign_binding(formal_binding, root)
    _campaign_job_envelope(plan, spot_checks, campaign_context, formal_binding)
    return _freeze_fixed_job(plan, definition, policy, arm, seed, vector, root=root,
        spot_checks=spot_checks, campaign_context=campaign_context, formal_binding=formal_binding)


def _freeze_fixed_job(plan, definition, policy, arm, seed, vector, *, root=None,
                      spot_checks=None, campaign_context=None, formal_binding=None, storage_mode='legacy',
                      debug_forward_history=False):
    if type(debug_forward_history) is not bool or (debug_forward_history and storage_mode != 'window100'):
        raise ValueError('Debug forward history requires development window100')
    from dataclasses import asdict
    from pathlib import Path
    from .plan import ROOT
    from .preflight import freeze
    from .component_constraints import validate_values, physical_bounds
    from lpf.rf_core.model import build_rf_model
    from ._job_evaluation import source_identity
    root = Path(root or ROOT).resolve()
    data = plan.data
    if sha(data) != plan.sha256 or sha(freeze(data['config'], root)) != plan.sha256:
        raise ValueError('Plan/source/RF/grid SHA mismatch')
    config = data['config']
    if formal_binding is None and campaign_context is None and 'selection' in config:
        raise ValueError('Development requires a selectionless Plan; old Plans are not converted')
    if campaign_context is not None and 'selection' not in config:
        raise ValueError('Campaign retains its existing Selection Plan')
    if formal_binding is not None and 'selection' not in config:
        raise ValueError('Formal Campaign requires its existing Selection Plan')
    from .preflight import definition_sha
    if sha(asdict(definition)) != definition_sha(config['definition']):
        raise ValueError('Development Job requires a frozen complete definition')
    if type(seed) is not int or seed not in config['seeds']:
        raise ValueError('Seed not frozen in Plan')
    chosen = next((a for a in config['arms'] if a['name'] == arm), None)
    if chosen is None:
        raise ValueError('Arm not frozen in Plan')
    model = build_rf_model(definition, policy)
    if model.policy_fingerprint != data['requirements']['policy_fingerprint']:
        raise ValueError('Development Job RF mismatch')
    validate_values(definition, model.schema, vector, policy)
    spot_checks = {} if spot_checks is None else spot_checks
    if not isinstance(spot_checks, dict):
        raise ValueError('Explicit stage/sample-index mapping required')
    allowed = {f"{arm}/{s['name']}" for s in chosen['steps']} | {'terminal', 'anytime'}
    if campaign_context is not None:
        allowed.add('selection')
    for grid, indices in spot_checks.items():
        if (grid not in allowed or not isinstance(indices, list) or not indices or
                len(set(indices)) != len(indices) or any(type(i) is not int or
                not 0 <= i < data['grids'][grid]['requested_samples_per_forward'] for i in indices)):
            raise ValueError('Invalid frozen independent spot-check request')
    source = source_identity(root)
    frozen = dict(kind='development_only', plan=data, definition=asdict(definition),
        arm=arm, seed=seed, start=dict(vector=plain(vector), vector_sha256=vector_sha(vector)),
        source=source, spot_checks=spot_checks, bounds=physical_bounds(definition, model.schema, policy),
        solver_options=[_development_options(s) for s in chosen['steps']])
    if storage_mode != 'legacy':
        if storage_mode != 'window100' or formal_binding is not None or campaign_context is not None:
            raise ValueError('Window storage is for standalone development Jobs only')
        frozen['storage_mode'] = storage_mode
        frozen['debug_forward_history'] = debug_forward_history
    job_id = f'development-{arm}-{seed}'
    if campaign_context is not None:
        import re
        from .plan import fields
        fields(campaign_context, 'job_id parent_job_id plan_sha256 proposal_sha256 based_on_state_sha256')
        if (not isinstance(campaign_context['job_id'], str) or
                not re.fullmatch(r'job-[0-9]{6,}', campaign_context['job_id']) or
                (campaign_context['parent_job_id'] is not None and
                 (not isinstance(campaign_context['parent_job_id'], str) or
                  not re.fullmatch(r'job-[0-9]{6,}', campaign_context['parent_job_id']))) or
                any(type(campaign_context[k]) is not str or not re.fullmatch('[0-9a-f]{64}', campaign_context[k])
                    for k in ('plan_sha256', 'proposal_sha256', 'based_on_state_sha256'))):
            raise ValueError('Invalid frozen Campaign Job provenance')
        frozen['campaign_context'] = campaign_context
        job_id = 'development-' + campaign_context['job_id']
    trial_id = 'development_only'
    if formal_binding is not None:
        if campaign_context is None:
            raise ValueError('Formal Job requires Campaign provenance')
        frozen.update(kind='campaign_formal_job_v1', formal_binding=formal_binding)
        trial_id = formal_binding['experiment_id']
        job_id = trial_id + '-' + campaign_context['job_id']
    return JobSpec(job_id, trial_id, plan.sha256, sha(source), canonical(frozen))


def _campaign_job_envelope(plan, spot_checks, context, binding):
    from .campaign import _structure
    from .proposals import definition_from_data
    import copy
    expected = copy.deepcopy(binding['plan']['config'])
    config = plan.data['config']
    expected['definition'] = config['definition']
    if config != expected or context['plan_sha256'] != binding['plan_sha256']:
        raise ValueError('Formal Job outside G1 Campaign Plan')
    # Use the same topology parser and envelope rules as proposal admission.
    _structure(definition_from_data(config['definition']), config['campaign'])
    independent = config['campaign']['independent']
    expected_spots = {} if independent['stage'] == 'not_run' else {'terminal': independent['sample_indices']}
    if spot_checks != expected_spots:
        raise ValueError('Formal Job independent validation outside G1')


def _development_options(step):
    # Freeze generic numerical defaults as well as explicitly configured budgets.
    if step['solver'] == 'hybrid':
        return dict(max_evaluations=step['options']['max_search_forwards'], restart_sigma=0.1)
    defaults = {'slsqp': dict(tolerance=1e-9, constraint_tolerance=1e-7),
                'slp': dict(initial_step=.25, min_step=1e-8, fd_step=1e-6,
                            tolerance=1e-7, constraint_tolerance=1e-7), 'hybrid': {}}
    return {**defaults[step['solver']], **step['options']}


def execute_development_job(spec, checkpoint, *, root=None, solver_kind='scipy', timer=None):
    """Single-process fixed steps, shared durable RF ledger, development tmp only.

    solver_kind labels patched solver tests as fixture; it does not replace RF.
    No scheduler/CLI/production gate is enabled. Existing raw always STOPs.
    """
    if spec.data.get('kind') != 'development_only' or spec.trial_id != 'development_only':
        raise ValueError('not_ready: Development entry rejects formal/unknown JobSpec')
    return _execute_fixed_job(spec, checkpoint, root=root, solver_kind=solver_kind, timer=timer)


def execute_campaign_job(spec, checkpoint, *, root, solver_kind='scipy'):
    """Formal entrance; reuse scientific execution, never relabel a dev raw."""
    from .gates import verify_campaign_job
    verify_campaign_job(spec, checkpoint, root)
    return _execute_fixed_job(spec, checkpoint, root=root, solver_kind=solver_kind)


def _timed_solver(timer, name, solver, *args, **kwargs):
    if timer is None:
        return solver(*args, **kwargs)
    with timer.measure(name):
        return solver(*args, **kwargs)


def _execute_fixed_job(spec, checkpoint, *, root=None, solver_kind='scipy', timer=None):
    from pathlib import Path
    import numpy as np
    from .plan import ROOT, Plan
    from .problem import Problem, hybrid_residuals
    from .component_constraints import validate_values
    from .evaluation import raw_numbers
    from .validation import rank_candidates
    from ._job_evaluation import FixedJobEvaluation
    from lpf.constraint_versions import load_constraint
    from lpf.topology_management import CircuitDefinition
    from lpf.topology_management import InductorTree, CapacitorPlacement
    root = Path(root or ROOT).resolve()
    d = spec.data
    formal = d.get('kind') == 'campaign_formal_job_v1'
    legacy_campaign = 'campaign_context' in d
    if not formal and (d.get('kind') != 'development_only' or spec.trial_id != 'development_only'):
        raise ValueError('Unknown fixed Job kind')
    if solver_kind not in ('scipy', 'fixture'):
        raise ValueError('Unknown solver execution kind')
    plan = Plan(canonical(d['plan']), spec.plan_sha256)
    definition = dict(d['definition'])
    definition['inductor_tree'] = InductorTree(**definition['inductor_tree'])
    definition['capacitor_placement'] = CapacitorPlacement(**definition['capacitor_placement'])
    definition = CircuitDefinition(**definition)
    cfg = plan.data['config']
    policy = load_constraint(cfg['rf']['constraint_id'], root=root, allow_trial=cfg['rf']['allow_trial'])
    # Rebuild the minimal frozen record, not only its self-declared hashes.
    if formal:
        _campaign_job_envelope(plan, d['spot_checks'], d['campaign_context'], d['formal_binding'])
    expected = _freeze_fixed_job(plan, definition, policy, d['arm'], d['seed'], d['start']['vector'],
                                      root=root, spot_checks=d['spot_checks'],
                                      campaign_context=d.get('campaign_context'),
                                      formal_binding=d.get('formal_binding') if formal else None,
                                      storage_mode=d.get('storage_mode', 'legacy'),
                                      debug_forward_history=d.get('debug_forward_history', False))
    if expected != spec:
        raise ValueError('Fixed Job/input/source/options SHA mismatch')
    from lpf.timing import timed_call
    if d.get('storage_mode', 'legacy') == 'window100':
        from ._window_evaluation import WindowJobEvaluation
        meter_class = WindowJobEvaluation
    else:
        meter_class = FixedJobEvaluation
    meter = timed_call(timer, 'evaluation_initialization', meter_class,
                       plan, definition, policy, d['arm'], checkpoint, spec, root=root)
    meter.timer = timer
    result = meter.result
    result.update(status='unknown', solver_execution_kind=solver_kind, rf_backend='rf_core')
    arm = next(a for a in cfg['arms'] if a['name'] == d['arm'])
    result['steps'] = [dict(name=s['name'], settings=s, status='not_started', candidates=[]) for s in arm['steps']]
    x = d['start']['vector']
    candidates = []
    all_success = True
    try:
        for i, step in enumerate(arm['steps']):
            meter.activate(f"{d['arm']}/{step['name']}", f"{d['arm']}/{step['name']}")
            raw = result['steps'][i]
            raw.update(status='unknown', input_vector=plain(x), input_vector_sha256=vector_sha(x))
            meter._checkpoint()
            p = Problem.from_fixed_stage(meter)
            p.timer = timer
            opts = d['solver_options'][i]
            observed_objectives = {}
            def record_objective(v, score):
                observed_objectives[vector_sha(v)] = score
            if step['solver'] == 'hybrid':
                def hybrid_callback(v):
                    return hybrid_residuals(meter.evaluate(v)['assessment'])
                def residuals(v):
                    return hybrid_callback(v)
                if timer is not None:
                    unmeasured_residuals = residuals
                    def residuals(v):
                        return timer.call('solver_callback', unmeasured_residuals, v)
                import os
                event_path = os.environ.get('LPF_DEVELOP_MONITOR_EVENTS') if not formal and timer is None else None
                def event_callback(event):
                    event.update(job_id=spec.job_id, arm=d['arm'], step=step['name'])
                    with open(event_path, 'a', encoding='utf-8') as stream:
                        stream.write(json.dumps(event, sort_keys=True) + '\n')
                if timer is not None:
                    def collect_event(event):
                        if event['event'] in ('local_run_end', 'restart_start_generated'):
                            label = 'hybrid_local_run' if event['event'] == 'local_run_end' else 'hybrid_restart_generation'
                            timer.add(f"{label}:{step['name']}", round(event['wall_s'] * 1e9),
                                      failed=event.get('interrupted', False))
                    extra = {'event_callback': collect_event}
                else:
                    extra = {'event_callback': event_callback} if event_path else {}
                if not legacy_campaign and solver_kind == 'scipy':
                    extra['objective_callback'] = record_objective
                out = _timed_solver(timer, f"solver:{step['name']}:hybrid", hybrid_minimize,
                                      residuals, x, d['bounds'], seed=d['seed'],
                                      aggregation=step['aggregation'], **extra, **opts)
                found = [r.end_x for r in out.runs if r.end_x is not None]
                if out.best_x is not None:
                    found.append(out.best_x)
                next_x = out.x if not legacy_campaign and solver_kind == 'scipy' else out.best_x
                success = bool(out.runs) and all(r.success for r in out.runs)
            else:
                solver = slsqp_minimize if step['solver'] == 'slsqp' else slp_minimize
                callback = p.residuals if step['solver'] == 'slsqp' else p.errors
                extra = {'objective_callback': record_objective} if not legacy_campaign and solver_kind == 'scipy' else {}
                out = _timed_solver(timer, f"solver:{step['name']}:{step['solver']}", solver,
                             callback, x, d['bounds'], constraints=p.constraints,
                             aggregation=step['aggregation'], **extra, **opts)
                next_x, success = out.x, out.success
                found = [out.x]
            raw.update(solver_result=raw_numbers(out), status='converged' if success else 'not_converged')
            if not legacy_campaign:
                found = [] if next_x is None else [next_x]
            if not legacy_campaign and meter.used(f"{d['arm']}/{step['name']}") == 0:
                raw['status'] = 'no_observation'
                raise ValueError('Search step made no RF forward; no candidate can be used')
            for v in found:
                candidate = dict(vector=raw_numbers(v))
                try:
                    candidate['vector_sha256'] = vector_sha(v)
                    validate_values(definition, meter.model.schema, v, policy)
                except ValueError as exc:
                    candidate.update(status='invalid', reason=str(exc))
                    if legacy_campaign:
                        result['selection']['excluded'].append(candidate)
                else:
                    candidate['status'] = 'unrun'
                    if legacy_campaign:
                        candidates.append(plain(v))
                raw['candidates'].append(candidate)
            meter._checkpoint()
            solver_raw = plain(out)
            numerical_reason = solver_raw.get('stop_reason', solver_raw.get('reason', ''))
            if numerical_reason.startswith('invalid_'):
                raw['status'] = 'numerical_failure'
                raise ValueError(f'Solver numerical STOP: {numerical_reason}; no implicit retry')
            if next_x is None:
                raw['status'] = 'no_candidate'
                raise ValueError('No solver output; no implicit retry or replacement')
            try:
                validate_values(definition, meter.model.schema, next_x, policy)
            except ValueError:
                raw['status'] = 'invalid_output'
                raise
            if not legacy_campaign and solver_kind == 'scipy':
                digest = vector_sha(next_x)
                score = out.objective
                if (not isinstance(out.stop_reason, str) or not out.stop_reason or
                        out.stop_reason.startswith('invalid_') or type(out.evaluations) is not int or
                        out.evaluations < 1 or type(out.converged) is not bool or
                        score is None or not np.isfinite(score) or digest not in observed_objectives or
                        score != observed_objectives[digest]):
                    raw['status'] = 'unverified_output'
                    raise ValueError('Solver output/objective was not observed on its Search grid')
                raw['output_objective'] = float(score)
                raw['optimizer_result'] = raw_numbers(dict(x=out.x, objective=out.objective,
                    converged=out.converged, stop_reason=out.stop_reason, evaluations=out.evaluations))
                success = out.converged
                raw['status'] = 'converged' if success else 'not_converged'
            all_success &= success
            raw.update(output_vector=plain(next_x), output_vector_sha256=vector_sha(next_x),
                       boundary_indices=np.flatnonzero(np.any(np.asarray(next_x)[:, None] == np.asarray(d['bounds']), axis=1)).tolist())
            x = plain(next_x)  # fixed rule: generic solver x / Hybrid best_x, no inter-step RF selection
            meter.finish()
        if not legacy_campaign:
            terminal = result['terminal']
            terminal['status'] = 'unknown'
            meter.activate('terminal:0', 'terminal')
            observation = meter.evaluate(x)
            terminal['candidates'].append(dict(vector_sha256=observation['vector_sha256'], batch_index=observation['batch_index']))
            meter.finish()
            terminal['status'] = 'completed'
            result.update(status='converged' if all_success else 'not_converged', exit_reason='fixed_steps_completed')
            meter._checkpoint()
            if d.get('storage_mode') == 'window100':
                return json.loads(meter.path.read_bytes())
            return meter.snapshot()
        selection = result['selection']
        selection['status'] = 'unknown'
        unique = {vector_sha(v): v for v in candidates}
        assessed = []
        for i, (digest, v) in enumerate(sorted(unique.items())):
            row = dict(vector=plain(v), vector_sha256=digest)
            if i >= cfg['selection']['max_candidates']:
                selection['excluded'].append(dict(row, status='unrun', reason='max_candidates'))
                continue
            try:
                validate_values(definition, meter.model.schema, v, policy)
            except ValueError as exc:
                selection['excluded'].append(dict(row, status='invalid', reason=str(exc)))
                continue
            meter.activate(f'selection:{i}', 'selection')
            try:
                evaluated = meter.evaluate(v)
            except BaseException as exc:
                selection['excluded'].append(dict(row, status='not_evaluated', reason=f'{type(exc).__name__}: {exc}'))
                raise
            assessed.append(evaluated)
            meter.finish()
            ranked = rank_candidates(assessed)
            selection['ranked'] = [{k: plain(v) for k, v in r.items() if k != 'model'} for r in ranked['ranked']]
            meter._checkpoint()
        selection['status'] = 'completed' if candidates else 'not_run'
        terminal = result['terminal']
        for i, candidate in enumerate(selection['ranked'][:cfg['selection']['top_k']]):
            terminal['status'] = 'unknown'
            meter.activate(f'terminal:{i}', 'terminal')
            observation = meter.evaluate(candidate['vector'])
            terminal['candidates'].append(dict(vector_sha256=observation['vector_sha256'], batch_index=observation['batch_index']))
            meter.finish()
        if terminal['candidates']:
            terminal['status'] = 'completed'
        result.update(status='converged' if all_success else 'not_converged', exit_reason='fixed_steps_completed')
    except BaseException as exc:
        status = ('interrupted' if isinstance(exc, KeyboardInterrupt) else
                  'budget_exhausted' if 'full batch exceeds' in str(exc) else 'failed')
        result.update(status=status, exit_reason=f'{type(exc).__name__}: {exc}')
        for scan in result['anytime']:
            if scan['status'] == 'not_run' and meter.search_requested >= scan['milestone']:
                scan['reason'] = 'no_completed_observation_at_crossing'
        for raw in result['steps']:
            if raw['status'] == 'unknown':
                raw['status'] = status
        for phase in (('selection', 'terminal') if legacy_campaign else ('terminal',)):
            if result[phase]['status'] == 'unknown':
                result[phase]['status'] = status
        # Storage failures must not overwrite the last durable unknown with
        # in-memory completed values or cause a second save/forward attempt.
        if meter.status == 'storage_failed':
            raise
    meter._checkpoint()
    if d.get('storage_mode') == 'window100':
        return json.loads(meter.path.read_bytes())
    return meter.snapshot()


@dataclass(frozen=True)
class JobSpec:
    job_id: str
    trial_id: str
    plan_sha256: str
    source_sha256: str
    frozen_json: str  # reconstruction data only, never callbacks/circuit objects

    @property
    def data(self):
        return json.loads(self.frozen_json)

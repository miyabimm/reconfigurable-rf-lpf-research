"""Same-process fixed-step executor; production EXP execution is not_ready."""
from dataclasses import dataclass
import json
import time

from lpf.optimizers.slsqp import slsqp_minimize
from lpf.optimizers.hybrid import hybrid_minimize
from lpf.optimizers.slp import slp_minimize
from .evaluation import Evaluation, BudgetExceeded
from .problem import Problem
from .starts import validate
from .storage import atomic, canonical, plain, sha, vector_sha
from .validation import select, pending


def freeze_development_job(plan, definition, policy, arm, seed, vector, *, root=None, spot_checks=None):
    """Freeze one schema-2 development Job; this is NOT a G1 JobSpec."""
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
    if config['definition'] is None or sha(asdict(definition)) != config['definition']['definition_sha256']:
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
    allowed = {f"{arm}/{s['name']}" for s in chosen['steps']} | {'selection', 'terminal', 'anytime'}
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
    return JobSpec(f'development-{arm}-{seed}', 'development_only', plan.sha256,
                   sha(source), canonical(frozen))


def _development_options(step):
    # Freeze generic numerical defaults as well as explicitly configured budgets.
    defaults = {'slsqp': dict(tolerance=1e-9, constraint_tolerance=1e-7),
                'slp': dict(initial_step=.25, min_step=1e-8, fd_step=1e-6,
                            tolerance=1e-7, constraint_tolerance=1e-7), 'hybrid': {}}
    return {**defaults[step['solver']], **step['options']}


def execute_development_job(spec, checkpoint, *, root=None, solver_kind='scipy'):
    """Single-process fixed steps, shared durable RF ledger, development tmp only.

    solver_kind labels patched solver tests as fixture; it does not replace RF.
    No scheduler/CLI/production gate is enabled. Existing raw always STOPs.
    """
    from pathlib import Path
    import numpy as np
    from .plan import ROOT, Plan
    from .problem import Problem
    from .component_constraints import validate_values
    from .evaluation import raw_numbers
    from .validation import rank_candidates
    from ._job_evaluation import FixedJobEvaluation
    from lpf.constraint_versions import load_constraint
    from lpf.topology_management import CircuitDefinition
    from lpf.topology_management import InductorTree, CapacitorPlacement
    root = Path(root or ROOT).resolve()
    d = spec.data
    if d.get('kind') != 'development_only' or spec.trial_id != 'development_only':
        raise ValueError('not_ready: production G0/G1 not connected')
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
    expected = freeze_development_job(plan, definition, policy, d['arm'], d['seed'], d['start']['vector'],
                                      root=root, spot_checks=d['spot_checks'])
    if expected != spec:
        raise ValueError('Development Job/input/source/options SHA mismatch')
    meter = FixedJobEvaluation(plan, definition, policy, d['arm'], checkpoint, spec, root=root)
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
            opts = d['solver_options'][i]
            if step['solver'] == 'hybrid':
                def residuals(v):
                    a = meter.evaluate(v)['assessment']
                    if not np.isfinite(a['worst_il_db']) or a['worst_il_db'] < 0:
                        raise ValueError('Hybrid requires finite nonnegative IL; no floor')
                    return np.r_[np.sqrt(a['worst_il_db']), np.maximum(0., -np.asarray(a['mandatory_g']))]
                out = hybrid_minimize(residuals, x, d['bounds'], seed=d['seed'],
                                      aggregation=step['aggregation'], **opts)
                found = [r.end_x for r in out.runs if r.end_x is not None]
                if out.best_x is not None:
                    found.append(out.best_x)
                next_x = out.best_x
                success = bool(out.runs) and all(r.success for r in out.runs)
            else:
                solver = slsqp_minimize if step['solver'] == 'slsqp' else slp_minimize
                callback = p.residuals if step['solver'] == 'slsqp' else p.errors
                out = solver(callback, x, d['bounds'], constraints=p.constraints,
                             aggregation=step['aggregation'], **opts)
                next_x, success = out.x, out.success
                found = [out.x]
            raw.update(solver_result=raw_numbers(out), status='converged' if success else 'not_converged')
            for v in found:
                candidate = dict(vector=raw_numbers(v))
                try:
                    candidate['vector_sha256'] = vector_sha(v)
                    validate_values(definition, meter.model.schema, v, policy)
                except ValueError as exc:
                    candidate.update(status='invalid', reason=str(exc))
                    result['selection']['excluded'].append(candidate)
                else:
                    candidate['status'] = 'unrun'
                    candidates.append(plain(v))
                raw['candidates'].append(candidate)
            meter._checkpoint()
            solver_raw = plain(out)
            numerical_reason = solver_raw.get('stop_reason', solver_raw.get('reason', ''))
            if numerical_reason.startswith('invalid_'):
                raw['status'] = 'numerical_failure'
                raise ValueError(f'Solver numerical STOP: {numerical_reason}; no implicit retry')
            all_success &= success
            if next_x is None:
                raw['status'] = 'no_candidate'
                raise ValueError('No solver output; no implicit retry or replacement')
            try:
                validate_values(definition, meter.model.schema, next_x, policy)
            except ValueError:
                raw['status'] = 'invalid_output'
                raise
            raw.update(output_vector=plain(next_x), output_vector_sha256=vector_sha(next_x),
                       boundary_indices=np.flatnonzero(np.any(np.asarray(next_x)[:, None] == np.asarray(d['bounds']), axis=1)).tolist())
            x = plain(next_x)  # fixed rule: generic solver x / Hybrid best_x, no inter-step RF selection
            meter.finish()
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
        for phase in ('selection', 'terminal'):
            if result[phase]['status'] == 'unknown':
                result[phase]['status'] = status
        # Storage failures must not overwrite the last durable unknown with
        # in-memory completed values or cause a second save/forward attempt.
        if meter.status == 'storage_failed':
            raise
    meter._checkpoint()
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


def execute_job(spec, directory):
    """Retired schema1 fixture runner; not used by schema2 development."""
    from ._legacy_schema1 import build
    from pathlib import Path
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=False)
    result = {'job_id': spec.job_id, 'trial_id': spec.trial_id, 'spec': plain(spec),
              'status': 'not_started', 'exit_reason': None, 'steps': [],
              'terminal17': {'status': 'not_run'}, 'validation': pending(), 'cost': None}
    path = directory / 'job.json'
    atomic(path, result)
    meter = None
    wall, cpu = time.monotonic(), time.process_time()
    try:
        d = spec.data
        if d['backend'] != 'fixture':
            raise ValueError('not_ready: production G0/G1 and G2-G5 not connected')
        frozen = d['plan']
        if sha(frozen) != spec.plan_sha256 or sha(d['source']) != spec.source_sha256:
            raise ValueError('Job provenance SHA mismatch')
        if vector_sha(d['start']['vector']) != d['start']['vector_sha256']:
            raise ValueError('Job complete x SHA mismatch')
        config = frozen['config']
        arm = config['arms'][d['arm_index']]
        circuit = build(frozen['definition'], config['rf'])
        from .plan import fingerprints
        if fingerprints(circuit) != frozen['rf_inputs']:
            raise ValueError('Frozen bands/S2P fingerprint mismatch')
        bounds = frozen['box']
        validate(circuit, d['start']['vector'], bounds)

        def checkpoint(cost):
            result['cost'] = cost
            atomic(path, result)
            for i, step_raw in enumerate(result['steps']):
                atomic(directory / f'step-{i}.json', step_raw)

        meter = Evaluation(circuit, bounds, arm['max_requested_samples'],
                           backend='fixture', sink=checkpoint, milestones=config['anytime_samples'])
        result['status'] = 'unknown'
        atomic(path, result)
        x = d['start']['vector']
        all_success = True
        for index, step in enumerate(arm['steps']):
            meter.begin_stage(step['max_requested_samples'])
            raw = {'name': step['name'], 'status': 'unknown', 'input_vector': x,
                   'input_vector_sha256': vector_sha(x), 'settings': step,
                   'selection_status': 'not_run', 'selection': []}
            result['steps'].append(raw)
            atomic(directory / f'step-{index}.json', raw)
            atomic(path, result)
            p = Problem(meter, step['points_per_interval'], step['name'], frozen['working_stop_db'])
            opts = step['options']
            if step['solver'] == 'hybrid':
                out = hybrid_minimize(p.residuals, x, bounds, seed=d['start']['seed'],
                                      aggregation=step['aggregation'], **opts)
                candidates = [r.end_x for r in out.runs if r.end_x is not None]
                if out.best_x is not None:
                    candidates.append(out.best_x)
                success = bool(out.runs) and all(r.success for r in out.runs)
            elif step['solver'] == 'slsqp':
                out = slsqp_minimize(p.residuals, x, bounds, constraints=p.constraints,
                                     aggregation=step['aggregation'], **opts)
                candidates, success = [out.x.tolist()], out.success
            else:
                out = slp_minimize(p.errors, x, bounds, constraints=p.constraints,
                                   aggregation=step['aggregation'], **opts)
                candidates, success = [out.x.tolist()], out.success
            raw.update(solver_result=plain(out), status='converged' if success else 'not_converged')
            all_success &= success
            atomic(directory / f'step-{index}.json', raw)
            # Selection forwards count against this step and the shared job/trial.
            if candidates:
                raw['selection_status'] = 'in_progress'
                atomic(directory / f'step-{index}.json', raw)
                def assessed(row):
                    raw['selection'].append(row)
                    raw['selection_status'] = 'partial'
                    atomic(directory / f'step-{index}.json', raw)
                    atomic(path, result)
                try:
                    ranked = select(meter, candidates, config['selection']['points_per_interval'],
                                    step['name'] + ':selection', on_assessed=assessed)
                except BaseException:
                    if not raw['selection']:
                        raw['selection_status'] = 'failed'
                    raise
                raw.update(selection=ranked, selection_status='completed')
                x = ranked[0]['vector']
                atomic(directory / f'step-{index}.json', raw)
            else:
                raw['selection'] = []
                raise ValueError('No solver candidate; selection not_run')
            atomic(path, result)
        result['status'] = 'converged' if all_success else 'not_converged'
        result['exit_reason'] = 'fixed_steps_completed'
    except BudgetExceeded as exc:
        result.update(status='budget_exhausted', exit_reason=str(exc))
    except KeyboardInterrupt:
        result.update(status='interrupted', exit_reason='KeyboardInterrupt')
    except Exception as exc:
        result.update(status='failed', exit_reason=f'{type(exc).__name__}: {exc}')
    # Do not issue new forwards after failure/interrupt. A budget stop still owns
    # its reserved terminal scan, evaluated only at an actually observed point.
    try:
        if meter is not None and meter.last is not None and result['status'] in (
                'converged', 'not_converged', 'budget_exhausted'):
            meter.forward(meter.last['vector'], 17, 'terminal17', terminal=True)
            result['terminal17'] = {'status': 'completed', 'observation': meter.last}
        elif meter is None or meter.last is None:
            result['terminal17']['reason'] = 'no_legal_observation'
        else:
            result['terminal17']['reason'] = 'failure_or_interrupt_no_further_forward'
    except KeyboardInterrupt:
        result.update(status='interrupted', exit_reason='terminal17 interrupted')
    except Exception as exc:
        result.update(status='failed', exit_reason=f'terminal17: {type(exc).__name__}: {exc}')
    finally:
        if meter is not None:
            result['cost'] = meter.snapshot()
        result['wall_seconds'] = time.monotonic() - wall
        result['cpu_seconds'] = time.process_time() - cpu
        for i, step_raw in enumerate(result['steps']):
            atomic(directory / f'step-{i}.json', step_raw)
        atomic(path, result)
    return result

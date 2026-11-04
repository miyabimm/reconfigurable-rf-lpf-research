"""Same-process fixed-step executor; production EXP execution is not_ready."""
from dataclasses import dataclass
import json
import time

from lpf.optimizers.slsqp import slsqp_minimize
from lpf.optimizers.hybrid import hybrid_minimize
from lpf.optimizers.slp import slp_minimize
from .evaluation import Evaluation, BudgetExceeded
from .problem import Problem, build
from .starts import validate
from .storage import atomic, canonical, plain, sha, vector_sha
from .validation import select, pending


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
    """Execute synthetic fixture or tightly capped development RF; never production."""
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
        if d['backend'] not in ('fixture', 'development_rf'):
            raise ValueError('not_ready: production G0/G1 and G2-G5 not connected')
        frozen = d['plan']
        if d['backend'] == 'development_rf':
            from .runner import check_development_plan
            from .starts import DEVELOPMENT_VECTOR
            check_development_plan(frozen)
            if d['start']['seed'] != 23 or d['start']['vector'] != list(DEVELOPMENT_VECTOR):
                raise ValueError('development_rf requires the fixed development vector')
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
        bounds, opened = frozen['box'], frozen['open_lower']
        validate(circuit, d['start']['vector'], bounds, opened)
        if d['backend'] == 'development_rf':
            from .starts import physical_box
            if (canonical([bounds, opened]) != canonical(physical_box(circuit)) or
                    frozen['working_stop_db'] != circuit.resolved_policy['evaluation']['full_phase2']['minimum_h2_h3_db']):
                raise ValueError('development_rf physical box or target mismatch')

        def checkpoint(cost):
            result['cost'] = cost
            atomic(path, result)
            for i, step_raw in enumerate(result['steps']):
                atomic(directory / f'step-{i}.json', step_raw)

        meter = Evaluation(circuit, bounds, opened, arm['max_requested_samples'],
                           backend='rf' if d['backend'] == 'development_rf' else 'fixture',
                           sink=checkpoint, milestones=config['anytime_samples'])
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

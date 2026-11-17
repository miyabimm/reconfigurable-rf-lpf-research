"""Sequential parent ledger, immutable job data and fail-closed gate boundary."""
from pathlib import Path
import hashlib

from .controller import actions
from .storage import atomic, canonical, sha, plain, vector_sha
from .worker import JobSpec, freeze_development_job, execute_development_job


def _selectionless_readback(result, spec, batches):
    """Bind the sole terminal to the final solver output, never a ranked observation."""
    d = spec.data
    if 'selection' in result or 'selection' in d['plan']['config']:
        raise ValueError('Selection is not valid in a new development Job')
    complete = result['status'] in ('converged', 'not_converged')
    steps = result['steps']
    chosen = next(a for a in d['plan']['config']['arms'] if a['name'] == d['arm'])
    if len(steps) != len(chosen['steps']):
        raise ValueError('Step count mismatch')
    if complete:
        previous = d['start']['vector_sha256']
        for step, configured in zip(steps, chosen['steps']):
            solver = step['solver_result']
            output = solver['x']
            stage = f"{d['arm']}/{configured['name']}"
            if (step['name'] != configured['name'] or step['settings'] != configured or
                    step['status'] not in ('converged', 'not_converged') or
                    vector_sha(step['input_vector']) != previous or
                    step['input_vector_sha256'] != previous or
                    output is None or vector_sha(output) != step['output_vector_sha256'] or
                    vector_sha(step['output_vector']) != step['output_vector_sha256'] or
                    not any(b['stage'] == stage and b['status'] == 'completed' for b in batches.values()) and
                    not result.get('progress_by_allocation', {}).get(stage, {}).get('completed')):
                raise ValueError('Completed step/solver/vector evidence mismatch')
            if result.get('solver_execution_kind') == 'scipy':
                import math
                common = solver
                if (not isinstance(common, dict) or set(common) != {'x', 'objective', 'converged', 'stop_reason', 'evaluations'} or
                        vector_sha(common['x']) != step['output_vector_sha256'] or
                        type(common['objective']) not in (float, int) or not math.isfinite(common['objective']) or
                        common['objective'] != step['output_objective'] or
                        type(common['converged']) is not bool or common['converged'] != (step['status'] == 'converged') or
                        not isinstance(common['stop_reason'], str) or not common['stop_reason'] or
                        common['stop_reason'].startswith('invalid_') or
                        (common['stop_reason'] in ('evaluation_limit', 'evaluation_budget_exhausted') and common['converged']) or
                        type(common['evaluations']) is not int or common['evaluations'] < 1):
                    raise ValueError('Optimizer result evidence mismatch')
            previous = step['output_vector_sha256']
    terminal = result['terminal']
    candidates = terminal['candidates']
    if len(candidates) > 1 or (candidates and terminal['status'] != 'completed') or (complete and len(candidates) != 1):
        raise ValueError('Terminal status/count mismatch')
    for candidate in candidates:
        batch = batches.get(candidate['batch_index'])
        if (not steps or 'output_vector_sha256' not in steps[-1] or batch is None or
                batch['stage'] != 'terminal' or batch['status'] != 'completed' or
                candidate['vector_sha256'] != steps[-1]['output_vector_sha256'] or
                candidate['vector_sha256'] != batch['vector_sha256']):
            raise ValueError('Terminal/final solver/batch mismatch')


def _development_readback(path, returned, spec):
    """Bind actual raw bytes to the Worker snapshot and frozen JobSpec.

    Byte SHA is not canonical content SHA. The existing atomic writer has one
    encoding; checking that encoding also detects post-return whitespace edits.
    This is accidental-corruption detection, not authentication of a Worker.
    """
    import json
    import numpy as np
    from .preflight import nonnegative
    raw = Path(path).read_bytes()
    if raw != (canonical(returned) + '\n').encode():
        raise ValueError('Worker/raw byte digest mismatch')
    return _validate_development_result(raw, json.loads(raw), spec, compact=False)


def _window_development_readback(path, returned, spec):
    """Strict readback for the separate opt-in evidence format only."""
    import json
    from .preflight import nonnegative
    raw = Path(path).read_bytes()
    if raw != (canonical(returned) + '\n').encode():
        raise ValueError('Window Worker/raw byte mismatch')
    envelope = json.loads(raw)
    d = spec.data
    if (d.get('kind') != 'development_only' or d.get('storage_mode') != 'window100' or
            envelope.get('kind') != 'development_forward_window_v1' or
            envelope.get('identity') != plain(spec)):
        raise ValueError('Window Job identity mismatch')
    number = envelope['checkpoint_number']
    if type(number) is not int or number < 1:
        raise ValueError('Invalid checkpoint number')
    io = envelope['io_before']
    for key in ('write_calls', 'written_bytes', 'read_calls', 'read_bytes'):
        nonnegative(io[key])
    if (io['write_calls'] != number-1 or io['read_calls'] != io['write_calls'] or
            io['read_bytes'] != io['written_bytes']):
        raise ValueError('Window I/O count mismatch')
    result = envelope['payload']
    if d.get('debug_forward_history') is False:
        from ._window_readback import readback_summaries
        return readback_summaries(raw, envelope, spec)
    if d.get('debug_forward_history') is not True:
        raise ValueError('Missing frozen window history mode')
    confirmed = envelope['confirmed']
    for value in confirmed.values(): nonnegative(value)
    if (set(confirmed) != {'forwards', 'requested', 'completed'} or
            envelope['window'] is not None or envelope['uncertain_upper'] != confirmed or
            result['requested'] != confirmed['requested'] or result['completed'] != confirmed['completed'] or
            sum(b['requested'] > 0 for b in result['batches']) != confirmed['forwards']):
        raise ValueError('Window remains uncertain or confirmed totals mismatch')
    def metric(value):
        import math
        if isinstance(value, dict) and set(value) == {'nonfinite'}:
            if value['nonfinite'] == '+inf': return float('inf')
            if value['nonfinite'] == '-inf': return float('-inf')
        if type(value) not in (int, float) or math.isnan(value):
            raise ValueError('Invalid best-observed metric')
        return value
    import math
    chosen = next(a for a in d['plan']['config']['arms'] if a['name'] == d['arm'])
    hybrid_stages = {f"{d['arm']}/{step['name']}": step['aggregation']
                     for step in chosen['steps'] if step['solver'] == 'hybrid'}
    best, hybrid_best = {}, {}
    for i, row in enumerate(result['batches']):
        if row['status'] != 'completed' or not row['stage'].startswith(d['arm']+'/'):
            continue
        a = row['assessment']
        physical = row['physical_checks']
        minimum = physical['min_L_eigenvalue_H']
        n_inductors = len(d['definition']['inductor_tree']['edges'])
        if (physical['component_policy_pass'] is not True or physical['checked_settings'] != 6 or
                (n_inductors and (type(minimum) not in (int, float) or minimum <= 0)) or
                (not n_inductors and minimum is not None) or type(a['nominal_pass']) is not bool):
            raise ValueError('Compact batch physical or nominal evidence mismatch')
        if type(a['strict_feasible']) is not bool:
            raise ValueError('Invalid feasibility flag')
        stage = row['stage']
        if stage in hybrid_stages:
            score = a['hybrid_objective']
            fields = {'aggregation', 'status', 'value', 'il_term', 'violation_squared_sum', 'max_violation_squared'}
            if set(score) != fields or score['aggregation'] != hybrid_stages[stage]:
                raise ValueError('Hybrid objective identity mismatch')
            if score['status'] == 'invalid':
                if any(score[k] is not None for k in fields - {'aggregation', 'status'}):
                    raise ValueError('Invalid Hybrid objective has a scalar')
            elif score['status'] == 'evaluated':
                values = (score['value'], score['il_term'], score['max_violation_squared'])
                if any(type(v) not in (int, float) or not math.isfinite(v) or v < 0 for v in values):
                    raise ValueError('Invalid Hybrid objective scalar')
                penalty = score['violation_squared_sum']
                if penalty is not None and (type(penalty) not in (int, float) or not math.isfinite(penalty) or penalty < 0):
                    raise ValueError('Invalid Hybrid squared violation sum')
                vmax = metric(a['max_violation_db'])
                il = metric(a['worst_il_db'])
                if (not math.isfinite(il) or il < 0 or not math.isfinite(vmax) or vmax < 0 or
                        not math.isclose(score['il_term'], il, rel_tol=1e-12, abs_tol=1e-12) or
                        not math.isclose(score['max_violation_squared'], vmax*vmax, rel_tol=1e-12, abs_tol=1e-12) or
                        (penalty is not None and penalty + 1e-12 < score['max_violation_squared'])):
                    raise ValueError('Hybrid objective component mismatch')
                if score['aggregation'] == 'sum':
                    expected_value = None if penalty is None else score['il_term'] + penalty
                else:
                    expected_value = max(score['il_term'], score['max_violation_squared'])
                if expected_value is None or not math.isclose(score['value'], expected_value, rel_tol=1e-12, abs_tol=1e-12):
                    raise ValueError('Hybrid objective value mismatch')
                if stage not in hybrid_best or score['value'] < hybrid_best[stage][0]:
                    hybrid_best[stage] = (score['value'], i)
            else:
                raise ValueError('Invalid Hybrid objective status')
        elif 'hybrid_objective' in a:
            raise ValueError('Unexpected Hybrid objective on non-Hybrid stage')
        key = ((0, metric(a['worst_il_db']), row['vector_sha256']) if a['strict_feasible'] else
               (1, metric(a['max_violation_db']), metric(a['sum_violation_db']), metric(a['worst_il_db']), row['vector_sha256']))
        stage = row['stage']
        if stage not in best or key < best[stage][0]: best[stage] = (key, i)
    expected_best = {stage: dict(batch_index=i, vector=result['batches'][i]['vector'],
        vector_sha256=result['batches'][i]['vector_sha256'], assessment=result['batches'][i]['assessment'])
        for stage, (_, i) in best.items()}
    expected_hybrid_best = {stage: dict(batch_index=i, vector=result['batches'][i]['vector'],
        vector_sha256=result['batches'][i]['vector_sha256'], assessment=result['batches'][i]['assessment'])
        for stage, (_, i) in hybrid_best.items()}
    if (result.get('best_observed_by_stage') != expected_best or
            result.get('best_hybrid_observed_by_stage') != expected_hybrid_best or
            result.get('unsaved_window_results_may_be_lost') is not True):
        raise ValueError('Window best-observed evidence mismatch')
    if 'selection' not in d['plan']['config']:
        _selectionless_readback(result, spec, dict(enumerate(result['batches'])))
        imported = _validate_development_result(raw, result, spec, compact=True, content=envelope)
        imported['worker_io'] = dict(atomic_writes=number, payload_bytes=io['written_bytes']+len(raw),
            atomic_readbacks=io['read_calls']+1, readback_bytes=io['read_bytes']+len(raw), scope='worker_raw_only')
        return imported
    from .evaluation import raw_numbers
    ranked = result['selection']['ranked']
    if ranked and result['selection']['status'] != 'completed':
        raise ValueError('Ranked selection without completed selection')
    solver_candidates = {c['vector_sha256'] for step in result['steps'] for c in step['candidates']
                         if c.get('status') == 'unrun'}
    rank_keys = []
    for row in ranked:
        i = row['batch_index']
        if type(i) is not int or not 0 <= i < len(result['batches']):
            raise ValueError('Invalid selection batch index')
        batch = result['batches'][i]
        a = batch['assessment']
        digest = batch['vector_sha256']
        key = ((0, metric(a['worst_il_db']), digest) if a['strict_feasible'] else
               (1, metric(a['max_violation_db']), metric(a['sum_violation_db']), metric(a['worst_il_db']), digest))
        if (batch['stage'] != 'selection' or batch['status'] != 'completed' or
                digest not in solver_candidates or row['vector_sha256'] != digest or
                row['vector'] != batch['vector'] or row['assessment'] != a or
                row['plan_sha256'] != spec.plan_sha256 or row['grid_sha256'] != batch['grid_sha256'] or
                row['rank_key'] != raw_numbers(key) or row['status'] != ('pass' if a['strict_feasible'] else 'fail')):
            raise ValueError('Selection candidate/batch identity or rank mismatch')
        rank_keys.append(key)
    if rank_keys != sorted(rank_keys) or len({r['vector_sha256'] for r in ranked}) != len(ranked):
        raise ValueError('Selection order or uniqueness mismatch')
    if result['status'] in ('converged', 'not_converged'):
        assessed = {i for i, b in enumerate(result['batches'])
                    if b['stage'] == 'selection' and b['status'] == 'completed'}
        if {r['batch_index'] for r in ranked} != assessed:
            raise ValueError('Completed Job omitted an assessed selection candidate')
    terminal = result['terminal']
    candidates = terminal['candidates']
    if candidates and terminal['status'] != 'completed':
        raise ValueError('Terminal candidates without completion')
    terminal_cap = min(len(ranked), d['plan']['config']['selection']['top_k'])
    if len(candidates) > terminal_cap:
        raise ValueError('Too many terminal candidates')
    if result['status'] in ('converged', 'not_converged'):
        if len(candidates) != terminal_cap:
            raise ValueError('Completed Job missing terminal candidates')
        for step in result['steps']:
            if (step['status'] not in ('converged', 'not_converged') or
                    vector_sha(step['input_vector']) != step['input_vector_sha256'] or
                    vector_sha(step['output_vector']) != step['output_vector_sha256']):
                raise ValueError('Completed step/vector evidence mismatch')
    for candidate, selected in zip(candidates, ranked):
        i = candidate['batch_index']
        if type(i) is not int or not 0 <= i < len(result['batches']):
            raise ValueError('Invalid terminal batch index')
        batch = result['batches'][i]
        if (batch['stage'] != 'terminal' or batch['status'] != 'completed' or
                candidate['vector_sha256'] != selected['vector_sha256'] or
                candidate['vector_sha256'] != batch['vector_sha256']):
            raise ValueError('Terminal/selection/batch mismatch')
    imported = _validate_development_result(raw, result, spec, compact=True, content=envelope)
    imported['worker_io'] = dict(atomic_writes=number, payload_bytes=io['written_bytes']+len(raw),
        atomic_readbacks=io['read_calls']+1, readback_bytes=io['read_bytes']+len(raw), scope='worker_raw_only')
    return imported


def _validate_development_result(raw, result, spec, *, compact, content=None, summary_progress=False):
    import numpy as np
    from .preflight import nonnegative
    d = spec.data
    plan = d['plan']
    cap = plan['costs']['jobs'][d['arm']]['max_requested_samples']
    formal = d.get('kind') == 'campaign_formal_job_v1'
    expected_kind = 'development_window_raw_v1' if compact else ('campaign_formal_raw_v1' if formal else 'stage4c1_development_only')
    expected = dict(spec=plain(spec), kind=expected_kind,
        plan_sha256=spec.plan_sha256, policy_id=plan['config']['rf']['constraint_id'],
        policy_fingerprint=plan['requirements']['policy_fingerprint'],
        requirements_fingerprint=plan['requirements']['fingerprint'],
        definition_sha256=sha(d['definition']), rf_inputs=plan['rf_inputs'], grids=plan['grids'],
        gates=dict(G0_G1='passed', G2='running', G3_G5='not_run') if formal else plan['gates'],
        rf_backend='rf_core')
    for key, value in expected.items():
        if result[key] != value:
            raise ValueError(f'Raw JobSpec/Plan identity mismatch: {key}')
    if (result['status'] not in ('converged', 'not_converged', 'budget_exhausted',
                                'failed', 'interrupted', 'unknown') or
            not isinstance(result['exit_reason'], str) or not result['exit_reason']):
        raise ValueError('Invalid raw status/exit reason')

    def counts(row, maximum):
        requested, completed = row['requested'], row['completed']
        nonnegative(requested); nonnegative(completed)
        if not completed <= requested <= maximum:
            raise ValueError('Raw requested/completed/cap mismatch')
        return requested, completed

    requested, completed = counts(result, cap)
    total_requested = total_completed = search = audit_requested = audit_completed = 0
    allocations = {}
    uncertain = False
    job = plan['costs']['jobs'][d['arm']]
    caps = {f"{d['arm']}/{name}": s['upper_reservation'] for name, s in job['stages'].items()}
    if 'selection' in plan['config']:
        caps.update({f'selection:{i}': job['selection_one_forward']
                     for i in range(plan['config']['selection']['max_candidates'])})
    caps.update({f'terminal:{i}': job['terminal_one_forward']
                 for i in range(plan['config']['selection']['top_k'] if 'selection' in plan['config'] else 1)})
    caps.update({f'anytime:{i}': job['anytime_one_forward']
                 for i in range(len(plan['config']['anytime_samples']))})
    for batch in result['batches']:
        stage, allocation = batch['stage'], batch['allocation']
        if stage not in plan['grids'] or allocation not in caps:
            raise ValueError('Raw batch stage/allocation mismatch')
        expected_stage = allocation if '/' in allocation else allocation.split(':')[0]
        if stage != expected_stage or batch['grid_sha256'] != plan['grids'][stage]['sha256']:
            raise ValueError('Raw batch grid mismatch')
        n = plan['grids'][stage]['requested_samples_per_forward']
        r, c = counts(batch, n)
        if r not in (0, n) or c not in (0, r):
            raise ValueError('Raw batch must charge a full grid')
        if batch['status'] == 'completed':
            if not r or c != r or vector_sha(batch['vector']) != batch['vector_sha256']:
                raise ValueError('Completed batch/vector mismatch')
            if not compact or not stage.startswith(d['arm']+'/') or d['spot_checks'].get(stage):
                response = batch['response']
                for key in ('s_real', 's_imag', 'il_db', 'apl_db', 'in_rl_db', 'out_rl_db'):
                    shape = (n, 2, 2) if key in ('s_real', 's_imag') else (n,)
                    if np.asarray(response[key]).shape != shape:
                        raise ValueError(f'Completed batch response shape mismatch: {key}')
            elif 'response' in batch:
                raise ValueError('Unexpected full response in compact search batch')
            assessment = batch['assessment']
            identity = dict(status='evaluated', policy_id=expected['policy_id'],
                policy_fingerprint=expected['policy_fingerprint'], mode=plan['config']['objective'],
                requirements_fingerprint=expected['requirements_fingerprint'],
                grid_fingerprint=batch['grid_sha256'])
            for key, value in identity.items():
                if assessment[key] != value:
                    raise ValueError(f'Completed batch assessment mismatch: {key}')
        elif batch['status'] != 'rejected' or r or c:
            uncertain = True
        total_requested += r; total_completed += c
        if stage.startswith(d['arm'] + '/'):
            search += r
        allocations[allocation] = allocations.get(allocation, 0) + r
        if allocations[allocation] > caps[allocation]:
            raise ValueError('Raw allocation cap exceeded')
        audit = batch['independent']
        if audit['status'] == 'not_run' and c and d['spot_checks'].get(stage):
            uncertain = True
        if audit['status'] != 'not_run':
            ar, ac = counts(audit, len(d['spot_checks'].get(stage, [])))
            if audit['sample_indices'] != d['spot_checks'].get(stage):
                raise ValueError('Independent spot request mismatch')
            if audit['status'] != 'pass' or ar != ac:
                uncertain = True
            audit_requested += ar; audit_completed += ac
    if summary_progress:
        progress = result['progress_by_allocation']
        if not isinstance(progress, dict) or not set(progress) <= set(caps):
            raise ValueError('Unknown progress allocation')
        observed = allocations
        allocations = {}
        total_requested = total_completed = search = 0
        for key, value in progress.items():
            if set(value) != {'forwards', 'requested', 'completed'}:
                raise ValueError('Invalid progress fields')
            for n in value.values(): nonnegative(n)
            stage = key if '/' in key else key.split(':')[0]
            n = plan['grids'][stage]['requested_samples_per_forward']
            if (value['requested'] != value['forwards'] * n or
                    value['completed'] > value['requested'] or value['completed'] % n or
                    value['requested'] > caps[key] or observed.get(key, 0) > value['requested']):
                raise ValueError('Progress allocation/cap mismatch')
            if value['requested'] != value['completed']:
                uncertain = True
            if (not key.startswith(d['arm']+'/') or d['spot_checks'].get(stage)) and observed.get(key, 0) != value['requested']:
                raise ValueError('Missing candidate or spot evidence')
            allocations[key] = value['requested']
            total_requested += value['requested']; total_completed += value['completed']
            if key.startswith(d['arm']+'/'): search += value['requested']
        if set(observed) - set(progress):
            raise ValueError('Evidence without progress')
    if (requested, completed, result['search_requested']) != (total_requested, total_completed, search):
        raise ValueError('Raw batch sums/job totals mismatch')
    if result['remaining'] != dict(job=cap-requested,
            trial=plan['costs']['max_trial_requested_samples']-requested):
        raise ValueError('Raw remaining budget mismatch')
    if (result['reservations']['other_jobs'] != plan['costs']['trial_job_cap_reservation']-cap or
            result['reservations']['dense'] != plan['costs']['dense']):
        raise ValueError('Raw reservations mismatch')
    inactive = 0
    for key, row in result['allocations'].items():
        if key not in caps:
            raise ValueError('Unknown raw allocation')
        r = allocations.get(key, 0)
        if row != dict(cap=caps[key], requested=r, reserved=caps[key]-r):
            raise ValueError('Raw allocation reservation mismatch')
        if key != result['active']:
            inactive += caps[key]-r
    if inactive != result['reservations']['inactive']:
        raise ValueError('Raw inactive reservation mismatch')
    campaign = 'campaign_context' in d
    if not campaign and not compact:
        _selectionless_readback(result, spec, dict(enumerate(result['batches'])))
    safe_statuses = ('converged', 'not_converged', 'budget_exhausted') if campaign else ('converged', 'not_converged')
    safe = (result['status'] in safe_statuses and
            result['evaluation_status'] in ('ready', 'stopped') and not uncertain and requested == completed)
    evidence = dict(terminal=result['terminal'], anytime=result['anytime'], dense=result['dense'],
        independent=[b['independent'] for b in result['batches']],
        observations=[dict(stage=b['stage'], grid_sha256=b['grid_sha256'],
            vector_sha256=b.get('vector_sha256'), status=b['status'],
            assessment={key: b['assessment'][key] for key in
                ('status', 'policy_id', 'policy_fingerprint', 'mode', 'requirements_fingerprint',
                 'grid_fingerprint', 'strict_feasible', 'worst_il_db', 'max_violation_db', 'sum_violation_db')}
                if 'assessment' in b else None)
            for b in result['batches']])
    return dict(raw_byte_sha256=hashlib.sha256(raw).hexdigest(), raw_content_sha256=sha(content if content is not None else result),
        worker_status=result['status'], exit_reason=result['exit_reason'],
        requested=requested, completed=completed,
        independent_requested=audit_requested, independent_completed=audit_completed,
        solver_evaluations=[s.get('solver_result', {}).get('evaluations') for s in result['steps']],
        evidence=evidence, safe_to_release=safe)


def _development_totals(state):
    """Parent-owned accounting only. No invented Campaign budget."""
    for trial_id, trial in state['trials'].items():
        jobs = [j for j in state['jobs'] if j['trial_id'] == trial_id]
        for key in ('requested', 'completed', 'reserved', 'released',
                    'independent_requested', 'independent_completed'):
            trial[key] = sum(j[key] for j in jobs)
        if trial['requested'] + trial['reserved'] > trial['cap']:
            raise ValueError('Trial requested/reserved cap exceeded')
        trial['remaining_unreserved'] = trial['cap']-trial['requested']-trial['reserved']
        trial['unknown_cost_upper_bound'] = sum(j['cap'] for j in jobs if j['status'] == 'unknown')
        trial['status'] = ('unknown' if any(j['status'] == 'unknown' for j in jobs) else
                           'completed' if all(j['status'] == 'completed' for j in jobs) else
                           'running' if any(j['status'] == 'completed' for j in jobs) else 'not_started')
    state['campaign'] = {key: sum(t[key] for t in state['trials'].values()) for key in
        ('requested', 'completed', 'reserved', 'released', 'independent_requested',
         'independent_completed', 'unknown_cost_upper_bound')}
    state['campaign']['status'] = state['status']


def _validate_development_output(output, root, storage_mode):
    import tempfile
    import subprocess
    if storage_mode == 'legacy':
        if (not output.is_relative_to(Path(tempfile.gettempdir()).resolve()) or output.is_relative_to(root)):
            raise ValueError('Development output must be system temp outside repository')
    elif storage_mode == 'window100':
        transient = {Path(tempfile.gettempdir()).resolve(), Path('/tmp').resolve(), Path('/dev/shm').resolve()}
        if output.is_relative_to(root) or any(output.is_relative_to(p) for p in transient):
            raise ValueError('Window output must be persistent and outside the repository/system temp')
        parent = output.parent
        if not parent.is_dir():
            raise ValueError('Window output parent must already exist')
        probe = subprocess.run(['git', '-C', str(parent), 'rev-parse', '--show-toplevel'],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if probe.returncode == 0:
            raise ValueError('Window output must be outside Git-managed directories')
    else:
        raise ValueError('Unknown development storage mode')


def run_development(plan, definition, policy, starts, output, *, root=None,
                    spot_checks=None, solver_kind='scipy', storage_mode='legacy', debug_forward_history=False,
                    timing_jobs=None):
    """Schema-2 same-process fixed seed×arm execution, system tmp only.

    starts maps *every* frozen integer seed to {vector, vector_sha256}; no start
    generation, EXP, G1 approval, retry/resume, scheduling or RF verdict here.
    On parent storage failure propagate immediately: never retry a save with
    in-memory success after the last durable unknown marker.
    """
    import copy
    from .plan import ROOT
    root = Path(root or ROOT).resolve()
    output = Path(output).resolve()
    _validate_development_output(output, root, storage_mode)
    if type(debug_forward_history) is not bool or (debug_forward_history and storage_mode != 'window100'):
        raise ValueError('Debug forward history requires window100')
    if output.exists():
        raise ValueError('Existing parent/raw path: no automatic resume or retry')
    config = plan.data['config']
    if (config['schema_version'] != 2 or not isinstance(starts, dict) or
            any(type(s) is not int for s in starts) or set(starts) != set(config['seeds'])):
        raise ValueError('Explicit complete starts for exactly the frozen seeds required')
    if solver_kind not in ('scipy', 'fixture'):
        raise ValueError('Unknown solver execution kind')
    specs, rows, identities = [], [], set()
    for action in actions(plan):
        start = starts[action.seed]
        if set(start) != {'vector', 'vector_sha256'} or vector_sha(start['vector']) != start['vector_sha256']:
            raise ValueError('Explicit start vector/SHA mismatch')
        arm = config['arms'][action.arm_index]
        options = {'storage_mode': storage_mode, 'debug_forward_history': debug_forward_history} if storage_mode != 'legacy' else {}
        spec = freeze_development_job(plan, definition, policy, arm['name'], action.seed,
            start['vector'], root=root, spot_checks=spot_checks, **options)
        if (spec.job_id in identities or spec.job_id != f"development-{arm['name']}-{action.seed}" or
                spec.trial_id != 'development_only' or spec.data['arm'] != arm['name'] or
                spec.data['seed'] != action.seed or spec.plan_sha256 != plan.sha256 or
                spec.data['start'] != plain(start) or sha(spec.data['source']) != spec.source_sha256):
            raise ValueError('Duplicate Job ID or Job/Trial/arm/start identity mismatch')
        if specs and spec.source_sha256 != specs[0].source_sha256:
            raise ValueError('Source changed while freezing Jobs')
        identities.add(spec.job_id)
        cap = arm['max_requested_samples']
        specs.append(spec)
        rows.append(dict(job_id=spec.job_id, trial_id=f'seed{action.seed}', seed=action.seed,
            arm=arm['name'], kind='development_only', spec=plain(spec), spec_sha256=sha(spec),
            plan_sha256=spec.plan_sha256, source_sha256=spec.source_sha256,
            depends_on=rows[-1]['job_id'] if rows else None, status='not_started',
            raw_path=f'{spec.job_id}.json', cap=cap, reserved=cap, released=0,
            requested=0, completed=0, independent_requested=0, independent_completed=0))
    if timing_jobs is not None:
        from lpf.timing import TimerCollector
        timing_jobs.extend(dict(job_id=spec.job_id, plan_sha256=spec.plan_sha256,
                                source_sha256=spec.source_sha256, status='not_started',
                                solvers=[{'step': step['name'], 'solver': step['solver']}
                                         for step in next(a for a in config['arms']
                                                          if a['name'] == spec.data['arm'])['steps']],
                                timer=TimerCollector()) for spec in specs)
    state = dict(kind='stage4c2_development_only', status='not_started', plan=plan.data,
        plan_sha256=plan.sha256, source_sha256=specs[0].source_sha256,
        gates=plan.data['gates'], jobs=rows, trials={})
    if storage_mode != 'legacy':
        state['storage_mode'] = storage_mode
    for seed in config['seeds']:
        reservation = sum(r['cap'] for r in rows if r['seed'] == seed)
        if (reservation != plan.data['costs']['trial_job_cap_reservation'] or
                reservation > config['max_trial_requested_samples']):
            raise ValueError('Trial cannot reserve all fixed Job caps')
        state['trials'][f'seed{seed}'] = dict(kind='development_only', seed=seed,
            cap=config['max_trial_requested_samples'], initial_reservation=reservation)
    _development_totals(state)
    output.mkdir(parents=True, exist_ok=False)
    ledger = output / 'run.json'
    parent_io = dict(atomic_writes=0, payload_bytes=0, atomic_readbacks=0, readback_bytes=0)
    def save_parent(value):
        if storage_mode == 'legacy':
            atomic(ledger, value)
        else:
            from .storage import atomic_verified
            value['parent_io_before'] = dict(parent_io)
            measured = atomic_verified(ledger, value)
            parent_io['atomic_writes'] += measured['write_calls']
            parent_io['payload_bytes'] += measured['written_bytes']
            parent_io['atomic_readbacks'] += measured['read_calls']
            parent_io['readback_bytes'] += measured['read_bytes']
    save_parent(state)
    for index, spec in enumerate(specs):
        # This durable marker precedes Worker invocation AND raw import.
        row = state['jobs'][index]
        row['status'] = 'unknown'
        state['status'] = 'unknown'
        _development_totals(state)
        save_parent(state)
        try:
            if timing_jobs is None:
                returned = execute_development_job(spec, output / row['raw_path'], root=root,
                                                   solver_kind=solver_kind)
            else:
                diagnostic = timing_jobs[index]
                diagnostic['status'] = 'unknown'
                timer = diagnostic['timer']
                returned = timer.call('job_worker', execute_development_job, spec,
                                      output / row['raw_path'], root=root,
                                      solver_kind=solver_kind, timer=timer)
                diagnostic['status'] = returned.get('payload', returned).get('status', 'unknown')
            readback = _window_development_readback if storage_mode == 'window100' else _development_readback
            imported = readback(output / row['raw_path'], returned, spec)
        except (Exception, KeyboardInterrupt) as exc:
            state['exit_reason'] = f'{type(exc).__name__}: {exc}'
            # No success state has touched the parent. Retain the entire cap.
            save_parent(state)
            return state
        candidate = copy.deepcopy(state)
        updated = candidate['jobs'][index]
        updated.update(imported)
        if imported['safe_to_release']:
            updated.update(status='completed', reserved=0, released=row['cap']-imported['requested'])
        else:
            # Observed requested is known, the rest remains uncertain/reserved.
            updated['reserved'] = row['cap']-imported['requested']
        candidate['status'] = ('completed' if index == len(specs)-1 and imported['safe_to_release']
                               else 'running' if imported['safe_to_release'] else 'unknown')
        _development_totals(candidate)
        save_parent(candidate)  # failure leaves durable unknown; no finalizer retry
        state = candidate
        if not imported['safe_to_release']:
            break
    return state


def _weighted_strict_winner(jobs):
    eligible = [r for r in jobs if r['status'] == 'completed' and
                r['terminal']['assessment']['strict_feasible']]
    eligible.sort(key=lambda r: (r['terminal']['assessment']['worst_il_db'], r['best']['vector_sha256']))
    return eligible[0]['job_id'] if eligible else None


def run_weighted_development(plan, definition, policy, starts, output, *, root=None, spot_checks=None):
    """Sequential budget-restart development Jobs; never a formal EXP entry."""
    import copy
    import json
    import subprocess
    from types import SimpleNamespace
    from lpf.rf_core import build_rf_model
    from ._development_runner import run_prepared_weighted_job
    from ._job_evaluation import source_identity
    from .plan import ROOT
    from .starts import validate
    root, output = Path(root or ROOT).resolve(), Path(output).resolve()
    _validate_development_output(output, root, 'legacy')
    if output.exists() or not output.parent.is_dir():
        raise ValueError('Fresh output in existing system temporary directory required')
    if subprocess.run(['git', '-C', str(output.parent), 'rev-parse', '--is-inside-work-tree'],
                      stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0:
        raise ValueError('Output must be outside Git checkouts')
    cfg = plan.data['config']
    mode = plan.data['development_weighted_restart']
    box = mode['search_bounds']
    max_search_forwards = cfg['arms'][0]['steps'][0]['options']['max_search_forwards']
    if (sha(plan.data) != plan.sha256 or sha(box) != mode['search_bounds_sha256'] or
            not isinstance(starts, dict) or set(starts) != set(cfg['seeds'])):
        raise ValueError('Frozen Plan/box/starts mismatch')
    model = build_rf_model(definition, policy)
    circuit = SimpleNamespace(definition=definition, schema=model.schema, resolved_policy=policy)
    for seed in cfg['seeds']:
        start = starts[seed]
        if (not isinstance(start, dict) or set(start) != {'vector', 'vector_sha256'} or
                vector_sha(start['vector']) != start['vector_sha256']):
            raise ValueError('Start vector/SHA mismatch')
        validate(circuit, start['vector'], box)
    source = source_identity(root)
    arm = cfg['arms'][0]['name']
    cap = cfg['arms'][0]['max_requested_samples']
    rows = [dict(job_id=f'development-{arm}-{seed}', trial_id=f'seed{seed}', seed=seed, arm=arm,
                 status='not_started', cap=cap, reserved=cap, released=0, requested=0, completed=0,
                 independent_requested=0, independent_completed=0, start=plain(starts[seed]),
                 raw_path=f'development-{arm}-{seed}') for seed in cfg['seeds']]
    if len({r['job_id'] for r in rows}) != len(rows):
        raise ValueError('Duplicate Job')
    state = dict(kind='development_weighted_sequential_v1', status='not_started', plan=plan.data,
                 plan_sha256=plan.sha256, source=source, source_sha256=sha(source),
                 gates=plan.data['gates'], jobs=rows,
                 trials={f'seed{s}': dict(kind='development_only', seed=s, cap=cap,
                                         initial_reservation=cap) for s in cfg['seeds']})
    _development_totals(state)
    output.mkdir(exist_ok=False)
    ledger = output / 'run.json'
    def save(value):
        atomic(ledger, value)
        if ledger.read_bytes() != (canonical(value) + '\n').encode():
            raise ValueError('Parent ledger readback mismatch')
    save(state)
    for index in range(len(state['jobs'])):
        row = state['jobs'][index]
        row['status'] = state['status'] = 'unknown'
        _development_totals(state)
        save(state)
        try:
            path = output / row['raw_path']
            result = run_prepared_weighted_job(plan, definition, policy, row['seed'], arm, row['start'], path,
                                               root=root, source=source, search_bounds=box, spot_checks=spot_checks)
            raw = (path / 'result.json').read_bytes()
            if raw != (canonical(result) + '\n').encode():
                raise ValueError('Job result byte mismatch')
            job_input = json.loads((path / 'input.json').read_text())
            if (job_input['plan'] != plan.data or job_input['plan_sha256'] != plan.sha256 or
                    job_input['source'] != source or job_input['source_sha256'] != sha(source) or
                    job_input['start'] != row['start'] or job_input['seed'] != row['seed'] or
                    job_input['arm'] != arm or job_input['search_bounds'] != box or
                    job_input['checkpoint_interval_forwards'] != mode['checkpoint_interval_forwards'] or
                    job_input['search_bounds_sha256'] != sha(box)):
                raise ValueError('Job input/Plan/source readback mismatch')
            costs = result['costs']
            n = costs['search_forwards']
            if (result['status'] != 'search_budget_exhausted' or type(n) is not int or
                    n != max_search_forwards or costs['search_requested_samples'] != n * 70 or
                    costs['search_completed_samples'] != n * 70 or
                    'selection_requested_samples' in costs or costs['terminal_requested_samples'] != 476 or
                    result['plan_sha256'] != plan.sha256 or result['steps'][0]['forward_count'] != n):
                raise ValueError('Job status or budget/readback mismatch')
            terminal = result['terminal']['candidates']
            best = result['steps'][0]['rf_best']
            solver = result['steps'][0]['solver_result']
            stats = result['steps'][0]['local_run_stats']
            if (set(solver) != {'x', 'objective', 'converged', 'stop_reason', 'evaluations'} or
                    vector_sha(solver['x']) != best['vector_sha256'] or
                    solver['objective'] != best['objective_j'] or solver['converged'] or
                    set(stats) != {'count', 'success', 'evaluations'} or
                    any(type(stats[k]) is not int or stats[k] < 0 for k in stats) or
                    not 0 < stats['count'] or stats['success'] > stats['count'] or
                    stats['evaluations'] != solver['evaluations'] or
                    solver['stop_reason'] != 'evaluation_budget_exhausted' or
                    'selection' in result or len(terminal) != 1 or
                    vector_sha(best['vector']) != best['vector_sha256'] or
                    terminal[0]['vector_sha256'] != best['vector_sha256']):
                raise ValueError('Job best/terminal mismatch')
            checkpoints = sorted((path / 'checkpoints').glob('*.json'))
            if not checkpoints:
                raise ValueError('Missing final checkpoint')
            last = json.loads(checkpoints[-1].read_text())
            if (last['forward_count'] != n or last['best'] != best or last['plan_sha256'] != plan.sha256 or
                    last['seed'] != row['seed'] or last['arm'] != arm or
                    last['sequence'] != len(checkpoints) or last['restart_count'] != stats['count'] - 1):
                raise ValueError('Final checkpoint readback mismatch')
            assessed = terminal[0]['assessment']
            audits = costs['independent_mna_samples_by_stage']
            stage = f"{arm}/{cfg['arms'][0]['steps'][0]['name']}"
            expected_audits = {name: len(indices) * (n if name == stage else 1)
                               for name, indices in (spot_checks or {}).items()}
            if audits != expected_audits:
                raise ValueError('Independent MNA accounting mismatch')
            count = sum(audits.values())
            requested = n * 70 + 476
            candidate = copy.deepcopy(state)
            updated = candidate['jobs'][index]
            best_summary = {key: best[key] for key in ('vector_sha256', 'objective_j')}
            terminal_summary = dict(vector_sha256=terminal[0]['vector_sha256'],
                assessment={key: assessed[key] for key in ('strict_feasible', 'worst_il_db')},
                independent=terminal[0]['independent'],
                min_harmonic_attenuation_db=terminal[0]['min_harmonic_attenuation_db'],
                target_30_01=terminal[0]['target_30_01'])
            updated.update(status='completed', worker_status=result['status'], requested=requested,
                           completed=requested, reserved=0, released=cap-requested,
                           independent_requested=count, independent_completed=count,
                           result_sha256=hashlib.sha256(raw).hexdigest(), best=best_summary,
                           terminal=terminal_summary, local_run_count=stats['count'])
            updated['local_solver_success_count'] = stats['success']
            updated['local_solver_failure_count'] = updated['local_run_count'] - updated['local_solver_success_count']
            if type(assessed['strict_feasible']) is not bool:
                raise ValueError('Invalid terminal strict feasibility')
            candidate['status'] = 'completed' if index == len(rows)-1 else 'running'
            _development_totals(candidate)
        except (Exception, KeyboardInterrupt) as exc:
            state['exit_reason'] = f'{type(exc).__name__}: {exc}'
            save(state)
            break
        save(candidate)  # failure leaves the durable unknown marker; do not retry
        state = candidate
    summary = dict(kind='development_weighted_sequential_summary_v1', status=state['status'],
                   plan_sha256=plan.sha256, source_sha256=sha(source), jobs=state['jobs'],
                   campaign=state['campaign'], trials=state['trials'], gates=state['gates'],
                   selected_job_id=_weighted_strict_winner(state['jobs']),
                   dense='not_run', continuous_frequency='not_verified', physical_feasibility='not_verified',
                   rf_compliance_certified=False, exit_reason=state.get('exit_reason'))
    atomic(output / 'summary.json', summary)
    if (output / 'summary.json').read_bytes() != (canonical(summary) + '\n').encode():
        raise ValueError('Summary readback mismatch')
    return summary


def finalize_development(state, output):
    """Read the final parent AND Worker files again; summarize without forwards.

    No save retry, budget release, candidate reranking or scientific gate approval.
    The original parent/raw files remain authoritative, including unknown markers.
    """
    import copy
    import json
    from .plan import ROOT
    output = Path(output).resolve()
    _validate_development_output(output, ROOT.resolve(), state.get('storage_mode', 'legacy'))
    parent = (output / 'run.json').read_bytes()
    if parent != (canonical(state) + '\n').encode():
        raise ValueError('Final parent/raw byte mismatch')
    durable = json.loads(parent)
    if sha(durable['plan']) != durable['plan_sha256']:
        raise ValueError('Final parent Plan SHA mismatch')
    if durable['gates'] != {'G0_G1': 'not_ready', 'G2_G5': 'not_ready'}:
        raise ValueError('Development gates must remain not_ready')
    totals = copy.deepcopy(durable)
    _development_totals(totals)
    if totals != durable:
        raise ValueError('Final parent totals mismatch')
    jobs = []
    for row in durable['jobs']:
        spec = JobSpec(**row['spec'])
        if (sha(spec) != row['spec_sha256'] or spec.plan_sha256 != durable['plan_sha256'] or
                spec.data['plan'] != durable['plan'] or
                spec.source_sha256 != durable['source_sha256']):
            raise ValueError('Final parent JobSpec/Plan/source mismatch')
        summary = {k: row[k] for k in ('job_id', 'trial_id', 'status', 'cap', 'requested',
            'completed', 'reserved', 'released', 'independent_requested', 'independent_completed')}
        summary['start_vector_sha256'] = spec.data['start']['vector_sha256']
        if 'raw_byte_sha256' in row:
            path = output / row['raw_path']
            raw_result = json.loads(path.read_bytes())
            readback = _window_development_readback if durable.get('storage_mode') == 'window100' else _development_readback
            imported = readback(path, raw_result, spec)
            result = raw_result['payload'] if durable.get('storage_mode') == 'window100' else raw_result
            if any(row[k] != value for k, value in imported.items()):
                raise ValueError('Final Worker/parent evidence mismatch')
            summary.update({k: row[k] for k in ('raw_path', 'raw_byte_sha256',
                'raw_content_sha256', 'worker_status', 'exit_reason', 'solver_evaluations')})
            summary['solver_steps'] = [dict(name=s['name'], status=s['status'],
                stop_reason=s.get('solver_result', {}).get('stop_reason',
                    s.get('solver_result', {}).get('reason'))) for s in result['steps']]
            summary.update(terminal=result['terminal'], anytime=result['anytime'])
            summary['independent_spots'] = [b['independent'] for b in result['batches']]
            summary['finite_grid'] = [dict(stage=b['stage'], grid_sha256=b['grid_sha256'],
                vector_sha256=b['vector_sha256'], strict_feasible=b['assessment']['strict_feasible'],
                nominal_pass=(b['assessment']['nominal_pass'] if 'nominal_pass' in b['assessment'] else
                    all(r['passed'] for r in b['assessment']['rows'] if r['requirement']['level'] == 'nominal')),
                worst_il_db=b['assessment']['worst_il_db'],
                max_violation_db=b['assessment']['max_violation_db'],
                sum_violation_db=b['assessment']['sum_violation_db'])
                for b in result['batches'] if b['status'] == 'completed']
        elif row['status'] == 'completed':
            raise ValueError('Completed Job missing raw evidence')
        jobs.append(summary)
    complete = durable['status'] == 'completed' and all(j['status'] == 'completed' for j in jobs)
    converged = complete and all(j.get('worker_status') == 'converged' for j in jobs)
    code = 0 if converged else 4 if complete else 2
    reason = ('development_flow_completed' if converged else
              'reconciled_budget_or_solver_not_converged' if complete else 'unknown_or_invalid_STOP')
    plan = durable['plan']
    summary = dict(kind='development_only_not_an_EXP', exit_code=code, exit_reason=reason,
        development_flow='completed' if complete else 'stopped',
        solver_converged=converged, rf_compliance_certified=False,
        gates=durable['gates'], dense='not_run', full_band_independent_mna='not_run',
        preservation_audit='not_run', continuous_frequency='not_verified',
        physical_feasibility='not_verified', parent_exit_reason=durable.get('exit_reason'),
        parent_raw_byte_sha256=hashlib.sha256(parent).hexdigest(),
        plan_sha256=durable['plan_sha256'], source_sha256=durable['source_sha256'],
        rf=plan['config']['rf'], effective_constraint_sha256=plan['requirements']['policy_fingerprint'],
        rf_inputs=plan['rf_inputs'], objective=plan['config']['objective'],
        interval_count=len(plan['requirements']['intervals']),
        setting_count=len(set(plan['grids']['terminal']['setting'])),
        grids={k: {f: v[f] for f in ('sha256', 'points_per_interval', 'requested_samples_per_forward')}
               for k, v in plan['grids'].items()},
        campaign=durable['campaign'], trials=durable['trials'], jobs=jobs)
    target = output / 'summary.json'
    if target.exists():
        raise ValueError('Existing summary: no automatic retry')
    if durable.get('storage_mode') == 'window100':
        from .storage import atomic_verified
        io_before = durable['parent_io_before']
        parent_io = dict(atomic_writes=io_before['atomic_writes']+1,
                         payload_bytes=io_before['payload_bytes']+len(parent),
                         atomic_readbacks=io_before['atomic_readbacks']+1,
                         readback_bytes=io_before['readback_bytes']+len(parent))
        worker_ios = [j['worker_io'] for j in durable['jobs'] if 'worker_io' in j]
        worker_io = {k: sum(j[k] for j in worker_ios) for k in
                     ('atomic_writes', 'payload_bytes', 'atomic_readbacks', 'readback_bytes')}
        summary['io'] = dict(scope='atomic JSON payload writes and immediate readbacks; excludes other I/O and unknown workers',
            complete_worker_accounting=len(worker_ios) == len(durable['jobs']),
            parent=parent_io, worker=worker_io,
            summary=dict(atomic_writes=1, payload_bytes=0, atomic_readbacks=1, readback_bytes=0),
            total=dict(atomic_writes=parent_io['atomic_writes']+worker_io['atomic_writes']+1,
                       payload_bytes=0, atomic_readbacks=parent_io['atomic_readbacks']+worker_io['atomic_readbacks']+1,
                       readback_bytes=0))
        # The summary reports its own serialized size; converge the decimal
        # length before the single actual write, never rewrite a checkpoint.
        while True:
            size = len((canonical(summary) + '\n').encode())
            total = parent_io['payload_bytes'] + worker_io['payload_bytes'] + size
            if (summary['io']['summary']['payload_bytes'] == size and summary['io']['total']['payload_bytes'] == total and
                    summary['io']['summary']['readback_bytes'] == size and summary['io']['total']['readback_bytes'] == total):
                break
            summary['io']['summary']['payload_bytes'] = summary['io']['summary']['readback_bytes'] = size
            summary['io']['total']['payload_bytes'] = summary['io']['total']['readback_bytes'] = total
        atomic_verified(target, summary)
    else:
        atomic(target, summary)
    if target.read_bytes() != (canonical(summary) + '\n').encode():
        raise ValueError('Summary readback mismatch')
    return summary

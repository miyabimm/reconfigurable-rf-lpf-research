"""Read-only Stage-4A plan compiler. No RF forward/worker/EXP imports."""
from dataclasses import asdict
import hashlib
import json
import math

from lpf.constraint_versions import load_constraint, rf_input_file
from .performance import compile_requirements, build_evaluation_grid, grid_fingerprint
from .storage import sha


def definition_sha(ref):
    """Source reference or the same CircuitDefinition data frozen per Job."""
    if ref is None:
        raise ValueError('Null definition is preflight-only')
    return sha(ref) if 'inductor_tree' in ref else ref['definition_sha256']


def nonnegative(value):
    if type(value) is not int or value < 0:
        raise ValueError('Nonnegative integer required')


def check_next_batch(batch_samples, *, step_remaining, job_remaining, trial_remaining,
                     job_reserved, trial_reserved):
    """Pure runtime arithmetic: STOP before a full batch invades any reservation.

    Remaining includes unspent reservations. Callers must release the reservation
    being executed before calling; e.g. a terminal batch releases only its own
    share. This is not a ledger and does not claim any samples were executed.
    """
    from .plan import positive
    positive(batch_samples)
    for v in (step_remaining, job_remaining, trial_remaining, job_reserved, trial_reserved):
        nonnegative(v)
    if (batch_samples > step_remaining or batch_samples+job_reserved > job_remaining or
            batch_samples+trial_reserved > trial_remaining):
        raise ValueError('STOP: next full batch exceeds unreserved sample budget')


def _solver(step):
    from .plan import fields, positive
    solver, agg, options = step['solver'], step['aggregation'], step['options']
    if solver == 'hybrid':
        fields(options, 'maxiter max_restarts max_evaluations restart_sigma')
        positive(options['maxiter'])
        nonnegative(options['max_restarts'])
        sigma = options['restart_sigma']
        if type(sigma) not in (int, float) or not math.isfinite(sigma) or not 0 < sigma <= 1:
            raise ValueError('Invalid restart sigma')
    elif solver in ('slsqp', 'slp'):
        fields(options, 'max_iterations max_evaluations')
        positive(options['max_iterations'])
    else:
        raise ValueError('Unknown solver')
    if agg not in (('signed_max',) if solver == 'slp' else ('sum', 'max')):
        raise ValueError('Unknown solver aggregation')
    positive(options['max_evaluations'])


def freeze(d, root):
    from .plan import fields, positive
    base_fields = 'schema_version rf objective definition seeds arms max_trial_requested_samples selection validation anytime_samples anytime_points_per_interval'
    fields(d, base_fields + (' campaign' if isinstance(d, dict) and 'campaign' in d else ''))
    if 'campaign' in d:
        envelope = d['campaign']
        fields(envelope, 'max_topologies max_rf_samples structure independent')
        positive(envelope['max_topologies']); positive(envelope['max_rf_samples'])
        structure = envelope['structure']
        fields(structure, 'max_nodes max_fixed_capacitors max_variable_capacitors inductor_types fixed_c_types variable_roles allow_coupling allow_ic_fixed')
        positive(structure['max_nodes'])
        nonnegative(structure['max_fixed_capacitors'])
        nonnegative(structure['max_variable_capacitors'])
        for key in ('inductor_types', 'fixed_c_types', 'variable_roles'):
            if (not isinstance(structure[key], list) or not structure[key] or
                    any(type(v) is not str for v in structure[key]) or
                    len(set(structure[key])) != len(structure[key])):
                raise ValueError('Explicit unique allowed structural types/roles required')
        if any(type(structure[k]) is not bool for k in ('allow_coupling', 'allow_ic_fixed')):
            raise ValueError('Explicit structural capability booleans required')
        independent = envelope['independent']
        fields(independent, 'stage max_candidates sample_indices')
        if independent['stage'] not in ('not_run', 'terminal'):
            raise ValueError('Only bounded terminal independent spots supported')
        nonnegative(independent['max_candidates'])
        indices = independent['sample_indices']
        if (not isinstance(indices, list) or any(type(i) is not int or i < 0 for i in indices) or
                len(set(indices)) != len(indices)):
            raise ValueError('Unique independent sample indices required')
        if independent['stage'] == 'not_run':
            if independent['max_candidates'] or indices:
                raise ValueError('not_run independent validation cannot request samples')
        elif not independent['max_candidates'] or not indices:
            raise ValueError('Bounded independent candidate/sample request required')
    if type(d['schema_version']) is not int or d['schema_version'] != 2:
        raise ValueError('Stage-4A requires schema_version 2')
    fields(d['rf'], 'constraint_id allow_trial')
    if (type(d['rf']['allow_trial']) is not bool or
            not isinstance(d['rf']['constraint_id'], str) or not d['rf']['constraint_id']):
        raise ValueError('Explicit RF ID and boolean trial opt-in required')
    policy = load_constraint(d['rf']['constraint_id'], root=root, allow_trial=d['rf']['allow_trial'])
    bands = rf_input_file(root, policy['bands_file'])
    req = compile_requirements(policy, bands, d['objective'])
    seeds = d['seeds']
    if (not isinstance(seeds, list) or not seeds or
            any(type(s) is not int or s < 0 for s in seeds) or len(set(seeds)) != len(seeds)):
        raise ValueError('Unique nonnegative seeds required')
    positive(d['max_trial_requested_samples'])
    # References are source evidence only, not topology/physical/G1 approval.
    ref = d['definition']
    if ref is not None and not isinstance(ref, dict):
        raise ValueError('Definition must be a reference, CircuitDefinition data, or null')
    if ref is not None and 'inductor_tree' in ref:
        from .proposals import definition_from_data
        definition_from_data(ref)
    elif ref is not None:
        fields(ref, 'path source_sha256 definition_sha256')
        source = (root / ref['path']).resolve()
        if not source.is_relative_to(root):
            raise ValueError('Definition must be repository-local')
        raw = source.read_bytes()
        if hashlib.sha256(raw).hexdigest() != ref['source_sha256']:
            raise ValueError('Definition source SHA mismatch')
        if sha(json.loads(raw)) != ref['definition_sha256']:
            raise ValueError('Definition canonical SHA mismatch')
    inputs = {'bands': {'path': policy['bands_file'], 'sha256': hashlib.sha256(bands.read_bytes()).hexdigest()}}
    for key in ('input_parasitic', 'output_parasitic'):
        spec = policy['external_port_parasitics'][key]
        actual = hashlib.sha256(rf_input_file(root, spec['path']).read_bytes()).hexdigest()
        if actual != spec['sha256']:
            raise ValueError('Fixed S2P SHA mismatch')
        inputs[key] = {'path': spec['path'], 'sha256': actual}
    grids = {}

    def grid(name, points, stop_points=None):
        g = build_evaluation_grid(req, points, stop_points)
        n = len(g.frequency_hz)
        grids[name] = dict(points_per_interval=points, requested_samples_per_forward=n,
                           sha256=grid_fingerprint(g), frequency_hz=g.frequency_hz.tolist(),
                           setting=g.setting.tolist(), segment=g.segment.tolist(),
                           interval_samples=[dict(identity=i.identity, segment=i.segment,
                                                  setting=i.setting,
                                                  samples=int(((g.segment == i.segment) &
                                                               (g.setting == i.setting)).sum()))
                                             for i in req.intervals])
        if stop_points is not None:
            grids[name]['stop_points_per_interval'] = stop_points
        return n

    selection = d['selection']
    fields(selection, 'rule top_k max_candidates points_per_interval')
    if selection['rule'] != 'mandatory_vmax_vsum_il_sha':
        raise ValueError('Unknown Stage-3 selection rule')
    positive(selection['top_k'])
    positive(selection['max_candidates'])
    if selection['top_k'] > selection['max_candidates']:
        raise ValueError('Selection top_k exceeds candidate cap')
    selection_one = grid('selection', selection['points_per_interval'])
    validation = d['validation']
    fields(validation, 'terminal_points dense_points max_candidates max_requested_samples')
    positive(validation['max_candidates'])
    positive(validation['max_requested_samples'])
    terminal_one = grid('terminal', validation['terminal_points'])
    dense_one = grid('dense', validation['dense_points'])
    if 'campaign' in d:
        independent = d['campaign']['independent']
        if (any(i >= terminal_one for i in independent['sample_indices']) or
                independent['max_candidates'] > selection['top_k']):
            raise ValueError('Independent candidate/sample request exceeds terminal selection')
    dense_upper = validation['max_candidates']*dense_one
    if dense_upper > validation['max_requested_samples']:
        raise ValueError('Dense validation cap cannot reserve its candidate upper bound')
    anytime_one = grid('anytime', d['anytime_points_per_interval'])
    milestones = d['anytime_samples']
    if (not isinstance(milestones, list) or
            any(type(m) is not int or m <= 0 for m in milestones) or
            milestones != sorted(set(milestones))):
        raise ValueError('Anytime milestones must be increasing positive samples')
    arms = d['arms']
    if not isinstance(arms, list) or not arms:
        raise ValueError('Nonempty fixed arms required')
    names, jobs = set(), {}
    for arm in arms:
        fields(arm, 'name steps max_requested_samples')
        name = arm['name']
        if not isinstance(name, str) or not name.isidentifier() or name in names:
            raise ValueError('Unique identifier arm names required')
        names.add(name)
        positive(arm['max_requested_samples'])
        steps = arm['steps']
        if not isinstance(steps, list) or not steps:
            raise ValueError('Nonempty fixed steps required')
        stage_names, stages = set(), {}
        for step in steps:
            fields(step, 'name solver aggregation points_per_interval max_requested_samples options' +
                   (' stop_points_per_interval' if isinstance(step, dict) and
                    'stop_points_per_interval' in step else ''))
            if 'stop_points_per_interval' in step and step['stop_points_per_interval'] is None:
                raise ValueError('stop_points_per_interval must be an integer >=2')
            sname = step['name']
            if not isinstance(sname, str) or not sname.isidentifier() or sname in stage_names:
                raise ValueError('Unique identifier step names required')
            stage_names.add(sname)
            _solver(step)
            positive(step['max_requested_samples'])
            one = grid(f'{name}/{sname}', step['points_per_interval'],
                       step.get('stop_points_per_interval'))
            check_next_batch(one, step_remaining=step['max_requested_samples'],
                             job_remaining=arm['max_requested_samples'],
                             trial_remaining=d['max_trial_requested_samples'],
                             job_reserved=0, trial_reserved=0)
            stages[sname] = dict(one_forward_samples=one,
                                 upper_reservation=step['max_requested_samples'],
                                 solver_max_evaluations=step['options']['max_evaluations'],
                                 status='not_run')
        terminal = selection['top_k']*terminal_one
        anytime = len(milestones)*anytime_one
        selected = selection['max_candidates']*selection_one
        stage_upper = sum(s['upper_reservation'] for s in stages.values())
        required = stage_upper+selected+terminal+anytime
        if required > arm['max_requested_samples']:
            raise ValueError('STOP: stage/selection caps invade terminal/anytime reservations')
        if any(m > stage_upper for m in milestones):
            raise ValueError('Anytime milestone unreachable within stage upper budgets')
        future_reserved = selected+terminal+anytime
        for stage in reversed(list(stages.values())):
            stage['reserved_after_step'] = future_reserved
            future_reserved += stage['upper_reservation']
        jobs[name] = dict(stages=stages, selection_one_forward=selection_one,
                          selection_upper_reservation=selected,
                          terminal_one_forward=terminal_one, terminal_fixed_reservation=terminal,
                          anytime_one_forward=anytime_one, anytime_fixed_reservation=anytime,
                          runtime_reserved_samples=selected+terminal+anytime,
                          total_upper_reservation=required,
                          max_requested_samples=arm['max_requested_samples'], status='not_run')
    trial_reservation = sum(a['max_requested_samples'] for a in arms)
    if trial_reservation > d['max_trial_requested_samples']:
        raise ValueError('STOP: Trial cannot reserve all fixed jobs')
    return dict(config=d, requirements=asdict(req), grids=grids, rf_inputs=inputs,
                costs=dict(jobs=jobs, trial_job_cap_reservation=trial_reservation,
                           max_trial_requested_samples=d['max_trial_requested_samples'],
                           dense=dict(one_forward_samples=dense_one, upper_reservation=dense_upper,
                                      max_requested_samples=validation['max_requested_samples'],
                                      budget_scope='independent_validation', status='not_run')),
                gates={'G0_G1': 'not_ready', 'G2_G5': 'not_ready'},
                execution={'requested_samples': 0, 'completed_samples': 0, 'status': 'not_run'})

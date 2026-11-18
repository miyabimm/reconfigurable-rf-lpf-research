"""Compile one effective Plan for an RF profile development Run (no RF forwards)."""
from dataclasses import asdict
import hashlib
import json

from lpf.minimax_profile import load_minimax_profile
from .component_constraints import _check_vector_box, physical_bounds, validate_search_box
from .performance import build_evaluation_grid, compile_profile_grid, grid_fingerprint
from .plan import Plan, fields, positive, validate_solver
from .proposals import definition_from_data
from .storage import _normalize_search_bounds, canonical, plain, sha, vector_sha

COSTS = ('rf_samples', 'rf_forwards', 'independent_mna_samples')


def solver_options(step):
    if step['solver'] == 'hybrid':
        return dict(max_evaluations=step['options']['max_search_forwards'], restart_sigma=0.1)
    defaults = {'slsqp': dict(tolerance=1e-9, constraint_tolerance=1e-7),
                'slp': dict(initial_step=.25, min_step=1e-8, fd_step=1e-6,
                            tolerance=1e-7, constraint_tolerance=1e-7)}
    return {**defaults[step['solver']], **step['options']}


def freeze_run(config, starts, *, root, spot_checks, search_bounds, checkpoint_interval):
    """Return the immutable Plan and its verified physical/profile inputs."""
    d = json.loads(canonical(config))
    if (not isinstance(d, dict) or not isinstance(d.get('rf'), dict)
            or set(d['rf']) != {'constraint_id', 'allow_trial'}
            or d['rf']['allow_trial'] is not True):
        raise ValueError('Development requires a profile ID and explicit trial opt-in')
    fields(d, 'schema_version rf definition seeds arms terminal_points budget')
    if type(d['schema_version']) is not int or d['schema_version'] != 1:
        raise ValueError('Expected development schema_version 1')
    positive(checkpoint_interval)
    ref = d['definition']
    if isinstance(ref, dict) and 'inductor_tree' in ref:
        definition = definition_from_data(ref)
    else:
        fields(ref, 'path source_sha256 definition_sha256')
        path = (root / ref['path']).resolve()
        if not path.is_relative_to(root):
            raise ValueError('Definition must be repository-local')
        blob = path.read_bytes()
        if hashlib.sha256(blob).hexdigest() != ref['source_sha256'] or sha(json.loads(blob)) != ref['definition_sha256']:
            raise ValueError('Definition source SHA mismatch')
        definition = definition_from_data(json.loads(blob))
    profile = load_minimax_profile(d['rf']['constraint_id'], root=root, allow_trial=True)
    policy = json.loads(profile.base_json)
    model = profile.build_model(definition)
    physical = physical_bounds(definition, model.schema, policy)
    bounds = physical if search_bounds is None else _normalize_search_bounds(search_bounds)
    validate_search_box(bounds, physical)
    req = compile_profile_grid(profile)
    grids, spots = {}, {}
    if not isinstance(spot_checks, dict) or not spot_checks.get('terminal'):
        raise ValueError('Development requires Terminal MNA spots')

    def grid(stage, points, stop=None):
        g = build_evaluation_grid(req, points, stop)
        n = len(g.frequency_hz)
        grids[stage] = dict(frequency_hz=plain(g.frequency_hz), setting=plain(g.setting),
                            segment=plain(g.segment), sha256=grid_fingerprint(g))
        if stage in spot_checks:
            indices = spot_checks[stage]
            if (not isinstance(indices, list) or not indices or
                    any(type(i) is not int or not 0 <= i < n for i in indices) or
                    len(set(indices)) != len(indices)):
                raise ValueError(f'Invalid independent spot checks: {stage}')
            spots[stage] = list(indices)
        return n, len(spots.get(stage, ()))

    terminal, terminal_spots = grid('terminal', d['terminal_points'])
    seeds = d['seeds']
    if (not isinstance(seeds, list) or not seeds or any(type(s) is not int or s < 0 for s in seeds)
            or len(set(seeds)) != len(seeds)):
        raise ValueError('Unique nonnegative seeds required')
    if not isinstance(d['arms'], list) or not d['arms']:
        raise ValueError('At least one arm required')
    reservations = {}
    for arm in d['arms']:
        fields(arm, 'name steps')
        name = arm['name']
        if not isinstance(name, str) or not name.isidentifier() or name in reservations:
            raise ValueError('Unique identifier arm names required')
        if not isinstance(arm['steps'], list) or not arm['steps']:
            raise ValueError('At least one Search step required')
        samples, forwards, mna = terminal, 1, terminal_spots
        for step in arm['steps']:
            fields(step, 'name solver objective aggregation options points_per_interval' +
                   (' stop_points_per_interval' if 'stop_points_per_interval' in step else ''))
            sname = step['name']
            stage = f'{name}/{sname}'
            if not isinstance(sname, str) or not sname.isidentifier() or stage in grids:
                raise ValueError('Unique identifier step names required within an arm')
            if step['objective'] != 'signed_margin_db':
                raise ValueError('Development requires signed_margin_db residuals')
            validate_solver(step)
            points = step['points_per_interval']
            stop = step.get('stop_points_per_interval', points)
            if type(stop) is not int or type(points) is not int or d['terminal_points'] <= max(points, stop):
                raise ValueError('Terminal must be denser than each Search interval')
            n, k = grid(stage, points, stop)
            step['effective_options'] = solver_options(step)
            step['effective_objective'] = ('signed_max_db' if step['solver'] == 'slp'
                                           else f"{step['aggregation']}_squared_db2_unit_weights")
            limit = step['effective_options']['max_evaluations']
            samples += n * limit
            forwards += limit
            mna += k * limit
        reservations[name] = dict(rf_samples=samples, rf_forwards=forwards, independent_mna_samples=mna)
    if set(spot_checks) != set(spots):
        raise ValueError('Unknown MNA spot stage')
    fields(d['budget'], ' '.join(COSTS))
    for k in COSTS:
        upper = len(seeds) * sum(r[k] for r in reservations.values())
        cap = d['budget'][k]
        if type(cap) is not int or not upper <= cap <= 2**63 - 1:
            raise ValueError(f'STOP: total budget cannot reserve all Jobs: {k}')
    fields(starts, ' '.join(map(str, seeds)))
    jobs = []
    for seed in seeds:
        fields(starts[str(seed)], ' '.join(reservations))
        for arm in reservations:
            start = starts[str(seed)][arm]
            fields(start, 'vector vector_sha256')
            vector = plain(_check_vector_box(start['vector'], bounds).astype(float))
            if vector_sha(vector) != start['vector_sha256']:
                raise ValueError('Start vector SHA mismatch')
            jobs.append(dict(seed=seed, arm=arm, vector=vector, vector_sha256=start['vector_sha256'],
                             reservation=reservations[arm]))
    p = profile.profile
    data = dict(config=d, definition=plain(asdict(definition)), parameter_schema=plain(model.schema),
                rf_profile=dict(constraint_id=p['constraint_id'], effective_sha256=profile.fingerprint,
                                base_constraint_id=p['base_physical_constraint_id'],
                                base_constraint_sha256=profile.base_sha256, bands_sha256=profile.bands_sha256,
                                external_s2p=p['external_s2p']),
                grids=grids, search_bounds=plain(bounds), search_bounds_sha256=sha(bounds),
                spot_checks=spots, checkpoint_interval=checkpoint_interval, jobs=jobs)
    return Plan(canonical(data), sha(data)), definition, profile, model, physical

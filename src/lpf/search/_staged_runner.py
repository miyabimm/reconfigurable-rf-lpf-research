"""Four bounded development phases using the existing single-Plan Runner.

No formal EXP, retry, resume, extra RF forward, or adaptive budget allocation.
"""
import json
import math
from pathlib import Path
import subprocess
import tempfile

from lpf.minimax_profile import load_minimax_profile
from . import _development_runner as development
from ._staged_selection import rank_candidates, select_discovery, assess_reproducibility
from .development_plan import COSTS, freeze_run, resolve_definition
from .plan import fields, positive
from .source import source_identity
from .starts import generate_for_definition
from .storage import atomic_verified, canonical, sha, sync_directory, vector_sha

PHASES = ('screening', 'discovery', 'exploitation', 'refinement')
METRICS = ('search_objective', 'worst_il_db', 'min_h2_db', 'min_h3_db')


def _phase_config(config, name, seeds, budget):
    phase = config['phases'][name]
    options = dict(max_evaluations=phase['max_evaluations'], ftol=1e-6, x_scale=1.0,
                   restart_sigma=.1, restart_center='best' if name == 'exploitation' else 'last')
    if name == 'discovery':
        options['target_objective'] = config['selection']['target_objective']
    if name == 'refinement':
        options = dict(max_evaluations=phase['max_evaluations'], ftol=1e-8,
                       x_scale='jac', restart_sigma=None)
    step = dict(name='search', solver='trf', objective='signed_margin_db', aggregation='sum',
                options=options, points_per_interval=phase['points_per_interval'],
                stop_points_per_interval=phase['stop_points_per_interval'])
    return dict(schema_version=1, rf=config['rf'], definition=config['definition'], seeds=seeds,
                arms=[dict(name='baseline', steps=[step])], terminal_points=phase['terminal_points'], budget=budget)


def _spots(phase):
    spots = {'terminal': phase['spot_checks']['terminal']}
    if phase['spot_checks']['search']:
        spots['baseline/search'] = phase['spot_checks']['search']
    return spots


def _validate_config(config):
    fields(config, 'schema_version rf definition seeds search_bounds checkpoint_interval budget selection phases')
    if type(config['schema_version']) is not int or config['schema_version'] != 1:
        raise ValueError('Expected staged schema_version 1')
    seeds = config['seeds']
    if (not isinstance(seeds, list) or not seeds or any(type(s) is not int or s < 0 for s in seeds)
            or len(set(seeds)) != len(seeds)):
        raise ValueError('Unique nonnegative seeds required')
    positive(config['checkpoint_interval'])
    fields(config['budget'], ' '.join(COSTS))
    if any(type(config['budget'][k]) is not int or not 0 <= config['budget'][k] <= 2**63-1 for k in COSTS):
        raise ValueError('Invalid global budget')
    selection = config['selection']
    fields(selection, 'screening_count discovery_count target_objective terminal_max_margin required_seeds tolerances')
    for name in ('screening_count', 'discovery_count', 'required_seeds'):
        positive(selection[name])
    if not selection['discovery_count'] <= selection['screening_count'] <= len(seeds):
        raise ValueError('Invalid phase selection counts')
    for name in ('target_objective', 'terminal_max_margin'):
        v = selection[name]
        if type(v) not in (int, float) or not math.isfinite(v) or (name == 'target_objective' and v < 0):
            raise ValueError('Invalid selection threshold')
    fields(selection['tolerances'], ' '.join(METRICS))
    if any(type(v) not in (int, float) or not math.isfinite(v) or v < 0
           for v in selection['tolerances'].values()):
        raise ValueError('Invalid reproducibility tolerances')
    fields(config['phases'], ' '.join(PHASES))
    for phase in config['phases'].values():
        fields(phase, 'max_evaluations points_per_interval stop_points_per_interval terminal_points spot_checks')
        for key in ('max_evaluations', 'points_per_interval', 'stop_points_per_interval', 'terminal_points'):
            positive(phase[key])
        fields(phase['spot_checks'], 'search terminal')
        if not isinstance(phase['spot_checks']['search'], list):
            raise ValueError('Search spots must be a list')
    if config['search_bounds'] is None:
        raise ValueError('Explicit search_bounds required')


def _preflight(config, root, source):
    _validate_config(config)
    if config['rf'].get('allow_trial') is not True:
        raise ValueError('Trial opt-in required')
    definition = resolve_definition(config['definition'], root)
    profile = load_minimax_profile(config['rf']['constraint_id'], root=root, allow_trial=True)
    policy = json.loads(profile.base_json)
    initial = [generate_for_definition(definition, policy, seed, bounds=config['search_bounds'])
               for seed in config['seeds']]
    first = initial[0]
    test_start = {str(first['seed']): {'baseline': {k: first[k] for k in ('vector', 'vector_sha256')}}}
    maximum = (len(initial), config['selection']['screening_count'],
               config['selection']['discovery_count'], config['selection']['discovery_count'])
    plans, reservations, common = {}, {}, None
    for name, count in zip(PHASES, maximum, strict=True):
        cfg = _phase_config(config, name, [first['seed']], {k: 2**63-1 for k in COSTS})
        compiled = freeze_run(cfg, test_start, root=root, spot_checks=_spots(config['phases'][name]),
                              search_bounds=config['search_bounds'], checkpoint_interval=config['checkpoint_interval'])
        data = compiled[0].data
        identity = {k: data[k] for k in ('definition', 'parameter_schema', 'rf_profile', 'search_bounds', 'search_bounds_sha256')}
        if common is not None and common != identity:
            raise ValueError('Preflight phase identity mismatch')
        common = identity
        per_job = data['jobs'][0]['reservation']
        reservations[name] = dict(count=count, per_job=per_job, maximum={k: per_job[k]*count for k in COSTS})
        plans[name] = dict(search_grid_sha256=data['grids']['baseline/search']['sha256'],
                           terminal_grid_sha256=data['grids']['terminal']['sha256'],
                           effective_options=data['config']['arms'][0]['steps'][0]['effective_options'])
    maximum_cost = {k: sum(reservations[n]['maximum'][k] for n in PHASES) for k in COSTS}
    if any(maximum_cost[k] > config['budget'][k] for k in COSTS):
        raise ValueError(f'STOP: global budget cannot reserve all phases: {maximum_cost}')
    if source_identity(root) != source:
        raise ValueError('Source changed during preflight')
    return dict(kind='staged_development_manifest_v1', config_sha256=sha(config), source=source,
                source_sha256=sha(source), identity=common, initial_starts=initial,
                preflight_plans=plans, reservations=reservations, maximum_cost=maximum_cost,
                note='Singleton Plans are reservation preflight only; later starts are not yet known.'), profile


def _load_candidates(directory, state, plan, profile, phase):
    if state['status'] != 'completed' or json.loads((directory/'run.json').read_text()) != state:
        raise ValueError('Incomplete or changed phase ledger')
    if development._bytes_info((directory/'plan.json').read_bytes()) != state['plan_raw']:
        raise ValueError('Changed phase Plan')
    if sha(plan) != state['plan_sha256'] or json.loads((directory/'plan.json').read_text()) != plan:
        raise ValueError('Phase Plan SHA mismatch')
    rows = []
    for job, frozen in zip(state['jobs'], plan['jobs'], strict=True):
        if job['status'] != 'completed' or (job['seed'], job['arm']) != (frozen['seed'], frozen['arm']):
            raise ValueError('Incomplete phase job')
        folder = directory/job['raw_path']
        checked = development._verify_receipt(folder, job['raw']['receipt.json'], job, state)
        if any(checked[k] != job[k] for k in ('scientific_status', 'actual', 'released', 'raw')):
            raise ValueError('Phase receipt/ledger mismatch')
        result = json.loads((folder/'result.json').read_text())
        step, candidate = result['steps'][0], result['terminal']['candidates'][0]
        if step['stop_reason'] == 'solver_failure' or any(r['status'] < 0 for r in step['local_run_details']):
            raise ValueError('STOP: TRF solver_failure')
        if (result['initial_vector_sha256'] != frozen['vector_sha256'] or
                candidate['vector_sha256'] != vector_sha(candidate['vector']) or
                step['solver_result']['x'] != candidate['vector'] or
                result['terminal_grid_sha256'] != plan['grids']['terminal']['sha256']):
            raise ValueError('Phase candidate identity mismatch')
        response = candidate['response']
        grid, il = response['grid'], response['il_db']
        if any(grid[k] != plan['grids']['terminal'][k] for k in ('frequency_hz', 'setting', 'segment')):
            raise ValueError('Terminal grid mismatch')
        segments = grid['segment']
        if len(il) != len(segments) or len(il) != len(candidate['signed_margins_db']):
            raise ValueError('Terminal sample mismatch')
        records = profile.records
        def values(predicate):
            return [v for v, seg in zip(il, segments, strict=True) if predicate(records[seg])]
        rows.append(dict(seed=job['seed'], vector=candidate['vector'], vector_sha256=candidate['vector_sha256'],
                         initial_vector=frozen['vector'], initial_vector_sha256=frozen['vector_sha256'],
                         terminal_margins=candidate['signed_margins_db'], terminal_grid_sha256=result['terminal_grid_sha256'],
                         search_objective=step['solver_result']['objective'], converged=step['converged'],
                         stop_reason=step['stop_reason'], performance_feasible=candidate['performance_feasible'],
                         worst_il_db=max(values(lambda r: r['type'] == 'pass')),
                         min_h2_db=min(values(lambda r: r['region'] == 'H2')),
                         min_h3_db=min(values(lambda r: r['region'] == 'H3')),
                         provenance=dict(phase=phase, job=job['job_id'], plan_sha256=state['plan_sha256'],
                                         receipt=job['raw']['receipt.json'], source_sha256=state['source_sha256'])))
    return rows


def _run_phase(name, candidates, config, manifest, profile, root, output, rf_cache_mode):
    seeds = [r['seed'] for r in candidates]
    reservation = manifest['reservations'][name]
    budget = {k: reservation['per_job'][k]*len(seeds) for k in COSTS}
    cfg = _phase_config(config, name, seeds, budget)
    starts = {str(r['seed']): {'baseline': {k: r[k] for k in ('vector', 'vector_sha256')}} for r in candidates}
    spots = _spots(config['phases'][name])
    compiled = freeze_run(cfg, starts, root=root, spot_checks=spots, search_bounds=config['search_bounds'],
                          checkpoint_interval=config['checkpoint_interval'])
    data = compiled[0].data
    identity = {k: data[k] for k in manifest['identity']}
    expected = manifest['preflight_plans'][name]
    if (identity != manifest['identity'] or source_identity(root) != manifest['source'] or
            any(j['reservation'] != reservation['per_job'] for j in data['jobs']) or
            data['grids']['baseline/search']['sha256'] != expected['search_grid_sha256'] or
            data['grids']['terminal']['sha256'] != expected['terminal_grid_sha256'] or
            data['config']['arms'][0]['steps'][0]['effective_options'] != expected['effective_options']):
        raise ValueError('Phase boundary identity or reservation changed')
    directory = output/name
    state = development.run(cfg, starts, directory, root=root, spot_checks=spots,
                            search_bounds=config['search_bounds'], checkpoint_interval=config['checkpoint_interval'],
                            rf_cache_mode=rf_cache_mode)
    if state['plan_sha256'] != compiled[0].sha256 or state['source_sha256'] != manifest['source_sha256']:
        raise ValueError('Executed phase identity changed')
    if source_identity(root) != manifest['source']:
        raise ValueError('Source changed after phase')
    return _load_candidates(directory, state, data, profile, name)


def _ledger(summary, manifest, output, *, normal_end=False):
    totals = {k: dict(maximum=manifest['maximum_cost'][k], completed=0, released=0, unknown=0, not_started=0)
              for k in COSTS}
    phases = {}
    for name in PHASES:
        spec = manifest['reservations'][name]
        status = summary['phases'][name]['status']
        path = output/name/'run.json'
        rows = None
        if path.exists():
            try:
                state = json.loads(path.read_text())
                rows = state['jobs']
                plan_blob = (output/name/'plan.json').read_bytes()
                plan = json.loads(plan_blob)
                frozen = plan['jobs']
                phase = summary['phases'][name]
                expected = phase['candidates'] if status == 'completed' else phase['input']
                if (state['source_sha256'] != manifest['source_sha256'] or
                        development._bytes_info(plan_blob) != state['plan_raw'] or
                        sha(plan) != state['plan_sha256'] or
                        not 0 < len(rows) == len(frozen) == len(expected) <= spec['count'] or
                        sorted(j['seed'] for j in frozen) != sorted(j['seed'] for j in expected) or
                        state['status'] not in ('incomplete', 'completed') or
                        (status == 'completed' and state['status'] != 'completed') or
                        (state['status'] == 'completed' and any(r['status'] != 'completed' for r in rows))):
                    raise ValueError('Invalid phase ledger')
                for i, (row, job) in enumerate(zip(rows, frozen, strict=True), 1):
                    if (row['job_id'] != f'job-{i:04d}' or
                            (row['seed'], row['arm']) != (job['seed'], job['arm']) or
                            row['reservation'] != job['reservation'] or row['reservation'] != spec['per_job'] or
                            row['status'] not in ('completed', 'unknown', 'not_started')):
                        raise ValueError('Invalid phase Job ledger')
                    if row['status'] == 'completed':
                        checked = development._verify_receipt(output/name/row['raw_path'], row['raw']['receipt.json'], row, state)
                        if any(checked[k] != row[k] for k in ('scientific_status', 'actual', 'released', 'raw')):
                            raise ValueError('Invalid completed receipt')
            except Exception:
                rows = None
                status = 'unknown'
        elif status in ('running', 'completed'):
            status = 'unknown'
        phase_totals = {k: dict(completed=0, released=0, unknown=0, not_started=0) for k in COSTS}
        for k in COSTS:
            p = phase_totals[k]
            if rows is None:
                p['unknown' if status == 'unknown' else 'released' if normal_end else 'not_started'] = spec['maximum'][k]
            else:
                for row in rows:
                    if row['status'] == 'completed':
                        p['completed'] += row['actual'][k]
                        p['released'] += row['released'][k]
                    elif row['status'] == 'unknown':
                        p['unknown'] += row['reservation'][k]
                    else:
                        p['not_started'] += row['reservation'][k]
                p['released' if status == 'completed' or normal_end else 'not_started'] += (spec['count']-len(rows))*spec['per_job'][k]
            for key, value in p.items():
                totals[k][key] += value
        phases[name] = phase_totals
    return dict(total=totals, phases=phases, budget=config_budget(manifest, summary))


def config_budget(manifest, summary):
    return {k: dict(limit=summary['budget'][k], reserved_maximum=manifest['maximum_cost'][k],
                    outside_reservation=summary['budget'][k]-manifest['maximum_cost'][k]) for k in COSTS}


def run(config, output, *, root, rf_cache_mode='lk'):
    """Preflight and execute four phases; STOP retains unknown reservations."""
    root, output = Path(root).resolve(), Path(output).expanduser().resolve()
    if (not output.is_relative_to(Path(tempfile.gettempdir()).resolve()) or output.is_relative_to(root)
            or output.exists() or not output.parent.is_dir() or rf_cache_mode not in ('off', 'lk', 'response', 'both')):
        raise ValueError('Fresh temporary output outside repository and valid cache mode required')
    if subprocess.run(['git', '-C', str(output.parent), 'rev-parse', '--is-inside-work-tree'],
                      capture_output=True, check=False).returncode == 0:
        raise ValueError('Output must be outside Git repositories')
    config = json.loads(canonical(config))
    source = source_identity(root)
    output.mkdir(exist_ok=False)
    sync_directory(output.parent)
    atomic_verified(output/'config.json', config)
    summary = dict(kind='staged_development_summary_v1', status='preflight', phases={n: dict(status='not_started') for n in PHASES},
                   budget=config.get('budget'), reproducible=False, finite_grid_only=True, rf_compliance_certified=False,
                   retry_allowed=False, selection={}, final=None)
    atomic_verified(output/'summary.json', summary)
    manifest = None
    try:
        manifest, profile = _preflight(config, root, source)
        manifest['rf_cache_mode'] = rf_cache_mode
        atomic_verified(output/'manifest.json', manifest)
        initial = manifest['initial_starts']
        selected = [dict(seed=r['seed'], vector=r['vector'], vector_sha256=r['vector_sha256']) for r in initial]
        for name in PHASES:
            # Check previous phases before marking the next one as in flight.
            summary['ledger'] = _ledger(summary, manifest, output)
            if any(summary['ledger']['total'][k]['unknown'] for k in COSTS):
                raise ValueError('STOP: phase ledger or receipt became unverified')
            summary['phases'][name] = dict(status='running', input=selected)
            summary['ledger'] = _ledger(summary, manifest, output)
            atomic_verified(output/'summary.json', summary)
            rows = _run_phase(name, selected, config, manifest, profile, root, output, rf_cache_mode)
            ranked = rank_candidates(rows)
            summary['phases'][name] = dict(status='completed', candidates=ranked)
            if name == 'screening':
                chosen = ranked[:config['selection']['screening_count']]
            elif name == 'discovery':
                chosen = select_discovery(ranked, target_objective=config['selection']['target_objective'],
                                          terminal_max_margin=config['selection']['terminal_max_margin'],
                                          count=config['selection']['discovery_count'])
            else:
                chosen = ranked
            summary['selection'][name] = [dict(seed=r['seed'], vector=r['vector'], vector_sha256=r['vector_sha256'],
                                                provenance=r['provenance']) for r in chosen]
            selected = summary['selection'][name]
            summary['ledger'] = _ledger(summary, manifest, output)
            if any(summary['ledger']['total'][k]['unknown'] for k in COSTS):
                raise ValueError('STOP: phase ledger or receipt became unverified')
            atomic_verified(output/'summary.json', summary)
            if name == 'discovery' and not selected:
                summary['status'] = 'no_promising_candidate'
                break
        else:
            summary['final'] = assess_reproducibility(ranked, manifest['identity']['search_bounds'],
                                                       tolerances=config['selection']['tolerances'],
                                                       required_seeds=config['selection']['required_seeds'])
            summary['reproducible'] = summary['final']['reproducible']
            summary['status'] = 'completed'
        summary['ledger'] = _ledger(summary, manifest, output, normal_end=True)
        if any(summary['ledger']['total'][k]['unknown'] for k in COSTS):
            raise ValueError('STOP: final ledger or receipt became unverified')
        atomic_verified(output/'summary.json', summary)
        return summary
    except (Exception, KeyboardInterrupt) as exc:
        summary['status'] = 'STOP'
        summary['reproducible'] = False
        summary['reason'] = f'{type(exc).__name__}: {exc}'
        if manifest is not None:
            summary['ledger'] = _ledger(summary, manifest, output)
        atomic_verified(output/'summary.json', summary)
        raise

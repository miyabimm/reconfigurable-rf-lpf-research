"""One development-only Worker invocation; not a production or EXP runner."""
from dataclasses import asdict
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

import yaml

from lpf.constraint_versions import constraint_fingerprint, load_constraint, rf_input_file
from ._development_worker import DevelopmentWorker, _normalize_search_bounds, _save_checkpoint
from ._job_evaluation import source_identity
from .plan import ROOT, Loader, Plan, load_preflight
from .preflight import freeze
from .performance import build_evaluation_grid, compile_requirements
from .proposals import definition_from_data
from .starts import load_explicit
from .storage import canonical, sha, vector_sha


def _weighted_plan(config, root, arm, n, *, budget_restarts=False, search_bounds=None, start_method='explicit',
                   checkpoint_interval_forwards=1000):
    """Derive the existing Plan format before freezing; never alter formal preflight."""
    if type(checkpoint_interval_forwards) is not int or checkpoint_interval_forwards < 1:
        raise ValueError('checkpoint_interval_forwards must be a positive integer')
    if type(n) is not int or n < 1 or n > (2**63 - 1) // 1_000_000:
        raise ValueError('max_search_forwards must be a bounded positive integer')
    with Path(config).open() as stream:
        cfg = copy.deepcopy(yaml.load(stream, Loader=Loader))
    if (not isinstance(cfg, dict) or cfg.get('rf') != {'constraint_id': 'RF-T008', 'allow_trial': True}
            or cfg.get('objective') != 'full_lpf' or len(cfg.get('arms', [])) != 1
            or cfg['arms'][0].get('name') != arm or len(cfg['arms'][0].get('steps', [])) != 1
            or (not budget_restarts and len(cfg.get('seeds', [])) != 1)
            or cfg.get('anytime_samples') != []):
        raise ValueError('Weighted mode requires RF-T008/full_lpf, one arm, seed and step, no anytime')
    step = cfg['arms'][0]['steps'][0]
    if step.get('solver') != 'hybrid' or step.get('aggregation') != 'sum':
        raise ValueError('Weighted mode requires Hybrid/sum')
    policy = load_constraint('RF-T008', root=root, allow_trial=True)
    req = compile_requirements(policy, rf_input_file(root, policy['bands_file']), 'full_lpf')
    grid = build_evaluation_grid(req, step['points_per_interval'], step.get('stop_points_per_interval'))
    selection = cfg['selection']
    terminal = cfg['validation']
    if (step['points_per_interval'] != 2 or step.get('stop_points_per_interval') != 3 or
            len(grid.frequency_hz) != 70 or selection['points_per_interval'] != 3 or
            terminal['terminal_points'] != 17):
        raise ValueError('Weighted mode requires 70/84/476 search/selection/terminal samples')
    step['options'] = dict(maxiter=n, max_restarts=0, max_evaluations=n, restart_sigma=0.1)
    step['max_requested_samples'] = n * len(grid.frequency_hz)
    selection['max_candidates'] = selection['top_k'] = 1
    total = step['max_requested_samples'] + 84 + 476
    if total > 2**63 - 1:
        raise ValueError('Sample reservation overflow')
    cfg['arms'][0]['max_requested_samples'] = cfg['max_trial_requested_samples'] = total
    # Dense is independent and not run by this worker; preflight still reserves its cap.
    dense = build_evaluation_grid(req, terminal['dense_points'])
    terminal['max_requested_samples'] = terminal['max_candidates'] * len(dense.frequency_hz)
    frozen = freeze(cfg, root)
    costs = frozen['costs']['jobs'][arm]
    if (costs['stages'][step['name']]['upper_reservation'] != n * len(grid.frequency_hz) or
            costs['selection_upper_reservation'] != 84 or costs['terminal_fixed_reservation'] != 476 or
            costs['total_upper_reservation'] != total):
        raise ValueError('Weighted budget arithmetic mismatch')
    if budget_restarts:
        if start_method not in ('explicit', 'scrambled_sobol_single_point'):
            raise ValueError('Unknown start method')
        frozen['development_weighted_restart'] = dict(
            max_search_forwards=n, max_restarts=None, restart_sigma=0.1,
            checkpoint_interval_forwards=checkpoint_interval_forwards, search_bounds=search_bounds, start_method=start_method,
            search_bounds_sha256=sha(search_bounds), objective='weighted_violation')
    return Plan(canonical(frozen), sha(frozen))


def run_prepared_weighted_job(plan, definition, policy, seed, arm, start, output, *, root,
                              source, search_bounds, spot_checks=None):
    """Run one already-frozen budget-restart Job for the sequential parent."""
    from ._development_worker import WEIGHTED_OBJECTIVE
    output, root = Path(output), Path(root)
    if source_identity(root) != source:
        raise ValueError('Source changed before Job')
    checkpoint_interval = plan.data['development_weighted_restart']['checkpoint_interval_forwards']
    record = dict(kind='development_weighted_restart_input_v1', plan=plan.data,
                  plan_sha256=plan.sha256, definition=asdict(definition),
                  definition_sha256=sha(asdict(definition)), policy_id=policy['active_constraint_id'],
                  policy_fingerprint=constraint_fingerprint(policy), seed=seed, arm=arm,
                  start=start, checkpoint_interval_forwards=checkpoint_interval, spot_checks=spot_checks,
                  search_bounds=search_bounds, search_bounds_sha256=sha(search_bounds),
                  weighted_objective=WEIGHTED_OBJECTIVE, weighted_objective_sha256=sha(WEIGHTED_OBJECTIVE),
                  source=source, source_sha256=sha(source))
    output.mkdir(exist_ok=False)
    _save_checkpoint(output / 'input.json', record)
    if canonical(json.loads((output / 'input.json').read_text())) != canonical(record):
        raise ValueError('Input readback mismatch')
    try:
        worker = DevelopmentWorker(plan, definition, policy, arm, seed, start['vector'], start['vector_sha256'],
                                   root=root, checkpoint=output / 'checkpoints', checkpoint_interval=checkpoint_interval,
                                   spot_checks=spot_checks, search_bounds=search_bounds,
                                   objective_mode='weighted_violation', budget_restarts=True)
        result = worker.run()
        if source_identity(root) != source:
            raise ValueError('Source changed during Job')
        _save_checkpoint(output / 'result.json', result)
        if canonical(json.loads((output / 'result.json').read_text())) != canonical(result):
            raise ValueError('Result readback mismatch')
        return result
    except (Exception, KeyboardInterrupt) as exc:
        try:
            _save_checkpoint(output / 'failure.json', dict(status='STOP', reason=f'{type(exc).__name__}: {exc}'))
        except Exception:
            pass  # preserve the original failure; never retry a checkpoint
        raise


def run_development_worker(config, starts, seed, arm, output, *, root=ROOT,
                           checkpoint_interval=1000, spot_checks=None, search_bounds=None,
                           objective_mode=None, max_search_forwards=None):
    """Run exactly one seed/arm, preserving input and append-only Worker events.

    No budget ledger, retry, resume, or formal experiment protection is provided.
    Exceptions propagate, including failures to save or read back the result.
    """
    root = Path(root).resolve()
    output = Path(output).expanduser().resolve()
    if (not output.is_relative_to(Path(tempfile.gettempdir()).resolve()) or
            output.is_relative_to(root) or not output.parent.is_dir()):
        raise ValueError('Fresh system temporary output outside Git checkout required')
    probe = subprocess.run(['git', '-C', str(output.parent), 'rev-parse', '--is-inside-work-tree'],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if probe.returncode == 0:
        raise ValueError('Output must be outside Git checkouts')
    if objective_mode is None and max_search_forwards is None:
        plan = load_preflight(config, root=root)
    elif objective_mode == 'weighted_violation' and max_search_forwards is not None:
        plan = _weighted_plan(config, root, arm, max_search_forwards)
    else:
        raise ValueError('Specify weighted_violation and max_search_forwards together')
    cfg = plan.data['config']
    ref = cfg['definition']
    if ref is None:
        raise ValueError('Explicit complete definition required')
    data = ref if 'inductor_tree' in ref else json.loads((root / ref['path']).read_bytes())
    definition = definition_from_data(data)
    policy = load_constraint(cfg['rf']['constraint_id'], root=root, allow_trial=cfg['rf']['allow_trial'])
    entries = load_explicit(starts)
    if type(seed) is not int or seed not in cfg['seeds'] or seed not in entries:
        raise ValueError('Seed must occur in Plan and explicit starts')
    if not any(a['name'] == arm for a in cfg['arms']):
        raise ValueError('Arm must occur in Plan')
    start = entries[seed]
    if not isinstance(start, dict) or set(start) != {'vector', 'vector_sha256'} or vector_sha(start['vector']) != start['vector_sha256']:
        raise ValueError('Explicit start vector/SHA mismatch')
    box = None if search_bounds is None else _normalize_search_bounds(search_bounds)
    source = source_identity(root)
    script = root / 'scripts/run_development_worker.py'
    source['files']['scripts/run_development_worker.py'] = hashlib.sha256(script.read_bytes()).hexdigest()
    record = dict(kind='development_worker_input_v1', plan=plan.data, plan_sha256=plan.sha256,
                  definition=asdict(definition), definition_sha256=sha(asdict(definition)),
                  policy_id=cfg['rf']['constraint_id'], policy_fingerprint=constraint_fingerprint(policy),
                  seed=seed, arm=arm, start=start, checkpoint_interval=checkpoint_interval,
                  spot_checks=spot_checks, search_bounds=box,
                  search_bounds_sha256=None if box is None else sha(box),
                  search_bounds_mode='physical_full' if box is None else 'specified',
                  source=source, source_sha256=sha(source))
    if objective_mode:
        from ._development_worker import WEIGHTED_OBJECTIVE
        record['weighted_objective'] = WEIGHTED_OBJECTIVE
        record['weighted_objective_sha256'] = sha(WEIGHTED_OBJECTIVE)
        record['max_search_forwards'] = max_search_forwards
    # mkdir itself is exclusive: neither an existing job nor its files are touched.
    output.mkdir(exist_ok=False)
    _save_checkpoint(output / 'input.json', record)
    if objective_mode and canonical(json.loads((output / 'input.json').read_text())) != canonical(record):
        raise ValueError('Input readback mismatch')
    worker = DevelopmentWorker(plan, definition, policy, arm, seed, start['vector'], start['vector_sha256'],
                               root=root, checkpoint=output / 'checkpoints',
                               checkpoint_interval=checkpoint_interval, spot_checks=spot_checks,
                               search_bounds=box, objective_mode=objective_mode)
    result = worker.run()
    _save_checkpoint(output / 'result.json', result)
    if canonical(json.loads((output / 'result.json').read_text())) != canonical(result):
        raise ValueError('Result readback mismatch')
    return result

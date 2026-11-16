"""One development-only Worker invocation; not a production or EXP runner."""
from dataclasses import asdict
import copy
import json
from pathlib import Path

import yaml

from lpf.constraint_versions import constraint_fingerprint, load_constraint, rf_input_file
from ._development_worker import DevelopmentWorker, _save_checkpoint
from ._job_evaluation import source_identity
from .plan import Loader, Plan
from .preflight import freeze
from .performance import build_evaluation_grid, compile_requirements
from .storage import canonical, sha


def _weighted_plan(config, root, arm, n, *, search_bounds=None, start_method='explicit',
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
            or (search_bounds is None and len(cfg.get('seeds', [])) != 1)
            or cfg.get('anytime_samples') != []):
        raise ValueError('Weighted mode requires RF-T008/full_lpf, one arm, seed and step, no anytime')
    step = cfg['arms'][0]['steps'][0]
    if step.get('solver') != 'hybrid' or step.get('aggregation') != 'sum':
        raise ValueError('Weighted mode requires Hybrid/sum')
    if step.get('options') not in (None, {}):
        raise ValueError('Weighted development takes its search budget from --max-search-forwards; omit step options')
    if 'selection' in cfg:
        raise ValueError('Selection is not supported by Search→Terminal development; omit selection')
    policy = load_constraint('RF-T008', root=root, allow_trial=True)
    req = compile_requirements(policy, rf_input_file(root, policy['bands_file']), 'full_lpf')
    grid = build_evaluation_grid(req, step['points_per_interval'], step.get('stop_points_per_interval'))
    terminal = cfg['validation']
    if (step['points_per_interval'] != 2 or step.get('stop_points_per_interval') != 3 or
            len(grid.frequency_hz) != 70 or terminal['terminal_points'] != 17):
        raise ValueError('Weighted mode requires 70/476 search/terminal samples')
    step['options'] = dict(max_search_forwards=n)
    step['max_requested_samples'] = n * len(grid.frequency_hz)
    total = step['max_requested_samples'] + 476
    if total > 2**63 - 1:
        raise ValueError('Sample reservation overflow')
    cfg['arms'][0]['max_requested_samples'] = cfg['max_trial_requested_samples'] = total
    # Dense is independent and not run by this worker; preflight still reserves its cap.
    dense = build_evaluation_grid(req, terminal['dense_points'])
    terminal['max_requested_samples'] = terminal['max_candidates'] * len(dense.frequency_hz)
    frozen = freeze(cfg, root)
    costs = frozen['costs']['jobs'][arm]
    if (costs['stages'][step['name']]['upper_reservation'] != n * len(grid.frequency_hz) or
            costs['terminal_fixed_reservation'] != 476 or
            costs['total_upper_reservation'] != total):
        raise ValueError('Weighted budget arithmetic mismatch')
    if search_bounds is not None:
        if start_method not in ('explicit', 'scrambled_sobol_single_point'):
            raise ValueError('Unknown start method')
        frozen['development_weighted_restart'] = dict(
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
                                   objective_mode='weighted_violation')
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

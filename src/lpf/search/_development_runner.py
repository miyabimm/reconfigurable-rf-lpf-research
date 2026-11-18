"""One development-only Worker invocation; not a production or EXP runner."""
from dataclasses import asdict
import copy
import hashlib
import json
from pathlib import Path

import yaml

from lpf.constraint_versions import constraint_fingerprint, load_constraint, rf_input_file
from ._development_worker import DevelopmentWorker
from ._job_evaluation import source_identity
from .plan import Loader, Plan
from .preflight import freeze
from .performance import build_evaluation_grid, compile_requirements
from .storage import _save_checkpoint, canonical, sha


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


def run_profile_development(plan, definition, policy, seed, arm, start, output, *, root,
                            spot_checks, search_bounds=None, checkpoint_interval=1000):
    """Single RF-T009 development job; fresh tmp evidence, no Campaign or resume."""
    import tempfile
    from .storage import vector_sha
    output, root = Path(output).resolve(), Path(root).resolve()
    if (not output.is_relative_to(Path(tempfile.gettempdir()).resolve()) or
            output.is_relative_to(root) or output.exists()):
        raise ValueError('Fresh temporary output outside repository required')
    data = plan.data
    if (data['config']['rf'] != {'constraint_id': 'RF-T009', 'allow_trial': True} or
            'rf_profile' not in data or sha(data) != plan.sha256 or not isinstance(start, dict) or
            set(start) != {'vector', 'vector_sha256'} or vector_sha(start['vector']) != start['vector_sha256']):
        raise ValueError('Explicit RF-T009 Plan and complete start/SHA required')
    costs = data['costs']['jobs'][arm]
    spots = {} if spot_checks is None else spot_checks
    if not isinstance(spots, dict) or any(not isinstance(v, list) for v in spots.values()):
        raise ValueError('Spot checks must be stage to index lists')
    independent_upper = len(spots.get('terminal', []))
    for step in next(a['steps'] for a in plan.data['config']['arms'] if a['name'] == arm):
        stage = f"{arm}/{step['name']}"
        samples = len(plan.requested_grid(stage).frequency_hz)
        independent_upper += (costs['stages'][step['name']]['upper_reservation'] // samples) * len(spots.get(stage, []))
    reservation = dict(rf_samples=costs['total_upper_reservation'], independent_mna_samples=independent_upper,
                       rf_forwards=1 + sum(s['solver_max_evaluations'] for s in costs['stages'].values()))
    output.mkdir(exist_ok=False)
    try:
        # Construction verifies inputs but does not execute any RF forwards.
        worker = DevelopmentWorker(plan, definition, policy, arm, seed, start['vector'], start['vector_sha256'],
            root=root, checkpoint=output/'checkpoints', checkpoint_interval=checkpoint_interval,
            spot_checks=spot_checks, search_bounds=search_bounds)
        record = dict(kind='development_rf_profile_input_v1', plan=data, plan_sha256=plan.sha256,
                      definition=asdict(definition), definition_sha256=sha(asdict(definition)),
                      physical_policy_id=policy['active_constraint_id'],
                      physical_policy_sha256=constraint_fingerprint(policy), seed=seed, arm=arm,
                      start=start, spot_checks=spot_checks, search_bounds=search_bounds, reservation=reservation,
                      checkpoint_interval=checkpoint_interval, source=worker.source, source_sha256=worker.source_sha256,
                      reservation_status='unknown_until_verified_receipt')
        _save_checkpoint(output/'input.json', record)
        input_bytes = (output/'input.json').read_bytes()
        if canonical(json.loads(input_bytes)) != canonical(record):
            raise ValueError('Input readback mismatch')
        result = worker.run()
        if result['source_sha256'] != record['source_sha256']:
            raise ValueError('Result source/Job mismatch')
        actual = result['costs']
        rf_used = actual['search_requested_samples'] + actual['terminal_requested_samples']
        independent_used = sum(actual['independent_mna_samples_by_stage'].values())
        forwards = actual['search_forwards'] + actual['terminal_forwards']
        if (rf_used > reservation['rf_samples'] or independent_used > reservation['independent_mna_samples'] or
                forwards > reservation['rf_forwards']):
            raise ValueError('Completed cost exceeds reservation')
        result['ledger'] = dict(status='completed', reservation=reservation,
            rf_samples=dict(completed=rf_used, released=reservation['rf_samples'] - rf_used, unknown=0),
            rf_forwards=dict(completed=forwards, released=reservation['rf_forwards'] - forwards, unknown=0),
            independent_mna_samples=dict(completed=independent_used,
                released=reservation['independent_mna_samples'] - independent_used, unknown=0))
        _save_checkpoint(output/'result.json', result)
        result_bytes = (output/'result.json').read_bytes()
        if canonical(json.loads(result_bytes)) != canonical(result):
            raise ValueError('Result readback mismatch')
        if (output/'input.json').read_bytes() != input_bytes:
            raise ValueError('Input bytes changed')
        # Hash the actual persisted bytes, not a reconstructed serialization.
        files = {name: dict(bytes=len(blob), sha256=hashlib.sha256(blob).hexdigest())
                 for name, blob in (('input.json', input_bytes), ('result.json', result_bytes))}
        checkpoints = sorted((output/'checkpoints').glob('*.json'))
        if {p.name for p in checkpoints} != set(worker.checkpoint_files):
            raise ValueError('Checkpoint set changed')
        for path in checkpoints:
            blob = path.read_bytes()
            info = dict(bytes=len(blob), sha256=hashlib.sha256(blob).hexdigest())
            if worker.checkpoint_files[path.name] != info:
                raise ValueError('Checkpoint bytes changed')
            files[f'checkpoints/{path.name}'] = info
        receipt = dict(kind='development_rf_profile_receipt_v1', files=files)
        _save_checkpoint(output/'receipt.json', receipt)
        if canonical(json.loads((output/'receipt.json').read_text())) != canonical(receipt):
            raise ValueError('Receipt readback mismatch')
        return result
    except (Exception, KeyboardInterrupt) as exc:
        try:
            # A failure can interrupt a forward, validation, or persistence. Do not infer
            # completed work from a partial checkpoint: retain the whole reservation as unknown.
            _save_checkpoint(output/'failure.json', dict(status='STOP', reason=f'{type(exc).__name__}: {exc}',
                reservation=reservation, rf_samples_unknown_upper_bound=reservation['rf_samples'],
                rf_forwards_unknown_upper_bound=reservation['rf_forwards'],
                independent_mna_samples_unknown_upper_bound=reservation['independent_mna_samples'],
                retry_allowed=False))
        except Exception:
            pass
        raise


def run_prepared_weighted_job(plan, definition, policy, seed, arm, start, output, *, root,
                              source, search_bounds, spot_checks=None):
    """Run one already-frozen budget-restart Job for the sequential parent."""
    from ._legacy_development_worker import LegacyDevelopmentWorker, WEIGHTED_OBJECTIVE
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
        worker = LegacyDevelopmentWorker(plan, definition, policy, arm, seed, start['vector'], start['vector_sha256'],
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

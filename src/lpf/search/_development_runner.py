"""Single fixed-order RF profile development Runner. No formal EXP integration."""
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import sys

from lpf.timing import TimerCollector, timed_call

from ._development_worker import DevelopmentWorker
from .controller import actions
from .development_plan import COSTS, freeze_run
from .source import source_identity
from .storage import _atomic_data, _save_checkpoint, atomic_verified, canonical, sha, sync_directory


def _bytes_info(blob):
    return dict(bytes=len(blob), sha256=hashlib.sha256(blob).hexdigest())


def _save_raw(path, record):
    digest = _save_checkpoint(path, record)
    blob = path.read_bytes()
    if _bytes_info(blob)['sha256'] != digest or canonical(json.loads(blob)) != canonical(record):
        raise ValueError(f'Raw readback mismatch: {path.name}')
    return _bytes_info(blob)


def _run_job(compiled, index, source, root, output, collector=None, timing_steps=None, timing_level='timed', rf_cache_mode='off'):
    plan = compiled[0]
    data = plan.data
    job = data['jobs'][index]
    reservation = job['reservation']
    output.mkdir(exist_ok=False)
    try:
        worker = DevelopmentWorker(compiled, index, source, root=root, checkpoint=output/'checkpoints',
                                   timer=collector, timing_steps=timing_steps, timing_level=timing_level, rf_cache_mode=rf_cache_mode)
        record = dict(kind='development_rf_profile_input_v1', plan=data, plan_sha256=plan.sha256,
                      definition=data['definition'], definition_sha256=sha(data['definition']),
                      physical_policy_id=data['rf_profile']['base_constraint_id'],
                      physical_policy_sha256=data['rf_profile']['base_constraint_sha256'],
                      seed=job['seed'], arm=job['arm'], start={k: job[k] for k in ('vector', 'vector_sha256')},
                      spot_checks=data['spot_checks'], search_bounds=data['search_bounds'], reservation=reservation,
                      checkpoint_interval=data['checkpoint_interval'], source=source, source_sha256=sha(source),
                      reservation_status='unknown_until_verified_receipt')
        files = {'input.json': _save_raw(output/'input.json', record)}
        result = worker.run()
        if any(result[k] != record[k] for k in ('plan_sha256', 'source_sha256', 'arm', 'seed')) or (
                result['initial_vector_sha256'] != job['vector_sha256']):
            raise ValueError('Result/Job identity mismatch')
        costs = result['costs']
        actual = dict(rf_samples=costs['search_requested_samples'] + costs['terminal_requested_samples'],
                      rf_forwards=costs['search_forwards'] + costs['terminal_forwards'],
                      independent_mna_samples=sum(costs['independent_mna_samples_by_stage'].values()))
        if any(type(actual[k]) is not int or not 0 <= actual[k] <= reservation[k] for k in COSTS):
            raise ValueError('Completed cost exceeds reservation')
        result['ledger'] = dict(status='completed', reservation=reservation,
                                **{k: dict(completed=actual[k], released=reservation[k]-actual[k], unknown=0)
                                   for k in COSTS})
        files['result.json'] = _save_raw(output/'result.json', result)
        files.update({f'checkpoints/{name}': info for name, info in worker.checkpoint_files.items()})
        return _save_raw(output/'receipt.json', dict(kind='development_rf_profile_receipt_v1', files=files))
    except (Exception, KeyboardInterrupt) as exc:
        try:
            _save_checkpoint(output/'failure.json', dict(status='STOP', reason=f'{type(exc).__name__}: {exc}',
                reservation=reservation, retry_allowed=False))
        except Exception:
            pass
        raise


def _verify_receipt(output, expected, row, state):
    if (output/'failure.json').exists():
        raise ValueError('Job failure record forbids completion')
    blob = (output/'receipt.json').read_bytes()
    if _bytes_info(blob) != expected:
        raise ValueError('Receipt bytes changed')
    receipt = json.loads(blob)
    files = receipt['files']
    required = {'input.json', 'result.json'} | {f'checkpoints/{p.name}' for p in (output/'checkpoints').iterdir()}
    if (receipt['kind'] != 'development_rf_profile_receipt_v1' or set(files) != required or len(required) < 3):
        raise ValueError('Raw/checkpoint set changed')
    records = {}
    for name, info in files.items():
        raw = (output/name).read_bytes()
        if _bytes_info(raw) != info:
            raise ValueError(f'Raw/checkpoint bytes changed: {name}')
        if name in ('input.json', 'result.json'):
            records[name] = json.loads(raw)
    for record in records.values():
        for k, value in dict(seed=row['seed'], arm=row['arm'], plan_sha256=state['plan_sha256'],
                             source_sha256=state['source_sha256']).items():
            if record[k] != value:
                raise ValueError(f'Raw identity mismatch: {k}')
    result = records['result.json']
    status = result['status']
    if status not in ('converged', 'not_converged') or result['terminal']['status'] != 'completed':
        raise ValueError('Raw scientific execution incomplete')
    ledger = result['ledger']
    actual = {k: ledger[k]['completed'] for k in COSTS}
    if ledger['reservation'] != row['reservation'] or any(
            type(actual[k]) is not int or not 0 <= actual[k] <= row['reservation'][k] for k in COSTS):
        raise ValueError('Invalid raw costs')
    return dict(scientific_status=status, actual=actual,
                released={k: row['reservation'][k]-actual[k] for k in COSTS},
                raw={**files, 'receipt.json': expected})


def _publish(path, state, previous=None):
    """Advance the verified ledger or restore the last verified bytes and STOP."""
    if previous is not None and path.read_bytes() != previous:
        # The trusted prior state is still known in memory; never adopt edited data.
        _atomic_data(path, previous)
        raise ValueError('Parent ledger bytes changed')
    try:
        atomic_verified(path, state)
    except (Exception, KeyboardInterrupt):
        # os.replace may already have happened before fsync or readback failed.
        # Roll back while storage is available. If rollback fails, do not continue.
        if previous is not None:
            try:
                _atomic_data(path, previous)
                if path.read_bytes() != previous:
                    raise OSError('Parent ledger rollback readback failed')
            except Exception as exc:
                raise OSError('Parent ledger durability unverified; no retry or budget release') from exc
        raise
    return canonical(state).encode() + b'\n'


def _timing_path(path, output, root):
    path = Path(path).expanduser().resolve()
    output, root = Path(output).expanduser().resolve(), Path(root).resolve()
    if (path.exists() or not path.parent.is_dir() or path == output or path.is_relative_to(output)
            or output.is_relative_to(path) or path.is_relative_to(root)):
        raise ValueError('Timing output must be a fresh file outside the scientific output and Git')
    git = subprocess.run(['git', '-C', str(path.parent), 'rev-parse', '--is-inside-work-tree'],
                         capture_output=True, text=True, check=False)
    if git.returncode == 0:
        raise ValueError('Timing output must be outside Git repositories')
    return path


def run(config, starts, output, *, root, spot_checks, search_bounds=None, checkpoint_interval=1000,
        timing_output=None, timing_level=None, rf_cache_mode='lk'):
    """Freeze once, reserve all Jobs, and execute each at most once in seed→arm order."""
    if timing_level not in (None, 'timed', 'deep') or (timing_level is not None and timing_output is None):
        raise ValueError('timing level requires timing output and must be timed or deep')
    if rf_cache_mode not in ('off', 'lk', 'response', 'both'):
        raise ValueError('Invalid RF cache mode')
    timing_level = timing_level or 'timed'
    timing_path = None if timing_output is None else _timing_path(timing_output, output, root)
    diagnostics = None if timing_path is None else dict(kind='development_timing_v1', status='incomplete',
        plan_sha256=None, source_sha256=None, jobs=[], level=timing_level,
        semantics='Inclusive regions overlap; do not sum. Search RF port_admittance contains node_admittance, '
                  'which contains matrices; cascade is called twice per forward. RF regions exclude Terminal. '
                  'Same-run differences include instrumentation overhead. Missing regions/events were not observed. '
                  'Local run wall is absent when no end event was emitted; residual time is not identified.')
    try:
        result = _run(config, starts, output, root=root, spot_checks=spot_checks, search_bounds=search_bounds,
                      checkpoint_interval=checkpoint_interval, diagnostics=diagnostics, timing_level=timing_level,
                      rf_cache_mode=rf_cache_mode)
        if diagnostics is not None:
            diagnostics['status'] = 'completed'
        return result
    finally:
        if diagnostics is not None:
            try:
                with timing_path.open('x', encoding='utf-8') as f:
                    json.dump(diagnostics, f, sort_keys=True, allow_nan=False)
                    f.write('\n')
            except Exception as exc:
                print(f'Warning: timing output unavailable: {exc}', file=sys.stderr)


def _run(config, starts, output, *, root, spot_checks, search_bounds, checkpoint_interval, diagnostics, timing_level, rf_cache_mode):
    output, root = Path(output).expanduser().resolve(), Path(root).resolve()
    if (not output.is_relative_to(Path(tempfile.gettempdir()).resolve()) or output.is_relative_to(root)
            or output.exists() or not output.parent.is_dir()):
        raise ValueError('Fresh temporary output outside repository required')
    inside_git = subprocess.run(['git', '-C', str(output.parent), 'rev-parse', '--is-inside-work-tree'],
                                capture_output=True, text=True, check=False)
    if inside_git.returncode == 0:
        raise ValueError('Output must be outside Git repositories')
    source = source_identity(root)
    compiled = freeze_run(config, starts, root=root, spot_checks=spot_checks, search_bounds=search_bounds,
                          checkpoint_interval=checkpoint_interval)
    plan = compiled[0]
    data = plan.data
    if diagnostics is not None:
        diagnostics.update(plan_sha256=plan.sha256, source_sha256=sha(source),
                           jobs=[dict(seed=j['seed'], arm=j['arm'], status='not_started', regions={}, steps={})
                                 for j in data['jobs']])
    order = [(a.seed, data['config']['arms'][a.arm_index]['name']) for a in actions(plan)]
    if order != [(j['seed'], j['arm']) for j in data['jobs']]:
        raise ValueError('Frozen Jobs/order mismatch')
    rows = [dict(job_id=f'job-{i:04d}', seed=j['seed'], arm=j['arm'], status='not_started',
                 reservation=j['reservation'], actual=None, released=None, unknown={k: 0 for k in COSTS})
            for i, j in enumerate(data['jobs'], 1)]
    output.mkdir(exist_ok=False)
    sync_directory(output.parent)
    plan_raw = _save_raw(output/'plan.json', data)
    state = dict(kind='development_rf_profile_run_v1', plan_sha256=plan.sha256, plan_raw=plan_raw,
                 source_sha256=sha(source), budget=data['config']['budget'], jobs=rows,
                 status='incomplete', retry_allowed=False,
                 boundary_limit='Changes reverted between Job boundary checks may go undetected.')
    path = output/'run.json'
    previous = _publish(path, state)
    for index, row in enumerate(rows):
        row.update(status='unknown', unknown=row['reservation'])
        previous = _publish(path, state, previous)
        directory = output/row['job_id']
        diagnostic = None if diagnostics is None else diagnostics['jobs'][index]
        timer = None if diagnostic is None else TimerCollector()
        if diagnostic is not None:
            diagnostic['status'] = 'incomplete'
        try:
            receipt = timed_call(timer, 'job', _run_job, compiled, index, source, root, directory,
                                 collector=timer, timing_steps=None if diagnostic is None else diagnostic['steps'],
                                 timing_level=timing_level, rf_cache_mode=rf_cache_mode)
        finally:
            if diagnostic is not None:
                diagnostic['regions'] = timer.snapshot()
        verified = _verify_receipt(directory, receipt, row, state)
        if _bytes_info((output/'plan.json').read_bytes()) != plan_raw:
            raise ValueError('Frozen Plan raw bytes changed')
        row.update(verified, status='completed', raw_path=row['job_id'], unknown={k: 0 for k in COSTS})
        if index == len(rows) - 1:
            state['status'] = 'completed'
        previous = _publish(path, state, previous)
        if diagnostic is not None:
            diagnostic['status'] = 'completed'
    return state

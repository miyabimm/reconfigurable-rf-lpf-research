"""Sequential frozen-start dispatcher. No optimizer, retry policy or RF validator here."""
from copy import deepcopy
import hashlib
import fcntl
import json
import os
from pathlib import Path
import subprocess

from lpf.checkpoint_io import atomic_write_json, canonical_config_hash
from lpf.experiment_manifest import _environment, file_sha256
from .experiment_config import load_plan
from .evaluation_cost import SampleBudgetCost, EvaluationCost
from .staged_optimization import run_c1_staged, scipy_slsqp_stage
from .candidate_records import record_candidate, CandidateRecord, recheck_record, pareto_report
from .synthetic_runner import _read


LIMITATIONS = [
    'Best-found finite coarse/fine grid observations only; no global optimum claim.',
    '17-point, dense1001, independent MNA/power/passivity, continuous/physical validation not_run.',
    'Logical references are shared results, not additional physical trials.',
    'Candidate promotion blocked; retain raw until explicit audited Git preservation.']


def _git(root, *args):
    return subprocess.check_output(['git', *args], cwd=root)


def _gate(root, experiment_id, loaded, *, resuming):
    """G0/G1 remote byte readback, same source/environment, existing storage audit."""
    from scripts.run_phase2_shared import _complete_checkout, _fresh_main, exp_preflight, ROOT
    from scripts.experiment_id_registry import is_reserved_on_main
    from scripts.audit_new_experiment_storage import find_run, validate_run
    _complete_checkout(root)
    main = _fresh_main(root)
    row = is_reserved_on_main(root, experiment_id)
    run = find_run(root, experiment_id)
    relative = run.relative_to(root).as_posix()
    # origin/main is freshly verified against remote, so this is actual remote
    # planned evidence, not a caller-provided "readback passed" flag.
    originals = {}
    for name in ('manifest.json', 'storage_record.json'):
        raw = _git(root, 'show', f'origin/main:{relative}/{name}')
        originals[name] = json.loads(raw)
        if not resuming and (run / name).read_bytes() != raw:
            raise ValueError('G1 local/remote byte mismatch')
    manifest, storage = originals['manifest.json'], originals['storage_record.json']
    config = loaded['config']
    if (manifest['execution']['status'] != 'planned' or storage['stage'] != 'planned' or
            manifest['objective'] != config['objective'] or
            manifest['search_scope'].get('input_source') != loaded['input_source'] or
            manifest['search_scope'].get('input_source_sha256') != loaded['input_source_sha256'] or
            manifest['constraints']['constraint_id'] != config['rf']['id'] or
            manifest['constraints']['effective_constraint_sha256'] != config['rf']['effective_sha256'] or
            manifest['environment'] != _environment() or manifest['random_seed'] != config['seeds'][0] or
            storage['selection']['top_k'] != config['selection']['top_k_per_method'] or
            storage['selection']['retain'] != ['pareto']):
        raise ValueError('G1 frozen plan/RF/environment/selection mismatch')
    source = manifest['code']['execution_sha']
    paths = ('src', 'scripts', 'project', 'rf', 'pyproject.toml', 'uv.lock')
    if (manifest['code']['working_tree_dirty'] or
            subprocess.run(['git', 'merge-base', '--is-ancestor', source, 'HEAD'], cwd=root).returncode or
            _git(root, 'diff', '--name-only', source, 'HEAD', '--', *paths).strip() or
            _git(root, 'diff', 'HEAD', '--', *paths).strip() or
            _git(root, 'ls-files', '--others', '--exclude-standard', '--', *paths).strip()):
        raise ValueError('Source/input provenance mismatch')
    names = _git(root, 'ls-files', '-z', '--', *paths).split(b'\0')[:-1]
    if names != _git(ROOT, 'ls-files', '-z', '--', *paths).split(b'\0')[:-1] or any(
            file_sha256(root / n.decode()) != file_sha256(ROOT / n.decode()) for n in names):
        raise ValueError('Executing checkout differs from G1 source')
    local_storage = _read(run / 'storage_record.json')
    if local_storage['stage'] == 'complete':
        raise ValueError('Finalized evidence is immutable; use storage-audit')
    local = _read(run / 'manifest.json')
    for key in ('search_scope', 'code', 'environment', 'constraints', 'bands_sha256', 'random_seed'):
        if local[key] != manifest[key]:
            raise ValueError('Local G1 identity changed: ' + key)
    from lpf.constraint_versions import rf_input_file
    policy = loaded['circuit'].resolved_policy
    if file_sha256(rf_input_file(root, policy['bands_file'])) != manifest['bands_sha256']:
        raise ValueError('Bands fingerprint mismatch')
    for role in ('input_parasitic', 'output_parasitic'):
        spec = policy['external_port_parasitics'][role]
        if file_sha256(rf_input_file(root, spec['path'])) != spec['sha256']:
            raise ValueError('S2P fingerprint mismatch')
    if not resuming:
        exp_preflight(root, experiment_id, owner=row['owner'], request_id=row['request_id'],
            policy_id=config['rf']['id'], policy_sha256=config['rf']['effective_sha256'],
            source_sha=source, bands_sha256=manifest['bands_sha256'],
            input_sha256=loaded['input_source_sha256'], allow_trial=True)
    else:
        validate_run(root, experiment_id, mode='audit', main_ref='origin/main')
    return dict(run=run, manifest=manifest, storage=storage, source_sha=source,
                g1_sha256=canonical_config_hash(originals), main_sha=main)


def phase_ids(loaded, phase):
    if phase not in ('pilot', 'remaining'):
        raise ValueError('Unknown phase')
    pilot = {r['actual_start_id'] for r in loaded['logical']
             if r['method'] == 'common' or r['seed'] in loaded['config']['pilot_seeds']}
    return [key for key in loaded['actual'] if (key in pilot) == (phase == 'pilot')]


def _save(path, state):
    atomic_write_json(path, dict(body=state, sha256=canonical_config_hash(state)))


def _candidate(circuit, key, staged, provenance, cost_meter):
    if staged['numerical_state'] in ('budget_exhausted', 'failed'):
        return None  # Full stages remain diagnostics; do not forge a C2 success.
    vector = staged['stage_calls'][-1]['output_vector'][:-1]
    return record_candidate(key, circuit, vector, staged_record=staged,
                            source_provenance=provenance, cost_meter=cost_meter).as_dict()


def _load_g1_plan(root, config_path, experiment_id):
    """Read portable executable inputs from G1, never from ignored preparation.

    This is a static load only. _gate must still verify the exact remote G1
    bytes, source/environment and reservation before any execution or no-op.
    """
    from scripts.audit_new_experiment_storage import find_run
    manifest = _read(find_run(root, experiment_id) / 'manifest.json')
    scope = manifest['search_scope']
    frozen = scope['input_source']
    if canonical_config_hash(frozen) != scope['input_source_sha256']:
        raise ValueError('G1 input checksum mismatch')
    return load_plan(root, config_path, frozen_input=frozen)


def run_plan(root, config_path, experiment_id, phase, *, optimize_stage=scipy_slsqp_stage):
    """Explicit G0/G1-gated run; mock injection is only for isolated tests.

    Completed starts alone are skipped. Unknown outcomes, STOP, changed evidence
    or failed atomic writes STOP the entire dispatch without clearing markers.
    No automatic retry, new seeds, dense checks, commits, push or raw deletion.
    """
    if optimize_stage is scipy_slsqp_stage and any(os.environ.get(k) != '1'
            for k in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS')):
        raise ValueError('Explicit BLAS/OMP/MKL thread settings of 1 required')
    root = Path(root).resolve()
    loaded = _load_g1_plan(root, config_path, experiment_id)
    raw = root / 'results' / experiment_id / 'run.json'
    gate = _gate(root, experiment_id, loaded, resuming=raw.exists())
    # WSL/Linux execution: reject concurrent invocations of the same EXP.
    # Kernel releases the lock on a kill; the durable marker still blocks retry.
    lock_path = root / 'results' / (experiment_id + '.lock')
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ValueError('Another dispatcher holds this EXP lock') from exc
        return _dispatch_loaded(root, config_path, experiment_id, phase, optimize_stage, loaded, gate, raw)


def _dispatch_loaded(root, config_path, experiment_id, phase, optimize_stage, loaded, gate, raw):
    from scripts.run_phase2_one_start import _optimizer_provenance
    if subprocess.run(['git', 'check-ignore', '-q', '--', str(raw.relative_to(root))], cwd=root).returncode:
        raise ValueError('Raw results must be ignored')
    provenance = dict(kind='recorded', **_optimizer_provenance(optimize_stage),
        git_head=gate['source_sha'], dirty_patch_sha256=hashlib.sha256(b'').hexdigest(),
        input_source_sha256=loaded['input_source_sha256'],
        thread_environment={k: os.environ.get(k) for k in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS')})
    identity = dict(experiment_id=experiment_id, input_source_sha256=loaded['input_source_sha256'],
                    g1_sha256=gate['g1_sha256'], source_provenance=provenance)
    recheck_cost = EvaluationCost()
    if raw.exists():
        saved = _read(raw)
        if canonical_config_hash(saved['body']) != saved['sha256']:
            raise ValueError('Raw snapshot checksum mismatch')
        state = saved['body']
        if state['identity'] != identity or state['input_source'] != loaded['input_source']:
            raise ValueError('Raw/G1 identity mismatch')
        if state['in_progress'] is not None:
            raise ValueError('Unknown in-progress outcome; automatic retry prohibited')
        for name, value in state['recheck_cost'].items():
            setattr(recheck_cost, name, value)
        for key, result in state['completed'].items():
            if key not in loaded['actual'] or result['seed_record'] != loaded['actual'][key]['seed_record']:
                raise ValueError('Saved start binding mismatch')
            staged = result['staged_record']
            if (staged['seed'] != result['seed_record'] or
                    staged['source_provenance']['value'] != provenance or
                    staged['definition_sha256'] != loaded['config']['definition_sha256'] or
                    staged['policy_fingerprint'] != loaded['circuit'].policy_fingerprint or
                    staged['evaluation_cost']['frequency_samples_requested'] > loaded['config']['samples_per_start'] or
                    staged['numerical_state'] not in ('converged', 'not_converged', 'budget_exhausted', 'failed')):
                raise ValueError('Unclassified or mismatched saved outcome')
            if result['candidate'] is not None:
                # Loading is structural only. RF replay is planned packaging
                # work, not a side effect of reading a completed phase.
                candidate = CandidateRecord.from_json(json.dumps(result['candidate'])).as_dict()
                if (candidate['staged_record'] != staged or candidate['seed_record'] != result['seed_record'] or
                        candidate['candidate_id'] != key or candidate['source_provenance']['value'] != provenance):
                    raise ValueError('Saved candidate/start binding mismatch')
    else:
        if raw.parent.exists():
            raise ValueError('Unclassified existing raw directory; investigate manually')
        raw.parent.mkdir(parents=True)
        state = dict(identity=identity, input_source=loaded['input_source'], completed={},
                     in_progress=None, staged_record=None, pilot_complete=False, completed_phases=[],
                     validation=dict(intermediate_17='not_run', dense_1001='not_run',
                         independent_mna='not_run', power_balance='not_run', spd_independent='not_run'),
                     preservation='preservation_incomplete', recheck_cost=recheck_cost.snapshot())
        _save(raw, state)
    ids = phase_ids(loaded, phase)
    if phase == 'remaining' and (not state['pilot_complete'] or 'pilot' not in state['completed_phases'] or
            not set(phase_ids(loaded, 'pilot')) <= set(state['completed'])):
        raise ValueError('Pilot must be complete and preserved before remaining')
    if phase in state['completed_phases']:
        if not set(ids) <= set(state['completed']):
            raise ValueError('Completed phase missing confirmed results')
        # G1/raw/storage consistency has been checked without any RF calls.
        # Do not repackage, charge rechecks, or rewrite evidence on repeated run.
        return state
    circuit = loaded['circuit']
    for key in ids:
        if key in state['completed']:
            continue
        if (raw.parent / 'STOP').exists():
            raise ValueError('STOP present; raw retained')
        # Recheck source/config and evidence before each physical start.
        current = _load_g1_plan(root, config_path, experiment_id)
        if current['input_source'] != loaded['input_source']:
            raise ValueError('Plan changed during execution')
        _gate(root, experiment_id, loaded, resuming=bool(state['completed']))
        start = loaded['actual'][key]
        state.update(in_progress=key, staged_record=None)
        _save(raw, state)
        def sink(record):
            state['staged_record'] = record
            _save(raw, state)
            if (raw.parent / 'STOP').exists():
                raise ValueError('STOP at stage boundary; preserve in-progress marker')
        staged = run_c1_staged(circuit, start['seed_record'],
            **loaded['config']['grids'], optimize_stage=optimize_stage,
            cost_meter=SampleBudgetCost(loaded['config']['samples_per_start']),
            source_provenance=provenance, record_sink=sink)
        if (staged.get('exception') or {}).get('type') in ('OSError', 'MemoryError', 'TimeoutError'):
            raise RuntimeError('System failure during stage; retain unknown in-progress evidence')
        # Provenance/storage failures are global STOP, not numerical failures.
        _gate(root, experiment_id, loaded, resuming=True)
        candidate = _candidate(circuit, key, staged, provenance, recheck_cost)
        state['recheck_cost'] = recheck_cost.snapshot()
        state['completed'][key] = dict(seed_record=start['seed_record'],
            staged_record=staged, candidate=candidate)
        state.update(in_progress=None, staged_record=None)
        _save(raw, state)
    if phase == 'pilot':
        state['pilot_complete'] = True
        _save(raw, state)
    _package(root, gate, loaded, state, recheck_cost)
    state['recheck_cost'] = recheck_cost.snapshot()
    state['preservation'] = 'awaiting_git_readback'
    state['completed_phases'].append(phase)
    _save(raw, state)
    return state


def _curated_result(result):
    staged = result['staged_record']
    # Keep complete vectors/status/recovery and costs, not bulky per-sample
    # residuals or redundant candidate copies. Raw is retained, never deleted.
    keys = ('call_index', 'attempt_index', 'stage', 'maxiter', 'input_vector',
            'input_vector_sha256', 'warm_start_source', 'output_vector', 'status',
            'exception', 'elapsed_seconds', 'evaluation_cost', 'exit_cause')
    return dict(seed_record=result['seed_record'], numerical_state=staged['numerical_state'],
        exception=staged['exception'], evaluation_cost=staged['evaluation_cost'],
        controller=staged['controller'],
        stage_calls=[{k: call[k] for k in keys if k in call} for call in staged['stage_calls']])


def _package(root, gate, loaded, state, recheck_cost):
    """Existing single-EXP manifest/storage/checkpoints; no parallel authority."""
    from scripts.run_phase2_one_start import candidate_checkpoint
    from scripts.audit_new_experiment_storage import validate_run, validate_summary
    run = gate['run']
    manifest, storage = deepcopy(gate['manifest']), deepcopy(gate['storage'])
    results = state['completed']
    records = [CandidateRecord.from_json(json.dumps(r['candidate']))
               for r in results.values() if r['candidate'] is not None]
    report = pareto_report([recheck_record(r, cost_meter=recheck_cost) for r in records])
    selected = [r['candidate_id'] for r in report['candidates'] if r['pareto_within_group'] is True]
    counts = dict(planned=len(loaded['actual']), attempted=len(results), converged=0,
                  nonconverged=0, failed=0, not_started=len(loaded['actual']) - len(results))
    for result in results.values():
        status = result['staged_record']['numerical_state']
        counts[dict(converged='converged', not_converged='nonconverged', failed='failed',
                    budget_exhausted='failed')[status]] += 1
    costs = [r['staged_record']['evaluation_cost'] for r in results.values()]
    physical = {k: sum(c[k] for c in costs) for k in costs[0]} if costs else {}
    summary = dict(experiment_id=state['identity']['experiment_id'], attempts=counts,
        selected_candidate_count=len(selected), best_found=selected, limitations=LIMITATIONS,
        input_source_sha256=loaded['input_source_sha256'], logical_starts=loaded['logical'],
        comparison_groups=[dict(seed=seed, method=method,
            logical_start_ids=[r['id'] for r in loaded['logical']
                               if r['method'] == 'common' or (r['seed'] == seed and r['method'] == method)],
            actual_result_refs=list(dict.fromkeys(r['actual_start_id'] for r in loaded['logical']
                               if r['method'] == 'common' or (r['seed'] == seed and r['method'] == method))))
            for seed in loaded['config']['seeds'] for method in loaded['config']['methods']],
        actual_results={key: _curated_result(value) for key, value in results.items()},
        pareto=report, validation=state['validation'],
        costs=dict(physical_optimization=physical, screen=loaded['input_source']['executable_plan']['screen_cost'],
                   screen_by_group=loaded['input_source']['executable_plan']['screen_by_group'],
                   logical_shared='Reference actual_start_id; never sum duplicated solver results.',
                   recheck=recheck_cost.snapshot()))
    if not selected:
        summary['no_candidate_reason'] = 'No checked finite-grid eligible Pareto candidate.'
    validate_summary(summary, state['identity']['experiment_id'], len(selected))
    def save(path, body):
        atomic_write_json(path, body)
        return dict(path=path.relative_to(root).as_posix(), sha256=file_sha256(path))
    storage['checkpoints'] = [dict(candidate_id=key, selection_reason='pareto',
        **save(run / 'checkpoints' / (key + '.json'), candidate_checkpoint(loaded['circuit'], results[key]['candidate'],
                                                                      cost_meter=recheck_cost)))
        for key in selected]
    # Old selected checkpoints may no longer be Pareto after remaining starts.
    # Never delete evidence: retain them as representative diagnostics instead.
    existing = list((run / 'checkpoints').glob('*.json')) if (run / 'checkpoints').exists() else []
    for path in existing:
        if path.stem not in selected:
            storage['checkpoints'].append(dict(candidate_id=path.stem, selection_reason='other',
                path=path.relative_to(root).as_posix(), sha256=file_sha256(path)))
    summary['selected_candidate_count'] = len(storage['checkpoints'])
    summary['costs']['recheck'] = recheck_cost.snapshot()
    storage['summary'] = save(run / 'run_summary.json', summary)
    manifest['execution'].update(status='running' if counts['not_started'] else 'completed',
                                 elapsed_seconds=sum(r['staged_record']['elapsed_seconds'] for r in results.values()),
                                 evaluation_count=None)
    refs = storage['checkpoints'] + storage['validation_overlays'] + storage.get('supporting_evidence', [])
    manifest['evidence'] = [storage['summary']] + [{k: ref[k] for k in ('path', 'sha256')} for ref in refs]
    manifest['limitations'] = storage['limitations'] = LIMITATIONS
    storage.update(stage='running' if counts['not_started'] else 'preservation_incomplete', git_readback='not_run')
    save(run / 'manifest.json', manifest)
    save(run / 'storage_record.json', storage)
    validate_run(root, state['identity']['experiment_id'], mode='audit')

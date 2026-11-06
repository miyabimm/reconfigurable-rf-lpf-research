"""Explicit post-search packaging through the existing G0/G1 and storage gates.

No optimization or RF evaluation is dispatched here. The selected set must
already be frozen in the post-search journal and its G1 budget predeclared.
Historical/finalized evidence is never accepted or modified. The caller must
use the existing explicit finalize step for Git commit, readback and audit.
"""
from contextlib import contextmanager
from lpf.policy_schema import harmonic_limit_db
from copy import deepcopy
import csv
import fcntl
import hashlib
import io
import os
import re
from pathlib import Path
import subprocess
import tempfile

from lpf.checkpoint_io import atomic_write_json, canonical_config_hash
from lpf.experiment_manifest import INDEX_FIELDS
from .experiment_run import _gate, _load_g1_plan, LIMITATIONS as SEARCH_LIMITATIONS
from .limited_candidate_evidence import _identity
from .post_search_evidence import verify_candidate_evidence
from .post_search_journal import PostSearchJournal, aggregate_selected, candidate_binding
from .problem_seed import definition_fingerprint, vector_fingerprint
from .sampled_epigraph import SEARCH_GUARD_DB
from .synthetic_runner import _read


@contextmanager
def _experiment_lock(root, experiment_id):
    if not isinstance(experiment_id, str) or re.fullmatch(r'EXP-[0-9]{3}', experiment_id) is None:
        raise ValueError('Invalid experiment ID')
    path = root / 'results' / (experiment_id + '.lock')
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ValueError('Another experiment operation holds the lock') from exc
        yield


def _digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _index_update(path, experiment_id, g1_manifest, current_manifest, validation, manifest_path):
    original = path.read_text(encoding='utf-8')
    reader = csv.DictReader(io.StringIO(original, newline=''))
    if tuple(reader.fieldnames or ()) != INDEX_FIELDS:
        raise ValueError('Experiment index schema mismatch')
    rows = list(reader)
    matches = [r for r in rows if r['experiment_id'] == experiment_id]
    if len(matches) != 1:
        raise ValueError('Experiment index target missing or duplicated')
    row = matches[0]
    for column, value in (('constraint_id', g1_manifest['constraints']['constraint_id']),
                          ('effective_constraint_sha256', g1_manifest['constraints']['effective_constraint_sha256']),
                          ('objective', g1_manifest['objective']),
                          ('manifest', manifest_path),
                          ('execution_status', g1_manifest['execution']['status']),
                          ('numerical_validation', g1_manifest['validation']['numerical']),
                          ('independent_validation', g1_manifest['validation']['independent'])):
        if row[column] != value:
            raise ValueError('Experiment index differs from frozen G1: ' + column)
    baseline = io.StringIO(newline='')
    writer = csv.DictWriter(baseline, fieldnames=INDEX_FIELDS, lineterminator='\n')
    writer.writeheader()
    writer.writerows(rows)
    if baseline.getvalue() != original:
        raise ValueError('Experiment index is not in canonical form')
    row['execution_status'] = current_manifest['execution']['status']
    row['numerical_validation'] = validation['numerical']
    row['independent_validation'] = validation['independent']
    output = io.StringIO(newline='')
    writer = csv.DictWriter(output, fieldnames=INDEX_FIELDS, lineterminator='\n')
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue()


def _write_text(path, text):
    fd, temp = tempfile.mkstemp(dir=path.parent, prefix='.' + path.name + '.', suffix='.tmp')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8', newline='') as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def _check_plan(plan, bindings, config):
    fields = {'schema', 'selection_rule', 'search_guard', 'max_selected', 'separate17', 'dense1001',
              'independent_forward84', 'independent_mna84'}
    if (not isinstance(plan, dict) or set(plan) != fields or plan['schema'] != 'post-search-g1-1' or
            plan['search_guard'] is not True or
            not isinstance(plan['selection_rule'], str) or not plan['selection_rule'].strip() or
            any(type(plan[k]) is not int or plan[k] < 0 for k in fields - {'schema', 'selection_rule', 'search_guard'})):
        raise ValueError('G1 must predeclare post-search selection and sample budgets')
    if (len(bindings) > plan['max_selected'] or
            sum(b['budgets']['separate17'] for b in bindings) > plan['separate17'] or
            sum(b['budgets']['dense1001'] for b in bindings) > plan['dense1001'] or
            sum(b['budgets']['independent_forward84'] for b in bindings) > plan['independent_forward84'] or
            sum(b['budgets']['independent_mna84'] for b in bindings) > plan['independent_mna84'] or
            plan['separate17'] > config['budgets']['intermediate_samples'] or
            plan['dense1001'] > config['budgets']['dense_samples']):
        raise ValueError('Frozen selection exceeds G1 post-search budget')


def _optimization_state(raw, loaded):
    envelope = _read(raw / 'run.json')
    if (set(envelope) != {'body', 'sha256'} or
            canonical_config_hash(envelope['body']) != envelope['sha256']):
        raise ValueError('Optimization raw checksum mismatch')
    state = envelope['body']
    if (state['in_progress'] is not None or set(state['completed']) != set(loaded['actual']) or
            state['identity']['input_source_sha256'] != loaded['input_source_sha256'] or
            state['input_source'] != loaded['input_source']):
        raise ValueError('Optimization incomplete or G1 input mismatch')
    return state


def _check_bindings(bindings, optimization, loaded, plan, source_sha):
    _check_plan(plan, bindings, loaded['config'])
    source = optimization['identity']['source_provenance']
    if (source.get('git_head') != source_sha or
            source.get('input_source_sha256') != loaded['input_source_sha256']):
        raise ValueError('Optimization source differs from G1')
    for b in bindings:
        result = optimization['completed'].get(b['candidate_id'])
        if (result is None or canonical_config_hash(result['staged_record']) != b['optimization_sha256'] or
                canonical_config_hash(result.get('frequency_exchange')) != b['exchange_sha256'] or
                canonical_config_hash(optimization['identity']['source_provenance']) != b['source_sha256'] or
                result['staged_record'].get('source_provenance') != {
                    'state': 'provided', 'value': optimization['identity']['source_provenance']} or
                canonical_config_hash(result['staged_record'].get('seed')) !=
                    canonical_config_hash(loaded['actual'][b['candidate_id']]['seed_record']) or
                vector_fingerprint(b['vector']) != b['vector_sha256'] or
                b['policy_id'] != loaded['circuit'].policy_id or
                b['policy_sha256'] != loaded['circuit'].policy_fingerprint or
                b['definition_sha256'] != definition_fingerprint(loaded['circuit'].definition)):
            raise ValueError('Selection differs from saved optimization result')
        staged = result['staged_record']
        if loaded['config'].get('schema_version') == 4:
            continuation = result.get('continuation', {})
            final = continuation.get('last_valid_vector')
            anchor = result.get('validation_anchor', {})
            if (b.get('validate_terminal_anchor') is not True or
                    b.get('continuation_sha256') != canonical_config_hash(continuation) or
                    not isinstance(final, list) or len(final) != loaded['circuit'].schema.vector_length + 1 or
                    vector_fingerprint(final[:-1]) != b['vector_sha256'] or
                    anchor.get('vector_sha256') != b['vector_sha256'] or
                    continuation.get('method') != loaded['actual'][b['candidate_id']]['method']):
                raise ValueError('Validation vector differs from continuation last valid anchor')
            # An intermediate or exhausted anchor is explicitly not a final
            # guarded-search success. Its validation remains a separate record.
            continue
        if staged.get('numerical_state') in ('converged', 'not_converged'):
            mandatory = float(harmonic_limit_db(loaded['circuit'].resolved_policy))
            if staged.get('search_guard') != {'guard_db': SEARCH_GUARD_DB,
                    'mandatory_stop_db': mandatory, 'search_stop_db': mandatory + SEARCH_GUARD_DB}:
                raise ValueError('Selected optimization lacks frozen search guard')
            if (not staged.get('stage_calls') or not staged['stage_calls'][-1].get('output_vector') or
                    vector_fingerprint(staged['stage_calls'][-1]['output_vector'][:-1]) != b['vector_sha256']):
                raise ValueError('Selection vector differs from final optimization output')


def _ready_and_checkpoints(root, gate, bindings):
    run = gate['run']
    manifest, storage = _read(run / 'manifest.json'), _read(run / 'storage_record.json')
    if (storage['stage'] != 'preservation_incomplete' or storage['git_readback'] != 'not_run' or
            manifest['execution']['status'] not in ('completed', 'failed') or
            manifest['objective'] != 'full_lpf' or
            manifest['validation']['numerical'] != 'not_run' or
            manifest['validation']['independent'] != 'not_run' or storage['validation_overlays']):
        raise ValueError('Unfinalized, unvalidated completed run required')
    for key in ('search_scope', 'code', 'environment', 'constraints', 'bands_sha256', 'random_seed'):
        if manifest[key] != gate['manifest'][key]:
            raise ValueError('Frozen G1 manifest differs: ' + key)
    checkpoints = {c['candidate_id']: c for c in storage['checkpoints']}
    if len(checkpoints) != len(storage['checkpoints']):
        raise ValueError('Duplicate checkpoint ID')
    for b in bindings:
        item = checkpoints.get(b['candidate_id'])
        if item is None:
            raise ValueError('Selected candidate needs an existing checked checkpoint')
        path = root / item['path']
        if not path.resolve().is_relative_to(run.resolve()) or _digest(path) != item['sha256']:
            raise ValueError('Selected checkpoint path or SHA mismatch')
        record = _read(path).get('candidate_record', {})
        if (record.get('vector_sha256') != b['vector_sha256'] or
                record.get('policy_sha256') != b['policy_sha256'] or
                record.get('definition_sha256') != b['definition_sha256']):
            raise ValueError('Selected checkpoint candidate binding mismatch')
    return manifest, storage


def prepare_post_search(root, config_path, experiment_id, selections):
    """G0/G1-check and freeze an explicit candidate set before any validation."""
    root = Path(root).resolve()
    with _experiment_lock(root, experiment_id):
        return _prepare_post_search(root, config_path, experiment_id, selections)


def _prepare_post_search(root, config_path, experiment_id, selections):
    loaded = _load_g1_plan(root, config_path, experiment_id)
    gate = _gate(root, experiment_id, loaded, resuming=True)
    raw = root / 'results' / experiment_id
    if not isinstance(selections, list):
        raise ValueError('Explicit selection list required')
    if loaded['config']['schema_version'] == 4:
        if (len(selections) != 8 or {row.get('candidate_id') for row in selections if isinstance(row, dict)} != set(loaded['actual']) or
                any(not isinstance(row, dict) or row.get('run_dense') is not True or
                    row.get('run_independent') is not True or row.get('budgets') != {
                        'separate17': 476, 'dense1001': 28028,
                        'independent_forward84': 84, 'independent_mna84': 84} for row in selections)):
            raise ValueError('Continuation validation must freeze all eight anchors and full gate budgets')
    if subprocess.run(['git', 'check-ignore', '-q', '--', str((raw / 'post-search').relative_to(root))], cwd=root).returncode:
        raise ValueError('Post-search raw journal must be Git ignored')
    optimization = _optimization_state(raw, loaded)
    source = optimization['identity']['source_provenance']
    bindings = []
    for row in selections:
        if not isinstance(row, dict) or set(row) != {'candidate_id', 'vector', 'budgets', 'run_dense', 'run_independent'}:
            raise ValueError('Incomplete explicit candidate selection')
        result = optimization['completed'].get(row['candidate_id'])
        if result is None:
            raise ValueError('Selected candidate has no completed optimization record')
        identity = _identity(loaded['circuit'], row['vector'])
        bindings.append(candidate_binding(row['candidate_id'], loaded['circuit'], row['vector'],
            optimization_record=result['staged_record'], exchange_record=result.get('frequency_exchange'),
            source_provenance=source, validation_identity=identity, budgets=row['budgets'],
            run_dense=row['run_dense'], run_independent=row['run_independent'],
            validate_terminal_anchor=loaded['config']['schema_version'] == 4,
            continuation_record=result.get('continuation') if loaded['config']['schema_version'] == 4 else None))
    _check_bindings(bindings, optimization, loaded, gate['manifest']['search_scope'].get('post_search_validation'),
                    gate['manifest']['code']['execution_sha'])
    _ready_and_checkpoints(root, gate, bindings)
    return PostSearchJournal.create(raw / 'post-search', bindings)


def run_post_search_candidate(root, config_path, experiment_id, candidate_id, *, vector,
                              budgets, run_dense, run_independent):
    """Run one frozen target after rechecking G0/G1, source, raw and budgets."""
    root = Path(root).resolve()
    with _experiment_lock(root, experiment_id):
        return _run_post_search_candidate(root, config_path, experiment_id, candidate_id,
            vector=vector, budgets=budgets, run_dense=run_dense, run_independent=run_independent)


def _run_post_search_candidate(root, config_path, experiment_id, candidate_id, *, vector,
                               budgets, run_dense, run_independent):
    loaded = _load_g1_plan(root, config_path, experiment_id)
    gate = _gate(root, experiment_id, loaded, resuming=True)
    raw = root / 'results' / experiment_id
    journal = PostSearchJournal(raw / 'post-search')
    optimization = _optimization_state(raw, loaded)
    _check_bindings(journal.plan['targets'], optimization, loaded,
                    gate['manifest']['search_scope'].get('post_search_validation'),
                    gate['manifest']['code']['execution_sha'])
    _ready_and_checkpoints(root, gate, journal.plan['targets'])
    result = optimization['completed'].get(candidate_id)
    if result is None:
        raise ValueError('Candidate missing from optimization raw')
    return journal.run_candidate(candidate_id, loaded['circuit'], vector,
        optimization_record=result['staged_record'], exchange_record=result.get('frequency_exchange'),
        source_provenance=optimization['identity']['source_provenance'],
        validation_identity=_identity(loaded['circuit'], vector), budgets=budgets,
        run_dense=run_dense, run_independent=run_independent,
        validate_terminal_anchor=loaded['config']['schema_version'] == 4,
        continuation_record=result.get('continuation') if loaded['config']['schema_version'] == 4 else None)


def package_post_search(root, config_path, experiment_id):
    """Package one already-run journal; never start RF or change finalized data.

    Strict main/G1/source/storage checks are inherited from the existing shared
    driver. The G1 manifest must contain search_scope.post_search_validation
    (post-search-g1-1) and adequate explicit budgets. This separate opt-in does
    not change the meaning or replay of the existing frozen configurations.
    """
    root = Path(root).resolve()
    with _experiment_lock(root, experiment_id):
        return _package_post_search(root, config_path, experiment_id)


def _package_post_search(root, config_path, experiment_id):
    from scripts.audit_new_experiment_storage import validate_run
    loaded = _load_g1_plan(root, config_path, experiment_id)
    gate = _gate(root, experiment_id, loaded, resuming=True)
    raw = root / 'results' / experiment_id
    journal_path = raw / 'post-search'
    if subprocess.run(['git', 'check-ignore', '-q', '--', str(journal_path.relative_to(root))], cwd=root).returncode:
        raise ValueError('Post-search raw journal must be Git ignored')
    with (journal_path / 'run.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ValueError('Post-search journal is in use') from exc
        journal = PostSearchJournal(journal_path)
        return _package(root, experiment_id, loaded, gate, raw, journal, validate_run)


def _package(root, experiment_id, loaded, gate, raw, journal, validate_run):
    run = gate['run']
    bindings = journal.plan['targets']
    manifest, storage = _ready_and_checkpoints(root, gate, bindings)
    g1 = gate['manifest']
    optimization = _optimization_state(raw, loaded)
    _check_bindings(bindings, optimization, loaded, g1['search_scope'].get('post_search_validation'),
                    g1['code']['execution_sha'])
    summary_path = root / storage['summary']['path']
    if _digest(summary_path) != storage['summary']['sha256']:
        raise ValueError('Run summary changed')
    summary = _read(summary_path)
    if 'post_search' in summary:
        raise ValueError('Post-search evidence already packaged')
    index = root / 'data/experiment_index.csv'
    if subprocess.run(['git', 'diff', '--quiet', 'HEAD', '--', str(index.relative_to(root))], cwd=root).returncode:
        raise ValueError('Experiment index has uncommitted changes')
    completed = {}
    for b in bindings:
        entry = journal.state['candidates'][b['candidate_id']]
        if entry['state'] == 'completed':
            verify_candidate_evidence(loaded['circuit'], b, entry['report'])
            completed[b['candidate_id']] = entry['report']
    statuses = aggregate_selected(list(journal.targets), completed)
    index_text = _index_update(index, experiment_id, g1, manifest, statuses['validation'],
                               (run / 'manifest.json').relative_to(root).as_posix())
    selection_path = run / 'validation' / 'post-search-selection.json'
    overlay_paths = {b['candidate_id']: run / 'validation' / ('post-search-' + b['candidate_id'] + '.json') for b in bindings}
    if selection_path.exists() or any(p.exists() for p in overlay_paths.values()):
        raise ValueError('Post-search evidence already exists; investigate manually')
    marker = journal.directory / 'packaging.json'
    if marker.exists():
        raise ValueError('Prior packaging marker exists; investigate manually')
    marker_state = {'state': 'running', 'selection_sha256': journal.state['selection_sha256'],
                    'preservation': 'preservation_incomplete'}
    atomic_write_json(marker, marker_state, compact=True)
    def save(path, body):
        atomic_write_json(path, body, compact=True)
        if canonical_config_hash(_read(path)) != canonical_config_hash(body):
            raise ValueError('Post-search evidence readback mismatch')
        return {'path': path.relative_to(root).as_posix(), 'sha256': _digest(path)}
    selection_ref = save(selection_path, journal.plan)
    overlays = [dict(method='other', status='not_run', **selection_ref)]
    refs = {}
    for b in bindings:
        candidate_id = b['candidate_id']
        entry = journal.state['candidates'][candidate_id]
        report = deepcopy(entry.get('report'))
        # Optimization records already live in the raw run and curated summary;
        # retain their bound hashes rather than duplicate them in every overlay.
        if isinstance(report, dict):
            report.pop('optimization_record', None)
            report.pop('exchange_record', None)
        body = {'schema': 'post-search-overlay-1', 'candidate_id': candidate_id,
                'selection_sha256': journal.state['selection_sha256'], 'binding': b,
                'execution_state': entry['state'], 'validation': statuses['candidates'][candidate_id],
                'report': report, 'finite_grid_only': True, 'continuous_band_proven': False}
        ref = save(overlay_paths[candidate_id], body)
        row = statuses['candidates'][candidate_id]
        status = ('failed' if 'failed' in row.values() else
                  'passed' if all(x == 'passed' for x in row.values()) else 'not_run')
        overlays.append(dict(method='other', status=status, **ref))
        refs[candidate_id] = ref
    summary['post_search'] = {'selection': selection_ref, 'selection_sha256': journal.state['selection_sha256'],
        'candidates': statuses['candidates'], 'overlays': refs,
        'execution_state': 'incomplete' if journal.state['in_progress'] is not None or
                            any(v['state'] != 'completed' for v in journal.state['candidates'].values()) else 'complete',
        'validation': statuses['validation'], 'git_readback': 'see storage_record.git_readback'}
    summary.setdefault('validation', {}).update(
        intermediate_17='see_candidate_overlays', dense_1001='see_candidate_overlays',
        independent_mna='see_candidate_overlays', power_balance='see_candidate_overlays',
        spd_independent='see_candidate_overlays', **statuses['validation'])
    limitation = 'Finite sampled grids only; continuous frequency and physical implementation are not verified.'
    for doc in (summary, manifest, storage):
        doc['limitations'] = [x for x in doc.get('limitations', []) if x != SEARCH_LIMITATIONS[1]]
        if limitation not in doc['limitations']:
            doc['limitations'].append(limitation)
    storage['summary'] = save(summary_path, summary)
    storage['validation_overlays'] = overlays
    manifest['validation'].update(**statuses['validation'],
        analysis_grid={'separate17': '28 intervals x 17; see candidate overlays',
                       'dense1001': '28 intervals x 1001; see candidate overlays'},
        independent_grid='28 intervals x 3; see candidate overlays')
    refs_all = storage['checkpoints'] + overlays + storage.get('supporting_evidence', [])
    manifest['evidence'] = [storage['summary']] + [{k: ref[k] for k in ('path', 'sha256')} for ref in refs_all]
    # Preserve incomplete until the existing explicit finalize + HEAD readback.
    storage['stage'] = 'preservation_incomplete'
    save(run / 'manifest.json', manifest)
    save(run / 'storage_record.json', storage)
    _write_text(index, index_text)
    if index.read_text(encoding='utf-8') != index_text:
        raise ValueError('Experiment index readback mismatch')
    validate_run(root, experiment_id, mode='audit', main_ref='origin/main')
    marker_state.update(state='packaged', preservation='awaiting_git_readback')
    atomic_write_json(marker, marker_state, compact=True)
    return {'validation': statuses, 'selection_sha256': journal.state['selection_sha256'],
            'preservation': 'awaiting_git_readback', 'finalize_required': True}

"""Shared explicit G3/G4 preservation; no optimizer or legacy circuit imports."""
import csv
import hashlib
import io
from pathlib import Path
import subprocess

from lpf.checkpoint_io import atomic_write_json, canonical_config_hash
from lpf.experiment_storage_audit import (
    find_run, read_json, tracked_file, validate_run, audit_all)

LIMITATIONS = [
    'Diagnostic 1/2/3-point separate-interval grids only, not RF scientific PASS.',
    'Independent MNA/power/dense RF/continuous frequency/physical validation not_run.',
    'Candidate promotion blocked; best-found is not a proven global optimum.',
    'Timeout/STOP is cooperative between stages; external termination can leave partial evidence.']


def _candidate_status(report):
    """Only explicit check counterexamples are failures; exceptions are not_run."""
    if not isinstance(report, dict) or report.get('schema') != 'post-search-validation-1':
        return {'numerical': 'not_run', 'independent': 'not_run'}
    component = report.get('component', {}).get('state')
    grid17 = report.get('separate17', {}).get('state')
    dense = report.get('dense1001', {}).get('state')
    independent = report.get('independent84', {}).get('state')
    numerical = ('failed' if 'fail' in (component, grid17, dense) else
                 'passed' if (component, grid17, dense) == ('pass', 'pass', 'pass') else 'not_run')
    # Independent can fail independently of numerical aggregation; a candidate
    # not actually reaching MNA is not an independent FAIL.
    mna = ('failed' if independent == 'fail' else
           'passed' if independent == 'pass' and numerical == 'passed' else 'not_run')
    return {'numerical': numerical, 'independent': mna}


def aggregate_selected(candidate_ids, outcomes):
    """Apply PR #268's fixed-set rule independently to both validation levels.

    ``outcomes`` contains only completed journal records, not all search starts.
    A missing or interrupted target is not_run; unexpected IDs are rejected.
    These are validation summaries, not evidence authentication or RF approval.
    """
    if (not isinstance(candidate_ids, list) or len(candidate_ids) != len(set(candidate_ids)) or
            any(not isinstance(c, str) or not c for c in candidate_ids) or not isinstance(outcomes, dict) or
            set(outcomes) - set(candidate_ids)):
        raise ValueError('Invalid frozen selection or unexpected outcome')
    rows = {c: _candidate_status(outcomes.get(c)) for c in candidate_ids}
    result = {}
    for level in ('numerical', 'independent'):
        states = [rows[c][level] for c in candidate_ids]
        result[level] = ('failed' if 'failed' in states else
                         'passed' if states and all(s == 'passed' for s in states) else 'not_run')
    return {'validation': result, 'candidates': rows}


def _post_search_finalize_guard(root, run, manifest, storage, summary):
    """Bind new opt-in post-search evidence and index before G3 Git commits."""
    if 'campaign' in manifest['search_scope']:
        from lpf.search.preservation import campaign_index_guard
        return campaign_index_guard(root, run, manifest, storage, summary)
    planned = manifest['search_scope'].get('post_search_validation')
    post = summary.get('post_search')
    if planned is None and post is None:
        return None
    if planned is None or not isinstance(post, dict) or post.get('execution_state') != 'complete':
        raise ValueError('Planned post-search evidence is missing or incomplete')
    if any(manifest['validation'][k] != post['validation'][k] for k in ('numerical', 'independent')):
        raise ValueError('Post-search manifest and summary status mismatch')
    receipt = read_json(root / 'results' / manifest['experiment_id'] / 'post-search' / 'packaging.json')
    if (receipt.get('state') != 'packaged' or receipt.get('preservation') != 'awaiting_git_readback' or
            receipt.get('selection_sha256') != post.get('selection_sha256')):
        raise ValueError('Post-search packaging receipt missing or mismatched')
    allowed = [{k: v for k, v in item.items() if k in ('path', 'sha256')}
               for item in storage['validation_overlays']]
    def checked_ref(ref):
        if not isinstance(ref, dict) or ref not in allowed:
            raise ValueError('Post-search evidence not in storage')
        path = (root / ref['path']).resolve()
        if not path.is_relative_to(run.resolve()) or hashlib.sha256(path.read_bytes()).hexdigest() != ref['sha256']:
            raise ValueError('Post-search evidence path or SHA mismatch')
        return read_json(path)
    selection = checked_ref(post['selection'])
    if canonical_config_hash(selection) != post['selection_sha256']:
        raise ValueError('Post-search frozen selection evidence mismatch')
    targets = [item['candidate_id'] for item in selection['targets']]
    if len(targets) != len(set(targets)) or set(targets) != set(post['candidates']) or set(targets) != set(post['overlays']):
        raise ValueError('Post-search candidate set mismatch')
    for candidate_id in targets:
        ref = post['overlays'][candidate_id]
        overlay = checked_ref(ref)
        if (overlay.get('candidate_id') != candidate_id or
                overlay.get('selection_sha256') != post['selection_sha256'] or
                overlay.get('execution_state') != 'completed' or
                overlay.get('validation') != post['candidates'][candidate_id]):
            raise ValueError('Post-search candidate overlay mismatch')
    reports = {key: checked_ref(post['overlays'][key])['report'] for key in targets}
    aggregated = aggregate_selected(targets, reports)
    if aggregated['validation'] != post['validation'] or aggregated['candidates'] != post['candidates']:
        raise ValueError('Post-search aggregate mismatch')
    index = root / 'data/experiment_index.csv'
    from lpf.experiment_manifest import INDEX_FIELDS
    def rows(text):
        reader = csv.DictReader(io.StringIO(text, newline=''))
        if tuple(reader.fieldnames or ()) != INDEX_FIELDS:
            raise ValueError('Experiment index schema mismatch')
        return list(reader)
    current = rows(index.read_text(encoding='utf-8'))
    prior = rows(subprocess.check_output(['git', 'show', 'HEAD:data/experiment_index.csv'], cwd=root, text=True))
    if len(current) != len(prior):
        raise ValueError('Unrelated experiment index change')
    found = 0
    for now, old in zip(current, prior):
        if now['experiment_id'] != manifest['experiment_id']:
            if now != old:
                raise ValueError('Unrelated experiment index change')
            continue
        found += 1
        for key in ('execution_status', 'numerical_validation', 'independent_validation'):
            old[key] = now[key]
        if now != old or (now['execution_status'], now['numerical_validation'], now['independent_validation']) != (
                manifest['execution']['status'], post['validation']['numerical'], post['validation']['independent']):
            raise ValueError('Experiment index and post-search manifest mismatch')
    if found != 1:
        raise ValueError('Post-search experiment index row missing or duplicated')
    return index


def finalize_experiment(root, experiment_id):
    """Shared single-EXP G3/G4 commits -> byte readback -> record commit -> audit.

    Does not push, delete raw or certify RF. A failure leaves raw intact and a
    preservation_incomplete record, including when a Git commit/readback fails.
    Call after inspecting the curated diff; only this EXP directory is staged.
    """
    root = Path(root).resolve()
    run = find_run(root, experiment_id)
    storage = read_json(run / 'storage_record.json')
    if storage['stage'] == 'complete':
        # Rechecking already-preserved evidence must never rewrite it.
        report = validate_run(root, experiment_id, mode='finalize')
        audit_all(root, main_ref='origin/main')
        return report
    if storage['stage'] != 'preservation_incomplete' or storage['git_readback'] != 'not_run':
        raise ValueError('Expected unfinalized preservation state')
    try:
        manifest = read_json(run / 'manifest.json')
        summary = read_json(root / storage['summary']['path'])
        if manifest['execution']['status'] in ('planned', 'running', 'not_run'):
            raise ValueError('Unexecuted run cannot be finalized')
        if summary.get('partial_staged_record') is not None:
            raise ValueError('Unclassified partial evidence cannot be finalized')
        # Never include unrelated staged changes in the evidence commits.
        if subprocess.check_output(['git', 'diff', '--cached', '--name-only'], cwd=root).strip():
            raise ValueError('Index must be empty before explicit preservation commits')
        index = _post_search_finalize_guard(root, run, manifest, storage, summary)
        validate_run(root, experiment_id, mode='audit')
        def commit(message):
            paths = [run.relative_to(root).as_posix()]
            if index is not None:
                paths.append(index.relative_to(root).as_posix())
            subprocess.check_call(['git', 'add', '--', *paths], cwd=root)
            subprocess.check_call(['git', 'commit', '-m', message], cwd=root)
        commit(experiment_id + ': preserve experiment evidence')
        for ref in manifest['evidence'] + [{'path': (run / name).relative_to(root).as_posix()}
                for name in ('manifest.json', 'storage_record.json')] + (
                [{'path': index.relative_to(root).as_posix()}] if index is not None else []):
            tracked_file(root, ref['path'], committed=True)
        storage.update(stage='complete', git_readback='passed')
        atomic_write_json(run / 'storage_record.json', storage)
        commit(experiment_id + ': confirm HEAD byte readback')
        report = validate_run(root, experiment_id, mode='finalize')
        audit_all(root, main_ref='origin/main')
        return report
    except (Exception, KeyboardInterrupt) as exc:
        storage.update(stage='preservation_incomplete', git_readback='not_run')
        storage['limitations'] = LIMITATIONS + ['G3/G4 failed; retain raw: ' + str(exc)]
        atomic_write_json(run / 'storage_record.json', storage)
        raise

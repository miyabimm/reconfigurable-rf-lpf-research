"""Explicit Campaign G3/G4 preservation and read-only G5 eligibility.

No RF evaluation, push, reservation, retry, or deletion. Git preservation is not
scientific validation. The caller inspects the curated diff before finalizing.
"""
import base64
import csv
import hashlib
import io
import json
from pathlib import Path

from lpf.experiment_manifest import INDEX_FIELDS, experiment_index
from lpf.rf_core.model import build_rf_model
from lpf.constraint_versions import load_constraint
from scripts.audit_new_experiment_storage import find_run, validate_checkpoint, validate_run, audit_all
from .storage import atomic, sha
from .gates import _git, campaign_raw_directory, verify_campaign_binding

LIMITATIONS = [
    'Bounded best-found search only; no global optimum or continuous-frequency guarantee.',
    'Finite-grid observations and independent spots only; dense/full-band independent validation not run.',
    'SRF, Q(f), EM, tolerance and physical feasibility not verified.',
    'Preservation completion is not solver convergence or RF certification.',
]


def _read(path):
    return json.loads(path.read_bytes())


def _inventory(directory):
    result = {}
    for path in sorted(directory.rglob('*')):
        if path.is_symlink() or path.resolve() != path:
            raise ValueError('Raw symlink/redirect; retain raw')
        if path.is_file():
            result[path.relative_to(directory).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def _checkpoint(data, vector, candidate_id, root):
    from .proposals import definition_from_data
    policy = load_constraint(data['plan']['config']['rf']['constraint_id'], root=root,
                             allow_trial=data['plan']['config']['rf']['allow_trial'])
    definition = definition_from_data(data['definition'])
    model = build_rf_model(definition, policy)
    from .component_constraints import validate_values
    validate_values(definition, model.schema, vector, policy)
    values, schema, topology = model.decode(vector), model.schema, model.topology
    settings = ('B71', 'B12', 'B28', 'B13+B14', 'B26', 'B8')
    components = [dict(id=f'L{i}', L_nH=v, Q=topology.inductor_q[i],
                       series=definition.inductor_types[i], terminals=list(definition.inductor_tree.edges[i]))
                  for i, v in enumerate(values.inductances_nh)]
    kinds = definition.fixed_c_types + ('IC_VARIABLE_C',)*schema.n_variable + ('IC_FIXED_C',)*schema.n_ic_fixed
    for i, kind in enumerate(kinds):
        components.append(dict(id=f'C{i}', series=kind, Q=topology.capacitor_q[i],
            terminals=list(topology.capacitor_edges[i]),
            C_pf_by_setting={s: values.capacitors_pf_by_setting[j][i] for j, s in enumerate(settings)}))
    payload = dict(candidate_id=candidate_id, topology=data['definition'], components=components,
        couplings=[dict(inductor_indices=list(pair), signed_k=k)
                   for pair, k in zip(topology.coupling_pairs, values.coupling_k)],
        chip_row=[f'L{i}' for i in definition.physical_order],
        fixed_values=dict(inductances_nh=list(values.inductances_nh),
                          capacitors_pf=list(values.capacitors_pf_by_setting[0][:schema.n_fixed]),
                          ic_fixed_capacitors_pf=list(values.capacitors_pf_by_setting[0][schema.n_fixed+schema.n_variable:])),
        ic_variable_C_pf_by_setting={s: list(values.capacitors_pf_by_setting[j][schema.n_fixed:schema.n_fixed+schema.n_variable])
                                    for j, s in enumerate(settings)}, vector=vector,
        definition_sha256=sha(data['definition']), policy_sha256=data['plan']['requirements']['policy_fingerprint'])
    validate_checkpoint(payload, candidate_id)
    return payload


def _index_rows(raw):
    reader = csv.DictReader(io.StringIO(raw.decode(), newline=''))
    if tuple(reader.fieldnames or ()) != INDEX_FIELDS:
        raise ValueError('Experiment index schema mismatch')
    return list(reader)


def _update_index(root, run, manifest):
    path = root/'data/experiment_index.csv'
    rows = _index_rows(path.read_bytes())
    ident = manifest['experiment_id']
    row = _index_rows(experiment_index([(run.relative_to(root).as_posix()+'/manifest.json', manifest)]).encode())[0]
    matches = [i for i, r in enumerate(rows) if r['experiment_id'] == ident]
    if len(matches) > 1:
        raise ValueError('Duplicate Campaign index row')
    if matches:
        rows[matches[0]] = row
    else:
        rows.append(row)
    out = io.StringIO(newline='')
    writer = csv.DictWriter(out, fieldnames=INDEX_FIELDS, lineterminator='\n')
    writer.writeheader(); writer.writerows(rows)
    path.write_text(out.getvalue(), encoding='utf-8')


def campaign_index_guard(root, run, manifest, storage, summary):
    """Called by the existing explicit two-commit finalizer."""
    if summary.get('preservation_kind') != 'campaign_v1' or summary.get('preservation_errors'):
        raise ValueError('Incomplete Campaign preservation; retain raw')
    directory = campaign_raw_directory(root, manifest['experiment_id'])
    if _inventory(directory) != summary['raw_inventory']:
        raise ValueError('Raw changed/unclassified since curation; retain raw')
    path = root/'data/experiment_index.csv'
    prior = _index_rows(_git(root, 'show', 'HEAD:data/experiment_index.csv'))
    current = _index_rows(path.read_bytes())
    ident = manifest['experiment_id']
    if [r for r in prior if r['experiment_id'] != ident] != [r for r in current if r['experiment_id'] != ident]:
        raise ValueError('Unrelated experiment index change')
    expected = _index_rows(experiment_index([(run.relative_to(root).as_posix()+'/manifest.json', manifest)]).encode())
    if [r for r in current if r['experiment_id'] == ident] != expected:
        raise ValueError('Campaign index/manifest mismatch')
    budget = _read(root/'data/phase2_git_storage_budget.json')['thresholds']
    total = sum(p.stat().st_size for p in run.rglob('*') if p.is_file())
    if total > budget['new_experiment_curated_soft_bytes'] and storage.get('size_exception') is None:
        raise ValueError('Campaign curated capacity exceeded; retain raw')
    return path


def curate_campaign(experiment_id, *, root):
    """Close G2 and curate all bounded valid outputs (conservative A/B superset).

    Future proposals are not planned trials. Unknown jobs are not relabeled as
    failed/not-started. Missing evidence is recorded as preservation_incomplete.
    No existing curated results may be overwritten or automatically retried.
    """
    from .campaign import _check_ready_state
    from .plan import Plan
    from .storage import canonical
    root = Path(root).resolve()
    directory = campaign_raw_directory(root, experiment_id)
    state = _read(directory/'campaign.json')
    if state.get('kind') != 'campaign_formal_v1' or state['formal_binding']['experiment_id'] != experiment_id:
        raise ValueError('Formal Campaign required')
    verify_campaign_binding(state['formal_binding'], root)
    run = find_run(root, experiment_id)
    manifest, storage = _read(run/'manifest.json'), _read(run/'storage_record.json')
    if (run/'run_summary.json').exists() or storage['stage'] != 'planned':
        raise ValueError('Existing curation; no automatic retry')
    inventory = _inventory(directory)
    errors = []
    try:
        if state['status'] != 'ready':
            raise ValueError('Unknown Campaign; reservations retained')
        _check_ready_state(state, Plan(canonical(state['plan']), state['plan_sha256']), directory, root)
        expected = {'campaign.json'} | {e['input_path'] for e in state['events'] if 'input_path' in e} | {j['raw_path'] for j in state['jobs']}
        if set(inventory) != expected:
            raise ValueError('Unclassified raw files; retain raw')
    except (ValueError, KeyError, OSError) as exc:
        errors.append(str(exc))
    def save(path, value):
        if path.exists():
            raise ValueError('Refuse existing evidence overwrite: '+str(path))
        atomic(path, value)
        return dict(path=path.relative_to(root).as_posix(), sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    counts = dict(planned=len(state['jobs']), attempted=0, converged=0, nonconverged=0, failed=0, not_started=0, unknown=0)
    jobs, checkpoints, seen = [], [], set()
    for row in state['jobs']:
        counts['attempted'] += 1
        status = row.get('worker_status', 'unknown')
        # Unknown is represented separately, never finalized as a scientific failure.
        counts['unknown' if row['status'] != 'completed' else 'converged' if status == 'converged' else 'nonconverged' if status in ('not_converged', 'budget_exhausted') else 'failed'] += 1
        info = {k: v for k, v in row.items() if k not in ('evidence',)}
        info['observations'] = row.get('evidence', {})
        jobs.append(info)
        if errors:
            continue
        from .worker import JobSpec
        data = JobSpec(**row['spec']).data
        raw = _read(directory/row['raw_path'])
        info.update(steps=raw['steps'], selection=raw['selection'], terminal=raw['terminal'])
        vectors = [c['vector'] for s in raw['steps'] for c in s['candidates'] if c.get('status') == 'unrun']
        vectors += [c['vector'] for c in raw['selection']['ranked']]
        if not vectors:
            vectors = [data['start']['vector']]
        for vector in vectors:
            key = (row['definition_sha256'], sha(vector))
            if key in seen:
                continue
            seen.add(key)
            cid = f'candidate-{len(checkpoints):06d}'
            try:
                payload = _checkpoint(data, vector, cid, root)
            except (ValueError, TypeError, KeyError) as exc:
                errors.append(f'Candidate conversion failed for {row["job_id"]}: {exc}')
                continue
            payload.update(job_id=row['job_id'], spec_sha256=row['spec_sha256'], raw_byte_sha256=row['raw_byte_sha256'])
            checkpoints.append(dict(candidate_id=cid, selection_reason='other',
                **save(run/'checkpoints'/f'{cid}.json', payload)))
    journal = dict(parent={k: v for k, v in state.items() if k != 'jobs'}, jobs=jobs, proposals=[dict(event=e,
        original_base64=base64.b64encode((directory/e['input_path']).read_bytes()).decode()
        if (directory/e['input_path']).is_file() else None) for e in state['events'] if 'input_path' in e])
    provenance = save(run/'campaign_evidence.json', journal)
    summary = dict(experiment_id=experiment_id, preservation_kind='campaign_v1', attempts=counts,
        unknown_job_ids=[j['job_id'] for j in state['jobs'] if j['status'] != 'completed'],
        selected_candidate_count=len(checkpoints), best_found=[], preservation_errors=errors,
        partial_staged_record=errors or None, raw_inventory=inventory,
        selection_reason='Conservative superset: all unique valid bounded solver outputs; start retained if no output. No cross-grid reranking.',
        limitations=LIMITATIONS + errors)
    if not checkpoints:
        summary['no_candidate_reason'] = 'No verified candidate available; see preservation_errors and Campaign journal.'
    storage.update(stage='preservation_incomplete', git_readback='not_run', checkpoints=checkpoints,
        summary=save(run/'run_summary.json', summary), supporting_evidence=[dict(provenance,
            role='recovery_state', reason='Campaign proposals, frozen starts/specs, rejected/failed/unrun evidence and raw source SHAs')],
        limitations=LIMITATIONS+errors)
    manifest['execution']['status'] = 'unknown' if errors else 'completed' if state['jobs'] else 'not_run'
    manifest['evidence'] = [storage['summary'], provenance] + [{k: c[k] for k in ('path', 'sha256')} for c in checkpoints]
    manifest['limitations'] = LIMITATIONS+errors
    atomic(run/'manifest.json', manifest); atomic(run/'storage_record.json', storage)
    _update_index(root, run, manifest)
    validate_run(root, experiment_id, mode='audit')
    return summary


def finalize_campaign(experiment_id, *, root):
    """Inspect curated diff first. Reuse existing commits/readback/storage audit."""
    from scripts.run_phase2_one_start import finalize_experiment
    root = Path(root).resolve()
    run = find_run(root, experiment_id)
    campaign_index_guard(root, run, _read(run/'manifest.json'), _read(run/'storage_record.json'),
                         _read(run/'run_summary.json'))
    return finalize_experiment(root, experiment_id)


def campaign_cleanup_eligibility(experiment_id, *, root, resume_needed, classification_complete):
    """G5 read-only decision, never deletes. Recompute every gate, not cached PASS.

    Only exact raw bytes inventoried at curation can be eligible as temporary C.
    The caller explicitly confirms no resume or remaining A/B promotion is needed.
    """
    from scripts.run_phase2_shared import _fresh_main, _complete_checkout
    root = Path(root).resolve()
    _complete_checkout(root)
    if resume_needed is not False or classification_complete is not True:
        raise ValueError('Resume/classification unresolved; retain raw')
    if _git(root, 'status', '--porcelain', '--untracked-files=all').strip():
        raise ValueError('Dirty preservation checkout; retain raw')
    main = _fresh_main(root)
    run = find_run(root, experiment_id)
    validate_run(root, experiment_id, mode='finalize')
    audit_all(root, main_ref='origin/main')
    summary = _read(run/'run_summary.json')
    storage = _read(run/'storage_record.json')
    manifest = _read(run/'manifest.json')
    if summary.get('preservation_kind') != 'campaign_v1' or summary['preservation_errors'] or summary['unknown_job_ids']:
        raise ValueError('Incomplete Campaign; retain raw')
    campaign_index_guard(root, run, manifest, storage, summary)
    for name in [e['path'] for e in manifest['evidence']] + [(run/n).relative_to(root).as_posix() for n in ('manifest.json', 'storage_record.json')] + ['data/experiment_index.csv']:
        if _git(root, 'show', f'{main}:{name}') != (root/name).read_bytes():
            raise ValueError('Remote main preservation bytes mismatch; retain raw')
    directory = campaign_raw_directory(root, experiment_id)
    if _inventory(directory) != summary['raw_inventory']:
        raise ValueError('Raw changed/unclassified; retain raw')
    return dict(experiment_id=experiment_id, eligible=True, deleted=False,
        finalize_commit=_git(root, 'rev-parse', 'HEAD').decode().strip(), remote_main=main,
        retained_evidence=manifest['evidence'], temporary_c=[str(directory/n) for n in summary['raw_inventory']],
        preservation_stage=storage['stage'])

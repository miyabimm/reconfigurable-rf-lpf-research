"""Explicit RF-T005 3L one-start driver; no CLI, reservation or unattended run.

Call only within the launched experiment Issue. prepare_one_start stays read-only.
Git commits are a separate explicit step. Timeout/STOP checks are cooperative at
stage boundaries, not a hard wall-clock kill of SciPy; external kills retain the
last atomic raw snapshot and require manual investigation, never automatic retry.
"""
from copy import deepcopy
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'src'))

from lpf.checkpoint_io import atomic_write_json, canonical_config_hash
from lpf.phase2_models.candidate_records import record_candidate, CandidateRecord, recheck_record
from lpf.phase2_models.circuit_layout import CapacitorPlacement, InductorTree
from lpf.phase2_models.api import CircuitDefinition
from lpf.phase2_models._grid import CASES
from lpf.phase2_models.staged_optimization import run_c1_staged, scipy_slsqp_stage, _json_value
from lpf.phase2_models.synthetic_runner import checked_one_start_selection
from scripts.run_phase2_shared import prepare_one_start
from scripts.audit_new_experiment_storage import (
    find_run, read_json, tracked_file, validate_checkpoint, validate_summary, validate_run, audit_all)


LIMITATIONS = [
    'Diagnostic 1/2/3-point separate-interval grids only, not RF scientific PASS.',
    'Independent MNA/power/dense RF/continuous frequency/physical validation not_run.',
    'Candidate promotion blocked; best-found is not a proven global optimum.',
    'Timeout/STOP is cooperative between stages; external termination can leave partial evidence.']


def _supported(circuit):
    expected = CircuitDefinition(
        InductorTree(4, ((0, 1), (1, 2), (1, 3))), ('LQP02HV',) * 3,
        (0, 1, 2), ((0, 1), (0, 2)),
        CapacitorPlacement(4, ((0, 1), (1, -1)), ((3, -1), (0, 2)), ()),
        ('GJM01', 'PCB_PATTERN_C'), ('shunt_to_ground', 'bridge'))
    if circuit.policy_id != 'RF-T005' or circuit.definition != expected:
        raise ValueError('Only the existing RF-T005 3L layout is supported')


def candidate_checkpoint(circuit, row):
    """Actual stamped values -> existing checkpoint schema, never RF PASS."""
    _supported(circuit)
    checked = recheck_record(CandidateRecord.from_json(json.dumps(row))).as_dict()
    d, t, s = circuit.definition, circuit.topology, circuit.schema
    if (s.n_ic_fixed or s.constant_caps_pf or
            checked['policy_sha256'] != circuit.policy_fingerprint or
            checked['definition'] != json.loads(json.dumps(asdict(d)))):
        raise ValueError('Unsupported/mismatched circuit')
    values = circuit.decode(checked['vector'])
    components = [dict(id=f'L{i}', L_nH=value, Q=t.inductor_q[i],
                       series=d.inductor_types[i], terminals=list(d.inductor_tree.edges[i]))
                  for i, value in enumerate(values.inductances_nh)]
    for i, edge in enumerate(t.capacitor_edges):
        components.append(dict(id=f'C{i}', Q=t.capacitor_q[i], terminals=list(edge),
            series=d.fixed_c_types[i] if i < s.n_fixed else 'IC_VARIABLE_C',
            C_pf_by_setting={case: values.capacitors_pf_by_setting[j][i]
                             for j, case in enumerate(CASES)}))
    payload = dict(candidate_id=checked['candidate_id'], topology=checked['stamped_topology'],
        components=components,
        couplings=[dict(inductor_indices=list(pair), signed_k=k)
                   for pair, k in zip(t.coupling_pairs, values.coupling_k)],
        chip_row=[f'L{i}' for i in d.physical_order],
        fixed_values=dict(inductances_nh=list(values.inductances_nh),
                          capacitors_pf=list(values.capacitors_pf_by_setting[0][:s.n_fixed])),
        ic_variable_C_pf_by_setting={case: list(values.capacitors_pf_by_setting[j][
            s.n_fixed:s.n_fixed + s.n_variable]) for j, case in enumerate(CASES)},
        candidate_record=checked)
    validate_checkpoint(payload, checked['candidate_id'])
    return payload


class _Stopped(Exception):
    pass


def run_one_start(root, experiment_id, *, optimize_stage=scipy_slsqp_stage,
                  timeout_seconds=None, **kwargs):
    """G0/G1 -> one existing v2 start -> raw and curated evidence, no Git commit.

    Existing raw output prohibits replay, even after a crash. No retries beyond
    the v2 controller. Injected callbacks are explicitly recorded as such, never
    as actual SciPy evidence. A separate experiment Issue defines any timeout;
    it is not inferred from maxiter. The planned selection must retain checked
    Pareto points and all exclusions/partial stage diagnostics in the summary.
    """
    if timeout_seconds is not None and (type(timeout_seconds) not in (int, float)
            or not 0 < timeout_seconds < float('inf')):
        raise ValueError('Timeout must be finite and positive')
    circuit = kwargs['circuit']
    _supported(circuit)
    prepared = prepare_one_start(root, experiment_id, **kwargs)
    root = Path(root).resolve()
    source_paths = ('src', 'scripts', 'project', 'rf', 'pyproject.toml', 'uv.lock')
    source_names = subprocess.check_output(
        ['git', 'ls-files', '-z', '--', *source_paths], cwd=root).split(b'\0')[:-1]
    def source_bytes(repo):
        return [hashlib.sha256((repo / name.decode()).read_bytes()).hexdigest()
                for name in source_names]
    source_before = source_bytes(root)
    run = find_run(root, experiment_id)
    manifest = read_json(run / 'manifest.json')
    storage = read_json(run / 'storage_record.json')
    if (storage['stage'] != 'planned' or storage['selection']['top_k'] != 0 or
            storage['selection']['retain'] != ['pareto'] or manifest['evidence'] or
            storage['summary'] is not None or storage['checkpoints'] or
            storage['validation_overlays'] or storage.get('supporting_evidence') or
            any(manifest['validation'][key] != 'not_run'
                for key in ('numerical', 'independent', 'implementation'))):
        raise ValueError('Pristine planned one-start Pareto preservation required')
    raw = root / 'results' / experiment_id
    if raw.exists():
        raise ValueError('Raw already exists; investigate manually, never retry automatically')
    # Raw must actually be ignored, including in a separately supplied checkout.
    if subprocess.run(['git', 'check-ignore', '-q', '--', f'results/{experiment_id}/run.json'],
                      cwd=root).returncode != 0:
        raise ValueError('Raw results must be Git ignored')
    raw.mkdir(parents=True, exist_ok=False)
    provenance = {'kind': 'recorded',
        'optimizer_kind': 'reported_slsqp' if optimize_stage is scipy_slsqp_stage else 'synthetic_callback',
        'execution_kind': 'scipy_slsqp' if optimize_stage is scipy_slsqp_stage else 'injected_callback',
        'git_head': kwargs['source_sha'], 'dirty_patch_sha256': hashlib.sha256(b'').hexdigest(),
        'input_source_sha256': canonical_config_hash(prepared['input_source'])}
    state = {'experiment_id': experiment_id, 'preflight': prepared['preflight'],
        'input_source': prepared['input_source'], 'seed_record': prepared['seed_record'],
        'selection_before_run': deepcopy(storage['selection']), 'source_provenance': provenance,
        'result': {'completed': [], 'not_started': 1}, 'staged_record': None,
        'termination': None, 'timeout_seconds': timeout_seconds,
        'callback_returns': [], 'preservation': 'preservation_incomplete',
        'candidate_promotion_blocked': True, 'rf_compliance_certified': False}
    def save():
        atomic_write_json(raw / 'run.json', state)
    def sink(record):
        state['staged_record'] = record
        save()
    started = time.monotonic()
    dispatched = False
    def check_stop():
        if (raw / 'STOP').exists():
            raise _Stopped('STOP requested')
        if timeout_seconds is not None and time.monotonic() - started >= timeout_seconds:
            raise TimeoutError('Cooperative stage-boundary timeout')
    def callback(*args):
        nonlocal dispatched
        check_stop()
        dispatched = True
        state['result']['not_started'] = 0
        save()  # Durable dispatch marker; an external kill is never not_started.
        try:
            output = optimize_stage(*args)
        except KeyboardInterrupt as exc:
            state['termination'] = {'type': 'KeyboardInterrupt', 'message': str(exc)}
            raise _Stopped('KeyboardInterrupt during solver') from exc
        # A STOP/timeout arriving during a call must not erase its observed
        # return, even though it cannot complete the controller's stage pair.
        state['callback_returns'].append(_json_value(output))
        save()
        check_stop()
        return output
    save()
    try:
        check_stop()
        staged = run_c1_staged(circuit, prepared['seed_record'],
            coarse_points=kwargs['coarse_points'], fine_points=kwargs['fine_points'],
            optimize_stage=callback, source_provenance=provenance, record_sink=sink)
        if source_bytes(root) != source_before or source_bytes(ROOT) != source_before:
            raise ValueError('Source/input changed during execution; retain partial raw')
        if dispatched:
            final = (prepared['seed_record']['vector'][:-1] if staged['numerical_state'] == 'failed'
                     else staged['stage_calls'][-1]['output_vector'][:-1])
            row = record_candidate('start-0', circuit, final, staged_record=staged,
                                   source_provenance=provenance).as_dict()
            state['result'] = {'completed': [row], 'not_started': 0}
        state['termination'] = state['termination'] or staged['exception'] or {
            'type': 'completed', 'message': staged['numerical_state']}
    except (Exception, KeyboardInterrupt) as exc:
        state['termination'] = {'type': type(exc).__name__, 'message': str(exc)}
        # An unclassifiable attempted start must never become not_started or success.
        state['unclassified_attempt'] = dispatched
    state['elapsed_seconds'] = time.monotonic() - started
    save()
    try:
        if (read_json(run / 'manifest.json') != manifest or
                read_json(run / 'storage_record.json') != storage):
            raise ValueError('Planned manifest/storage changed during execution')
        _package(root, run, circuit, state, manifest, storage)
        state['preservation'] = ('preservation_incomplete' if state['result']['not_started']
            or state.get('unclassified_attempt') else 'awaiting_git_readback')
    except Exception as exc:
        state['preservation_error'] = {'type': type(exc).__name__, 'message': str(exc)}
        storage['stage'] = 'preservation_incomplete'
        storage['limitations'] = LIMITATIONS + ['Packaging failed; retain raw: ' + str(exc)]
        atomic_write_json(run / 'storage_record.json', storage)
    save()
    return state


def _package(root, run, circuit, state, manifest, storage):
    """Use the checked classifier; all excluded records remain inspectable."""
    if state.get('unclassified_attempt'):
        # No fabricated candidate/status: retain partial C1/C2 in the summary.
        actual = {'pareto': None, 'selected': [], 'run_summary': {
            'attempts': dict(planned=1, attempted=1, converged=0, nonconverged=0, failed=1, not_started=0),
            'selected_candidate_count': 0, 'best_found': [],
            'no_candidate_reason': 'Attempt interrupted before candidate could be checked.'}}
    else:
        actual = checked_one_start_selection(state['result'])
    rows = {r['candidate_id']: r for r in state['result']['completed']}
    for row in rows.values():
        if (row['seed_record']['input_vector'] != state['input_source']['vector'] or
                row['seed_record']['seed'] != manifest['random_seed'] or
                row['source_provenance']['value'] != state['source_provenance'] or
                row['policy_id'] != manifest['constraints']['constraint_id'] or
                row['policy_sha256'] != manifest['constraints']['effective_constraint_sha256']):
            raise ValueError('Candidate differs from bound manifest input/source/RF')
    summary = deepcopy(actual['run_summary'])
    summary.update(experiment_id=state['experiment_id'], pareto=actual['pareto'], selected=actual['selected'],
        selection_before_run=state['selection_before_run'], input_source=state['input_source'],
        source_provenance=state['source_provenance'], termination=state['termination'],
        elapsed_seconds=state['elapsed_seconds'], timeout_seconds=state['timeout_seconds'],
        callback_returns=state['callback_returns'],
        excluded_records=[r for cid, r in rows.items() if cid not in summary['best_found']],
        partial_staged_record=state['staged_record'] if not rows else None,
        limitations=LIMITATIONS)
    validate_summary(summary, state['experiment_id'], len(actual['selected']))
    def save(path, body):
        atomic_write_json(path, body)
        return {'path': path.relative_to(root).as_posix(),
                'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
    storage['checkpoints'] = [item | save(run / 'checkpoints' / (item['candidate_id'] + '.json'),
        candidate_checkpoint(circuit, rows[item['candidate_id']])) for item in actual['selected']]
    storage['summary'] = save(run / 'run_summary.json', summary)
    counts = summary['attempts']
    observed_calls = (state['staged_record'] or {}).get('stage_calls', [])
    nfev = (sum(c['status']['nfev'] for c in observed_calls)
            if observed_calls and all(isinstance(c.get('status'), dict) and
                type(c['status'].get('nfev')) is int and c['exception'] is None
                for c in observed_calls) else None)
    manifest['execution'].update(status='not_run' if counts['not_started'] else
        'failed' if counts['failed'] else 'completed', elapsed_seconds=state['elapsed_seconds'],
        evaluation_count=nfev)
    # This driver does not run independent RF validation, even if status=0.
    manifest['evidence'] = [storage['summary']] + [
        {k: cp[k] for k in ('path', 'sha256')} for cp in storage['checkpoints']]
    manifest['limitations'] = storage['limitations'] = LIMITATIONS
    storage['stage'] = 'preservation_incomplete'
    save(run / 'manifest.json', manifest)
    save(run / 'storage_record.json', storage)
    validate_run(root, state['experiment_id'], mode='audit')


def finalize_one_start(root, experiment_id):
    """Explicit G3/G4 commits -> byte readback -> final record commit -> audit.

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
        validate_run(root, experiment_id, mode='audit')
        def commit(message):
            subprocess.check_call(['git', 'add', '--', run.relative_to(root).as_posix()], cwd=root)
            subprocess.check_call(['git', 'commit', '-m', message], cwd=root)
        commit(experiment_id + ': preserve one-start evidence')
        for ref in manifest['evidence'] + [{'path': (run / name).relative_to(root).as_posix()}
                for name in ('manifest.json', 'storage_record.json')]:
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

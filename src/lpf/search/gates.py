"""Campaign G0/G1 preparation and read-only verification; never execute RF.

Uses the existing reservation/manifest/storage gates. A ready report is technical
readiness, not an extra owner authentication or permission to launch an EXP.
"""
import hashlib
import json
from pathlib import Path
import subprocess

from lpf.experiment_manifest import RUNS, new_manifest
from scripts.audit_new_experiment_storage import (
    find_run, reservation_on_main, validate_run, validate_selection,
)
from scripts.experiment_id_registry import is_reserved_on_main
from scripts.run_phase2_shared import _complete_checkout, _fresh_main
from ._job_evaluation import source_identity
from .storage import atomic, sha


def _git(root, *args):
    return subprocess.check_output(['git', '-C', str(root), *args], stderr=subprocess.PIPE)


def _base(plan, root, experiment_id, owner, request_id):
    from .campaign import _plan
    root = Path(root).resolve()
    _plan(plan, root)
    _complete_checkout(root)
    main = _fresh_main(root)
    if _git(root, 'status', '--porcelain', '--untracked-files=all').strip():
        raise ValueError('Campaign G1 requires a clean checkout')
    if subprocess.run(['git', '-C', str(root), 'merge-base', '--is-ancestor', main, 'HEAD'],
                      capture_output=True).returncode:
        raise ValueError('Campaign checkout does not contain latest main')
    row = is_reserved_on_main(root, experiment_id)
    other = reservation_on_main(root, experiment_id, main_ref='origin/main', starting=True)
    config = plan.data['config']
    if row != other or (row['owner'], row['request_id'], row['constraint_id']) != (
            owner, request_id, config['rf']['constraint_id']):
        raise ValueError('Campaign main reservation identity mismatch')
    return root, main, row


def _storage_estimate(root, selection, size_exception=None):
    validate_selection(selection)
    budget = json.loads((root/'data/phase2_git_storage_budget.json').read_bytes())
    limit = budget['thresholds']['new_experiment_curated_soft_bytes']
    if selection['estimated_curated_bytes'] > limit and size_exception is None:
        raise ValueError('Campaign curated size estimate exceeds storage budget without size exception')


def prepare_campaign(plan, experiment_id, *, owner, request_id, purpose, selection, root):
    """Create a new planned manifest/storage pair, without commit/push/reservation.

    The caller must commit these files to main and rerun campaign_preflight.
    Future topology definitions, starts and Jobs are deliberately absent.
    Existing run directories are never replaced; interrupted preparation is not
    retried automatically. Only this new EXP directory is written.
    """
    root, main, reservation = _base(plan, root, experiment_id, owner, request_id)
    _storage_estimate(root, selection)
    if purpose != reservation['purpose']:
        raise ValueError('Campaign purpose differs from main reservation')
    source = source_identity(root)
    binding = dict(kind='campaign_v1', plan=plan.data, plan_sha256=plan.sha256,
                   approved_source=source, reservation=reservation, reservation_main_sha=main)
    config = plan.data['config']
    manifest = new_manifest(experiment_id, purpose, {'campaign': binding},
        objective=config['objective'], seed=config['seeds'][0], root=root,
        constraint_id=config['rf']['constraint_id'], allow_trial=config['rf']['allow_trial'])
    record = dict(schema_version=1, policy='phase2-git-only-v1', experiment_id=experiment_id,
        phase='Phase 2', stage='planned', selection=selection, summary=None, checkpoints=[],
        validation_overlays=[], supporting_evidence=[], git_readback='not_run',
        size_exception=None, limitations=[])
    # Also protect against the same ID already present under another run family.
    try:
        find_run(root, experiment_id)
    except ValueError:
        pass
    else:
        raise ValueError('Campaign EXP already exists')
    run = root/RUNS/experiment_id
    run.mkdir(parents=True, exist_ok=False)
    atomic(run/'manifest.json', manifest)
    atomic(run/'storage_record.json', record)
    report = validate_run(root, experiment_id, mode='preflight')
    return dict(status='planned_not_remote_verified', experiment_id=experiment_id,
                approved_source_sha256=sha(source), plan_sha256=plan.sha256,
                storage=report, execution='not_run', execution_allowed=False)


def campaign_preflight(plan, experiment_id, *, owner, request_id, root):
    """Verify main-backed planned bytes and current code/env/RF without forward.

    HEAD may change when planned evidence is committed, but all approved code,
    project/RF inputs and lock bytes must remain unchanged. Runtime HEAD and the
    approved source identity are returned separately, avoiding a self-reference.
    """
    root, main, reservation = _base(plan, root, experiment_id, owner, request_id)
    run = find_run(root, experiment_id)
    digests = {}
    payloads = {}
    for name in ('manifest.json', 'storage_record.json'):
        path = run/name
        relative = path.relative_to(root).as_posix()
        raw = path.read_bytes()
        if any(_git(root, 'show', f'{ref}:{relative}') != raw for ref in ('HEAD', main)):
            raise ValueError('Campaign planned remote/HEAD byte mismatch: ' + name)
        digests[name] = hashlib.sha256(raw).hexdigest()
        payloads[name] = json.loads(raw)
    manifest, record = payloads['manifest.json'], payloads['storage_record.json']
    binding = manifest['search_scope'].get('campaign', {})
    if (binding.get('kind') != 'campaign_v1' or binding.get('plan') != plan.data or
            binding.get('plan_sha256') != plan.sha256 or
            binding.get('reservation') != reservation or manifest['purpose'] != reservation['purpose'] or
            manifest['objective'] != plan.data['config']['objective'] or
            manifest['random_seed'] != plan.data['config']['seeds'][0] or
            manifest['execution']['status'] != 'planned' or record['stage'] != 'planned' or
            manifest['evidence'] or record['summary'] is not None or record['checkpoints'] or
            record['validation_overlays'] or record.get('supporting_evidence', [])):
        raise ValueError('Campaign planned envelope/reservation mismatch')
    approved = binding['approved_source']
    current = source_identity(root)
    # source_identity covers implementation files and effective numeric environment;
    # the wider Git diff also freezes scripts, project input YAML and RF data.
    empty_patch = hashlib.sha256(b'').hexdigest()
    if (manifest['code']['execution_sha'] != approved['head'] or
            manifest['code']['working_tree_dirty'] or
            approved['dirty_patch_sha256'] != empty_patch or
            current['dirty_patch_sha256'] != empty_patch or
            approved['files'] != current['files'] or approved['environment'] != current['environment']):
        raise ValueError('Campaign approved source/environment mismatch')
    for ancestor in (approved['head'], binding['reservation_main_sha']):
        if subprocess.run(['git', '-C', str(root), 'merge-base', '--is-ancestor', ancestor, main],
                          capture_output=True).returncode:
            raise ValueError('Campaign approved source/reservation not on main')
    if _git(root, 'diff', '--name-only', approved['head'], 'HEAD', '--',
            'src', 'scripts', 'rf', 'project', 'pyproject.toml', 'uv.lock',
            'data/phase2_git_storage_budget.json').strip():
        raise ValueError('Campaign approved code/input bytes changed')
    report = validate_run(root, experiment_id, mode='preflight')
    # Existing storage validation checks any recorded exception's required fields.
    _storage_estimate(root, record['selection'], record.get('size_exception'))
    return dict(status='preflight_ready', experiment_id=experiment_id, main_sha=main,
        plan_sha256=plan.sha256, approved_source=approved, runtime_source=current,
        planned_bytes_sha256=digests, storage=report, execution='not_run',
        execution_allowed=False, gates={'G0_G1': 'passed', 'G2_G5': 'not_ready'})

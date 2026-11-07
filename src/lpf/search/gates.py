"""Campaign G0/G1 preparation and read-only verification; never execute RF.

Uses the existing reservation/manifest/storage gates. A ready report is technical
readiness, not an extra owner authentication or permission to launch an EXP.
"""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

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


def _verify_import_origins(root):
    """Bind loaded project modules and package search paths to tracked source.

    This is an accidental checkout-mixup check, not an import-hook sandbox.
    Dependencies remain covered by the existing environment binding.
    """
    root = Path(root).resolve()
    bases = {'lpf': root/'src/lpf', 'scripts': root/'scripts'}
    for base in bases.values():
        if base.resolve() != base or not base.is_dir():
            raise ValueError('Campaign G1 import root redirects or is missing: ' + str(base))
    tracked = set(_git(root, 'ls-files', '-z', '--', 'src/lpf', 'scripts').decode().split('\0'))
    files = source_identity(root)['files']
    for name, module in tuple(sys.modules.items()):
        top = name.split('.')[0]
        if top not in bases:
            continue
        base = bases[top]
        target = base.joinpath(*name.split('.')[1:])
        spec = getattr(module, '__spec__', None)
        if getattr(spec, 'name', None) != name:
            raise ValueError('Campaign G1 import spec mismatch: ' + name)
        origin = getattr(spec, 'origin', None)
        file = getattr(module, '__file__', None)
        paths = getattr(module, '__path__', None)
        locations = getattr(spec, 'submodule_search_locations', None)
        if paths is not None or locations is not None:
            if paths is None or locations is None or not target.is_dir():
                raise ValueError('Campaign G1 import package path missing: ' + name)
            for entries in (paths, locations):
                if not entries or any(Path(p).resolve() != target for p in entries):
                    raise ValueError('Campaign G1 import package path mismatch: ' + name)
        # A real namespace package has no source file, but its search paths
        # must still resolve only to the expected package directory.
        if origin is None and file is None and paths is not None and not (target/'__init__.py').exists():
            continue
        expected = target/'__init__.py' if paths is not None else target.with_suffix('.py')
        if (not origin or not file or Path(origin).resolve() != expected or
                Path(file).resolve() != expected or not expected.is_file()):
            raise ValueError('Campaign G1 import origin mismatch: ' + name)
        relative = expected.relative_to(root).as_posix()
        if relative not in tracked or (top == 'lpf' and
                files.get(relative) != hashlib.sha256(expected.read_bytes()).hexdigest()):
            raise ValueError('Campaign G1 import source untracked or unknown: ' + name)


def _base(plan, root, experiment_id, owner, request_id):
    from .campaign import _plan
    root = Path(root).resolve()
    _verify_import_origins(root)
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


def campaign_raw_directory(root, experiment_id):
    """Only the ignored, non-symlink results/<reserved EXP> is a formal raw root."""
    root = Path(root).resolve()
    path = root/'results'/experiment_id
    if path.resolve() != path or path.parent.is_symlink():
        raise ValueError('Campaign raw path must not redirect through symlinks')
    relative = path.relative_to(root).as_posix()
    if subprocess.run(['git', '-C', str(root), 'check-ignore', '-q', relative+'/campaign.json'],
                      capture_output=True).returncode:
        raise ValueError('Campaign results must be Git ignored')
    if _git(root, 'ls-files', '--', relative).strip():
        raise ValueError('Campaign raw must not be Git tracked')
    return path


def verify_campaign_binding(binding, root):
    """Recompute G0/G1; a cached ready report alone never authorizes forward."""
    from .plan import Plan
    from .storage import canonical
    plan = Plan(canonical(binding['plan']), binding['plan_sha256'])
    report = campaign_preflight(plan, binding['experiment_id'], owner=binding['owner'],
        request_id=binding['request_id'], root=root)
    if report != binding['preflight']:
        raise ValueError('Campaign frozen G1/runtime binding changed')
    return report


def verify_campaign_job(spec, checkpoint, root):
    """Check G1 plus the parent's durable active reservation before any RF."""
    from .storage import plain
    data = spec.data
    if data.get('kind') != 'campaign_formal_job_v1':
        raise ValueError('Formal entry rejects development JobSpec')
    binding = data['formal_binding']
    verify_campaign_binding(binding, root)
    directory = campaign_raw_directory(root, binding['experiment_id'])
    context = data['campaign_context']
    expected = directory/(context['job_id']+'.json')
    if Path(checkpoint).absolute() != expected or expected.resolve() != expected:
        raise ValueError('Formal Worker raw path mismatch')
    state = json.loads((directory/'campaign.json').read_bytes())
    row = state['jobs'][-1] if state['jobs'] else {}
    cap = data['plan']['costs']['jobs'][data['arm']]['max_requested_samples']
    if (state['plan'] != binding['plan'] or state['source'] != data['source'] or
            sha(data['source']) != spec.source_sha256 or sha(data['plan']) != spec.plan_sha256 or
            state['reserved'] != sum(j['reserved'] for j in state['jobs']) or
            state['requested'] != sum(j['requested'] for j in state['jobs']) or
            row.get('definition_sha256') != sha(data['definition']) or
            row.get('proposal_sha256') != context['proposal_sha256'] or
            spec.trial_id != binding['experiment_id'] or
            spec.job_id != spec.trial_id+'-'+context['job_id'] or
            state.get('kind') != 'campaign_formal_v1' or state.get('formal_binding') != binding or
            state['status'] != 'unknown' or row.get('status') != 'unknown' or
            state['plan_sha256'] != binding['plan_sha256'] or
            context['plan_sha256'] != binding['plan_sha256'] or
            row.get('spec') != plain(spec) or row.get('spec_sha256') != sha(spec) or
            row.get('raw_path') != expected.name or row.get('cap') != cap or
            row.get('reserved') != cap or state['reserved'] != cap or
            state['requested']+state['reserved'] > binding['plan']['config']['campaign']['max_rf_samples']):
        raise ValueError('Formal Job/parent reservation mismatch')
    from .proposals import load_proposal
    accepted = [e for e in state['events'] if e.get('job_id') == context['job_id'] and e['status'] == 'accepted']
    if len(accepted) != 1:
        raise ValueError('Formal Job accepted proposal missing')
    event = accepted[0]
    index = state['events'].index(event)
    if event['input_path'] != f'proposal-{index:06d}.yaml':
        raise ValueError('Formal Job proposal path mismatch')
    path = directory/event['input_path']
    proposal = load_proposal(path)
    if (path.resolve() != path or hashlib.sha256(path.read_bytes()).hexdigest() != event['input_sha256'] or
            sha(proposal) != context['proposal_sha256'] or sha(proposal['definition']) != sha(data['definition']) or
            proposal['based_on_state_sha256'] != context['based_on_state_sha256'] or
            event['spec_sha256'] != sha(spec)):
        raise ValueError('Formal Job proposal bytes/provenance mismatch')
    return binding


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

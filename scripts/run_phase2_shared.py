#!/usr/bin/env python3
"""Shared diagnostic entrypoint. Never starts an EXP or a real optimizer."""
import argparse
import json
import re
import sys
import tempfile
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'src'))


def synthetic(policy_id, inductors):
    from lpf.constraint_versions import load_constraint
    from lpf.phase2_models.api import build_nominal_circuit
    from lpf.phase2_models.circuit_layout import InductorTree
    from lpf.phase2_models.topology_enumeration import TopologySpace, enumerate_topologies
    from lpf.phase2_models.problem_seed import vector_fingerprint
    from lpf.phase2_models.synthetic_plan import make_synthetic_plan
    from lpf.phase2_models.synthetic_runner import run_synthetic_preview

    policy = load_constraint(policy_id, allow_trial=True)
    space = TopologySpace(
        trees=(InductorTree(inductors + 1, tuple((0, i) for i in range(1, inductors + 1))),),
        inductor_assignments=(("LQP02HV",) * inductors,),
        fixed_layouts=(( ((0, 1), "GJM01"), ((1, -1), "PCB_PATTERN_C") ),),
        variable_layouts=(( ((3, -1), "shunt_to_ground"), ((0, 2), "bridge") ),),
        coupling_slot_counts=(inductors - 1,), physical_order_limit=1, max_candidates=1)
    rows = enumerate_topologies(policy, space)['candidates']
    if len(rows) != 1:
        raise ValueError('Synthetic fixture topology unavailable')
    row = rows[0]
    circuit = build_nominal_circuit(policy, row['definition'])
    vector = list(map(float, row['representative_vector']))
    starts = [{'id': 'start-0', 'vector': vector, 'vector_sha256': vector_fingerprint(vector),
               'seed': 0, 'jitter_fraction': 0.0}]
    source = {'kind': 'synthetic', 'policy_id': policy_id, 'vectors': {'start-0': vector}}
    envelope = make_synthetic_plan(circuit, starts, run_id='synthetic-shared',
                                   coarse_points=1, fine_points=2, input_source=source)

    def mock(problem, vector, budget, target):
        return vector, {'success': True, 'status': 0, 'message': 'synthetic mock',
                        'nit': 0, 'nfev': 0}

    with tempfile.TemporaryDirectory(prefix='lpf-synthetic-') as tmp:
        return run_synthetic_preview(circuit, envelope, Path(tmp) / 'checkpoint.json',
                                     optimize_stage=mock)


def _complete_checkout(root):
    root = Path(root)
    for name in ('data/experiment_number_registry.csv', 'data/phase2_git_storage_budget.json',
                 'experiments', 'rf/bands.csv'):
        if not (root / name).exists():
            raise ValueError('Full checkout required; missing ' + name)
    sparse = subprocess.run(['git', 'config', '--bool', 'core.sparseCheckout'], cwd=root,
                            capture_output=True, text=True)
    if sparse.stdout.strip() == 'true':
        raise ValueError('Full checkout required; sparse checkout is not sufficient')
    tracked = subprocess.check_output(['git', 'ls-files', '-z', '--', 'data', 'experiments'], cwd=root)
    for name in filter(None, tracked.split(b'\0')):
        path = root / name.decode('utf-8')
        if not path.exists():
            raise ValueError('Full checkout required; missing tracked evidence: ' + name.decode('utf-8'))


def _fresh_main(root):
    local = subprocess.check_output(['git', 'rev-parse', 'refs/remotes/origin/main'], cwd=root, text=True).strip()
    remote = subprocess.check_output(['git', 'ls-remote', '--exit-code', 'origin', 'refs/heads/main'],
                                     cwd=root, text=True).split()
    if len(remote) != 2 or remote[0] != local or remote[1] != 'refs/heads/main':
        raise ValueError('origin/main is stale or unavailable; fetch and recheck')
    return local


def exp_preflight(root, experiment_id, *, owner, request_id, policy_id, policy_sha256,
                  source_sha, bands_sha256, input_sha256, allow_trial):
    """Read-only future-run preflight; it never authorizes or starts an EXP."""
    from scripts.experiment_id_registry import is_reserved_on_main
    from scripts.audit_new_experiment_storage import find_run, read_json, reservation_on_main, validate_run
    from lpf.checkpoint_io import canonical_config_hash
    from lpf.constraint_versions import rf_input_file
    from lpf.experiment_manifest import file_sha256
    root = Path(root).resolve()
    _complete_checkout(root)
    main_sha = _fresh_main(root)
    if policy_id not in ('RF-T005', 'RF-T007', 'RF-T008') or not allow_trial:
        raise ValueError('Supported trial and explicit trial opt-in required; F003/T006 unsupported')
    row = is_reserved_on_main(root, experiment_id)
    other = reservation_on_main(root, experiment_id, main_ref='origin/main', starting=True)
    if row != other or (row['owner'], row['request_id'], row['constraint_id']) != (owner, request_id, policy_id):
        raise ValueError('Main reservation identity mismatch')
    report = validate_run(root, experiment_id, mode='preflight', main_ref='origin/main')
    manifest = read_json(find_run(root, experiment_id) / 'manifest.json')
    code = manifest['code']
    ports = manifest['constraints']['effective_constraints']['external_port_parasitics']
    for role in ('input_parasitic', 'output_parasitic'):
        spec = ports[role]
        if file_sha256(rf_input_file(root, spec['path'])) != spec['sha256']:
            raise ValueError('Fixed S2P fingerprint mismatch: ' + role)
    if not re.fullmatch(r'[0-9a-f]{40}', source_sha):
        raise ValueError('Invalid source SHA')
    dirty = subprocess.check_output(['git', 'status', '--porcelain', '--untracked-files=all'], cwd=root, text=True).strip()
    ancestor = subprocess.run(['git', 'merge-base', '--is-ancestor', source_sha, 'HEAD'], cwd=root,
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0
    source_diff = subprocess.check_output(['git', 'diff', '--name-only', source_sha, 'HEAD', '--',
                                           'src', 'scripts', 'rf', 'project', 'pyproject.toml', 'uv.lock'],
                                          cwd=root, text=True, stderr=subprocess.PIPE).strip()
    if (code['execution_sha'] != source_sha or not ancestor or source_diff or dirty or code['working_tree_dirty']
            or manifest['constraints']['effective_constraint_sha256'] != policy_sha256
            or manifest['bands_sha256'] != bands_sha256
            or manifest['search_scope'].get('input_source_sha256') != input_sha256
            or 'input_source' not in manifest['search_scope']
            or canonical_config_hash(manifest['search_scope']['input_source']) != input_sha256
            or len(input_sha256) != 64 or any(c not in '0123456789abcdef' for c in input_sha256)):
        raise ValueError('Source, policy, bands or input fingerprint mismatch')
    return {'mode': 'exp_preflight_read_only', 'main_sha': main_sha, 'reservation': row,
            'storage': report, 'owner_approval': 'not_verified', 'execution_allowed': False,
            'candidate_promotion_blocked': True,
            'next_gate': 'Owner must independently verify GitHub approval before any EXP start.'}


def one_start_gate(root, experiment_id, **preflight_args):
    """Read-only production gate, deliberately without an optimizer dispatch.

    Even a successful storage preflight is not evidence of owner approval.
    Until that approval can be independently verified this entry cannot accept
    a callback or start a solver. Exceptions retain the underlying rejection
    reason; no EXP evidence or partial success is written.
    """
    report = exp_preflight(root, experiment_id, **preflight_args)
    return {'mode': 'one_start_gate', 'preflight': report,
            'execution': 'not_run', 'rejection': 'owner_approval_not_verified',
            'owner_approval': 'not_verified', 'execution_allowed': False,
            'finite_grid_rf': 'not_run', 'independent_mna': 'not_run',
            'dense_rf': 'not_run', 'git_readback': 'not_run',
            'candidate_promotion_blocked': True}


def manifest_preview(root, experiment_id, purpose, scope, *, policy_id, seed, allow_trial):
    from lpf.experiment_manifest import new_manifest, validate_manifest
    if policy_id not in ('RF-T005', 'RF-T007', 'RF-T008') or not allow_trial:
        raise ValueError('Supported trial and explicit trial opt-in required')
    manifest = new_manifest(experiment_id, purpose, scope, objective='full_lpf', seed=seed,
                            root=root, constraint_id=policy_id, allow_trial=True)
    validate_manifest(manifest, root=root)
    return {'mode': 'manifest_preview_not_saved', 'manifest': manifest,
            'owner_approval': 'not_verified', 'execution_allowed': False}


def storage_audit(root, mode, experiment_id=None):
    from scripts.audit_new_experiment_storage import audit_all, validate_run
    _complete_checkout(root)
    main_sha = _fresh_main(root)
    if mode == 'audit':
        if experiment_id is not None:
            raise ValueError('audit does not accept an experiment ID')
        report = audit_all(root, main_ref='origin/main')
    else:
        if not experiment_id:
            raise ValueError('experiment ID required')
        report = validate_run(root, experiment_id, mode=mode, main_ref='origin/main')
    return {'mode': 'storage_' + mode + '_read_only', 'main_sha': main_sha, 'result': report,
            'execution_allowed': False, 'candidate_promotion_blocked': True}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='mode', required=True)
    diag = sub.add_parser('synthetic', help='bounded explicit mock diagnostic only')
    diag.add_argument('--mock', action='store_true', required=True)
    diag.add_argument('--policy', required=True, choices=('RF-T005', 'RF-T007', 'RF-T008'))
    diag.add_argument('--inductors', required=True, type=int, choices=(3, 4))
    pre = sub.add_parser('exp-preflight', help='read-only future-run checks, not approval')
    for arg in ('experiment-id', 'owner', 'request-id', 'policy', 'policy-sha256',
                'source-sha', 'bands-sha256', 'input-sha256'):
        pre.add_argument('--' + arg, required=True)
    pre.add_argument('--allow-trial', action='store_true', required=True)
    preview = sub.add_parser('manifest-preview', help='generate and validate in memory; never save')
    for arg in ('experiment-id', 'purpose', 'policy', 'scope-json'):
        preview.add_argument('--' + arg, required=True)
    preview.add_argument('--seed', type=int, required=True)
    preview.add_argument('--allow-trial', action='store_true', required=True)
    audit = sub.add_parser('storage-audit', help='read-only storage audit or finalize check')
    audit.add_argument('operation', choices=('audit', 'finalize'))
    audit.add_argument('--experiment-id')
    args = parser.parse_args(argv)
    if args.mode == 'synthetic':
        result = synthetic(args.policy, args.inductors)
    elif args.mode == 'exp-preflight':
        result = exp_preflight(ROOT, args.experiment_id, owner=args.owner, request_id=args.request_id,
                               policy_id=args.policy, policy_sha256=args.policy_sha256,
                               source_sha=args.source_sha, bands_sha256=args.bands_sha256,
                               input_sha256=args.input_sha256, allow_trial=args.allow_trial)
    elif args.mode == 'manifest-preview':
        result = manifest_preview(ROOT, args.experiment_id, args.purpose, json.loads(args.scope_json),
                                  policy_id=args.policy, seed=args.seed, allow_trial=args.allow_trial)
    else:
        result = storage_audit(ROOT, args.operation, args.experiment_id)
    print(json.dumps(result, sort_keys=True, allow_nan=False))


if __name__ == '__main__':
    main()

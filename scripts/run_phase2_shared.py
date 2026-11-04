#!/usr/bin/env python3
"""Shared diagnostic/plan entrypoint with explicit G0/G1-gated run and finalize."""
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
    """Check technical readiness, not Issue scope or user launch; never start an EXP.

    execution_allowed=False describes this read-only entrypoint, not an owner
    authentication failure. Reservation owner is provenance, not authentication.
    """
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
            'storage': report, 'manifest_sha256': canonical_config_hash(manifest),
            'status': 'preflight_ready', 'execution': 'not_run', 'execution_allowed': False,
            'candidate_promotion_blocked': True,
            'next_gate': 'Use a separate driver within the explicit Issue scope and user launch; '
                         'no additional owner authentication is required.'}


def prepare_one_start(root, experiment_id, *, circuit, vector, seed, jitter_fraction,
                      coarse_points, fine_points, budget, **preflight_args):
    """Bind one C1 start to a read-only technical preflight and planned manifest.

    The input_source is the complete one-start description, not a new manifest
    schema. No solver callback is accepted here. A seed is generated once and
    returned for the caller's diagnostic use. Imported code is not authenticated
    in memory; tracked working files are compared to the preflight checkout.
    """
    from dataclasses import asdict
    from lpf.checkpoint_io import canonical_config_hash
    from lpf.experiment_manifest import _environment, file_sha256
    from lpf.constraint_versions import rf_input_file
    from lpf.slsqp_budget import STANDARD_SLSQP_BUDGET, TERMINATION_AWARE_POLICY_ID
    from lpf.phase2_models.api import build_nominal_circuit
    from lpf.phase2_models.problem_seed import definition_fingerprint, vector_fingerprint
    from lpf.phase2_models.sampled_epigraph import SampledEpigraph
    from scripts.audit_new_experiment_storage import find_run, read_json

    root = Path(root).resolve()
    report = exp_preflight(root, experiment_id, **preflight_args)
    manifest = read_json(find_run(root, experiment_id) / 'manifest.json')
    if canonical_config_hash(manifest) != report['manifest_sha256']:
        raise ValueError('Manifest changed after preflight')
    if manifest['objective'] != 'full_lpf' or manifest['execution']['status'] != 'planned':
        raise ValueError('Planned full_lpf manifest required')
    paths = ('src', 'scripts', 'project', 'rf', 'pyproject.toml', 'uv.lock')
    def tracked(repo):
        return subprocess.check_output(['git', 'ls-files', '-z', '--', *paths], cwd=repo).split(b'\0')[:-1]
    names = tracked(ROOT)
    if names != tracked(root) or any(file_sha256(ROOT / n.decode()) != file_sha256(root / n.decode())
                                     for n in names):
        raise ValueError('Executing source/input files differ from preflight checkout')
    if manifest['environment'] != _environment():
        raise ValueError('Manifest environment mismatch')
    c = manifest['constraints']
    if (c['constraint_id'] != circuit.policy_id or
            c['effective_constraint_sha256'] != circuit.policy_fingerprint or
            build_nominal_circuit(c['effective_constraints'], circuit.definition) != circuit):
        raise ValueError('Circuit/policy mismatch')
    if file_sha256(rf_input_file(ROOT, c['effective_constraints']['bands_file'])) != manifest['bands_sha256']:
        raise ValueError('Executing bands mismatch')
    if (type(seed) is not int or seed < 0 or manifest['random_seed'] != seed or
            type(coarse_points) is not int or type(fine_points) is not int or
            coarse_points not in (1, 2, 3) or fine_points not in (1, 2, 3) or fine_points < coarse_points):
        raise ValueError('Seed or diagnostic grid mismatch')
    expected_budget = {**STANDARD_SLSQP_BUDGET.as_dict(), 'policy_id': TERMINATION_AWARE_POLICY_ID}
    if budget != expected_budget:
        raise ValueError('SLSQP v2 budget mismatch')
    vector = list(map(float, vector))
    start = {'definition': asdict(circuit.definition), 'vector': vector,
             'vector_sha256': vector_fingerprint(vector), 'seed': seed,
             'jitter_fraction': jitter_fraction,
             'grids': {'coarse_points': coarse_points, 'fine_points': fine_points},
             'budget': budget}
    # Normalize tuple/list representation and reject NaN/Infinity.
    start = json.loads(json.dumps(start, allow_nan=False))
    scope = manifest['search_scope']
    if (scope['input_source'] != start or
            canonical_config_hash(start) != preflight_args['input_sha256']):
        raise ValueError('Manifest one-start input mismatch')
    circuit.validate_components(vector)
    problem = SampledEpigraph(circuit, coarse_points)
    seed_record = problem.seed(vector, policy_id=circuit.policy_id,
        policy_fingerprint=circuit.policy_fingerprint,
        definition_sha256=definition_fingerprint(circuit.definition),
        input_sha256=start['vector_sha256'], seed=seed, jitter_fraction=jitter_fraction)
    return {'preflight': report, 'input_source': start, 'seed_record': seed_record,
            'seed_preparation': 'coarse_forward_observed_not_rf_validation',
            'status': 'preflight_ready', 'execution': 'not_run', 'execution_allowed': False}


def one_start_gate(root, experiment_id, **kwargs):
    """Return read-only readiness; no callback or solver dispatch exists here.

    Under the explicit Issue scope and user launch, a separate driver may use
    this checked preparation for run_c1_staged(... optimize_stage=scipy_slsqp_stage).
    G0/G1 remain required; no additional owner authentication gate is needed.
    Readiness is not execution, RF validation or completed evidence preservation.
    """
    prepared = prepare_one_start(root, experiment_id, **kwargs)
    return {'mode': 'one_start_gate', 'preflight': prepared['preflight'],
            'seed_preparation': prepared['seed_preparation'],
            'status': 'preflight_ready', 'execution': 'not_run', 'execution_allowed': False,
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
            'execution': 'not_run', 'execution_allowed': False}


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


def prepare_continuation_plan(root, config_path, experiment_id):
    """Explicit reviewed-main-only initialization; writes one ignored prepared plan."""
    import hashlib
    import os
    import yaml
    from lpf.checkpoint_io import atomic_write_json, canonical_config_hash
    from lpf.constraint_versions import load_constraint
    from lpf.phase2_models.api import CircuitDefinition, build_nominal_circuit
    from lpf.phase2_models.circuit_layout import InductorTree, CapacitorPlacement
    from lpf.phase2_models.experiment_config import (_Loader, _check_continuation_reference,
        continuation_program_sha256, ContinuationPreparationError, prepare_continuation_starts,
        prepare_diagnostic_starts, stable_identity)
    from lpf.phase2_models.synthetic_runner import _read
    from scripts.experiment_id_registry import is_reserved_on_main

    root = Path(root).resolve()
    _complete_checkout(root)
    main_sha = _fresh_main(root)
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip()
    if head != main_sha or subprocess.check_output(
            ['git', 'status', '--porcelain', '--untracked-files=all', '--',
             'src', 'scripts', 'project', 'rf', 'pyproject.toml', 'uv.lock'], cwd=root).strip():
        raise ValueError('Preparation requires clean, reviewed origin/main source')
    reservation = is_reserved_on_main(root, experiment_id)
    if reservation.get('constraint_id') != 'RF-T008':
        raise ValueError('Continuation requires an RF-T008 main reservation')
    if any(os.environ.get(key) != '1' for key in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS')):
        raise ValueError('Explicit BLAS/OMP/MKL thread settings of 1 required')
    config_file = (root / config_path).resolve()
    if not config_file.is_relative_to(root):
        raise ValueError('Config outside checkout')
    config_bytes = config_file.read_bytes()
    if subprocess.check_output(['git', 'show', 'origin/main:' + config_file.relative_to(root).as_posix()], cwd=root) != config_bytes:
        raise ValueError('Preparation config differs from origin/main')
    config = yaml.load(config_bytes, Loader=_Loader)
    diagnostic = isinstance(config, dict) and config.get('schema_version') == 5
    if diagnostic:
        expected_keys = {'schema_version', 'rf', 'objective', 'definition_sha256', 'plan',
            'iteration_policy_id', 'grids', 'samples_per_start', 'seeds', 'methods', 'pilot_seeds',
            'selection', 'budgets', 'continuation', 'definition_source', 'topology_reference', 'nominal_source'}
        if (set(config) != expected_keys or config['methods'] != ['Control100', 'Limit10'] or
                config['seeds'] != [23] or config['pilot_seeds'] != [23] or
                config['samples_per_start'] != 500000 or
                config['grids'] != {'coarse_points': 2, 'fine_points': 3} or
                config['iteration_policy_id'] != 'slsqp-staged-v2' or config['objective'] != 'full_lpf' or
                config['definition_sha256'] != 'bc50042a1b0b1ebf19c0272fb2ee944b52cd76e14eb8d44673bfa57f6033c068' or
                config['rf'] != {'id': 'RF-T008', 'allow_trial': True,
                    'effective_sha256': '7de08611f8dd15b40fdfb7946e8c93de5796d026641bdca0f12e992962d05fd4'} or
                config['continuation'] != {'mode': 'opt_in', 'il_only_bands': ['B8', 'B8+B71', 'all'],
                    'thresholds_db': [10, 20], 'stop_after': 'all_20.0', 'scan_points': 17,
                    'gjm_search_max_pf': {'Control100': None, 'Limit10': 10}} or
                config['selection'] != {'intermediate_points': 17, 'dense_points': 0,
                    'independent_points': 0, 'top_k_per_method': 1} or
                config['budgets'] != {'logical_starts': 2, 'actual_starts': 2, 'stages': 80,
                    'optimization_samples': 1000000, 'screen_forwards': 1, 'screen_samples': 56,
                    'intermediate_samples': 952, 'dense_samples': 0} or
                set(config['plan']) != {'path', 'sha256'} or
                not re.fullmatch('[0-9a-f]{64}', config['plan']['sha256'])):
            raise ValueError('Invalid diagnostic preparation contract')
    elif (not isinstance(config, dict) or config.get('schema_version') != 4 or
            config.get('methods') != ['A', 'B', 'C', 'D'] or config.get('seeds') != [0, 23] or
            config.get('pilot_seeds') != [0] or config.get('samples_per_start') != 1_500_000 or
            config.get('grids') != {'coarse_points': 2, 'fine_points': 3} or
            config.get('iteration_policy_id') != 'slsqp-staged-v2' or
            config.get('objective') != 'full_lpf' or
            config.get('definition_sha256') != 'bc50042a1b0b1ebf19c0272fb2ee944b52cd76e14eb8d44673bfa57f6033c068' or
            config.get('rf') != {'id': 'RF-T008', 'allow_trial': True,
                'effective_sha256': '7de08611f8dd15b40fdfb7946e8c93de5796d026641bdca0f12e992962d05fd4'} or
            config.get('rf', {}).get('allow_trial') is not True or
            config.get('continuation') != {'mode': 'opt_in', 'il_only_bands': ['B8', 'B8+B71', 'all'],
                'thresholds_db': [10, 20, 25, 28], 'final_guard_db': 30.005,
                'scan_points': 17, 'max_additions': 4, 'max_rounds': 3} or
            config.get('selection') != {'intermediate_points': 17, 'dense_points': 1001,
                'independent_points': 3, 'top_k_per_method': 2} or
            config.get('budgets') != {'logical_starts': 8, 'actual_starts': 8, 'stages': 296,
                'optimization_samples': 12_000_000, 'screen_forwards': 2, 'screen_samples': 112,
                'intermediate_samples': 3808, 'dense_samples': 224224}):
        raise ValueError('Invalid continuation preparation contract')
    output = (root / config['plan']['path']).resolve()
    if (not output.is_relative_to((root / 'results').resolve()) or output.exists() or
            subprocess.run(['git', 'check-ignore', '-q', '--', str(output.relative_to(root))], cwd=root).returncode):
        raise ValueError('New ignored results path required; never overwrite preparation')
    for key in ('definition_source', 'topology_reference') + (('nominal_source',) if diagnostic else ()):
        ref = config[key]
        path = (root / ref['path']).resolve()
        if not path.is_relative_to(root):
            raise ValueError('Source outside checkout')
        tracked = subprocess.check_output(['git', 'show', 'origin/main:' + path.relative_to(root).as_posix()], cwd=root)
        if tracked != path.read_bytes() or hashlib.sha256(tracked).hexdigest() != ref['sha256']:
            raise ValueError('Source differs from frozen origin/main: ' + key)
    definition = dict(_read(root / config['definition_source']['path']))
    definition['inductor_tree'] = InductorTree(**definition['inductor_tree'])
    definition['capacitor_placement'] = CapacitorPlacement(**definition['capacitor_placement'])
    circuit = build_nominal_circuit(load_constraint(config['rf']['id'], allow_trial=True), CircuitDefinition(**definition))
    _check_continuation_reference(root, config, circuit)
    program_sha = continuation_program_sha256(root)
    # The marker precedes any forward; unknown interruption cannot be retried.
    atomic_write_json(output, dict(state='running', experiment_id=experiment_id,
                                   git_head=head, program_sha256=program_sha), compact=True)
    try:
        prepared = (prepare_diagnostic_starts(root, circuit, config) if diagnostic else
                    prepare_continuation_starts(circuit, config))
    except ContinuationPreparationError as exc:
        atomic_write_json(output, dict(state='failed', experiment_id=experiment_id,
            git_head=head, program_sha256=program_sha,
            exception=dict(type=exc.cause_type, message=str(exc)),
            initialization_cost=exc.cost, initialization_timing=exc.timing), compact=True)
        raise
    prepared['input_source']['preparation_source'] = dict(git_head=head, experiment_id=experiment_id,
        program_sha256=program_sha, definition_source=config['definition_source'],
        topology_reference=config['topology_reference'])
    prepared['input_source'] = stable_identity(prepared['input_source'])
    prepared['input_source_sha256'] = canonical_config_hash(prepared['input_source'])
    atomic_write_json(output, prepared, compact=True)
    return dict(mode='continuation_preparation', path=output.relative_to(root).as_posix(),
                plan_sha256=prepared['input_source_sha256'], initialization_cost=prepared['input_source']['screen_cost'],
                initialization_timing=prepared['input_source']['initialization_timing'], execution='not_run',
                candidate_promotion_blocked=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='mode', required=True)
    diag = sub.add_parser('synthetic', help='bounded explicit mock diagnostic only')
    diag.add_argument('--mock', action='store_true', required=True)
    diag.add_argument('--policy', required=True, choices=('RF-T005', 'RF-T007', 'RF-T008'))
    diag.add_argument('--inductors', required=True, type=int, choices=(3, 4))
    comparison = sub.add_parser('comparison-readiness', help='partial read-only RF-T008 comparison checks; never execute')
    comparison.add_argument('--allow-trial', action='store_true', required=True)
    comparison.add_argument('--config', help='optional proposed comparison YAML; read-only, not G1')
    pre = sub.add_parser('exp-preflight', help='read-only technical readiness checks; never execute')
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
    prepare = sub.add_parser('prepare', help='reviewed-main-only bounded continuation start preparation')
    prepare.add_argument('--config', required=True)
    prepare.add_argument('--experiment-id', required=True)
    plan = sub.add_parser('plan', help='read-only frozen YAML/prepared-plan checks')
    plan.add_argument('--config', required=True)
    run = sub.add_parser('run', help='explicit G0/G1-gated frozen actual starts')
    run.add_argument('--config', required=True)
    run.add_argument('--experiment-id', required=True)
    run.add_argument('--phase', required=True, choices=('pilot', 'remaining'))
    final = sub.add_parser('finalize', help='explicit single-EXP Git commits and existing audit; inspect diff first')
    final.add_argument('--experiment-id', required=True)
    args = parser.parse_args(argv)
    if args.mode == 'synthetic':
        result = synthetic(args.policy, args.inductors)
    elif args.mode == 'comparison-readiness':
        from lpf.phase2_models.comparison_readiness import comparison_readiness
        result = comparison_readiness(ROOT, allow_trial=args.allow_trial)
        if args.config:
            from lpf.phase2_models.experiment_config import load_comparison_preflight
            result['proposed_plan'] = load_comparison_preflight(ROOT, args.config)
    elif args.mode == 'exp-preflight':
        result = exp_preflight(ROOT, args.experiment_id, owner=args.owner, request_id=args.request_id,
                               policy_id=args.policy, policy_sha256=args.policy_sha256,
                               source_sha=args.source_sha, bands_sha256=args.bands_sha256,
                               input_sha256=args.input_sha256, allow_trial=args.allow_trial)
    elif args.mode == 'manifest-preview':
        result = manifest_preview(ROOT, args.experiment_id, args.purpose, json.loads(args.scope_json),
                                  policy_id=args.policy, seed=args.seed, allow_trial=args.allow_trial)
    elif args.mode == 'prepare':
        result = prepare_continuation_plan(ROOT, args.config, args.experiment_id)
    elif args.mode == 'plan':
        from lpf.phase2_models.experiment_config import plan_preview
        result = plan_preview(ROOT, args.config)
    elif args.mode == 'run':
        from lpf.phase2_models.experiment_run import run_plan
        result = run_plan(ROOT, args.config, args.experiment_id, args.phase)
    elif args.mode == 'finalize':
        from scripts.run_phase2_one_start import finalize_experiment
        _complete_checkout(ROOT)
        _fresh_main(ROOT)
        result = finalize_experiment(ROOT, args.experiment_id)
    else:
        result = storage_audit(ROOT, args.operation, args.experiment_id)
    print(json.dumps(result, sort_keys=True, allow_nan=False))


if __name__ == '__main__':
    main()

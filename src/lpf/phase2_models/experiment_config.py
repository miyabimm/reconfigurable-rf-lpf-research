"""Small frozen prepared-start contract; loading never evaluates RF or writes files."""
import math
from dataclasses import asdict
import re
from pathlib import Path

import yaml

from lpf.checkpoint_io import canonical_config_hash
from lpf.constraint_versions import load_constraint, rf_input_file
from lpf.experiment_manifest import file_sha256
from ._grid import ROOT
from .api import CircuitDefinition, build_nominal_circuit
from .circuit_layout import InductorTree, CapacitorPlacement
from .problem_seed import circuit_box, definition_fingerprint, vector_fingerprint
from .synthetic_runner import _read, _unique


def stable_identity(value):
    """Preparation timings are observations, not replayable plan identity."""
    if isinstance(value, dict):
        return {k: stable_identity(v) for k, v in value.items()
                if k not in ('wall_seconds', 'cpu_seconds')}
    if isinstance(value, list):
        return [stable_identity(v) for v in value]
    return value


class _Loader(yaml.SafeLoader):
    pass


def _mapping(loader, node):
    return _unique([(loader.construct_object(k), loader.construct_object(v))
                    for k, v in node.value])


_Loader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _mapping)


def _fields(value, names):
    if not isinstance(value, dict) or set(value) != set(names.split()):
        raise ValueError('Missing/unknown fields; expected: ' + names)


def _number(value, *, positive=False):
    if type(value) not in (int, float) or not math.isfinite(value) or value < 0 or (positive and value == 0):
        raise ValueError('Expected finite nonnegative number')


def _ids(values, *, integers=False):
    if not isinstance(values, list) or not values or len(set(values)) != len(values):
        raise ValueError('Empty/duplicate IDs or seeds')
    for v in values:
        if integers:
            if type(v) is not int or v < 0:
                raise ValueError('Invalid seed')
        elif not isinstance(v, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*', v):
            raise ValueError('Invalid ID')


def load_plan(root, config_path, *, frozen_input=None):
    """Validate frozen vectors, provenance and mapping without RF forwards.

    plan.sha256 hashes stable input_source (not timing or envelope metadata).
    G1 preserves the returned complete executable input in the existing strict
    manifest. With frozen_input, validate only that G1 input and YAML; never
    open the local preparation plan or perform RF. The existing staged C1 API
    deterministically replays each saved seed before optimizer dispatch.
    A prepared plan is not itself G0/G1 or permission to execute.
    """
    root = Path(root).resolve()
    path = Path(config_path)
    path = (root / path).resolve() if not path.is_absolute() else path.resolve()
    if not path.is_relative_to(root):
        raise ValueError('Config must be in checkout')
    config = yaml.load(path.read_text(), Loader=_Loader)
    if not isinstance(config, dict) or type(config.get('schema_version')) is not int or config['schema_version'] not in (1, 2, 3):
        raise ValueError('Unsupported config schema')
    exchange = config['schema_version'] == 3
    _fields(config, 'schema_version rf objective definition_sha256 plan iteration_policy_id grids samples_per_start seeds methods pilot_seeds selection budgets' +
            (' frequency_exchange' if exchange else ''))
    explicit = config['schema_version'] >= 2
    if config['schema_version'] == 2 and config['methods'] != ['physical', 'normalized']:
        raise ValueError('Explicit coordinate comparison requires physical/normalized arms')
    if exchange:
        _fields(config['frequency_exchange'], 'mode scan_points max_additions max_rounds')
        if (config['methods'] != ['baseline', 'exchange'] or
                config['frequency_exchange'] != dict(mode='opt_in', scan_points=17, max_additions=4, max_rounds=3)):
            raise ValueError('Unsupported frequency exchange comparison contract')
    _fields(config['rf'], 'id effective_sha256 allow_trial')
    _fields(config['plan'], 'path sha256')
    _fields(config['grids'], 'coarse_points fine_points')
    _fields(config['selection'], 'intermediate_points dense_points independent_points top_k_per_method')
    _fields(config['budgets'], 'logical_starts actual_starts stages optimization_samples screen_forwards screen_samples intermediate_samples dense_samples')
    if (config['rf']['id'] not in ('RF-T005', 'RF-T008') or config['rf']['allow_trial'] is not True
            or config['objective'] != 'full_lpf' or config['iteration_policy_id'] != 'slsqp-staged-v2'
            or config['grids'] != dict(coarse_points=2, fine_points=3)):
        raise ValueError('Unsupported RF/objective/v2/grid contract')
    for key in ('seeds', 'pilot_seeds'):
        _ids(config[key], integers=True)
    _ids(config['methods'])
    if not set(config['pilot_seeds']) < set(config['seeds']):
        raise ValueError('Pilot must be a proper seed subset')
    if {k: config['selection'][k] for k in ('intermediate_points', 'dense_points', 'independent_points')} != dict(
            intermediate_points=17, dense_points=1001, independent_points=3):
        raise ValueError('Unsupported validation scope')
    for section in ('budgets', 'selection'):
        for v in config[section].values():
            if type(v) is not int:
                raise ValueError('Integer budget required')
            _number(v, positive=True)
    if type(config['samples_per_start']) is not int:
        raise ValueError('Integer sample ceiling required')
    _number(config['samples_per_start'], positive=True)
    for sha in (config['rf']['effective_sha256'], config['definition_sha256'], config['plan']['sha256']):
        if not isinstance(sha, str) or not re.fullmatch('[0-9a-f]{64}', sha):
            raise ValueError('Invalid SHA256')
    plan_path = (root / config['plan']['path']).resolve()
    if not plan_path.is_relative_to(root):
        raise ValueError('Plan outside checkout')
    if frozen_input is None:
        envelope = _read(plan_path)
        source = stable_identity(envelope['input_source'])
        digest = canonical_config_hash(source)
        if digest != config['plan']['sha256'] or digest != envelope['input_source_sha256']:
            raise ValueError('Prepared plan SHA mismatch')
    else:
        _fields(frozen_input, 'config executable_plan rf_inputs config_sha256 plan_sha256')
        if (frozen_input['config'] != config or
                frozen_input['config_sha256'] != canonical_config_hash(config) or
                frozen_input['plan_sha256'] != config['plan']['sha256']):
            raise ValueError('G1 config/plan SHA mismatch')
        source = dict(frozen_input['executable_plan'])
        # G1 includes the full C1 record, not just its hash. Restore the same
        # prepared-start shape for the common validation below, without RF.
        starts = []
        for item in source['actual_starts']:
            _fields(item, 'id vector vector_sha256 seed seed_record seed_record_sha256' +
                    (' coordinates source_ref' if explicit else '') + (' method' if exchange else ''))
            record = item['seed_record']
            if (canonical_config_hash(record) != item['seed_record_sha256'] or
                    record['seed'] != item['seed']):
                raise ValueError('G1 C1 seed record SHA mismatch')
            starts.append(dict(id=item['id'],
                **({k: item[k] for k in ('coordinates', 'source_ref')} if explicit else {}),
                **({'method': item['method']} if exchange else {}),
                start=dict(vector=item['vector'],
                vector_sha256=item['vector_sha256'], seed_record=record,
                policy_id=source['policy_id'], policy_sha256=source['policy_sha256'],
                definition_sha256=source['definition_sha256'], jitter_fraction=0)))
        source['actual_starts'] = starts
        digest = frozen_input['plan_sha256']
    if (source['policy_id'] != config['rf']['id'] or
            source['policy_sha256'] != config['rf']['effective_sha256'] or
            source['objective'] != config['objective'] or source['seeds'] != config['seeds'] or
            source['pilot_seeds'] != config['pilot_seeds']):
        raise ValueError('Plan/config RF or seed mismatch')
    d = dict(source['definition'])
    d['inductor_tree'] = InductorTree(**d['inductor_tree'])
    d['capacitor_placement'] = CapacitorPlacement(**d['capacitor_placement'])
    circuit = build_nominal_circuit(load_constraint(config['rf']['id'], allow_trial=True), CircuitDefinition(**d))
    if (circuit.policy_fingerprint != config['rf']['effective_sha256'] or
            definition_fingerprint(circuit.definition) != config['definition_sha256'] or
            source['definition_sha256'] != config['definition_sha256']):
        raise ValueError('RF or exact definition SHA mismatch')
    limits = source['limits']
    expected = dict(max_starts=config['budgets']['logical_starts'], max_stages=config['budgets']['stages'],
        max_samples_per_start=config['samples_per_start'], max_optimization_samples=config['budgets']['optimization_samples'],
        max_screen_forwards=config['budgets']['screen_forwards'], max_screen_samples=config['budgets']['screen_samples'],
        max_intermediate_samples=config['budgets']['intermediate_samples'], max_dense_samples=config['budgets']['dense_samples'],
        top_k_per_method=config['selection']['top_k_per_method'], **config['grids'],
        iteration_policy_id=config['iteration_policy_id'])
    from lpf.slsqp_budget import STANDARD_SLSQP_BUDGET
    b = STANDARD_SLSQP_BUDGET
    expected.update(coarse_maxiter=b.coarse, fine_maxiter=b.fine,
                    rescue_coarse_maxiter=b.recovery_coarse, rescue_fine_maxiter=b.recovery_fine,
                    max_stages_per_start=12 if exchange else 4)
    if limits != expected:
        raise ValueError('Prepared budget differs from config/standard v2')
    actual, logical = source['actual_starts'], source['logical_starts']
    _ids([r['id'] for r in actual])
    _ids([r['id'] for r in logical])
    budget = config['budgets']
    if (len(logical) != budget['logical_starts'] or len(actual) != budget['actual_starts'] or
            len(actual) > len(logical) or budget['stages'] != (4 * len(logical) * 2 if exchange else 4 * len(logical)) or
            budget['optimization_samples'] != len(logical) * config['samples_per_start']):
        raise ValueError('Start/stage/sample count mismatch')
    by_id, shas = {}, set()
    box = circuit_box(circuit)
    for row in actual:
        _fields(row, 'id start' + (' coordinates source_ref' if explicit else '') + (' method' if exchange else ''))
        start = row['start']
        if explicit:
            if (row['coordinates'] != 'physical' if exchange else row['coordinates'] not in config['methods']):
                raise ValueError('Unknown coordinate mode')
            if exchange and row['method'] not in config['methods']:
                raise ValueError('Unknown exchange method')
            ref = row['source_ref']
            _fields(ref, 'path sha256 vector_sha256' + (' raw_path raw_sha256 summary_path summary_sha256 actual_id' if exchange else ''))
            ref_path = (root / ref['path']).resolve()
            if (not ref_path.is_relative_to(root) or file_sha256(ref_path) != ref['sha256'] or
                    ref['vector_sha256'] != start['vector_sha256']):
                raise ValueError('Explicit source reference SHA mismatch')
            original = _read(ref_path)
            if (original['vector'] != start['vector'] or
                    original['vector_sha256'] != ref['vector_sha256']):
                raise ValueError('Explicit source vector mismatch')
            if exchange:
                for key in ('raw', 'summary'):
                    evidence = (root / ref[key + '_path']).resolve()
                    if not evidence.is_relative_to(root) or file_sha256(evidence) != ref[key + '_sha256']:
                        raise ValueError('Source raw/curated reference SHA mismatch')
                raw = _read(root / ref['raw_path'])
                if canonical_config_hash(raw['body']) != raw['sha256']:
                    raise ValueError('Source raw checksum mismatch')
                source_result = raw['body']['completed'][ref['actual_id']]
                source_final = source_result['staged_record']['stage_calls'][-1]['output_vector']
                from .experiment_run import restore_curated_result
                curated = _read(root / ref['summary_path'])['actual_results'][ref['actual_id']]
                restored = restore_curated_result(curated, raw['body']['input_source'])
                if (source_final != restored['stage_calls'][-1]['output_vector'] or
                        source_final[:-1] != start['vector'] or
                        vector_fingerprint(source_final[:-1]) != ref['vector_sha256']):
                    raise ValueError('Source raw/curated final vector mismatch')
        vector = start['vector']
        sha = vector_fingerprint(vector)
        identity = (sha, row['method'] if exchange else row['coordinates']) if explicit else sha
        if identity in shas or sha != start['vector_sha256'] or len(vector) != circuit.schema.vector_length:
            raise ValueError('Duplicate or invalid actual vector SHA/schema')
        for i, (v, (lo, hi)) in enumerate(zip(vector, box.bounds[:-1])):
            if v < lo or v > hi or (i in box.open_lower and v == lo):
                raise ValueError('Vector outside policy box')
        components = circuit.validate_components(vector)
        if components['connection_role_evidence_incomplete']:
            raise ValueError('Unproven connection role')
        if (start['policy_id'] != circuit.policy_id or start['policy_sha256'] != circuit.policy_fingerprint or
                start['definition_sha256'] != config['definition_sha256'] or
                (frozen_input is None and start['schema_sha256'] != canonical_config_hash(asdict(circuit.schema))) or
                start['jitter_fraction'] != 0):
            raise ValueError('Start provenance mismatch')
        seed = start['seed_record']
        if (not isinstance(seed, dict) or list(seed['input_vector']) != vector or seed['changes'] or
                seed['input_vector_sha256'] != sha or seed['definition_sha256'] != config['definition_sha256'] or
                seed['policy_fingerprint'] != circuit.policy_fingerprint or seed['policy_id'] != circuit.policy_id or
                type(seed['seed']) is not int or seed['seed'] not in config['seeds'] or
                seed['jitter_fraction'] != 0 or seed['points_per_interval'] != 2 or
                list(seed['vector'][:-1]) != vector):
            raise ValueError('C1 seed binding mismatch')
        _number(abs(seed['vector'][-1]))
        by_id[row['id']] = dict(row, seed_record=seed)
        shas.add(identity)
    referenced = set()
    pairs = set()
    group_counts = {}
    common_count = 0
    for row in logical:
        _fields(row, 'id seed method vector_sha256 actual_start_id')
        target = by_id.get(row['actual_start_id'])
        if target is None or row['vector_sha256'] != target['start']['vector_sha256']:
            raise ValueError('Logical/actual binding mismatch')
        if explicit and (row['method'] != (target['method'] if exchange else target['coordinates']) or
                         row['seed'] != target['seed_record']['seed']):
            raise ValueError('Logical coordinate/source binding mismatch')
        if row['method'] == 'common':
            common_count += 1
            if row['seed'] is not None:
                raise ValueError('Common start seed must be null')
        elif row['method'] not in config['methods'] or row['seed'] not in config['seeds']:
            raise ValueError('Unknown comparison group/seed')
        else:
            pair = (row['method'], row['seed'])
            pairs.add(pair)
            group_counts[pair] = group_counts.get(pair, 0) + 1
        referenced.add(row['actual_start_id'])
    if (common_count != (0 if explicit else 1) or len(set(group_counts.values())) != 1 or
            (explicit and (set(group_counts.values()) != {1} or len(actual) != len(logical))) or
            referenced != set(by_id) or
            pairs != {(m, s) for m in config['methods'] for s in config['seeds']}):
        raise ValueError('Incomplete logical/actual or paired seed mapping')
    if explicit:
        for seed in config['seeds']:
            paired = [by_id[r['actual_start_id']] for r in logical if r['seed'] == seed]
            if (len({canonical_config_hash(r['source_ref']) for r in paired}) != 1 or
                    len({canonical_config_hash(r['seed_record']) for r in paired}) != 1):
                raise ValueError('Coordinate arms must share exact source and C1 seed')
    cost = source['screen_cost']
    for v in cost.values():
        _number(v)
    if 'pools' in source:
        pool_pairs = [(p['method'], p['seed']) for p in source['pools']]
        if len(pool_pairs) != len(set(pool_pairs)) or set(pool_pairs) != pairs:
            raise ValueError('Screen pool/paired seed mismatch')
        for key in cost:
            if sum(p['cost'][key] for p in source['pools']) != cost[key]:
                raise ValueError('Aggregate physical screen cost mismatch')
    if (cost['RF_forward_calls'] > budget['screen_forwards'] or
            cost['frequency_samples_requested'] > budget['screen_samples']):
        raise ValueError('Screen budget exceeded')
    # Preserve the complete executable plan in G1, not megabytes of regenerable
    # screening diagnostics. The full preparation is still bound by stable SHA.
    executable = {k: source[k] for k in ('policy_id', 'policy_sha256', 'objective',
        'definition', 'definition_sha256', 'seeds', 'pilot_seeds', 'actual_starts',
        'logical_starts', 'screen_cost', 'limits')}
    executable['screen_by_group'] = (source['screen_by_group'] if frozen_input is not None else
        [dict(seed=p['seed'], method=p['method'], cost=p['cost'], pool_sha256=canonical_config_hash(p))
         for p in source.get('pools', [])])
    executable['actual_starts'] = [dict(id=row['id'],
        **({k: row[k] for k in ('coordinates', 'source_ref')} if explicit else {}),
        **({'method': row['method']} if exchange else {}),
        vector=row['start']['vector'],
        vector_sha256=row['start']['vector_sha256'], seed=row['start']['seed_record']['seed'],
        seed_record=row['start']['seed_record'],
        seed_record_sha256=canonical_config_hash(row['start']['seed_record'])) for row in actual]
    policy = circuit.resolved_policy
    rf_inputs = dict(bands_sha256=file_sha256(rf_input_file(ROOT, policy['bands_file'])), s2p_sha256={})
    for role in ('input_parasitic', 'output_parasitic'):
        spec = policy['external_port_parasitics'][role]
        observed = file_sha256(rf_input_file(ROOT, spec['path']))
        if observed != spec['sha256']:
            raise ValueError('Fixed S2P SHA mismatch')
        rf_inputs['s2p_sha256'][role] = observed
    frozen = dict(config=config, executable_plan=executable, rf_inputs=rf_inputs,
                  config_sha256=canonical_config_hash(config), plan_sha256=digest)
    if frozen_input is not None and frozen != frozen_input:
        raise ValueError('G1 executable input differs from validated RF/plan')
    return dict(circuit=circuit, config=config, actual=by_id, logical=logical,
                input_source=frozen, input_source_sha256=canonical_config_hash(frozen))


def plan_preview(root, config_path):
    loaded = load_plan(root, config_path)
    from .limited_candidate_evidence import _identity
    first = next(iter(loaded['actual'].values()))
    source = _identity(loaded['circuit'], first['start']['vector'])
    return dict(mode='plan_read_only', source=source, input_source=loaded['input_source'],
                input_source_sha256=loaded['input_source_sha256'], execution='not_run',
                g0_reservation='not_verified', g1_manifest='not_verified',
                candidate_promotion_blocked=True)

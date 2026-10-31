"""Bounded deterministic starts and synthetic-only dispatch; never an EXP driver."""
from dataclasses import asdict
import hashlib
import json
from pathlib import Path

import numpy as np
from scipy.stats import qmc

from lpf.checkpoint_io import canonical_config_hash
from .candidate_records import CandidateRecord, recheck_record, pareto_report, _circuit
from .limited_candidate_evidence import _identity
from .problem_seed import circuit_box, definition_fingerprint, vector_fingerprint
from .sampled_epigraph import SampledEpigraph
from .synthetic_plan import make_synthetic_plan
from .synthetic_runner import run_synthetic
from .topology_enumeration import exact_candidate_key


def unique_topologies(circuits):
    """Deduplicate configurations only, before assigning starts (stable order)."""
    seen, result = set(), []
    for circuit in circuits:
        key = (circuit.policy_fingerprint, exact_candidate_key(circuit))
        if key not in seen:
            seen.add(key)
            result.append(circuit)
    return result


def generate_starts(problem, nominal_vector, *, seed, warm_checkpoint=None,
                    warm_sha256=None):
    """Exactly nominal/design (or verified warm) + two scrambled Sobol starts.

    One fixed Sobol block of 16 is inspected, with no clipping, epsilon floor,
    retries or projection across definitions. Insufficient legal distinct starts
    raises with diagnostics. Warm JSON must explicitly bind policy, definition,
    schema and full vector; a length-compatible legacy vector is not sufficient.
    This preparation runs forward diagnostics, not optimization or RF validation.
    """
    if type(seed) is not int or seed < 0:
        raise ValueError('seed must be a nonnegative integer')
    circuit = problem.circuit
    definition_sha = definition_fingerprint(circuit.definition)
    schema_sha = canonical_config_hash(asdict(circuit.schema))
    source = None
    method = 'nominal_design'
    if warm_checkpoint is not None:
        path = Path(warm_checkpoint).resolve()
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != warm_sha256:
            raise ValueError('Warm checkpoint SHA mismatch')
        saved = json.loads(raw)
        if (saved['policy_id'] != circuit.policy_id or
                saved['policy_sha256'] != circuit.policy_fingerprint or
                saved['definition_sha256'] != definition_sha or
                saved['parameter_schema'] != json.loads(json.dumps(asdict(circuit.schema)))):
            raise ValueError('Warm checkpoint policy/topology/schema mismatch')
        nominal_vector = saved['vector']
        if vector_fingerprint(nominal_vector) != saved['vector_sha256']:
            raise ValueError('Warm checkpoint vector SHA mismatch')
        source = {'path': str(path), 'sha256': warm_sha256}
        method = 'verified_warm_checkpoint'
    elif warm_sha256 is not None:
        raise ValueError('Warm SHA without checkpoint')

    starts, seen, rejected = [], set(), []

    def accept(vector, method, index, source=None):
        x = np.asarray(vector, float)
        if x.shape != (circuit.schema.vector_length,):
            raise ValueError('Incomplete vector')
        # Unlike make_seed, this precheck must not silently clip the design.
        for i, (lo, hi) in enumerate(problem.box.bounds[:-1]):
            if not np.isfinite(x[i]) or not lo <= x[i] <= hi:
                raise ValueError('Box violation at index ' + str(i))
        if any(x[i] <= problem.box.bounds[i][0] for i in problem.box.open_lower):
            raise ValueError('Excluded open lower bound')
        component = circuit.validate_components(x)
        if component['connection_role_evidence_incomplete']:
            raise ValueError('Connection role not proven')
        sha = vector_fingerprint(x)
        if sha in seen:
            raise ValueError('Duplicate vector')
        record = problem.seed(x, policy_id=circuit.policy_id,
            policy_fingerprint=circuit.policy_fingerprint,
            definition_sha256=definition_sha, input_sha256=sha, seed=seed)
        if record['changes']:
            raise ValueError('Unexpected seed clipping')
        seen.add(sha)
        starts.append({'id': f'{definition_sha[:12]}-seed-{seed}-start-{len(starts)}',
            'vector': x.tolist(),
            'vector_sha256': sha, 'seed': seed, 'jitter_fraction': 0.0,
            'generation_method': method, 'sobol_index': index,
            'source_checkpoint': source, 'policy_id': circuit.policy_id,
            'policy_sha256': circuit.policy_fingerprint,
            'definition_sha256': definition_sha, 'schema_sha256': schema_sha,
            'seed_record': record})

    accept(nominal_vector, method, None, source)
    bounds = np.asarray(problem.box.bounds[:-1], float)
    block = qmc.Sobol(d=circuit.schema.vector_length, scramble=True, seed=seed).random_base2(4)
    for index, unit in enumerate(block):
        try:
            accept(bounds[:, 0] + unit * (bounds[:, 1] - bounds[:, 0]), 'sobol', index)
        except ValueError as exc:
            rejected.append({'sobol_index': index, 'reason': str(exc)})
        if len(starts) == 3:
            return {'starts': starts, 'rejected': rejected, 'sobol_block_size': 16,
                    'generation_policy': 'nominal-plus-sobol-v1',
                    'candidate_promotion_blocked': True}
    raise ValueError(f'Insufficient legal distinct starts: {len(starts)}/3; {rejected}')


def intermediate_scan(circuit, vector):
    """Read-only 17 points per each of 28 separate intervals; no CandidateRecord."""
    before = _identity(circuit, vector)
    observed = circuit.evaluate_sampled(vector, points_per_interval=17)
    if before != _identity(circuit, vector):
        raise ValueError('Source/input changed during intermediate scan')
    return {'policy_id': circuit.policy_id, 'policy_sha256': circuit.policy_fingerprint,
            'definition_sha256': definition_fingerprint(circuit.definition),
            'vector_sha256': vector_fingerprint(vector), 'identity': before,
            'grid': {'points_per_interval': 17, 'segment_count': 28,
                     'sample_count': 476, 'settings': 6},
            'observation': observed, 'evidence_class': 'forward_only_diagnostic',
            'validation': dict.fromkeys(('dense_rf_1001', 'independent_mna_84',
                'power_balance', 'passivity'), 'not_run'),
            'candidate_promotion_blocked': True, 'rf_compliance_certified': False}


def two_axis_report(records, *, historical_benchmarks):
    """Keep each start, classify with existing strict gates, rank only like for like.

    Historical entries are source-labelled external observations, always shown,
    never inserted into coarse-grid Pareto groups or treated as fresh validation.
    """
    required = {'source', 'policy_id', 'policy_sha256', 'objective',
                'reference_planes', 'grid', 'validation'}
    if not historical_benchmarks or any(not required <= b.keys() or
            any(not b[k] for k in required) for b in historical_benchmarks):
        raise ValueError('Source/condition/grid/depth-labelled historical benchmarks required')
    checked = [recheck_record(r) for r in records]
    for record in checked:
        b = record.as_dict()
        if any((h['policy_id'], h['policy_sha256'], h['objective'], h['reference_planes']) !=
               (b['policy_id'], b['policy_sha256'], b['context']['objective'],
                b['context']['reference_planes']) for h in historical_benchmarks):
            raise ValueError('Historical benchmark RF/objective/reference plane mismatch')
    report = pareto_report(checked)
    bodies = {r.as_dict()['candidate_id']: r.as_dict() for r in checked}
    for row in report['candidates']:
        b = bodies[row['candidate_id']]
        box = circuit_box(_circuit(b))
        x = b['vector']
        box_pass = (all(lo <= value <= hi for value, (lo, hi) in zip(x, box.bounds[:-1]))
                    and all(x[i] > box.bounds[i][0] for i in box.open_lower))
        detail = b['component'].get('detail')
        row.update(box_state='pass' if box_pass else 'fail',
            role_state=('pass' if not detail['connection_role_evidence_incomplete'] else 'fail')
                       if detail else 'not_run',
            spd_state='pass' if detail else 'not_run',
            min_L_eigenvalue_H=detail.get('min_L_eigenvalue_H') if detail else None,
            component_state=b['component']['state'],
            topology_key=b['topology_key'], vector_sha256=b['vector_sha256'],
            numerical_state=b['numerical']['state'], component=b['component'],
            nominal_area=b['nominal_area'],
            policy_id=b['policy_id'], policy_sha256=b['policy_sha256'],
            grid=b['rf'].get('grid'), validation=b['validation'],
            classification='finite_grid_eligible' if not row['reasons'] else 'diagnostic')
    report['historical_benchmarks'] = historical_benchmarks
    report['historical_comparison'] = 'external_only; different grids/depths are not ranked together'
    return report


def run_multistart_preview(circuit, generated, checkpoint, *, optimize_stage,
                           historical_benchmarks, max_new_starts=None):
    """Mock-only 2/3-point dispatch, v2 240/120 with existing bounded recovery.

    Existing synthetic runner supplies atomic markers/readback and kill refusal.
    Stop after a failed callback; do not automatically try another start, including
    on re-entry. Clean boundary stops can resume. No production gate is bypassed:
    EXP dispatch is intentionally absent; future wiring must use G0--G4.
    """
    if max_new_starts is not None and (type(max_new_starts) is not int or max_new_starts < 0):
        raise ValueError('Invalid boundary stop count')
    starts = []
    if len(generated['starts']) < 3:
        raise ValueError('Multistart preview requires at least three prepared starts')
    for item in generated['starts']:
        if (item['policy_sha256'] != circuit.policy_fingerprint or
                item['definition_sha256'] != definition_fingerprint(circuit.definition) or
                item['schema_sha256'] != canonical_config_hash(asdict(circuit.schema))):
            raise ValueError('Generated start policy/topology/schema mismatch')
        origin = item['source_checkpoint']
        if origin is not None and hashlib.sha256(Path(origin['path']).read_bytes()).hexdigest() != origin['sha256']:
            raise ValueError('Warm source changed after generation')
        saved = item['seed_record']
        problem = SampledEpigraph(circuit, saved['points_per_interval'])
        actual = problem.seed(item['vector'], policy_id=circuit.policy_id,
            policy_fingerprint=circuit.policy_fingerprint,
            definition_sha256=item['definition_sha256'],
            input_sha256=item['vector_sha256'], seed=item['seed'], jitter_fraction=0.0)
        if canonical_config_hash(actual) != canonical_config_hash(saved):
            raise ValueError('Generated seed replay mismatch')
        starts.append({k: item[k] for k in ('id', 'vector', 'vector_sha256', 'seed', 'jitter_fraction')})
    source = {'kind': 'synthetic', 'policy_id': circuit.policy_id,
              'vectors': {s['id']: s['vector'] for s in starts}}
    envelope = make_synthetic_plan(circuit, starts,
        run_id='synthetic-multistart-' + canonical_config_hash(generated),
        coarse_points=2, fine_points=3, input_source=source)
    # Preflight benchmark input before any dispatch.
    two_axis_report([], historical_benchmarks=historical_benchmarks)
    if any(h['policy_id'] != circuit.policy_id or
           h['policy_sha256'] != circuit.policy_fingerprint or
           h['objective'] != 'full_lpf_worst_six_setting_UL_DL_external_port_IL' or
           h['reference_planes'] != 'external_input_to_external_output'
           for h in historical_benchmarks):
        raise ValueError('Historical benchmark RF/objective/reference plane mismatch')
    result = run_synthetic(circuit, envelope, checkpoint, optimize_stage=optimize_stage, max_new_starts=0)
    count = 0
    while (result['not_started'] and
           not any(r['numerical']['state'] == 'failed' for r in result['completed']) and
           (max_new_starts is None or count < max_new_starts)):
        result = run_synthetic(circuit, envelope, checkpoint, optimize_stage=optimize_stage, max_new_starts=1)
        count += 1
    result = run_synthetic(circuit, envelope, checkpoint, optimize_stage=optimize_stage, max_new_starts=0)
    records = [CandidateRecord.from_json(json.dumps(r, allow_nan=False)) for r in result['completed']]
    counts = dict(planned=len(starts), attempted=len(records), converged=0,
                  nonconverged=0, failed=0, not_started=result['not_started'])
    for record in records:
        state = record.as_dict()['numerical']['state']
        counts['nonconverged' if state == 'not_converged' else state] += 1
    return {'mode': 'synthetic_mock', 'attempts': counts, 'result': result,
            'generated': generated, 'plan_fingerprint': envelope['fingerprint'],
            'report': two_axis_report(records, historical_benchmarks=historical_benchmarks),
            'experiment_execution': 'not_run', 'git_readback': 'not_run',
            'storage_audit': 'not_run', 'execution_allowed': False,
            'candidate_promotion_blocked': True, 'rf_compliance_certified': False}

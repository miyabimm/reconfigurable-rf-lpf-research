#!/usr/bin/env python3
"""Issue #250 G0 preparation only: no EXP reservation, mutation or optimizer.

Historical vectors are used solely for read-only reference verification. All
comparison starts derive from the policy box midpoint and fixed Sobol blocks.
Output belongs in ignored results/, not in historical EXP directories.
"""
import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'src'))

from lpf.checkpoint_io import atomic_write_json, canonical_config_hash
from lpf.constraint_versions import load_constraint
from lpf.phase2_models.api import CircuitDefinition, build_nominal_circuit
from lpf.phase2_models.circuit_layout import CapacitorPlacement, InductorTree
from lpf.phase2_models.evaluation_cost import EvaluationCost
from lpf.phase2_models.limited_candidate_evidence import recompute_limited_evidence
from lpf.phase2_models.multistart import generate_starts
from lpf.phase2_models.problem_seed import circuit_box, definition_fingerprint, vector_fingerprint
from lpf.phase2_models.sampled_epigraph import SampledEpigraph
from scripts.run_phase2_shared import _complete_checkout, _fresh_main

POLICY_SHA = '7de08611f8dd15b40fdfb7946e8c93de5796d026641bdca0f12e992962d05fd4'
REFERENCE = 'experiments/chatgpt_topology_search/runs/EXP-062/'
REFERENCE_SHA = {
    'checkpoints/a6_best.json': '4fbd86e8b46ad7bcb550ba327672b0983e8b58e9ce4b2a9364f8c6557a812b4b',
    'manifest.json': '9b5301ffc24bd1130fb7263b61626fff902ff378f23e92c180fc3c3876cb3f3a',
    'validation/a6_best_mna.json': '65a0e12fb8da7b36586c70c0b7dccb2cf58cddcf6b8d2b368c6873ef77a96889',
}
LIMITS = dict(max_starts=73, max_stages=292, max_samples_per_start=1_500_000,
              max_optimization_samples=109_500_000, max_screen_forwards=444,
              max_screen_samples=24_864, max_intermediate_samples=34_748,
              max_dense_samples=448_448, top_k_per_method=5,
              coarse_points=2, fine_points=3, coarse_maxiter=240,
              fine_maxiter=120, rescue_coarse_maxiter=500, rescue_fine_maxiter=280,
              max_stages_per_start=4, iteration_policy_id='slsqp-staged-v2')


def comparison_circuit():
    """Frozen electrical ordering, signed k slots and physical row; never project."""
    definition = CircuitDefinition(
        InductorTree(5, ((0, 1), (1, 3), (1, 4), (1, 2))),
        ('LQP02HV',) * 4, (0, 1, 3, 2), ((0, 1), (1, 3), (3, 2)),
        CapacitorPlacement(5, ((0, 1), (4, -1), (1, 2), (3, -1)),
                           ((0, 3), (1, 2)), ((0, 3), (1, 2))),
        ('GJM01',) * 3 + ('PCB_PATTERN_C',), ('bridge', 'bridge'))
    circuit = build_nominal_circuit(load_constraint('RF-T008', allow_trial=True), definition)
    if circuit.policy_fingerprint != POLICY_SHA:
        raise ValueError('Issue #250 requires the frozen RF-T008 rev3 policy')
    return circuit


def verify_reference(root, circuit):
    """Fail before pool generation on any source or present-forward mismatch."""
    sources = {}
    for name, expected in REFERENCE_SHA.items():
        path = REFERENCE + name
        raw = (root / path).read_bytes()
        if hashlib.sha256(raw).hexdigest() != expected:
            raise ValueError('Historical reference SHA mismatch: ' + path)
        remote = subprocess.check_output(['git', 'show', 'origin/main:' + path], cwd=root)
        if raw != remote:
            raise ValueError('Historical reference differs from main: ' + path)
        sources[path] = expected
    saved = json.loads((root / (REFERENCE + 'checkpoints/a6_best.json')).read_bytes())
    vector = saved['vector']
    component = circuit.validate_components(vector)
    if component['connection_role_evidence_incomplete']:
        raise ValueError('Reference connection role not proven')
    dense = circuit.forward_evaluator(1001).summary(vector)
    keys = ('worst_IL_db', 'min_H2_db', 'min_H3_db')
    if any(abs(dense[k] - saved['metrics'][k]) > 1e-9 for k in keys):
        raise ValueError('Historical reference incompatible with current forward')
    independent = recompute_limited_evidence(circuit, vector, 3)
    return dict(sources=sources, vector_sha256=vector_fingerprint(vector),
                components=component, dense_1001=dense,
                independent_mna_84=independent, use='external_reference_only_not_a_start')


def _stable_plan_identity(value):
    """Exclude measured timing from the replayable preparation identity."""
    if isinstance(value, dict):
        return {key: _stable_plan_identity(item) for key, item in value.items()
                if key not in ('wall_seconds', 'cpu_seconds')}
    if isinstance(value, list):
        return [_stable_plan_identity(item) for item in value]
    return value


def prepare(root):
    root = Path(root).resolve()
    _complete_checkout(root)
    main_sha = _fresh_main(root)
    circuit = comparison_circuit()
    reference = verify_reference(root, circuit)
    bounds = np.asarray(circuit_box(circuit).bounds[:-1], float)
    nominal = bounds.mean(axis=1)  # symmetric k bounds give exactly zero
    component = circuit.validate_components(nominal)
    if component['connection_role_evidence_incomplete']:
        raise ValueError('Midpoint nominal connection role not proven')
    problem = SampledEpigraph(circuit, 2)
    logical, actual, pools, seen = [], [], [], {}
    total = EvaluationCost()
    for seed in range(23, 35):
        for method in ('D', 'A', 'B'):
            meter = EvaluationCost()
            kwargs = {} if method == 'D' else dict(
                selection='rf_pareto', max_initial_samples=952,
                candidate_pool='physical_transform' if method == 'B' else 'sobol')
            wall, cpu = time.perf_counter(), time.process_time()
            generated = generate_starts(problem, nominal, seed=seed,
                                        cost_meter=meter, **kwargs)
            # RF selection already times its inner candidates; report whole
            # screen elapsed time once rather than nesting additive timers.
            meter.wall_seconds = time.perf_counter() - wall
            meter.cpu_seconds = time.process_time() - cpu
            cost = meter.snapshot()
            if (cost['RF_forward_calls'] > (3 if method == 'D' else 17) or
                    cost['frequency_samples_requested'] > (168 if method == 'D' else 952)):
                raise ValueError('Screen ceiling exceeded')
            for key, value in cost.items():
                setattr(total, key, getattr(total, key) + value)
            pools.append(dict(seed=seed, method=method, cost=cost, generated=generated))
            for index, start in enumerate(generated['starts']):
                if index == 0 and (seed != 23 or method != 'D'):
                    if start['vector_sha256'] != vector_fingerprint(nominal):
                        raise ValueError('Common nominal changed')
                    continue
                sha = start['vector_sha256']
                start_id = 'nominal' if index == 0 else f'{method}-{seed}-{index}'
                if sha not in seen:
                    seen[sha] = start_id
                    actual.append(dict(id=start_id, start=start))
                logical.append(dict(id=start_id, seed=seed if index else None,
                                    method=method if index else 'common',
                                    vector_sha256=sha, actual_start_id=seen[sha]))
    if len(logical) != 73 or len(actual) > 73:
        raise ValueError('Incomplete start mapping')
    if (total.RF_forward_calls > LIMITS['max_screen_forwards'] or
            total.frequency_samples_requested > LIMITS['max_screen_samples']):
        raise ValueError('Aggregate screen ceiling exceeded')
    source = dict(
        issue=250, policy_id='RF-T008', policy_sha256=POLICY_SHA, objective='full_lpf',
        definition=asdict(circuit.definition), definition_sha256=definition_fingerprint(circuit.definition),
        nominal=dict(rule='all legal policy box midpoints, signed k=0; no checkpoint values',
                     vector=nominal.tolist(), vector_sha256=vector_fingerprint(nominal),
                     components=component), limits=LIMITS, seeds=list(range(23, 35)),
        pilot_seeds=[23, 24], logical_starts=logical, actual_starts=actual,
        pools=pools, screen_cost=total.snapshot(), reference=reference)
    return dict(schema='issue250-preparation-v1', main_sha=main_sha,
                input_source=source,
                input_source_sha256=canonical_config_hash(_stable_plan_identity(source)),
                execution='not_run', g0_reservation='not_run', g1_manifest='not_run',
                g2_review='required', limitations=[
                    'Preparation is not a G0/G1 PASS or permission to bypass independent review.',
                    'No SLSQP, EXP reservation, G2 pilot, or result selection performed.',
                    'Finite-grid reference agreement is not continuous-band/physical certification.'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    if not output.is_relative_to(ROOT / 'results') or output.exists():
        parser.error('output must be a new file under ignored results/')
    atomic_write_json(output, prepare(ROOT))
    print(output)


if __name__ == '__main__':
    main()

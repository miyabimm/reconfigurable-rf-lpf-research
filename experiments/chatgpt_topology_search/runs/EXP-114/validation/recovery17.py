#!/usr/bin/env python3
"""EXP-114 one-shot 17-point recovery. No optimizer, retries or marker resets."""
import csv
import hashlib
import json
import math
import os
from pathlib import Path
import sys
from copy import copy

import numpy as np

ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'src'))
from lpf.checkpoint_io import atomic_write_json, canonical_config_hash
from lpf.phase2_models.evaluation_cost import SampleBudgetCost
from lpf.phase2_models.experiment_run import _load_g1_plan, _gate, restore_curated_result, _curated_result
from lpf.phase2_models.problem_seed import circuit_box, vector_fingerprint
from scripts.audit_new_experiment_storage import validate_run

RUN = ROOT / 'experiments/chatgpt_topology_search/runs/EXP-114'
RAW = ROOT / 'results/EXP-114'
ATTEMPT = RAW / 'validation17-recovery-1.json'
IDS = ('B-31-1-physical', 'B-31-1-normalized', 'B-28-1-physical', 'B-28-1-normalized')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def preflight():
    if any(os.environ.get(k) != '1' for k in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS')):
        raise ValueError('single-thread environment required')
    if ATTEMPT.exists():
        raise ValueError('existing recovery attempt; no retry')
    paths = [RAW / 'run.json', RAW / 'validation17-progress.json',
             ROOT / 'results/EXP-114-pilot.log', ROOT / 'results/EXP-114-remaining.log']
    fingerprints = {str(p.relative_to(ROOT)): sha(p) for p in paths}
    stop = json.loads((RUN / 'validation/validation17-stop.json').read_text())
    old = json.loads(paths[1].read_text())
    if old != stop['raw_progress_snapshot']:
        raise ValueError('original marker differs from preserved STOP evidence')
    saved = json.loads(paths[0].read_text())
    if canonical_config_hash(saved['body']) != saved['sha256']:
        raise ValueError('raw checksum mismatch')
    state = saved['body']
    if (state['in_progress'] is not None or state['completed_phases'] != ['pilot', 'remaining']
            or set(state['completed']) != set(IDS)):
        raise ValueError('raw outcomes incomplete or unknown')
    loaded = _load_g1_plan(ROOT, 'project/experiments/issue259.yaml', 'EXP-114')
    gate = _gate(ROOT, 'EXP-114', loaded, resuming=True)
    validate_run(ROOT, 'EXP-114', mode='audit')
    if (state['identity']['g1_sha256'] != gate['g1_sha256'] or
            state['identity']['input_source_sha256'] != loaded['input_source_sha256'] or
            state['input_source'] != loaded['input_source'] or
            state['identity']['source_provenance']['git_head'] != gate['source_sha'] or
            state['identity']['source_provenance']['thread_environment'] != {
                k: '1' for k in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS')}):
        raise ValueError('raw G1/source/environment identity mismatch')
    summary = json.loads((RUN / 'run_summary.json').read_text())
    vectors = {}
    for key in IDS:
        raw = state['completed'][key]
        restored = restore_curated_result(summary['actual_results'][key], loaded['input_source'])
        if restored != _curated_result(raw):
            raise ValueError('curated/raw stage mismatch: ' + key)
        final = restored['stage_calls'][-1]['output_vector']
        raw_final = raw['staged_record']['stage_calls'][-1]['output_vector']
        if (len(final) != 26 or final != raw_final or
                vector_fingerprint(final[:-1]) != vector_fingerprint(raw_final[:-1])):
            raise ValueError('final stage vector/SHA mismatch: ' + key)
        vectors[key] = final[:-1]
        start = loaded['actual'][key]['start']['vector']
        if vector_fingerprint(start) != loaded['actual'][key]['source_ref']['vector_sha256']:
            raise ValueError('G1 source vector mismatch')
        cost = raw['staged_record']['evaluation_cost']
        if cost['frequency_samples_requested'] != cost['frequency_samples_completed'] or cost['frequency_samples_requested'] > 750000:
            raise ValueError('optimization cost mismatch')
    return loaded, gate, state, vectors, fingerprints


def execute(loaded, gate, state, vectors, fingerprints):
    meter = SampleBudgetCost(1904)
    record = {'attempt': 'EXP-114-validation17-recovery-1', 'status': 'running',
              'original_raw_sha256': fingerprints, 'source_script_sha256': sha(Path(__file__)),
              'main_sha': gate['main_sha'], 'g1_sha256': gate['g1_sha256'],
              'in_progress': None, 'completed': [], 'cost': meter.snapshot()}
    atomic_write_json(ATTEMPT, record)
    circuit = loaded['circuit']
    box = circuit_box(circuit)
    with (ROOT / 'rf/bands.csv').open(newline='') as f:
        bands = list(csv.DictReader(f))
    try:
        for key in IDS:
            record['in_progress'] = key
            atomic_write_json(ATTEMPT, record)
            vector = vectors[key]
            start = loaded['actual'][key]['start']['vector']
            before = meter.snapshot()
            component = meter.components(circuit, vector)
            evaluator = circuit.forward_evaluator(17)
            if len(evaluator.f) != 476:
                raise ValueError('unexpected grid sample count')
            class Hook:
                f = evaluator.f
                def il(self, x):
                    # SampleBudgetCost has charged actual entry before this hook.
                    record['cost'] = meter.snapshot()
                    atomic_write_json(ATTEMPT, record)
                    return evaluator.il(x)
            with meter.timed():
                y = meter.forward(Hook(), vector)
            segments = []
            for i, row in enumerate(bands):
                ix = np.flatnonzero(evaluator.segment == i)
                j = int(ix[np.argmax(y[ix]) if row['type'] == 'pass' else np.argmin(y[ix])])
                segments.append({'segment': i, 'case': row['case'], 'setting': row['case'],
                    'region': row['region'], 'subband': row['note'],
                    'frequency_mhz': float(evaluator.f[j]), 'il_db': float(y[j])})
            def worst(regions, maximize):
                subset = [s for s in segments if s['region'] in regions]
                return (max if maximize else min)(subset, key=lambda s: s['il_db'])
            locations = {'pass_il': worst(('UL', 'DL'), True), 'H2': worst(('H2',), False),
                         'H3': worst(('H3',), False)}
            metrics = {'worst_IL_db': locations['pass_il']['il_db'], 'min_H2_db': locations['H2']['il_db'],
                       'min_H3_db': locations['H3']['il_db']}
            box_pass = all(lo <= v <= hi for v, (lo, hi) in zip(vector, box.bounds[:-1])) and all(vector[i] > box.bounds[i][0] for i in box.open_lower)
            role_pass = not component['connection_role_evidence_incomplete']
            physical = bool(box_pass and role_pass and component['component_policy_pass'] and component['min_L_eigenvalue_H'] > 0)
            strict = metrics['min_H2_db'] >= 30 and metrics['min_H3_db'] >= 30
            source = json.loads((ROOT / loaded['actual'][key]['source_ref']['path']).read_text())
            distance = math.sqrt(sum(((x - s) / (hi - lo)) ** 2 for x, s, (lo, hi) in zip(vector, start, box.bounds[:-1])))
            result = {'experiment_id': 'EXP-114', 'actual_id': key, 'coordinates': loaded['actual'][key]['coordinates'],
                'source_ref': loaded['actual'][key]['source_ref'], 'vector': vector, 'vector_sha256': vector_fingerprint(vector),
                'final_stage_output_sha256': canonical_config_hash(state['completed'][key]['staged_record']['stage_calls'][-1]['output_vector']),
                'metrics': metrics, 'locations': locations, 'segments': segments, 'component': component,
                'box_pass': box_pass, 'role_pass': role_pass, 'physical_pass': physical, 'strict30_pass': strict,
                'max_attenuation_deficit_db': max(0., 30 - metrics['min_H2_db'], 30 - metrics['min_H3_db']),
                'normalized_vector_distance': distance,
                'il_delta_vs_source_17_db': metrics['worst_IL_db'] - source['metrics']['worst_IL_db'],
                'external_exp062_reference_il_db': 0.8278411484628513,
                'il_delta_vs_external_reference_db': metrics['worst_IL_db'] - 0.8278411484628513,
                'grid': {'points_per_interval': 17, 'segments': 28, 'frequency_samples': 476, 'settings': 6},
                'evaluation_cost': {k: v - before[k] for k, v in meter.snapshot().items()},
                'evidence_class': 'forward_only_finite_grid', 'dense1001': 'not_run',
                'independent_mna_power_passivity': 'not_run', 'candidate_promotion_blocked': True}
            path = RUN / 'validation' / (key + '-grid17.json')
            if path.exists():
                raise ValueError('existing overlay; no overwrite')
            atomic_write_json(path, result)
            record['completed'].append({'id': key, 'path': str(path.relative_to(ROOT)), 'sha256': sha(path),
                                        'vector_sha256': vector_fingerprint(vector)})
            record['in_progress'] = None
            record['cost'] = meter.snapshot()
            atomic_write_json(ATTEMPT, record)
            print(key, metrics, 'strict30', strict, 'physical', physical, flush=True)
        if sha(RAW / 'validation17-progress.json') != fingerprints['results/EXP-114/validation17-progress.json']:
            raise ValueError('original STOP marker changed')
        if meter.frequency_samples_requested != 1904 or meter.frequency_samples_completed != 1904:
            raise ValueError('17-point cost mismatch')
        record['status'] = 'complete'
        record['cost'] = meter.snapshot()
        atomic_write_json(ATTEMPT, record)
    except BaseException as exc:
        record['status'] = 'failed_or_interrupted'
        record['exception'] = {'type': type(exc).__name__, 'message': str(exc)}
        record['cost'] = meter.snapshot()
        atomic_write_json(ATTEMPT, record)
        raise


if __name__ == '__main__':
    args = sys.argv[1:]
    if args not in (['--preflight'], ['--execute']):
        raise SystemExit('use --preflight or --execute')
    checked = preflight()
    print('read-only preflight PASS', {k: vector_fingerprint(v) for k, v in checked[3].items()}, flush=True)
    if args == ['--execute']:
        execute(*checked)

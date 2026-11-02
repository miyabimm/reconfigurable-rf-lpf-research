#!/usr/bin/env python3
"""EXP-115 one-shot read-only final 17-point scan; no solver and no retries."""
import csv
import hashlib
import json
import os
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'src'))
from lpf.checkpoint_io import atomic_write_json, canonical_config_hash
from lpf.phase2_models.evaluation_cost import SampleBudgetCost
from lpf.phase2_models.experiment_run import _load_g1_plan, _gate, restore_curated_result, _curated_result
from lpf.phase2_models.problem_seed import circuit_box, vector_fingerprint
from scripts.audit_new_experiment_storage import validate_run

RUN = ROOT / 'experiments/chatgpt_topology_search/runs/EXP-115'
RAW = ROOT / 'results/EXP-115'
PROGRESS = RAW / 'validation17-progress.json'
IDS = ('B-31-1-baseline', 'B-31-1-exchange', 'B-28-1-baseline', 'B-28-1-exchange')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def preflight():
    if any(os.environ.get(k) != '1' for k in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS')):
        raise ValueError('single-thread environment required')
    if PROGRESS.exists():
        raise ValueError('existing validation marker; no retry')
    raw_path = RAW / 'run.json'
    raw = json.loads(raw_path.read_text())
    if canonical_config_hash(raw['body']) != raw['sha256']:
        raise ValueError('raw checksum mismatch')
    state = raw['body']
    if (state['in_progress'] is not None or state['completed_phases'] != ['pilot', 'remaining']
            or set(state['completed']) != set(IDS)):
        raise ValueError('raw outcomes incomplete or unknown')
    loaded = _load_g1_plan(ROOT, 'project/experiments/issue263.yaml', 'EXP-115')
    gate = _gate(ROOT, 'EXP-115', loaded, resuming=True)
    validate_run(ROOT, 'EXP-115', mode='audit')
    if (state['identity']['g1_sha256'] != gate['g1_sha256'] or
            state['identity']['input_source_sha256'] != loaded['input_source_sha256'] or
            state['input_source'] != loaded['input_source'] or
            state['identity']['source_provenance']['git_head'] != gate['source_sha'] or
            state['identity']['source_provenance']['thread_environment'] != {
                k: '1' for k in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS')}):
        raise ValueError('raw G1/source/environment identity mismatch')
    summary = json.loads((RUN / 'run_summary.json').read_text())
    vectors = {}
    total = 0
    for key in IDS:
        result = state['completed'][key]
        staged = result['staged_record']
        trace = result['frequency_exchange']
        if staged['numerical_state'] not in ('converged', 'not_converged'):
            raise ValueError('No completed terminal vector: ' + key)
        restored = restore_curated_result(summary['actual_results'][key], loaded['input_source'])
        if restored != _curated_result(result):
            raise ValueError('curated/raw stage mismatch: ' + key)
        final = restored['stage_calls'][-1]['output_vector']
        if (len(final) != 26 or final != staged['stage_calls'][-1]['output_vector'] or
                final != trace['final_vector']):
            raise ValueError('final x/t binding mismatch: ' + key)
        vector = final[:-1]
        if vector_fingerprint(vector) != vector_fingerprint(staged['stage_calls'][-1]['output_vector'][:-1]):
            raise ValueError('final physical vector SHA mismatch: ' + key)
        cost = staged['evaluation_cost']
        if cost != trace['evaluation_cost'] or cost['frequency_samples_requested'] != cost['frequency_samples_completed'] or cost['frequency_samples_requested'] > 750000:
            raise ValueError('optimization cost mismatch: ' + key)
        total += cost['frequency_samples_requested']
        vectors[key] = vector
    if total > 3000000 or total != summary['costs']['physical_optimization']['frequency_samples_requested']:
        raise ValueError('aggregate optimization budget mismatch')
    return loaded, gate, state, vectors, sha(raw_path)


def execute(loaded, gate, state, vectors, raw_sha):
    meter = SampleBudgetCost(1904)
    progress = {'experiment_id': 'EXP-115', 'purpose': 'independent_final_17_forward',
                'status': 'running', 'in_progress': None, 'completed': [],
                'raw_sha256': raw_sha, 'script_sha256': sha(Path(__file__)),
                'main_sha': gate['main_sha'], 'g1_sha256': gate['g1_sha256'],
                'cost': meter.snapshot()}
    atomic_write_json(PROGRESS, progress)
    circuit, box = loaded['circuit'], circuit_box(loaded['circuit'])
    with (ROOT / 'rf/bands.csv').open(newline='') as f:
        bands = list(csv.DictReader(f))
    try:
        for key in IDS:
            progress['in_progress'] = key
            atomic_write_json(PROGRESS, progress)
            vector = vectors[key]
            before = meter.snapshot()
            component = meter.components(circuit, vector)
            evaluator = circuit.forward_evaluator(17)
            if len(evaluator.f) != 476 or len(bands) != 28:
                raise ValueError('unexpected 17-point grid')
            class Hook:
                f = evaluator.f
                def il(self, x):
                    progress['cost'] = meter.snapshot()
                    atomic_write_json(PROGRESS, progress)
                    return evaluator.il(x)
            with meter.timed():
                y = meter.forward(Hook(), vector)
            if not np.all(np.isfinite(y)):
                raise ValueError('nonfinite 17-point result')
            segments = []
            for i, row in enumerate(bands):
                ix = np.flatnonzero(evaluator.segment == i)
                if len(ix) != 17:
                    raise ValueError('unexpected segment size')
                j = int(ix[np.argmax(y[ix]) if row['type'] == 'pass' else np.argmin(y[ix])])
                segments.append({'segment': i, 'case': row['case'], 'region': row['region'],
                                 'subband': row['note'], 'frequency_mhz': float(evaluator.f[j]),
                                 'il_db': float(y[j])})
            def worst(regions, maximize):
                subset = [s for s in segments if s['region'] in regions]
                return (max if maximize else min)(subset, key=lambda s: s['il_db'])
            locations = {'pass_il': worst(('UL', 'DL'), True), 'H2': worst(('H2',), False),
                         'H3': worst(('H3',), False)}
            metrics = {'worst_IL_db': locations['pass_il']['il_db'],
                       'min_H2_db': locations['H2']['il_db'], 'min_H3_db': locations['H3']['il_db']}
            box_pass = all(lo <= v <= hi for v, (lo, hi) in zip(vector, box.bounds[:-1])) and all(vector[i] > box.bounds[i][0] for i in box.open_lower)
            role_pass = not component['connection_role_evidence_incomplete']
            physical = bool(box_pass and role_pass and component['component_policy_pass'] and component['min_L_eigenvalue_H'] > 0)
            strict = metrics['min_H2_db'] >= 30 and metrics['min_H3_db'] >= 30
            baseline_il = state['completed'][key]['frequency_exchange']['initial_worst_il_db']
            result = {'experiment_id': 'EXP-115', 'actual_id': key,
                      'method': loaded['actual'][key]['method'], 'coordinates': 'physical',
                      'source_ref': loaded['actual'][key]['source_ref'],
                      'vector': vector, 'vector_sha256': vector_fingerprint(vector),
                      'final_stage_output_sha256': canonical_config_hash(state['completed'][key]['staged_record']['stage_calls'][-1]['output_vector']),
                      'metrics': metrics, 'locations': locations, 'segments': segments,
                      'component': component, 'box_pass': box_pass, 'role_pass': role_pass,
                      'physical_pass': physical, 'strict30_pass': strict,
                      'max_attenuation_deficit_db': max(0., 30 - metrics['min_H2_db'], 30 - metrics['min_H3_db']),
                      'initial_worst_IL_17_db': baseline_il, 'delta_IL_17_db': metrics['worst_IL_db'] - baseline_il,
                      'low_IL_maintained_experiment_label': bool(metrics['worst_IL_db'] - baseline_il <= 0.05),
                      'grid': {'points_per_interval': 17, 'segments': 28, 'frequency_samples': 476, 'settings': 6},
                      'evaluation_cost': {k: v - before[k] for k, v in meter.snapshot().items()},
                      'evidence_class': 'separate_final_forward_only_finite_grid',
                      'dense1001': 'not_run', 'independent_mna_power_passivity': 'not_run',
                      'candidate_promotion_blocked': True}
            path = RUN / 'validation' / (key + '-grid17.json')
            if path.exists():
                raise ValueError('existing overlay; no overwrite')
            atomic_write_json(path, result)
            progress['completed'].append({'id': key, 'path': str(path.relative_to(ROOT)),
                                          'sha256': sha(path), 'vector_sha256': vector_fingerprint(vector)})
            progress['in_progress'] = None
            progress['cost'] = meter.snapshot()
            atomic_write_json(PROGRESS, progress)
            print(key, metrics, 'strict30', strict, 'physical', physical, flush=True)
        if sha(RAW / 'run.json') != raw_sha:
            raise ValueError('optimization raw changed')
        if meter.frequency_samples_requested != 1904 or meter.frequency_samples_completed != 1904:
            raise ValueError('17-point cost mismatch')
        progress['status'] = 'complete'
        progress['cost'] = meter.snapshot()
        atomic_write_json(PROGRESS, progress)
    except BaseException as exc:
        progress['status'] = 'failed_or_interrupted'
        progress['exception'] = {'type': type(exc).__name__, 'message': str(exc)}
        progress['cost'] = meter.snapshot()
        atomic_write_json(PROGRESS, progress)
        raise


if __name__ == '__main__':
    if sys.argv[1:] not in (['--preflight'], ['--execute']):
        raise SystemExit('use --preflight or --execute')
    checked = preflight()
    print('read-only preflight PASS', {k: vector_fingerprint(v) for k, v in checked[3].items()}, flush=True)
    if sys.argv[1:] == ['--execute']:
        execute(*checked)

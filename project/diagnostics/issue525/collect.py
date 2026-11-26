#!/usr/bin/env python3
"""Audit complete standard CLI outputs and produce compact paired observations."""
import csv
import hashlib
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'src'))
from lpf.search.storage import sha, vector_sha


def load(path):
    return json.loads(path.read_text())


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def collect(inputs, raw):
    manifest = load(inputs / 'manifest.json')
    bands = list(csv.DictReader((ROOT / 'rf/bands.csv').open()))
    rows, identities, plans = [], {}, {}
    for arm in ('baseline', 'limited'):
        directory = raw / arm
        plan, state = load(directory / 'plan.json'), load(directory / 'run.json')
        meta = manifest['arms'][arm]
        assert all(digest(inputs / arm / name) == h for name, h in meta['files'].items())
        assert state['status'] == 'completed' and sha(plan) == state['plan_sha256'] == meta['plan_sha256']
        assert state['plan_raw'] == {'bytes': (directory / 'plan.json').stat().st_size, 'sha256': digest(directory / 'plan.json')}
        assert plan['search_bounds'] == load(inputs / arm / 'bounds.json')
        assert sha(plan['search_bounds']) == plan['search_bounds_sha256'] == meta['bounds_sha256']
        assert plan['rf_profile']['effective_sha256'] == manifest['profile_sha256']
        assert plan['spot_checks'] == {'terminal': [0, 111]}
        assert plan['config']['seeds'] == list(range(1001, 1021))
        assert plan['config']['budget'] == {k: 20*v for k, v in manifest['per_job'].items()}
        for stage, count in (('baseline/search', 70), ('terminal', 476)):
            g = plan['grids'][stage]
            assert g['sha256'] == meta['grid_sha256'][stage] and len(g['frequency_hz']) == count
            assert set(g['setting']) == set(range(6)) and set(g['segment']) == set(range(28))
        step_config = plan['config']['arms'][0]['steps'][0]
        assert (step_config['solver'], step_config['objective'], step_config['aggregation'], step_config['effective_options']) == ('trf', 'signed_margin_db', 'sum', {'max_evaluations': 5000, 'ftol': 1e-6, 'x_scale': 1.0, 'restart_sigma': .1})
        assert len(state['jobs']) == len(plan['jobs']) == 20
        assert [j['seed'] for j in state['jobs']] == list(range(1001, 1021))
        plans[arm] = plan
        identities[arm] = {'plan_sha256': sha(plan), 'plan_raw_sha256': digest(directory / 'plan.json'), 'run_raw_sha256': digest(directory / 'run.json'), 'source_sha256': state['source_sha256'], 'bounds_sha256': plan['search_bounds_sha256'], 'grid_sha256': meta['grid_sha256'], 'rf_profile': plan['rf_profile'], 'input_files': meta['files']}
        starts = load(inputs / arm / 'starts.json')
        for jobstate, jobplan in zip(state['jobs'], plan['jobs'], strict=True):
            seed = jobstate['seed']
            job = directory / jobstate['job_id']
            inp, result, receipt = (load(job / f'{name}.json') for name in ('input', 'result', 'receipt'))
            assert jobstate['status'] == 'completed' and jobstate['arm'] == jobplan['arm'] == 'baseline' and seed == jobplan['seed'] == inp['seed'] == result['seed']
            assert jobstate['reservation'] == inp['reservation'] == jobplan['reservation'] == manifest['per_job']
            assert inp['plan'] == plan == result['plan'] and inp['plan_sha256'] == result['plan_sha256'] == state['plan_sha256']
            assert sha(inp['source']) == inp['source_sha256'] == result['source_sha256'] == state['source_sha256']
            assert inp['source'] == result['source'] and inp['source']['environment']['threads'] == {k:'1' for k in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS')}
            initial = starts[str(seed)]['baseline']
            assert initial == inp['start'] and initial['vector_sha256'] == meta['starts'][str(seed)] == jobplan['vector_sha256'] == result['initial_vector_sha256'] == vector_sha(result['initial_vector'])
            assert set(receipt['files']) == {'input.json', 'result.json'} | {f'checkpoints/{p.name}' for p in (job / 'checkpoints').iterdir()}
            assert set(jobstate['raw']) == set(receipt['files']) | {'receipt.json'}
            for name, entry in jobstate['raw'].items():
                path = job / name
                assert entry == {'bytes': path.stat().st_size, 'sha256': digest(path)}
                if name != 'receipt.json':
                    assert receipt['files'][name] == entry
            step = result['steps'][0]
            c = result['terminal']['candidates'][0]
            assert vector_sha(c['vector']) == c['vector_sha256']
            assert step['solver_options'] == step_config['effective_options'] and step['grid_sha256'] == plan['grids']['baseline/search']['sha256']
            assert step['rf_cache_mode'] == 'off'  # TRF uses its sensitivity evaluator, not LK cache.
            assert jobstate['actual'] == {'rf_forwards': step['forward_count']+1, 'rf_samples': 70*step['forward_count']+476, 'independent_mna_samples': 2}
            assert sum(x['scipy_nfev'] for x in step['local_run_details']) == step['forward_count']
            assert c['physical']['component_policy_pass'] and c['physical']['checked_settings'] == 6 and c['physical']['min_L_eigenvalue_H'] > 0 and not c['physical']['connection_role_evidence_incomplete']
            assert c['external_passivity'] == c['power_balance'] == 'checked_on_terminal_grid'
            assert c['independent']['status'] == 'pass' and c['independent']['sample_indices'] == [0, 111]
            assert c['independent']['passivity'] == c['independent']['power_balance'] == 'pass_at_samples'
            grid, il = c['response']['grid'], c['response']['il_db']
            assert len(il) == 476 and all(grid[k] == plan['grids']['terminal'][k] for k in ('frequency_hz', 'segment', 'setting'))
            def vals(predicate):
                return [v for v, seg in zip(il, grid['segment'], strict=True) if predicate(bands[seg])]
            margins = np.asarray(c['signed_margins_db'])
            assert np.isclose(max(margins), c['terminal_signed_max_margin_db'])
            cp = []
            for path in sorted((job / 'checkpoints').iterdir()):
                item = load(path); obs = item['observation']
                assert vector_sha(obs['vector']) == obs['vector_sha256']
                cp.append({'forward_count': item['forward_count'], 'objective': obs['objective'], 'sha256': digest(path), 'vector_sha256': obs['vector_sha256']})
            box = np.asarray(plan['search_bounds']); final = np.asarray(c['vector'])
            assert np.all(final >= box[:, 0]) and np.all(final <= box[:, 1])
            rows.append({'condition': arm, 'seed': seed, 'job_id': jobstate['job_id'], 'initial_sha256': initial['vector_sha256'], 'final_sha256': c['vector_sha256'], 'receipt_sha256': digest(job/'receipt.json'), 'raw': jobstate['raw'], 'actual': jobstate['actual'], 'terminal_J_db2': float(np.square(np.maximum(margins, 0)).sum()), 'terminal_max_margin_db': c['terminal_signed_max_margin_db'], 'feasible': c['performance_feasible'], 'worst_il_db': max(vals(lambda b: b['type'] == 'pass')), 'min_h2_db': min(vals(lambda b: b['region'] == 'H2')), 'min_h3_db': min(vals(lambda b: b['region'] == 'H3')), 'search_J_db2': step['solver_result']['objective'], 'checkpoints': cp, 'local_runs': step['local_runs'], 'restarts': step['restart_count'], 'nfev': sum(x['scipy_nfev'] for x in step['local_run_details']), 'njev': sum(x['scipy_njev'] for x in step['local_run_details']), 'stop_reason': step['stop_reason'], 'converged': step['converged'], 'min_L_eigenvalue_H': c['physical']['min_L_eigenvalue_H'], 'independent': c['independent']['status'], 'final_vector': c['vector'], 'upper_distance_fraction_LC': ((box[:8, 1]-final[:8])/(box[:8, 1]-box[:8, 0])).tolist()})
    a, b = plans['baseline'], plans['limited']
    assert a['config'] == b['config'] and a['definition'] == b['definition'] and a['parameter_schema'] == b['parameter_schema'] and a['rf_profile'] == b['rf_profile'] and a['grids'] == b['grids']
    assert identities['baseline']['source_sha256'] == identities['limited']['source_sha256']
    assert [i for i, (x, y) in enumerate(zip(a['search_bounds'], b['search_bounds'], strict=True)) if x != y] == list(range(7))
    return {'identities': identities, 'runs': rows}

if __name__ == '__main__':
    output = Path(sys.argv[3])
    assert not output.exists()
    data = collect(Path(sys.argv[1]), Path(sys.argv[2]))
    output.write_text(json.dumps(data, indent=2, allow_nan=False) + '\n')
    print('PASS: audited', len(data['runs']), 'jobs:', output)

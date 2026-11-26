#!/usr/bin/env python3
"""Audit and compact saved development CLI runs; no search execution."""
import csv
import hashlib
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT/'src'))
from lpf.search.storage import sha, vector_sha


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def collect(directory, output):
    directory = Path(directory)
    info = json.loads((directory/'summary.json').read_text())
    bands = list(csv.DictReader((ROOT/'rf/bands.csv').open()))
    rows = []
    identities = {}
    for run in info['runs']:
        path = Path(run['output']); job = path/'job-0001'
        state = json.loads((path/'run.json').read_text())
        plan = json.loads((path/'plan.json').read_text())
        result = json.loads((job/'result.json').read_text())
        receipt = json.loads((job/'receipt.json').read_text())
        assert state['status'] == 'completed' and sha(plan) == state['plan_sha256'] == result['plan_sha256']
        assert result['source_sha256'] == state['source_sha256']
        assert vector_sha(result['initial_vector']) == result['initial_vector_sha256'] == run['initial_sha256']
        candidate = result['terminal']['candidates'][0]
        assert vector_sha(candidate['vector']) == candidate['vector_sha256']
        assert set(receipt['files']) == {'input.json', 'result.json'} | {f'checkpoints/{p.name}' for p in (job/'checkpoints').iterdir()}
        for name, entry in receipt['files'].items():
            file = job/name
            assert file.stat().st_size == entry['bytes'] and digest(file) == entry['sha256']
        step = result['steps'][0]; response = candidate['response']; grid = response['grid']; il = response['il_db']
        assert len(il) == len(grid['segment']) == 476
        assert set(plan['grids']['baseline/search']['setting']) == set(range(6))
        assert set(plan['grids']['baseline/search']['segment']) == set(range(28))
        assert len(plan['grids']['baseline/search']['frequency_hz']) == 70
        assert candidate['independent']['sample_indices'] == [0, 111]
        actual = state['jobs'][0]['actual']
        assert actual == {'rf_forwards': step['forward_count']+1, 'rf_samples': 70*step['forward_count']+476,
                          'independent_mna_samples': 2}
        assert result['initial_vector_sha256'] == run['initial_sha256']
        identity = {'grid_sha256': {k: v['sha256'] for k, v in plan['grids'].items()},
                    'bounds_sha256': plan['search_bounds_sha256'], 'rf_profile': plan['rf_profile']}
        if identities:
            assert identity == identities
        else:
            identities = identity
        def take(pred):
            return [v for v, seg in zip(il, grid['segment'], strict=True) if pred(bands[seg])]
        margins = np.asarray(candidate['signed_margins_db'])
        checkpoints = []
        for cp in sorted((job/'checkpoints').iterdir()):
            data = json.loads(cp.read_text()); obs = data['observation']
            assert vector_sha(obs['vector']) == obs['vector_sha256']
            checkpoints.append({'sha256': digest(cp), 'forward_count': data['forward_count'],
                                'vector_sha256': obs['vector_sha256'], 'objective': obs['objective']})
        row = dict(run)
        row.update(plan_sha256=state['plan_sha256'], source_sha256=result['source_sha256'],
                   result_sha256=digest(job/'result.json'), receipt_sha256=digest(job/'receipt.json'),
                   search_J=step['solver_result']['objective'],
                   terminal_J=float(np.square(np.maximum(margins, 0)).sum()),
                   terminal_max_margin_db=candidate['terminal_signed_max_margin_db'],
                   worst_il_db=max(take(lambda b: b['type'] == 'pass')),
                   min_h2_db=min(take(lambda b: b['region'] == 'H2')),
                   min_h3_db=min(take(lambda b: b['region'] == 'H3')),
                   feasible=candidate['performance_feasible'], external_passivity=candidate['external_passivity'],
                   power_balance=candidate['power_balance'], independent=candidate['independent']['status'],
                   independent_indices=candidate['independent']['sample_indices'],
                   component_pass=candidate['physical']['component_policy_pass'],
                   min_L_eigenvalue_H=candidate['physical']['min_L_eigenvalue_H'],
                   nfev=sum(x['scipy_nfev'] for x in step['local_run_details']),
                   njev=sum(x['scipy_njev'] for x in step['local_run_details']),
                   restarts=step['restart_count'], local_runs=step['local_runs'],
                   stop_reason=step['stop_reason'], converged=step['converged'], actual=actual,
                   final_vector=candidate['vector'], final_sha256=candidate['vector_sha256'], checkpoints=checkpoints)
        assert row['nfev'] == step['forward_count']
        rows.append(row)
    assert info.get('complete') and len(rows) == len(info['runs'])
    Path(output).write_text(json.dumps({'metadata': {k: v for k, v in info.items() if k != 'runs'},
                                        'identities': identities, 'runs': rows}, indent=2, allow_nan=False)+'\n')


if __name__ == '__main__':
    assert not Path(sys.argv[2]).exists()
    collect(sys.argv[1], sys.argv[2])

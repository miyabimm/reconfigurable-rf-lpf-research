#!/usr/bin/env python3
"""Audit one completed #513 run and extract compact evidence; no RF forwards."""
import csv
import hashlib
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT/'src'))
from lpf.search.storage import sha, vector_sha

COSTS = ('rf_samples', 'rf_forwards', 'independent_mna_samples')
def load(p): return json.loads(p.read_bytes())
def check(path, info):
    blob = path.read_bytes()
    assert len(blob) == info['bytes'] and hashlib.sha256(blob).hexdigest() == info['sha256'], path

def inspect(preflight, index, path, timing_path):
    expected = preflight['runs'][index-1]
    plan, run, timing = load(path/'plan.json'), load(path/'run.json'), load(timing_path)
    assert sha(plan) == run['plan_sha256'] == timing['plan_sha256'] == expected['plan_sha256']
    assert plan == expected['plan'] and run['status'] == timing['status'] == 'completed'
    check(path/'plan.json', run['plan_raw'])
    assert run['source_sha256'] == timing['source_sha256'] and run['budget'] == expected['budget']
    assert len(run['jobs']) == len(plan['jobs']) == len(timing['jobs'])
    bands = list(csv.DictReader((ROOT/'rf/bands.csv').open()))
    assert len(bands) == 28
    rows = []
    for job, pj, tj in zip(run['jobs'], plan['jobs'], timing['jobs'], strict=True):
        assert job['status'] == tj['status'] == 'completed'
        assert (job['seed'], job['arm']) == (pj['seed'], pj['arm']) == (tj['seed'], tj['arm'])
        assert job['reservation'] == pj['reservation']
        d = path/job['raw_path']
        assert not (d/'failure.json').exists()
        receipt = load(d/'receipt.json')
        assert set(job['raw']) == set(receipt['files']) | {'receipt.json'}
        assert set(receipt['files']) == {'input.json', 'result.json'} | {f'checkpoints/{p.name}' for p in (d/'checkpoints').iterdir()}
        for name, info in job['raw'].items():
            check(d/name, info)
            if name != 'receipt.json': assert receipt['files'][name] == info
        inp, result = load(d/'input.json'), load(d/'result.json')
        assert inp['plan_sha256'] == result['plan_sha256'] == run['plan_sha256']
        assert inp['source_sha256'] == result['source_sha256'] == run['source_sha256'] == sha(result['source'])
        assert inp['start']['vector'] == pj['vector'] == result['initial_vector']
        assert inp['start']['vector_sha256'] == pj['vector_sha256'] == result['initial_vector_sha256'] == vector_sha(pj['vector'])
        assert result['rf_profile'] == plan['rf_profile'] and result['search_bounds'] == plan['search_bounds']
        assert result['terminal']['status'] == 'completed' and len(result['terminal']['candidates']) == 1
        c = result['terminal']['candidates'][0]
        assert vector_sha(c['vector']) == c['vector_sha256']
        assert all(lo <= v <= hi for v, (lo, hi) in zip(c['vector'], plan['search_bounds'], strict=True))
        physical, independent = c['physical'], c['independent']
        assert physical['component_policy_pass'] and not physical['connection_role_evidence_incomplete'] and physical['min_L_eigenvalue_H'] > 0
        assert independent['status'] == 'pass' and independent['sample_indices'] == [0, 111]
        assert c['external_passivity'] == c['power_balance'] == 'checked_on_terminal_grid'
        assert c['independent_power_balance'] == 'checked_at_independent_mna_spots'
        grid, il = plan['grids']['terminal'], c['response']['il_db']
        assert len(il) == len(grid['segment']) == 476 and all(math.isfinite(v) for v in il)
        il_for = lambda pred: [v for v, seg in zip(il, grid['segment'], strict=True) if pred(bands[seg])]
        worst, h2, h3 = max(il_for(lambda b: b['type'] == 'pass')), min(il_for(lambda b: b['region'] == 'H2')), min(il_for(lambda b: b['region'] == 'H3'))
        margin = c['terminal_signed_max_margin_db']
        assert abs(margin-max(worst-.75, 30-min(h2, h3))) < 1e-9 and c['performance_feasible'] == (margin <= 0)
        assert len(result['steps']) == 1
        step = result['steps'][0]
        assert step['solver'] == ('trf' if job['arm'] == 'T' else 'hybrid')
        assert step['local_runs'] == len(step['local_run_details']) == step['restart_count']+1
        assert step['forward_count'] <= (5000 if job['arm'] == 'T' else preflight['N']+24)
        assert sum(r['sensitivity_evaluations' if job['arm'] == 'T' else 'nfev'] for r in step['local_run_details']) == step['forward_count']
        assert step['requested_samples'] == 70*step['forward_count']
        costs = result['costs']
        assert costs['search_forwards'] == step['forward_count'] and costs['terminal_forwards'] == 1
        assert costs['terminal_requested_samples'] == 476 and costs['independent_mna_samples_by_stage'] == {'terminal': 2}
        actual = {'rf_samples': step['requested_samples']+476, 'rf_forwards': step['forward_count']+1, 'independent_mna_samples': 2}
        assert job['actual'] == actual
        assert all(job['unknown'][k] == 0 and job['released'][k] == job['reservation'][k]-actual[k] for k in COSTS)
        assert all(result['ledger'][k] == {'completed': actual[k], 'released': job['released'][k], 'unknown': 0} for k in COSTS)
        assert tj['regions']['job']['count'] == 1 and tj['regions']['job']['failed'] == 0
        rows.append(dict(seed=job['seed'], arm=job['arm'], J=margin, finite_grid_pass=c['performance_feasible'],
            worst_il=worst, min_h2=h2, min_h3=h3, search_objective=step['solver_result']['objective'],
            search_forwards=step['forward_count'], actual=actual, released=job['released'],
            local_runs=step['local_runs'], restart_count=step['restart_count'], local_run_details=step['local_run_details'],
            local_timing=tj['steps'], stop_reason=step['stop_reason'], converged=step['converged'],
            job_wall_s=tj['regions']['job']['wall_ns']/1e9, job_cpu_s=None,
            initial_vector=result['initial_vector'], initial_sha=result['initial_vector_sha256'],
            final_vector=c['vector'], final_sha=c['vector_sha256'], physical=physical,
            independent={k:v for k,v in independent.items() if k != 'spots'},
            external_passivity=c['external_passivity'], power_balance=c['power_balance'],
            input_raw_sha=job['raw']['input.json']['sha256'], result_raw_sha=job['raw']['result.json']['sha256'],
            receipt_raw_sha=job['raw']['receipt.json']['sha256'], checkpoints=sum(k.startswith('checkpoints/') for k in job['raw'])))
    return {'run': index, 'plan_sha256': run['plan_sha256'], 'source_sha256': run['source_sha256'],
            'source': result['source'], 'budget': run['budget'],
            'actual': {k: sum(r['actual'][k] for r in rows) for k in COSTS},
            'released': {k: sum(r['released'][k] for r in rows) for k in COSTS},
            'unknown': {k: sum(j['unknown'][k] for j in run['jobs']) for k in COSTS}, 'jobs': rows}

if __name__ == '__main__':
    data = inspect(load(Path(sys.argv[1])), int(sys.argv[2]), Path(sys.argv[3]), Path(sys.argv[4]))
    output = Path(sys.argv[5])
    with output.open('x') as f: json.dump(data, f, indent=2, allow_nan=False); f.write('\n')
    print(json.dumps({'status': 'PASS', 'run': data['run'], 'jobs': len(data['jobs']), 'actual': data['actual'], 'released': data['released']}))

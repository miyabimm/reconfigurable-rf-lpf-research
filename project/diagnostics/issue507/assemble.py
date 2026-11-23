#!/usr/bin/env python3
"""Extract compact, auditable issue-507 records from compare.py output."""
import argparse
import csv
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT/'src'))
from lpf.search.storage import vector_sha


def grid_keys(grid):
    return list(zip(grid['frequency_hz'], grid['setting'], grid['segment']))


def main():
    p = argparse.ArgumentParser()
    p.add_argument('input', type=Path)
    p.add_argument('output', type=Path)
    args = p.parse_args()
    meta = json.loads((args.input/'meta.json').read_text())
    runs, warmups, plans = [], [], {}
    for name in [*(f'warmup-{a}' for a in 'ABCD'),
                 *(f'{a}{i}' for i, order in enumerate(('ABCD', 'BCDA', 'CDAB'), 1) for a in order)]:
        x = json.loads((args.input/(name+'.json')).read_text())
        if x['error']:
            raise ValueError(f'Unresolved run failure: {name}: {x["error"]}; retain raw')
        if name.startswith('warmup'):
            warmups.append(dict(run=name, status=x['trf']['status'], nfev=x['trf']['nfev'],
                                solver_wall_s=x['solver_wall_s'], error=None))
            continue
        original = json.loads((args.input/('runner-'+name)/'job-0001/result.json').read_text())
        terminal = original['terminal']['candidates'][0]
        grid = original['plan']['grids']
        mapping = dict(zip(grid_keys(grid['terminal']), terminal['signed_margins_db']))
        search_j = max(mapping[k] for k in grid_keys(grid['baseline/search']))
        t = x['terminal']
        t['independent'] = {k: t['independent'][k] for k in ('status', 'sample_indices', 'passivity', 'power_balance', 'whole_band_checked')}
        t['physical'] = {k: t['physical'][k] for k in ('checked_settings', 'component_policy_pass', 'min_L_eigenvalue_H', 'candidate_promotion_blocked', 'physical_q_srf_em_checked')}
        x['search_J_db'] = search_j
        x['final_vector_sha256'] = vector_sha(x['trf']['x'])
        x['best_vector_sha256'] = vector_sha(x['trf']['best_x'])
        assert x['best_vector_sha256'] == t['vector_sha256']
        plans[x['arm']] = x.pop('plan')
        x.pop('source')
        x.pop('initial_vector'); x.pop('search_bounds'); x.pop('profile')
        x.pop('blas'); x.pop('host'); x.pop('affinity'); x.pop('platform'); x.pop('threads')
        runs.append(x)
    reference = json.loads((args.input/'A1.json').read_text())
    summary = dict(kind='issue507_trial_development_diagnostic', meta=meta,
                   source=reference['source'], environment={k: reference[k] for k in ('platform', 'host', 'affinity', 'threads', 'blas')},
                   initial_vector=reference['initial_vector'], initial_vector_sha256=reference['initial_vector_sha256'],
                   search_bounds=reference['search_bounds'], search_bounds_sha256=reference['search_bounds_sha256'],
                   profile=reference['profile'], plans=plans, warmups=warmups, runs=runs,
                   search_J_method='Selected Terminal signed margins at identical (frequency, setting, segment) Search grid points; no additional RF forwards.')
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output/'summary.json').write_text(json.dumps(summary, indent=2, allow_nan=False)+'\n')
    columns = ['run', 'arm', 'error', 'status', 'stop_reason', 'scipy_status', 'message', 'optimality', 'nfev', 'njev',
               'sensitivity_evaluations', 'requested_samples', 'computed_samples', 'search_objective_db2', 'search_J_db',
               'terminal_J_db', 'max_pass_il_db', 'min_h2_h3_atten_db', 'finite_grid_pass', 'best_vector_sha256',
               'final_vector_sha256', 'solver_wall_s', 'solver_cpu_s', 'runner_wall_s', 'runner_cpu_s']
    with (args.output/'paired.csv').open('w', newline='') as f:
        writer = csv.DictWriter(f, columns, lineterminator='\n'); writer.writeheader()
        for x in runs:
            trf, t = x['trf'], x['terminal']
            row = {k: x[k] for k in ('run', 'arm', 'error', 'status', 'stop_reason', 'search_J_db', 'best_vector_sha256',
                                       'final_vector_sha256', 'solver_wall_s', 'solver_cpu_s', 'runner_wall_s', 'runner_cpu_s')}
            row.update({k: trf[k] for k in ('message', 'optimality', 'nfev', 'njev', 'sensitivity_evaluations', 'requested_samples', 'computed_samples')})
            row.update(scipy_status=trf['status'], search_objective_db2=trf['best_objective'], terminal_J_db=t['J'],
                       max_pass_il_db=t['max_pass_il_db'], min_h2_h3_atten_db=t['min_h2_h3_atten_db'], finite_grid_pass=t['finite_grid_pass'])
            writer.writerow(row)

if __name__ == '__main__':
    main()

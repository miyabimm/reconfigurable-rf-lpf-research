#!/usr/bin/env python3
"""Extract compact evidence from the four issue 509 diagnostic records."""
import csv
import json
from pathlib import Path
import sys

source, target = map(Path, sys.argv[1:])
records = [json.loads((source/f'{name}.json').read_text()) for name in ('warmup', 'run1', 'run2', 'run3')]
assert all(r['error'] is None for r in records)
shared = {key: records[1][key] for key in ('plan', 'plan_sha256', 'source', 'source_sha256', 'rf_profile', 'threads', 'platform', 'host', 'cpu', 'affinity', 'numpy_blas_config', 'diagnostic_script_sha256')}
rows = []
for name, record in zip(('warmup', 'run1', 'run2', 'run3'), records, strict=True):
    result = json.loads((source/f'{name}-run/job-0001/result.json').read_text())
    terminal = result['terminal']['candidates'][0]
    assert terminal['vector_sha256'] == record['final_vector_sha256']
    assert record['search_forwards'] == sum(r['sensitivity_evaluations'] for r in record['trf_diagnostics'])
    assert record['search_forwards'] <= record['limit']
    record['final_terminal'] = {key: terminal[key] for key in ('terminal_signed_max_margin_db', 'performance_feasible', 'physical', 'independent', 'external_passivity', 'power_balance')}
    record['additional_terminal_forwards'] = len({w['vector_sha256'] for w in record['windows'].values() if not w['missing']})
    record['additional_terminal_requested_samples'] = record['additional_terminal_forwards'] * 476
    record['additional_terminal_mna_samples'] = record['additional_terminal_forwards'] * 2
    record['run'] = name
    for key in shared:
        if key != 'plan_sha256':
            record.pop(key, None)
    if name == 'warmup':
        continue
    for window, row in record['windows'].items():
        assert row['terminal']['error'] is None and row['terminal']['independent_mna'] == 'pass'
        rows.append(dict(run=name, window_s=int(window), window_status=row['status'], observed_s=row['observed_s'],
                         forward_at_observation=row['forward_count_at_observation'], search_objective_db2=row['search_objective_db2'],
                         terminal_j_db=row['terminal']['J'], finite_grid_pass=row['terminal']['finite_grid_pass'],
                         max_pass_il_db=row['terminal']['max_pass_il_db'], min_h2_h3_atten_db=row['terminal']['min_h2_h3_atten_db'],
                         vector_sha256=row['vector_sha256'], solver_wall_s=record['solver_wall_s'],
                         local_runs=record['local_runs'], restart_count=record['restart_count'],
                         search_forwards=record['search_forwards'], stop_reason=record['stop_reason']))
target.mkdir(exist_ok=True)
(target/'summary.json').write_text(json.dumps(dict(kind='issue509_trial_development_diagnostic', shared=shared, records=records), indent=2, allow_nan=False)+'\n')
with (target/'paired.csv').open('w', newline='') as f:
    writer = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator='\n'); writer.writeheader(); writer.writerows(rows)

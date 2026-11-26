#!/usr/bin/env python3
"""Compact the saved fixed-vector and audited CLI evidence for review."""
import json
from pathlib import Path
import statistics
import sys
import numpy as np

fixed, runner, quality, out = map(Path, sys.argv[1:])
assert not out.exists()
r = json.loads(runner.read_text()); q = json.loads(quality.read_text())
ref = np.load(fixed/'base-0.npz')
summary = {'fixed': {}, 'runner_identities': r['identities'], 'runner': [], 'quality': [], 'deep': {}}
for mode in ('base', 'i1', 'i2'):
    records = []
    for p in sorted(fixed.glob(mode+'-*.json')):
        data = json.loads(p.read_text()); arrays = np.load(p.with_suffix('.npz'))
        errors = {}
        for k in ref.files:
            np.testing.assert_allclose(ref[k], arrays[k], rtol=1e-11, atol=1e-11)
            field = k.rsplit('-', 1)[-1]
            errors[field] = max(errors.get(field, 0.), float(np.max(np.abs(ref[k]-arrays[k]))))
        records.append({'commit': data['commit'], 'model_import': data['model_import'], 'affinity': data['affinity'],
                        'threads': data['threads'], 'python': data['python'], 'numpy': data['numpy'],
                        'vectors_sha256': data['vectors_sha256'], 'peak_rss_kib': data['peak_rss_kib'],
                        'median_wall_ns': statistics.median(t for row in data['rows'] for t in row['wall_ns']),
                        'max_abs_diff': errors,
                        'vectors': [{k: row[k] for k in ('seed', 'vector', 'vector_sha256', 'plan_sha256')} for row in data['rows']]})
    summary['fixed'][mode] = records
fields = ('phase', 'cycle', 'seed', 'mode', 'level', 'head', 'config_sha256', 'starts_sha256', 'initial_sha256',
          'exit_code', 'wall_s', 'cpu_s', 'user_s', 'system_s', 'minor_faults', 'major_faults', 'children_peak_rss_kib_so_far',
          'plan_sha256', 'source_sha256', 'result_sha256', 'receipt_sha256', 'search_J', 'terminal_J',
          'terminal_max_margin_db', 'worst_il_db', 'min_h2_db', 'min_h3_db', 'feasible', 'independent',
          'independent_indices', 'component_pass', 'external_passivity', 'power_balance', 'nfev', 'njev',
          'restarts', 'stop_reason', 'converged', 'actual', 'final_sha256', 'checkpoints')
for target, source in (('runner', r), ('quality', q)):
    summary[target] = [{k: row[k] for k in fields} for row in source['runs']]
for mode in ('base', 'I2'):
    rows = [row for row in r['runs'] if row['phase']=='measure' and row['level']=='deep' and row['mode']==mode]
    groups = ['decode', 'matrices', 'node_admittance', 'jac_forward/reorder', 'jac_forward/schur_solve',
              'jac_forward/schur_update', 'jac_forward/y_to_s_build', 'jac_forward/y_to_s_solve',
              'jac_forward/cascade_first', 'jac_forward/cascade_second', 'power_response',
              'jac_sensitivity/y_to_s', 'jac_sensitivity/cascade_first', 'jac_sensitivity/cascade_second',
              'jac_sensitivity/wave', 'jac_sensitivity/il', 'jac_sensitivity/freeze']
    groups += (['node_jacobian', 'jac_sensitivity/reorder', 'jac_sensitivity/schur'] if mode=='base' else
               ['jac_sensitivity/lift', 'port_jacobian', 'jac_sensitivity/restore'])
    values = []
    for row in rows:
        timer = json.loads(Path(row['timing']).read_text())['jobs'][0]['regions']
        prefix = 'baseline/search/rf/'
        d = {name: timer[prefix+name]['wall_ns']/1e9 for name in groups}
        total = timer['baseline/search/rf_evaluate']['wall_ns']/1e9
        d['other'] = total-sum(d.values())
        d['rf_evaluate'] = total
        values.append(d)
    summary['deep'][mode] = {k: statistics.median(v[k] for v in values) for k in values[0]}
out.write_text(json.dumps(summary, indent=2, allow_nan=False)+'\n')

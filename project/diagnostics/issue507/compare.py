#!/usr/bin/env python3
"""Issue 507 trial-only sequential TRF diagnostic. Output directory must be fresh."""
import argparse
import csv
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'src'))
import numpy as np
import scipy
from lpf.search.storage import vector_sha

spec = importlib.util.spec_from_file_location('issue505_compare', ROOT/'project/diagnostics/issue505/compare.py')
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)
ARMS = {'A': {'ftol': 1e-8, 'x_scale': 1.0},
        'B': {'ftol': None, 'x_scale': 1.0},
        'C': {'ftol': 1e-8, 'x_scale': 'jac'},
        'D': {'ftol': None, 'x_scale': 'jac'}}


def run(arm, limit, output):
    original = base.config_for
    def config_for(solver, cap):
        config = original(solver, cap)
        config['arms'][0]['steps'][0]['options'].update(ARMS[arm])
        return config
    with patch.object(base, 'config_for', config_for):
        raw = base.run('trf', limit, output, observe=False)
    if raw['error'] or not raw['result']:
        return dict(arm=arm, limit=limit, error=raw['error'], state=raw['state'],
                    solver_wall_s=raw['solver_wall_s'], runner_wall_s=raw['runner_wall_s'])
    result = raw['result']
    step = result['steps'][0]
    details = step['trf_details']
    t = result['terminal']['candidates'][0]
    with (ROOT/'rf/bands.csv').open(newline='') as f:
        bands = list(csv.DictReader(f))
    il = np.asarray(t['response']['il_db'])
    segments = t['response']['grid']['segment']
    mask = np.array([bands[i]['type'] == 'pass' for i in segments])
    assert t['vector_sha256'] == vector_sha(details['best_x'])
    return dict(arm=arm, limit=limit, options=ARMS[arm], error=None,
        plan_sha256=raw['plan_sha256'], plan=result['plan'], source=result['source'],
        source_sha256=result['source_sha256'], initial_vector=result['initial_vector'],
        initial_vector_sha256=result['initial_vector_sha256'], search_bounds=result['search_bounds'],
        search_bounds_sha256=result['search_bounds_sha256'], seed=result['seed'],
        profile=result['performance_profile'], costs=result['costs'], actual=raw['state']['jobs'][0]['actual'],
        status=result['status'], stop_reason=step['stop_reason'], trf=details,
        solver_wall_s=raw['solver_wall_s'], solver_cpu_s=raw['solver_cpu_s'],
        runner_wall_s=raw['runner_wall_s'], runner_cpu_s=raw['runner_cpu_s'],
        threads=raw['threads'], platform=raw['platform'], host=raw['host'], affinity=raw['affinity'],
        blas=raw['numpy_blas_config'], loadavg_start=raw['loadavg_start'], loadavg_end=raw['loadavg_end'],
        terminal=dict(J=t['terminal_signed_max_margin_db'], finite_grid_pass=t['performance_feasible'],
                      max_pass_il_db=float(il[mask].max()), min_h2_h3_atten_db=float(il[~mask].min()),
                      physical=t['physical'], independent=t['independent'],
                      external_passivity=t['external_passivity'], power_balance=t['power_balance'],
                      vector_sha256=t['vector_sha256']))


def main():
    p = argparse.ArgumentParser()
    p.add_argument('output', type=Path, help='fresh system temporary directory')
    args = p.parse_args()
    if any(os.environ.get(k) != '1' for k in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS')):
        p.error('set OPENBLAS_NUM_THREADS, OMP_NUM_THREADS, MKL_NUM_THREADS to 1 before Python')
    args.output.mkdir(parents=False, exist_ok=False)
    meta = dict(head=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
                git_status=subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT, text=True),
                script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                reference_script_sha256=hashlib.sha256(Path(base.__file__).read_bytes()).hexdigest(),
                python=sys.version, numpy=np.__version__, scipy=scipy.__version__,
                schedule=['warmup A/B/C/D (28)', 'ABCD', 'BCDA', 'CDAB'], limit=5000)
    (args.output/'meta.json').write_text(json.dumps(meta, indent=2, allow_nan=False)+'\n')
    schedule = [(f'warmup-{a}', a, 28) for a in ARMS]
    schedule += [(f'{a}{i}', a, 5000) for i, order in enumerate(('ABCD', 'BCDA', 'CDAB'), 1) for a in order]
    for name, arm, limit in schedule:
        print(name, flush=True)
        row = run(arm, limit, args.output/('runner-'+name))
        row['run'] = name
        (args.output/(name+'.json')).write_text(json.dumps(row, indent=2, allow_nan=False)+'\n')
        print(name, row.get('error'), row.get('solver_wall_s'), flush=True)

if __name__ == '__main__':
    main()

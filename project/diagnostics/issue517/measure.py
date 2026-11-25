#!/usr/bin/env python3
"""Issue 517: fixed RF-T010 replay and paired Runner timing, not a formal EXP.

Run with single-thread BLAS/OMP and a fresh /tmp directory argument. Run files
are retained there; summary is written after each completed run. Never resume a
partial run by overwriting it. Deep regions are inclusive, not additive.
"""
import csv
import hashlib
import json
import os
from pathlib import Path
import platform
import statistics
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT/'src'))
import numpy as np
import scipy
from lpf.minimax_profile import load_minimax_profile, _margin_parameters
from lpf.search import _development_runner as runner
from lpf.search.plan import grid_from_record
from lpf.search.proposals import definition_from_data
from lpf.search.starts import generate_for_definition
from lpf.search.storage import sha
from lpf.search._rf_deep_timing import search_rf_timing
from lpf.timing import TimerCollector

SEEDS = (1001, 1010, 1020)  # fixed before measurement: early, middle, late
THREADS = ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS')

def setup(seed):
    profile = load_minimax_profile('RF-T010', root=ROOT, allow_trial=True)
    assert profile.fingerprint == 'd50e6c9fef3e41b8258c00cbd14436a3bcb1d84444d50cf4a445ccf5d288e417'
    definition_data = json.loads((ROOT/'project/diagnostics/issue361/definition.json').read_text())
    assert sha(definition_data) == 'bc50042a1b0b1ebf19c0272fb2ee944b52cd76e14eb8d44673bfa57f6033c068'
    record = generate_for_definition(definition_from_data(definition_data), json.loads(profile.base_json), seed)
    with (ROOT/'project/diagnostics/issue513/paired.csv').open() as f:
        prior = {int(row['seed']): row['initial_sha'] for row in csv.DictReader(f)}
    assert record['vector_sha256'] == prior[seed]
    config = json.loads((ROOT/'project/diagnostics/issue470/config.json').read_text())
    config['seeds'] = [seed]
    config['arms'][0]['steps'][0].update(solver='trf', options=dict(max_evaluations=5000, restart_sigma=.1, ftol=1e-6, x_scale=1.0))
    config['budget'] = dict(rf_samples=70*5000+476, rf_forwards=5001, independent_mna_samples=2)
    starts = {str(seed): {'baseline': {k: record[k] for k in ('vector', 'vector_sha256')}}}
    spots = {'terminal': [0, 111]}
    plan, _, profile, model, _ = runner.freeze_run(config, starts, root=ROOT, spot_checks=spots, search_bounds=None, checkpoint_interval=1000)
    assert len(plan.data['grids']['baseline/search']['frequency_hz']) == 70
    assert len(plan.data['grids']['terminal']['frequency_hz']) == 476
    for grid in plan.data['grids'].values():
        assert set(grid['setting']) == set(range(6)) and set(grid['segment']) == set(range(28))
    return config, starts, spots, plan, profile, model

def save(path, data):
    path.write_text(json.dumps(data, indent=2, allow_nan=False)+'\n')

def run(out, seeds=SEEDS):
    assert seeds and all(seed in SEEDS for seed in seeds)
    assert all(os.environ.get(k) == '1' for k in THREADS)
    out = Path(out).resolve()
    assert out.parent == Path('/tmp') and not out.exists()
    out.mkdir()
    meta = dict(head=subprocess.check_output(['git','rev-parse','HEAD'], cwd=ROOT, text=True).strip(),
                status=subprocess.check_output(['git','status','--porcelain'], cwd=ROOT, text=True),
                python=sys.version, numpy=np.__version__, scipy=scipy.__version__, platform=platform.platform(),
                threads={k:os.environ[k] for k in THREADS}, seeds=seeds, pairs=3, replay_pairs=10,
                note='Trial, diagnostic only. Inclusive deep timings overlap; plain has no timing collector.')
    summary = dict(metadata=meta, inputs={}, replay=[], runs=[])
    save(out/'summary.json', summary)
    for seed in seeds:
        config, starts, spots, plan, profile, model = setup(seed)
        grid = grid_from_record(plan.data['grids']['baseline/search'])
        ev = model.evaluator(grid, cache_mode='off')
        x = np.asarray(starts[str(seed)]['baseline']['vector'])
        threshold, direction = _margin_parameters(profile, grid)
        ref, refjac = ev.evaluate_with_il_jacobian(x)  # warmup, excluded
        summary['inputs'][str(seed)] = dict(plan_sha256=plan.sha256, rf_profile=plan.data['rf_profile'],
            grid_sha256={k:v['sha256'] for k,v in plan.data['grids'].items()},
            start=starts[str(seed)]['baseline'], bounds_sha256=plan.data['search_bounds_sha256'],
            initial_positive_margin_count=int(np.count_nonzero(direction*(ref.il_db-threshold)>0)))
        for pair in range(10):
            for mode in (('plain','deep') if pair%2 == 0 else ('deep','plain')):
                timer = TimerCollector()
                wall, cpu = time.perf_counter(), time.process_time()
                if mode == 'deep':
                    with search_rf_timing(timer, 'replay'):
                        response, jac = ev.evaluate_with_il_jacobian(x)
                else:
                    response, jac = ev.evaluate_with_il_jacobian(x)
                wall, cpu = time.perf_counter()-wall, time.process_time()-cpu
                assert np.array_equal(ref.il_db, response.il_db) and np.array_equal(refjac, jac)
                summary['replay'].append(dict(seed=seed, pair=pair, mode=mode, wall_s=wall, cpu_s=cpu, regions=timer.snapshot()))
        save(out/'summary.json', summary)
    for seed in seeds:
        config, starts, spots, plan, _, _ = setup(seed)
        # Full same-plan Runner warmup; excluded from paired timings.
        warm = runner.run(config, starts, out/f'{seed}-warmup', root=ROOT,
                          spot_checks=spots, checkpoint_interval=1000)
        summary.setdefault('warmups', []).append(dict(seed=seed, actual=warm['jobs'][0]['actual']))
        save(out/'summary.json', summary)
        for pair in range(3):
            for mode in (('plain','deep') if pair%2 == 0 else ('deep','plain')):
                name = f'{seed}-{pair}-{mode}'
                kwargs = dict(root=ROOT, spot_checks=spots, checkpoint_interval=1000)
                if mode == 'deep': kwargs.update(timing_output=out/(name+'-timing.json'), timing_level='deep')
                wall, cpu = time.perf_counter(), time.process_time()
                state = runner.run(config, starts, out/name, **kwargs)
                wall, cpu = time.perf_counter()-wall, time.process_time()-cpu
                result = json.loads((out/name/'job-0001/result.json').read_text())
                for local in result['steps'][0]['local_run_details']:
                    local.pop('wall_s'); local.pop('cpu_s')
                checkpoints = sorted((out/name/'job-0001/checkpoints').iterdir())
                summary['runs'].append(dict(seed=seed, pair=pair, mode=mode, wall_s=wall, cpu_s=cpu,
                    actual=state['jobs'][0]['actual'], status=state['status'],
                    result_sha256=hashlib.sha256(json.dumps(result, sort_keys=True).encode()).hexdigest(),
                    checkpoints=[hashlib.sha256(p.read_bytes()).hexdigest() for p in checkpoints],
                    step=result['steps'][0], terminal=result['terminal']['candidates'][0]['vector_sha256'],
                    regions=json.loads((out/(name+'-timing.json')).read_text())['jobs'][0]['regions'] if mode == 'deep' else {}))
                save(out/'summary.json', summary)
                print(name, wall, flush=True)
    for seed in seeds:
        rows = [r for r in summary['runs'] if r['seed']==seed]
        assert len({r['result_sha256'] for r in rows}) == 1
        assert all(r['checkpoints'] == rows[0]['checkpoints'] for r in rows)
    summary['equivalence'] = 'PASS: result except local wall/cpu and all checkpoint bytes'
    save(out/'summary.json', summary)

if __name__ == '__main__': run(sys.argv[1], tuple(map(int, sys.argv[2:])) or SEEDS)

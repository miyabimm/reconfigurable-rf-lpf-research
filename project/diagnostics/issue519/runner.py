#!/usr/bin/env python3
"""Plain alternating #519 Runner comparison; raw jobs retained in fresh /tmp.

OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 uv run --frozen \
 python project/diagnostics/issue519/runner.py /tmp/issue519-runner-unique
No trace hooks or deep timer in these timed runs. Every completed run is saved.
"""
import hashlib
import json
import os
from pathlib import Path
import platform
import sys
import time

from probe import activate, restore
from measure import ROOT, SEEDS, THREADS, setup, save
import numpy as np
import scipy
from lpf.search import _development_runner as runner


def main(out):
    assert all(os.environ.get(k) == '1' for k in THREADS)
    out = Path(out).resolve()
    assert out.parent == Path('/tmp') and not out.exists()
    out.mkdir()
    summary = {'metadata': {'baseline': 'be0bdb2bf3662512b30408091efc3906389c1f6e',
        'python': sys.version, 'numpy': np.__version__, 'scipy': scipy.__version__,
        'platform': platform.platform(), 'threads': {k: os.environ[k] for k in THREADS},
        'pairs': 3, 'note': 'plain Runner; timing includes plan, terminal and save; no trace hooks'},
        'inputs': {}, 'warmups': [], 'runs': []}
    save(out/'summary.json', summary)
    for seed in SEEDS:
        config, starts, spots, plan, _, _ = setup(seed)
        summary['inputs'][str(seed)] = {'plan_sha256': plan.sha256, 'rf_profile': plan.data['rf_profile'],
            'grid_sha256': {k: v['sha256'] for k,v in plan.data['grids'].items()},
            'bounds_sha256': plan.data['search_bounds_sha256'], 'starts': starts}
        kwargs = dict(root=ROOT, spot_checks=spots, checkpoint_interval=1000)
        # Warm each candidate with a complete same-plan run; excluded from timing.
        for mode in ('base','A','B','AB'):
            activate(mode)
            state = runner.run(config, starts, out/f'{seed}-{mode}-warmup', **kwargs)
            summary['warmups'].append({'seed':seed, 'mode':mode, 'actual':state['jobs'][0]['actual']})
            save(out/'summary.json', summary)
            print(seed,mode,'warmup',flush=True)
        for mode in ('A','B','AB'):
            for pair in range(3):
                for arm in (('base',mode) if pair%2 == 0 else (mode,'base')):
                    activate(arm)
                    name = f'{seed}-{mode}-{pair}-{arm}'
                    wall, cpu = time.perf_counter(), time.process_time()
                    state = runner.run(config, starts, out/name, **kwargs)
                    wall, cpu = time.perf_counter()-wall, time.process_time()-cpu
                    job = out/name/'job-0001'
                    result = json.loads((job/'result.json').read_text())
                    step = result['steps'][0]
                    for local in step['local_run_details']:
                        local.pop('wall_s'); local.pop('cpu_s')
                    terminal = result['terminal']['candidates'][0]
                    checkpoints = []
                    for path in sorted((job/'checkpoints').iterdir()):
                        c = json.loads(path.read_text())
                        checkpoints.append({'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
                            'forward_count': c['forward_count'], 'observation': c['observation']})
                    summary['runs'].append({'seed':seed, 'comparison':mode, 'pair':pair, 'mode':arm,
                        'wall_s':wall, 'cpu_s':cpu, 'status':state['status'], 'actual':state['jobs'][0]['actual'],
                        'step':step, 'terminal':terminal, 'checkpoints':checkpoints})
                    save(out/'summary.json', summary)
                    print(name, round(wall,3),flush=True)
    restore()


if __name__ == '__main__':
    try:
        main(sys.argv[1])
    finally:
        restore()

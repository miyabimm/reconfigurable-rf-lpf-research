#!/usr/bin/env python3
"""Conditional L3: one warmup and three runs, only after the L2 batch."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

from lpf.search._job_evaluation import source_identity
from lpf.search.plan import ROOT
from lpf.search.storage import sha

HERE = Path(__file__).resolve().parent
OUT = HERE / 'issue401_raw'


def save(path, data):
    with path.open('x') as file:
        json.dump(data, file, sort_keys=True, indent=2, allow_nan=False)
        file.write('\n')
        file.flush()
        os.fsync(file.fileno())


def main():
    freeze = json.loads((OUT / 'freeze.json').read_text())
    previous = json.loads(json.loads((OUT / '00-plain.json').read_text())['stdout'])
    if not all((OUT / f'{i:02d}-{mode}.json').exists() for i, mode in enumerate(freeze['order'])):
        raise RuntimeError('L2 incomplete; STOP')
    current = source_identity(ROOT)
    for field in ('files', 'dirty_patch_sha256', 'environment'):
        if current[field] != freeze['source_identity'][field]:
            raise RuntimeError(f'{field} changed since L2; STOP')
    if sorted(os.sched_getaffinity(0)) != previous['affinity']:
        raise RuntimeError('affinity changed; STOP')
    source = sha(current)
    scripts = (HERE / 'issue401_deep.py', HERE / 'issue401_benchmark.py', HERE / 'issue401_timing.py')
    digests = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in scripts}
    save(OUT / 'deep-freeze.json', {'source_identity': current, 'source_sha': source, 'scripts': digests,
         'reason': 'RF forward dominates L2 callback', 'order': ['warmup', 'measurement', 'measurement', 'measurement']})
    for i in range(4):
        if sha(source_identity(ROOT)) != source or any(hashlib.sha256(p.read_bytes()).hexdigest() != digests[p.name] for p in scripts):
            raise RuntimeError('source changed; STOP')
        prefix = f'deep-{i:02d}'
        command = [sys.executable, str(HERE / 'issue401_benchmark.py'), '--mode', 'deep', '--source-sha', source]
        save(OUT / (prefix + '.started.json'), {'sequence': i, 'warmup': i == 0, 'command': command,
             'reservation_forward': 100, 'reservation_samples': 7000})
        run = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=False)
        save(OUT / (prefix + '.json'), {'sequence': i, 'warmup': i == 0, 'returncode': run.returncode,
             'stdout': run.stdout, 'stderr': run.stderr})
        if run.returncode:
            raise RuntimeError(f'{prefix} failed; STOP; reservation remains unknown')
        report = json.loads(run.stdout)
        if report['solver'] != previous['solver'] or report['source_sha'] != source:
            raise RuntimeError('solver/source mismatch; STOP')
        for name in ('solver_callback', 'rf_forward', 'requirements', 'residual', 'l3_port_admittance',
                     'l3_node_admittance', 'l3_matrices', 'l3_power_response'):
            if report['timers'][name]['count'] != 100 or report['timers'][name]['failed']:
                raise RuntimeError(f'{name} count/failure mismatch; STOP')
        print(prefix, 'ok', flush=True)


if __name__ == '__main__':
    main()

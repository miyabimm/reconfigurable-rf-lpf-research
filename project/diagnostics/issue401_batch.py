#!/usr/bin/env python3
"""Fixed phase A order, no retries. Each launched slot reserves 100 forwards."""
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
SCRIPTS = (HERE / 'issue401_batch.py', HERE / 'issue401_benchmark.py', HERE / 'issue401_timing.py')
OUTPUT = HERE / 'issue401_raw'


def hashes():
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in SCRIPTS}


def save(path, value):
    with path.open('x') as file:
        json.dump(value, file, sort_keys=True, indent=2, allow_nan=False)
        file.write('\n')
        file.flush()
        os.fsync(file.fileno())


def main():
    if any(os.environ.get(k) != '1' for k in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS')):
        raise ValueError('thread limits must be set before process start')
    identity = source_identity(ROOT)
    source = sha(identity)
    expected_scripts = hashes()
    OUTPUT.mkdir(exist_ok=False)
    save(OUTPUT / 'freeze.json', {'source_identity': identity, 'source_sha': source, 'scripts': expected_scripts,
         'order': ['plain', 'timed'] + ['plain', 'timed', 'timed', 'plain'] * 5,
         'warmup_count': 2, 'per_run_forward_reservation': 100, 'samples_per_forward': 70})
    order = ['plain', 'timed'] + ['plain', 'timed', 'timed', 'plain'] * 5
    reference = None
    for i, mode in enumerate(order):
        if sha(source_identity(ROOT)) != source or hashes() != expected_scripts:
            raise RuntimeError('source changed; STOP; no retry')
        prefix = f'{i:02d}-{mode}'
        command = [sys.executable, str(HERE / 'issue401_benchmark.py'), '--mode', mode, '--source-sha', source]
        save(OUTPUT / (prefix + '.started.json'), {'sequence': i, 'warmup': i < 2, 'command': command,
             'reservation_forward': 100, 'reservation_samples': 7000})
        run = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=False)
        record = {'sequence': i, 'warmup': i < 2, 'returncode': run.returncode, 'stdout': run.stdout, 'stderr': run.stderr}
        save(OUTPUT / (prefix + '.json'), record)
        if run.returncode:
            raise RuntimeError(f'{prefix} failed; STOP; reservation remains unknown')
        report = json.loads(run.stdout)
        if report['source_sha'] != source or report['mode'] != mode:
            raise RuntimeError('report mismatch; STOP')
        if reference is None:
            reference = report['solver']
        elif report['solver'] != reference:
            raise RuntimeError('solver output mismatch; STOP')
        if mode == 'timed':
            t = report['timers']
            if any(t[n]['count'] != 100 or t[n]['failed'] for n in ('solver_callback', 'rf_forward', 'requirements', 'residual')):
                raise RuntimeError('callback count/failure mismatch; STOP')
        print(prefix, 'ok', flush=True)


if __name__ == '__main__':
    main()

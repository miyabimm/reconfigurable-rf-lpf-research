#!/usr/bin/env python3
"""New independent L2/L3 repetitions; preserve all previous Issue 401 evidence."""
import argparse
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
OUT = HERE / 'issue401_refined_raw'
SCRIPTS = [HERE / name for name in ('issue401_refined_batch.py', 'issue401_benchmark.py', 'issue401_timing.py')]


def save(path, value):
    with path.open('x') as f:
        json.dump(value, f, sort_keys=True, indent=2, allow_nan=False)
        f.write('\n')
        f.flush()
        os.fsync(f.fileno())


def hashes():
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in SCRIPTS}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--post-ports', action='store_true', help='write a new post-optimization measurement set')
    args = parser.parse_args()
    output = HERE / 'issue401_postports_raw' if args.post_ports else OUT
    if any(os.environ.get(k) != '1' for k in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS')):
        raise ValueError('Single-thread environment required')
    identity, scripts = source_identity(ROOT), hashes()
    source = sha(identity)
    order = [('plain', True), ('timed', True), ('deep', True)]
    order += [(mode, False) for mode in ('plain', 'timed', 'timed', 'plain') * 5]
    order += [('deep', False)] * 10
    output.mkdir(exist_ok=False)
    save(output / 'freeze.json', dict(source_identity=identity, source_sha=source, scripts=scripts,
         order=order, samples_per_forward=70, max_nfev_per_run=100,
         affinity=sorted(os.sched_getaffinity(0))))
    reference = None
    for i, (mode, warmup) in enumerate(order):
        if sha(source_identity(ROOT)) != source or hashes() != scripts:
            raise RuntimeError('Source changed; STOP, no retry')
        prefix = f'{i:02d}-{mode}'
        command = [sys.executable, str(HERE / 'issue401_benchmark.py'), '--mode', mode, '--source-sha', source]
        save(output / (prefix + '.started.json'), dict(sequence=i, warmup=warmup, command=command,
             max_forward=100, samples_per_forward=70))
        result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=False)
        save(output / (prefix + '.json'), dict(sequence=i, warmup=warmup, returncode=result.returncode,
                                            stdout=result.stdout, stderr=result.stderr))
        if result.returncode:
            raise RuntimeError(f'{prefix} failed; STOP, retain unknown consumption')
        report = json.loads(result.stdout)
        if report['source_sha'] != source or report['mode'] != mode or report['affinity'] != sorted(os.sched_getaffinity(0)):
            raise RuntimeError(f'{prefix}: identity mismatch; STOP')
        if reference is None:
            reference = report['solver']
        elif report['solver'] != reference:
            raise RuntimeError(f'{prefix}: solver mismatch; STOP')
        if mode != 'plain':
            names = ['solver_callback', 'rf_forward', 'requirements', 'residual']
            if mode == 'deep':
                names += ['l3_port_admittance', 'l3_node_admittance', 'l3_matrices',
                          'l3_power_response', 'l3_decode', 'l3_encode', 'l3_y_to_s_solve']
                if report['timers']['l3_cascade']['count'] != 200 or report['timers']['l3_cascade']['failed']:
                    raise RuntimeError(f'{prefix}: cascade probe mismatch; STOP')
            if any(report['timers'][n]['count'] != 100 or report['timers'][n]['failed'] for n in names):
                raise RuntimeError(f'{prefix}: probe mismatch; STOP')
        print(prefix, 'ok', flush=True)


if __name__ == '__main__':
    main()

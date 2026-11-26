#!/usr/bin/env python3
"""Execute the existing develop CLI in fixed checkouts, recording process costs.

No RF runner internals or monkey patches are used. Every invocation has a fresh
output and its own stdout/stderr, including failures and exit code 4.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import resource
import subprocess
import sys
import time

CHECKOUTS = {'base': '/tmp/issue521-cli-base', 'D1': '/tmp/issue521-cli-d1', 'CD1': '/tmp/issue521-cli-cd1'}
HEADS = {'base': '7957fd60e685b6afb2f62fcdc1551ab8bdbfc43d',
         'D1': '729e12453c882bf23b91cf8d79c02cb0f31b4392',
         'CD1': '4d3def8f636f14938097f22965315fc22d6ab7ca'}
THREADS = ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS')


def save(path, data):
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(data, indent=2, allow_nan=False)+'\n')
    temp.replace(path)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    parser.add_argument('--python', required=True, type=Path)
    parser.add_argument('--inputs', required=True, type=Path)
    parser.add_argument('--seeds', type=int, nargs='+', default=[1001, 1010, 1020])
    parser.add_argument('--cycles', type=int, default=3)
    args = parser.parse_args()
    assert args.seeds and args.cycles > 0
    assert all(os.environ.get(k) == '1' for k in THREADS)
    assert args.python.is_absolute() and args.inputs.is_absolute() and args.directory.is_absolute()
    assert not args.directory.exists()
    args.directory.mkdir(parents=True)
    manifest = json.loads((args.inputs/'manifest.json').read_text())
    assert manifest['budget'] == 5000
    for mode, directory in CHECKOUTS.items():
        assert subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=directory, text=True).strip() == HEADS[mode]
        assert not subprocess.check_output(['git', 'status', '--porcelain'], cwd=directory, text=True).strip()
    result = {'heads': HEADS, 'manifest_sha256': digest(args.inputs/'manifest.json'),
              'threads': {k: os.environ[k] for k in THREADS}, 'affinity': sorted(os.sched_getaffinity(0)),
              'runs': [], 'seeds': args.seeds, 'cycles': args.cycles,
              'description': 'warmup one per mode; rotating/reversing order; plain CLI'}
    save(args.directory/'summary.json', result)
    schedule = [('warmup', 0, 1001, mode) for mode in ('base', 'D1', 'CD1')]
    for cycle in range(args.cycles):
        for n, seed in enumerate(args.seeds):
            order = ('base', 'D1', 'CD1')
            order = order[(n+cycle)%3:]+order[:(n+cycle)%3]
            if cycle % 2:
                order = tuple(reversed(order))
            schedule.extend(('calibration', cycle, seed, mode) for mode in order)
    for phase, cycle, seed, mode in schedule:
        config = args.inputs/f'{seed}-config.json'; starts = args.inputs/f'{seed}-starts.json'
        record = manifest['seeds'][str(seed)]
        assert digest(config) == record['config_sha256'] and digest(starts) == record['starts_sha256']
        name = f'{phase}-{cycle}-{seed}-{mode}'
        output = args.directory/name
        command = [str(args.python), 'scripts/run_rf_search.py', 'develop', '--config', str(config),
                   '--starts', str(starts), '--output', str(output), '--spot-checks', '{"terminal":[0,111]}',
                   '--checkpoint-interval-forwards', '1000']
        before = resource.getrusage(resource.RUSAGE_CHILDREN); t = time.perf_counter()
        proc = subprocess.run(command, cwd=CHECKOUTS[mode], capture_output=True, text=True)
        wall = time.perf_counter()-t; after = resource.getrusage(resource.RUSAGE_CHILDREN)
        (args.directory/(name+'.stdout')).write_text(proc.stdout)
        (args.directory/(name+'.stderr')).write_text(proc.stderr)
        row = {'phase': phase, 'cycle': cycle, 'seed': seed, 'mode': mode, 'head': HEADS[mode],
               'config_sha256': digest(config), 'starts_sha256': digest(starts), 'initial_sha256': record['vector_sha256'],
               'exit_code': proc.returncode, 'wall_s': wall,
               'cpu_s': after.ru_utime+after.ru_stime-before.ru_utime-before.ru_stime,
               'output': str(output), 'stdout_sha256': digest(args.directory/(name+'.stdout')),
               'stderr_sha256': digest(args.directory/(name+'.stderr'))}
        result['runs'].append(row); save(args.directory/'summary.json', result)
        print(name, 'exit', proc.returncode, 'wall', round(wall, 3), 'cpu', round(row['cpu_s'], 3), flush=True)
        if proc.returncode not in (0, 4):
            raise RuntimeError('CLI stopped; raw outputs retained; investigate before continuing')
    result['complete'] = True
    save(args.directory/'summary.json', result)


if __name__ == '__main__':
    main()

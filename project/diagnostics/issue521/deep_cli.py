#!/usr/bin/env python3
"""Orchestrate fixed-commit plain/deep comparisons using only the public CLI."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import resource
import subprocess
import time

CHECKOUTS = {'base': ('/tmp/issue521-deep-base', 'ea01eb9eb530ef11a82609414696c7f08305d4e8'),
             'CD1': ('/tmp/issue521-deep-cd1', 'e08c8097587d51e2036ead09f2816d5e9a1e2113')}
THREADS = ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS')


def digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def save(p, data):
    tmp = p.with_suffix('.tmp'); tmp.write_text(json.dumps(data, indent=2, allow_nan=False)+'\n'); tmp.replace(p)


def environment(cpu):
    def read(p):
        try:
            return Path(p).read_text().strip()
        except OSError:
            return None
    return {'loadavg': os.getloadavg(), 'affinity': sorted(os.sched_getaffinity(0)),
            'cpu_frequency_khz': read(f'/sys/devices/system/cpu/cpu{cpu}/cpufreq/scaling_cur_freq'),
            'temperature_millic': {str(p): read(p) for p in Path('/sys/class/thermal').glob('thermal_zone*/temp')}}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('out', type=Path)
    parser.add_argument('--python', type=Path, required=True)
    parser.add_argument('--inputs', type=Path, required=True)
    parser.add_argument('--cycles', type=int, default=3)
    args = parser.parse_args()
    assert all(os.environ.get(k) == '1' for k in THREADS)
    assert all(p.is_absolute() for p in (args.out, args.python, args.inputs)) and not args.out.exists()
    cpu = min(os.sched_getaffinity(0)); os.sched_setaffinity(0, {cpu})
    for directory, head in CHECKOUTS.values():
        assert subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=directory, text=True).strip() == head
        assert not subprocess.check_output(['git', 'status', '--porcelain'], cwd=directory, text=True).strip()
    manifest = json.loads((args.inputs/'manifest.json').read_text()); assert manifest['budget'] == 5000
    args.out.mkdir(parents=True)
    result = {'heads': {k: v[1] for k, v in CHECKOUTS.items()}, 'cpu': cpu,
              'python': str(args.python), 'manifest_sha256': digest(args.inputs/'manifest.json'),
              'threads': {k: os.environ[k] for k in THREADS}, 'runs': [], 'cycles': args.cycles}
    save(args.out/'summary.json', result)
    arms = (('base', 'plain'), ('CD1', 'plain'), ('base', 'deep'), ('CD1', 'deep'))
    schedule = [('warmup', 0, 1001, *arm) for arm in arms]
    for cycle in range(args.cycles):
        for i, seed in enumerate((1001, 1010, 1020)):
            offset = (cycle+i) % 4
            order = arms[offset:]+arms[:offset]
            if (cycle+i) % 2: order = tuple(reversed(order))
            schedule.extend(('measure', cycle, seed, *arm) for arm in order)
    for phase, cycle, seed, mode, level in schedule:
        inputs = manifest['seeds'][str(seed)]
        config, starts = args.inputs/f'{seed}-config.json', args.inputs/f'{seed}-starts.json'
        assert digest(config) == inputs['config_sha256'] and digest(starts) == inputs['starts_sha256']
        name = f'{phase}-{cycle}-{seed}-{mode}-{level}'
        output = args.out/name; timing = args.out/(name+'-timing.json')
        command = [str(args.python), 'scripts/run_rf_search.py', 'develop', '--config', str(config), '--starts', str(starts),
                   '--output', str(output), '--spot-checks', '{"terminal":[0,111]}', '--checkpoint-interval-forwards', '1000']
        if level == 'deep': command += ['--timing-output', str(timing), '--timing-level', 'deep']
        env_before = environment(cpu); usage = resource.getrusage(resource.RUSAGE_CHILDREN); start = time.perf_counter()
        proc = subprocess.run(command, cwd=CHECKOUTS[mode][0], capture_output=True, text=True)
        wall = time.perf_counter()-start; end = resource.getrusage(resource.RUSAGE_CHILDREN); env_after = environment(cpu)
        (args.out/(name+'.stdout')).write_text(proc.stdout); (args.out/(name+'.stderr')).write_text(proc.stderr)
        record = {'phase': phase, 'cycle': cycle, 'seed': seed, 'mode': mode, 'level': level,
                  'head': CHECKOUTS[mode][1], 'config_sha256': digest(config), 'starts_sha256': digest(starts),
                  'initial_sha256': inputs['vector_sha256'], 'exit_code': proc.returncode, 'wall_s': wall,
                  'cpu_s': end.ru_utime+end.ru_stime-usage.ru_utime-usage.ru_stime,
                  'output': str(output), 'timing': str(timing) if level == 'deep' else None,
                  'env_before': env_before, 'env_after': env_after}
        result['runs'].append(record); save(args.out/'summary.json', result)
        print(name, proc.returncode, 'wall', round(wall, 3), 'cpu', round(record['cpu_s'], 3), flush=True)
        if proc.returncode not in (0, 4): raise RuntimeError('CLI failed; retain outputs for review')
        if level == 'deep' and not timing.exists(): raise RuntimeError('Deep output missing; retain outputs')
    result['complete'] = True; save(args.out/'summary.json', result)


if __name__ == '__main__': main()

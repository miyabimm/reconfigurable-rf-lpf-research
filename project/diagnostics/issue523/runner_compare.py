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

CHECKOUTS = {'base': ('/tmp/issue523-base', '79f9edfd63aa1af07a2b355e38a957e57f742f54'),
             'I2': ('/tmp/issue523-i2', '82920f7a4ae635242908c16b4e11b29b27d5edf3')}
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
    parser.add_argument('--seeds', type=int, nargs='+', default=[1001, 1010, 1020])
    parser.add_argument('--plain-only', action='store_true')
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
    levels = ('plain',) if args.plain_only else ('plain', 'deep')
    arms = tuple((mode, level) for level in levels for mode in ('base', 'I2'))
    schedule = [('warmup', 0, args.seeds[0], *arm) for arm in arms]
    for cycle in range(args.cycles):
        for i, seed in enumerate(args.seeds):
            # Each level alternates its own version order, including per seed
            # when cycles is even. Also alternate which level is run first.
            level_order = levels if (cycle+i) % 2 == 0 else levels[::-1]
            for level in level_order:
                reverse = (cycle+i+(level == 'deep')) % 2
                modes = ('I2', 'base') if reverse else ('base', 'I2')
                schedule.extend(('measure', cycle, seed, mode, level) for mode in modes)
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
                  'user_s': end.ru_utime-usage.ru_utime, 'system_s': end.ru_stime-usage.ru_stime,
                  'minor_faults': end.ru_minflt-usage.ru_minflt, 'major_faults': end.ru_majflt-usage.ru_majflt,
                  'children_peak_rss_kib_so_far': end.ru_maxrss,
                  'output': str(output), 'timing': str(timing) if level == 'deep' else None,
                  'timing_sha256': digest(timing) if timing.exists() else None,
                  'env_before': env_before, 'env_after': env_after}
        result['runs'].append(record); save(args.out/'summary.json', result)
        print(name, proc.returncode, 'wall', round(wall, 3), 'cpu', round(record['cpu_s'], 3), flush=True)
        if proc.returncode not in (0, 4): raise RuntimeError('CLI failed; retain outputs for review')
        if level == 'deep' and not timing.exists(): raise RuntimeError('Deep output missing; retain outputs')
    result['complete'] = True; save(args.out/'summary.json', result)


if __name__ == '__main__': main()

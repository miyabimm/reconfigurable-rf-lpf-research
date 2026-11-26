#!/usr/bin/env python3
"""Run the 20-seed fixed/equal-time plan only through the existing develop CLI."""
import argparse
import json
import os
from pathlib import Path
import resource
import subprocess
import time
from cli_compare import CHECKOUTS, HEADS, THREADS, digest, save


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('out', type=Path)
    parser.add_argument('--python', type=Path, required=True)
    parser.add_argument('--fixed-inputs', type=Path, required=True)
    parser.add_argument('--time-inputs', type=Path, required=True)
    parser.add_argument('--frozen', type=Path, required=True)
    args = parser.parse_args()
    assert all(os.environ.get(k) == '1' for k in THREADS)
    assert all(x.is_absolute() for x in (args.out, args.python, args.fixed_inputs, args.time_inputs, args.frozen))
    assert not args.out.exists()
    frozen = json.loads(args.frozen.read_text())
    fixed = json.loads((args.fixed_inputs/'manifest.json').read_text())
    timed = json.loads((args.time_inputs/'manifest.json').read_text())
    assert fixed['budget'] == 5000 and set(frozen['budgets'].values()) == {timed['budget']}
    for mode, directory in CHECKOUTS.items():
        assert subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=directory, text=True).strip() == HEADS[mode]
        assert not subprocess.check_output(['git', 'status', '--porcelain'], cwd=directory, text=True).strip()
    args.out.mkdir(parents=True)
    result = {'heads': HEADS, 'threads': {k: os.environ[k] for k in THREADS},
              'affinity': sorted(os.sched_getaffinity(0)), 'frozen_sha256': digest(args.frozen),
              'fixed_manifest_sha256': digest(args.fixed_inputs/'manifest.json'),
              'time_manifest_sha256': digest(args.time_inputs/'manifest.json'),
              'frozen_budgets': frozen['budgets'], 'runs': [],
              'description': '20 seeds; cyclic/reversed 3-arm fixed then alternating 2-arm time; base fixed reused'}
    save(args.out/'summary.json', result)
    schedule = []
    for index, seed in enumerate(range(1001, 1021)):
        modes = ('base', 'D1', 'CD1')
        modes = modes[index%3:]+modes[:index%3]
        if index%2: modes = tuple(reversed(modes))
        schedule.extend(('fixed', seed, mode) for mode in modes)
        modes = ('D1', 'CD1') if index%2 == 0 else ('CD1', 'D1')
        schedule.extend(('time', seed, mode) for mode in modes)
    for phase, seed, mode in schedule:
        inputs, manifest = (args.fixed_inputs, fixed) if phase == 'fixed' else (args.time_inputs, timed)
        record = manifest['seeds'][str(seed)]
        assert record['vector_sha256'] == fixed['seeds'][str(seed)]['vector_sha256']
        config, starts = inputs/f'{seed}-config.json', inputs/f'{seed}-starts.json'
        assert digest(config) == record['config_sha256'] and digest(starts) == record['starts_sha256']
        name = f'{phase}-{seed}-{mode}'; output = args.out/name
        command = [str(args.python), 'scripts/run_rf_search.py', 'develop', '--config', str(config),
                   '--starts', str(starts), '--output', str(output), '--spot-checks', '{"terminal":[0,111]}',
                   '--checkpoint-interval-forwards', '1000']
        before = resource.getrusage(resource.RUSAGE_CHILDREN); t = time.perf_counter()
        proc = subprocess.run(command, cwd=CHECKOUTS[mode], capture_output=True, text=True)
        wall = time.perf_counter()-t; after = resource.getrusage(resource.RUSAGE_CHILDREN)
        (args.out/(name+'.stdout')).write_text(proc.stdout)
        (args.out/(name+'.stderr')).write_text(proc.stderr)
        row = {'phase': phase, 'seed': seed, 'mode': mode, 'head': HEADS[mode],
               'config_sha256': digest(config), 'starts_sha256': digest(starts),
               'initial_sha256': record['vector_sha256'], 'exit_code': proc.returncode, 'wall_s': wall,
               'cpu_s': after.ru_utime+after.ru_stime-before.ru_utime-before.ru_stime, 'output': str(output),
               'stdout_sha256': digest(args.out/(name+'.stdout')), 'stderr_sha256': digest(args.out/(name+'.stderr'))}
        result['runs'].append(row); save(args.out/'summary.json', result)
        print(name, 'exit', proc.returncode, 'wall', round(wall, 3), flush=True)
        if proc.returncode not in (0, 4):
            raise RuntimeError('CLI stopped; all outputs retained; investigate')
    result['complete'] = True; save(args.out/'summary.json', result)


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""Controlled glibc allocator sensitivity; launch only unmodified develop CLI."""
import json
import os
from pathlib import Path
import subprocess
import sys
from deep_cli import CHECKOUTS, THREADS, save

CONDITIONS = {'default': {}, 'threshold': {'MALLOC_MMAP_THRESHOLD_': '16777216'},
              'notrim': {'MALLOC_TRIM_THRESHOLD_': '2147483647'},
              'both': {'MALLOC_MMAP_THRESHOLD_': '16777216', 'MALLOC_TRIM_THRESHOLD_': '2147483647'}}


def main(out, python, inputs):
    assert all(os.environ.get(k) == '1' for k in THREADS)
    assert not out.exists(); out.mkdir(parents=True)
    cpu = min(os.sched_getaffinity(0)); os.sched_setaffinity(0, {cpu})
    rows = {'conditions': CONDITIONS, 'cpu': cpu, 'runs': []}
    save(out/'summary.json', rows)
    order = tuple(CONDITIONS)
    for cycle in range(2):
        for cond in (order if cycle == 0 else tuple(reversed(order))):
            for mode in (('base', 'CD1') if cycle == 0 else ('CD1', 'base')):
                directory, head = CHECKOUTS[mode]
                assert subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=directory, text=True).strip() == head
                name = f'{cycle}-{cond}-{mode}'; path = out/name; timefile = out/(name+'.time')
                env = dict(os.environ)
                for k in ('MALLOC_MMAP_THRESHOLD_', 'MALLOC_TRIM_THRESHOLD_'): env.pop(k, None)
                env.update(CONDITIONS[cond])
                cmd = ['/usr/bin/time', '-f', '%e %U %S %M %R %F', '-o', str(timefile), str(python),
                       'scripts/run_rf_search.py', 'develop', '--config', str(inputs/'1001-config.json'),
                       '--starts', str(inputs/'1001-starts.json'), '--output', str(path),
                       '--spot-checks', '{"terminal":[0,111]}', '--checkpoint-interval-forwards', '1000']
                proc = subprocess.run(cmd, cwd=directory, env=env, capture_output=True, text=True)
                (out/(name+'.stdout')).write_text(proc.stdout); (out/(name+'.stderr')).write_text(proc.stderr)
                vals = timefile.read_text().strip().splitlines()[-1].split()
                assert len(vals) == 6
                wall, user, system = map(float, vals[:3]); rss, minor, major = map(int, vals[3:])
                rows['runs'].append({'cycle': cycle, 'condition': cond, 'mode': mode, 'head': head,
                                     'exit_code': proc.returncode, 'wall_s': wall, 'user_s': user,
                                     'system_s': system, 'maxrss_kb': rss, 'minor_faults': minor,
                                     'major_faults': major, 'output': str(path)})
                save(out/'summary.json', rows)
                print(name, proc.returncode, wall, system, minor, flush=True)
                if proc.returncode not in (0, 4): raise RuntimeError('CLI failed; retain outputs')
    rows['complete'] = True; save(out/'summary.json', rows)


if __name__ == '__main__':
    main(*(Path(v).absolute() for v in sys.argv[1:]))

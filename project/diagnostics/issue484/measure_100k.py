#!/usr/bin/env python3
"""Plain 100k three-way diagnostic; raw Runner evidence stays in a fresh /tmp directory."""
import copy
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[3]
MODES = {'A': (False, False), 'B': (True, False), 'C': (True, True)}
ORDER = ('ABC', 'BCA', 'CAB', 'CBA', 'ACB', 'BAC')


def child(mode, count, output):
    sys.path.insert(0, str(ROOT / 'src'))
    from lpf.search import _development_runner as runner
    config = json.loads((ROOT / 'project/diagnostics/issue470/config.json').read_text())
    starts = json.loads((ROOT / 'project/diagnostics/issue470/starts.json').read_text())
    batch, partial = MODES[mode]
    config['arms'][0]['steps'][0]['options'].update(max_search_forwards=count, batch_fd=batch, partial_fd=partial)
    # Batched finite differences can complete a group of up to 24 extra forwards.
    cap = count + 24
    config['budget'] = dict(rf_samples=70*cap+476, rf_forwards=cap+1, independent_mna_samples=2)
    t = time.perf_counter()
    state = runner.run(config, starts, output, root=ROOT, spot_checks={'terminal': [0, 111]},
                       checkpoint_interval=1000, rf_cache_mode='lk')
    print(json.dumps({'runner_wall_s': time.perf_counter()-t, 'status': state['status']}), flush=True)


def main(directory):
    directory = Path(directory).resolve()
    directory.mkdir(exist_ok=False)
    env = dict(os.environ, OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1', MKL_NUM_THREADS='1')
    cpu = min(os.sched_getaffinity(0))
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    metadata = {'head': head, 'cpu_affinity': cpu, 'platform': platform.platform(),
                'cpuinfo': Path('/proc/cpuinfo').read_text().split('model name\t: ')[1].split('\n')[0],
                'threads': {k: env[k] for k in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS')},
                'order': ORDER}
    (directory / 'environment.json').write_text(json.dumps(metadata, indent=2)+'\n')
    schedule = [('warm-'+m, m, 312) for m in 'ABC'] + [(f'{i+1}-{m}', m, 100000) for i, order in enumerate(ORDER) for m in order]
    for name, mode, count in schedule:
        logfile = directory / (name+'.log')
        with logfile.open('w') as log:
            start = time.perf_counter()
            p = subprocess.Popen(['taskset', '-c', str(cpu), sys.executable, __file__, '--child', mode, str(count), str(directory/name)],
                                 cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
            _, status, usage = os.wait4(p.pid, 0)
            wall = time.perf_counter()-start
        row = dict(name=name, mode=mode, nominal_forwards=count, process_wall_s=wall,
                   cpu_s=usage.ru_utime+usage.ru_stime, max_rss_kib=usage.ru_maxrss,
                   exit_code=os.waitstatus_to_exitcode(status), log=logfile.name)
        with (directory/'measurements.jsonl').open('a') as f:
            f.write(json.dumps(row)+'\n'); f.flush(); os.fsync(f.fileno())
        print(json.dumps(row), flush=True)
        if row['exit_code'] != 0:
            raise SystemExit('failed; retained all evidence in '+str(directory))


if __name__ == '__main__':
    if sys.argv[1] == '--child':
        child(sys.argv[2], int(sys.argv[3]), sys.argv[4])
    else:
        main(sys.argv[1])

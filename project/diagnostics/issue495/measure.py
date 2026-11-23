#!/usr/bin/env python3
"""Run independent-process paired plain and trace/cache replays on two worktrees."""
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import time

base, new, output = map(lambda s: Path(s).resolve(), sys.argv[1:4])
output.mkdir(exist_ok=False)
cpu = min(os.sched_getaffinity(0))
env = dict(os.environ, OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1', MKL_NUM_THREADS='1')
roots = {'A': base, 'B': new}
metadata = {'heads': {k: subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=p, text=True).strip() for k, p in roots.items()},
            'status': {k: subprocess.check_output(['git', 'status', '--porcelain'], cwd=p, text=True) for k, p in roots.items()},
            'python': sys.version, 'platform': platform.platform(), 'cpu': cpu,
            'cpu_model': next(x for x in Path('/proc/cpuinfo').read_text().splitlines() if x.startswith('model name')),
            'threads': {k: env[k] for k in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS')}}
(output/'environment.json').write_text(json.dumps(metadata, indent=2))
schedule = [('warm-A', 'A', 312, False), ('warm-B', 'B', 312, False),
            ('1-A', 'A', 100000, False), ('1-B', 'B', 100000, False),
            ('2-B', 'B', 100000, False), ('2-A', 'A', 100000, False),
            ('3-A', 'A', 100000, False), ('3-B', 'B', 100000, False),
            ('trace-A', 'A', 100000, True), ('trace-B', 'B', 100000, True)]
for name, variant, count, trace in schedule:
    root = roots[variant]
    script = root/'project/diagnostics/issue491/cache_replay.py' if trace else root/'project/diagnostics/issue487/measure.py'
    args = ['plain', str(output/name)] if trace else ['--child', 'plain', str(count), str(output/name), '0']
    start = time.perf_counter()
    load_before = os.getloadavg()
    with (output/(name+'.log')).open('w') as log:
        p = subprocess.Popen(['taskset', '-c', str(cpu), sys.executable, str(script), *args], cwd=root,
                             env=env, stdout=log, stderr=subprocess.STDOUT)
        _, status, usage = os.wait4(p.pid, 0)
        p.returncode = os.waitstatus_to_exitcode(status)
    elapsed = time.perf_counter() - start
    row = dict(name=name, variant=variant, count=count, trace=trace, process_wall_s=elapsed,
               process_cpu_s=usage.ru_utime + usage.ru_stime, max_rss_kib=usage.ru_maxrss,
               voluntary_context_switches=usage.ru_nvcsw, involuntary_context_switches=usage.ru_nivcsw,
               load_before=load_before, load_after=os.getloadavg(), exit_code=p.returncode)
    if p.returncode == 0:
        lines = (output/(name+'.log')).read_text().splitlines()
        row.update(json.loads(lines[-2] if trace else lines[-1]))
        if trace:
            row['cache'] = json.loads(lines[-1])['search_cache']
    with (output/'measurements.jsonl').open('a') as f:
        f.write(json.dumps(row)+'\n')
    print(json.dumps(row), flush=True)
    if p.returncode:
        raise SystemExit('failed, evidence retained: '+str(output))

#!/usr/bin/env python3
"""Alternating plain independent-process #489 A/B using #487's fixed child."""
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import time


def main(old, new, output):
    old, new, output = map(lambda s: Path(s).resolve(), (old, new, output))
    output.mkdir(exist_ok=False)
    env = dict(os.environ, OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1', MKL_NUM_THREADS='1')
    cpu = min(os.sched_getaffinity(0))
    metadata = dict(python=sys.version, platform=platform.platform(),
                    affinity=cpu, cpuinfo=Path('/proc/cpuinfo').read_text().split('model name\t: ')[1].split('\n')[0],
                    threads={k:env[k] for k in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS')},
                    heads={tag:subprocess.check_output(['git','rev-parse','HEAD'], cwd=root, text=True).strip()
                           for tag, root in [('A',old),('B',new)]},
                    statuses={tag:subprocess.check_output(['git','status','--porcelain'], cwd=root, text=True)
                              for tag, root in [('A',old),('B',new)]})
    import numpy, scipy
    metadata.update(numpy=numpy.__version__, scipy=scipy.__version__)
    (output/'environment.json').write_text(json.dumps(metadata, indent=2)+'\n')
    schedule = [('warm-A',old,312), ('warm-B',new,312)]
    schedule += [(f'{i}-{tag}', root, 100000) for i, order in enumerate(((('A',old),('B',new)),
                 (('B',new),('A',old)), (('A',old),('B',new))), 1) for tag, root in order]
    for name, root, count in schedule:
        log = output/(name+'.log')
        cmd = ['taskset','-c',str(cpu),sys.executable,str(root/'project/diagnostics/issue487/measure.py'),
               '--child','plain',str(count),str(output/name),'0']
        with log.open('w') as f:
            start = time.perf_counter()
            proc = subprocess.Popen(cmd, cwd=root, env=env, stdout=f, stderr=subprocess.STDOUT)
            _, status, usage = os.wait4(proc.pid, 0)
            elapsed = time.perf_counter() - start
        row = dict(name=name, process_wall_s=elapsed, cpu_s=usage.ru_utime+usage.ru_stime,
                   max_rss_kib=usage.ru_maxrss, exit_code=os.waitstatus_to_exitcode(status))
        if row['exit_code'] == 0:
            row.update(json.loads(log.read_text().splitlines()[-1]))
        with (output/'measurements.jsonl').open('a') as f:
            f.write(json.dumps(row)+'\n'); f.flush(); os.fsync(f.fileno())
        print(json.dumps(row), flush=True)
        if row['exit_code']:
            raise SystemExit('failed; evidence retained in '+str(output))


if __name__ == '__main__':
    main(*sys.argv[1:])

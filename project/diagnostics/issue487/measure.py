#!/usr/bin/env python3
"""Fixed C-path timing diagnostic; each child and output is independent."""
import hashlib
import json
import os
from pathlib import Path
import platform
import struct
import subprocess
import sys
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
ORDER = ('plain,timed,deep', 'timed,deep,plain', 'deep,plain,timed')


def child(mode, count, output, trace=False):
    sys.path.insert(0, str(ROOT/'src'))
    from lpf.search import _development_runner as runner, _development_worker as worker
    config = json.loads((ROOT/'project/diagnostics/issue470/config.json').read_text())
    starts = json.loads((ROOT/'project/diagnostics/issue470/starts.json').read_text())
    config['arms'][0]['steps'][0]['options'].update(max_search_forwards=count, batch_fd=True, partial_fd=True)
    config['budget'] = dict(rf_samples=70*(count+24)+476, rf_forwards=count+25, independent_mna_samples=2)
    kwargs = {} if mode == 'plain' else dict(timing_output=Path(str(output)+'.timing.json'), timing_level=mode)
    h = hashlib.sha256(); n = [0]
    original = worker.hybrid_minimize
    def capture(*args, **kw):
        progress = kw['progress_callback']
        def observe(x, f, *extra):
            n[0] += 1
            h.update(struct.pack('<'+'d'*len(x)+'d', *x, f))
            progress(x, f, *extra)
        kw['progress_callback'] = observe
        return original(*args, **kw)
    from contextlib import nullcontext
    with patch.object(worker, 'hybrid_minimize', capture) if trace else nullcontext():
        start = time.perf_counter()
        state = runner.run(config, starts, output, root=ROOT, spot_checks={'terminal': [0,111]},
                           checkpoint_interval=1000, rf_cache_mode='lk', **kwargs)
        elapsed = time.perf_counter()-start
    print(json.dumps(dict(runner_wall_s=elapsed, status=state['status'],
                          callbacks=n[0] if trace else None, trace_sha256=h.hexdigest() if trace else None)), flush=True)


def main(directory, count=100000):
    import numpy, scipy
    directory = Path(directory).resolve()
    directory.mkdir(exist_ok=False)
    env = dict(os.environ, OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1', MKL_NUM_THREADS='1')
    cpu = min(os.sched_getaffinity(0))
    metadata = dict(head=subprocess.check_output(['git','rev-parse','HEAD'], cwd=ROOT, text=True).strip(),
                    status=subprocess.check_output(['git','status','--porcelain'], cwd=ROOT, text=True),
                    python=sys.version, numpy=numpy.__version__, scipy=scipy.__version__, platform=platform.platform(),
                    cpuinfo=Path('/proc/cpuinfo').read_text().split('model name\t: ')[1].split('\n')[0],
                    affinity=cpu, threads={k:env[k] for k in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS')},
                    order=ORDER, count=count)
    (directory/'environment.json').write_text(json.dumps(metadata, indent=2)+'\n')
    schedule = [(f'warm-{m}',m,312,False) for m in ('plain','timed','deep')]
    schedule += [(f'{i+1}-{m}',m,count,False) for i, order in enumerate(ORDER) for m in order.split(',')]
    schedule += [(f'trace-{m}',m,count,True) for m in ('plain','deep')]
    for name, mode, forwards, trace in schedule:
        logfile = directory/(name+'.log')
        with logfile.open('w') as log:
            start = time.perf_counter()
            cmd = ['taskset','-c',str(cpu),sys.executable,__file__,'--child',mode,str(forwards),str(directory/name),str(int(trace))]
            p = subprocess.Popen(cmd, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
            _, status, usage = os.wait4(p.pid, 0)
            wall = time.perf_counter()-start
        row = dict(name=name, mode=mode, nominal_forwards=forwards, trace=trace, process_wall_s=wall,
                   cpu_s=usage.ru_utime+usage.ru_stime, max_rss_kib=usage.ru_maxrss,
                   exit_code=os.waitstatus_to_exitcode(status), log=logfile.name)
        if row['exit_code'] == 0:
            row.update(json.loads(logfile.read_text().splitlines()[-1]))
        with (directory/'measurements.jsonl').open('a') as f:
            f.write(json.dumps(row)+'\n'); f.flush(); os.fsync(f.fileno())
        print(json.dumps(row), flush=True)
        if row['exit_code']:
            raise SystemExit('failed; evidence retained in '+str(directory))


if __name__ == '__main__':
    if sys.argv[1] == '--child':
        child(sys.argv[2], int(sys.argv[3]), Path(sys.argv[4]), bool(int(sys.argv[5])))
    else:
        main(sys.argv[1], int(sys.argv[2]) if len(sys.argv)>2 else 100000)

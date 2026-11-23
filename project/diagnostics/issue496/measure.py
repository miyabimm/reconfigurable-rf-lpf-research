#!/usr/bin/env python3
"""Alternating clean-checkout #496 plain runs and untimed cache/trace replays."""
import json, os, pathlib, platform, subprocess, sys, time
import numpy, scipy

base, candidate, out = map(pathlib.Path, sys.argv[1:4])
out.mkdir(exist_ok=False)
cpu = min(os.sched_getaffinity(0))
env = dict(os.environ, OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1', MKL_NUM_THREADS='1')
roots = {'A': base, 'B': candidate}
metadata = {'heads': {k: subprocess.check_output(['git','rev-parse','HEAD'],cwd=p,text=True).strip() for k,p in roots.items()},
            'status': {k: subprocess.check_output(['git','status','--porcelain'],cwd=p,text=True) for k,p in roots.items()},
            'python': sys.version, 'numpy': numpy.__version__, 'scipy': scipy.__version__, 'platform': platform.platform(),
            'cpuinfo': pathlib.Path('/proc/cpuinfo').read_text().split('model name\t: ')[1].split('\n')[0],
            'affinity': cpu, 'threads': {k:env[k] for k in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS')},
            'loadavg_at_start': os.getloadavg(), 'schedule': ['warm-A','warm-B','1-A','1-B','2-B','2-A','3-A','3-B','trace-A','trace-B']}
assert all(not v for v in metadata['status'].values()), metadata['status']
(out/'environment.json').write_text(json.dumps(metadata,indent=2)+'\n')
for name in metadata['schedule']:
    arm=name[-1]; root=roots[arm]; dest=out/name; trace=name.startswith('trace')
    if trace:
        args=[str(root/'project/diagnostics/issue491/cache_replay.py'),'plain',str(dest)]
    else:
        args=[str(root/'project/diagnostics/issue487/measure.py'),'--child','plain',str(312 if name.startswith('warm') else 100000),str(dest),'0']
    log=out/(name+'.log')
    with log.open('w') as f:
        start=time.perf_counter(); p=subprocess.Popen(['taskset','-c',str(cpu),sys.executable,*args],cwd=root,env=env,stdout=f,stderr=subprocess.STDOUT)
        _, status, usage=os.wait4(p.pid,0); wall=time.perf_counter()-start
    row={'name':name,'arm':arm,'trace':trace,'process_wall_s':wall,'cpu_s':usage.ru_utime+usage.ru_stime,
         'max_rss_kib':usage.ru_maxrss,'exit_code':os.waitstatus_to_exitcode(status),'loadavg':os.getloadavg()}
    if row['exit_code']==0:
        lines=log.read_text().splitlines(); row.update(json.loads(lines[-2 if trace else -1]))
        if trace: row.update(json.loads(lines[-1]))
    with (out/'measurements.jsonl').open('a') as f:
        f.write(json.dumps(row)+'\n'); f.flush(); os.fsync(f.fileno())
    print(json.dumps(row),flush=True)
    if row['exit_code']: raise SystemExit('failure; retained at '+str(out))

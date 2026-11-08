"""Launch exactly one sequential develop CLI; poll durable parent/CPU, never retry."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import psutil

ROOT = Path(__file__).resolve().parents[3]


def main():
    if len(sys.argv) != 3:
        raise SystemExit('usage: monitor_pilot.py <fresh output> <existing input/log directory>')
    output, logs = map(Path, sys.argv[1:])
    if output.exists() or not logs.is_dir():
        raise ValueError('existing output or missing log directory')
    cmd = [sys.executable, str(ROOT/'scripts/run_rf_search.py'), 'develop',
           '--config', str(ROOT/'project/diagnostics/issue372/pilot.yaml'),
           '--starts', str(ROOT/'project/diagnostics/issue361/pilot-starts.json'),
           '--storage-mode', 'window100', '--output', str(output)]
    with (logs/'stdout.txt').open('xb') as stdout, (logs/'stderr.txt').open('xb') as stderr, \
         (logs/'monitor.jsonl').open('x', buffering=1) as events:
        started = time.monotonic()
        child = subprocess.Popen(cmd, cwd=ROOT, stdout=stdout, stderr=stderr)
        proc = psutil.Process(child.pid)
        def record(value):
            events.write(json.dumps(value, sort_keys=True)+'\n')
            events.flush()
            os.fsync(events.fileno())
        record(dict(event='started', pid=child.pid, command=cmd, epoch=time.time()))
        while child.poll() is None:
            try:
                cpu = proc.cpu_times()
                cpu_s = cpu.user + cpu.system
            except psutil.Error:
                cpu_s = None
            parent = output/'run.json'
            try:
                data = json.loads(parent.read_bytes())
                jobs = [{k: row.get(k) for k in ('seed', 'status', 'requested', 'completed', 'reserved', 'worker_status')}
                        for row in data['jobs']]
            except FileNotFoundError:
                jobs = None
            record(dict(event='sample', elapsed_s=time.monotonic()-started, cpu_s=cpu_s, jobs=jobs))
            time.sleep(1)
        record(dict(event='exited', elapsed_s=time.monotonic()-started, exit_code=child.returncode, epoch=time.time()))
        stdout.flush(); os.fsync(stdout.fileno()); stderr.flush(); os.fsync(stderr.fileno())
    return child.returncode

if __name__ == '__main__':
    raise SystemExit(main())

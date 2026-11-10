"""Issue 381: repeated non-RF workload; attach and independent child profiling.

Run with: uv run --frozen python project/diagnostics/issue381/benchmark.py
The direct py-spy child mode is intentionally NOT an integrated CLI supervisor.
"""
import json
import os
from pathlib import Path
import resource
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[3]


def workload(path):
    start, cpu = time.monotonic(), time.process_time()
    x = 0
    for i in range(30000000):
        x = (x + i * 3) % 1000003
    Path(path).write_text(json.dumps(dict(pid=os.getpid(), wall_s=time.monotonic()-start,
        cpu_s=time.process_time()-cpu, peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
        checksum=x)))


def main():
    sys.path.insert(0, str(ROOT / 'src'))
    from lpf.search.monitor import supervise
    results = []
    with tempfile.TemporaryDirectory(prefix='issue381-synthetic-') as tmp:
        tmp = Path(tmp)
        for repeat in range(3):
            # Rotate order to reduce systematic first/last effects, not eliminate noise.
            modes = ['baseline', 'monitor', 'attach', 'child']
            modes = modes[repeat:] + modes[:repeat]
            for mode in modes:
                path = tmp / f'{repeat}-{mode}'
                result_path = tmp / f'{repeat}-{mode}.json'
                cmd = [sys.executable, __file__, '--workload', str(result_path)]
                before = time.monotonic()
                if mode in ('monitor', 'attach'):
                    rc = supervise(cmd, path, None, profile=mode == 'attach', root=ROOT, interval=.1)
                    summary = json.loads((path/'monitor-summary.json').read_text())
                    stderr = (path/'profile-stderr.txt').read_text() if (path/'profile-stderr.txt').exists() else None
                else:
                    profile = tmp / f'{repeat}-child.speedscope.json'
                    run_cmd = (['py-spy', 'record', '--rate', '100', '--format', 'speedscope',
                                '--output', str(profile), '--'] + cmd) if mode == 'child' else cmd
                    proc = subprocess.run(run_cmd, capture_output=True, text=True)
                    rc, stderr, summary = proc.returncode, proc.stderr, None
                    if mode == 'child' and profile.exists():
                        data = json.loads(profile.read_text())
                        samples = [stack for p in data['profiles'] for stack in p.get('samples', [])]
                        frames = data['shared']['frames']
                        counts = {}
                        for stack in samples:
                            for index in set(stack):
                                name = frames[index].get('name')
                                counts[name] = counts.get(name, 0) + 1
                        summary = dict(sample_count=len(samples), function_inclusive_samples=counts,
                                       profiler_stdout=proc.stdout)
                elapsed = time.monotonic()-before
                results.append(dict(repeat=repeat, mode=mode, wrapper_exit=rc, launch_wall_s=elapsed,
                    workload=json.loads(result_path.read_text()) if result_path.exists() else None,
                    summary=summary, profiler_stderr=stderr))
    print(json.dumps(results, indent=2))


if __name__ == '__main__':
    if len(sys.argv) == 3 and sys.argv[1] == '--workload':
        workload(sys.argv[2])
    else:
        main()

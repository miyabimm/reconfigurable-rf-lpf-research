"""Reproduce Issue 378 synthetic overhead check; no RF/experiment inputs."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'src'))
from lpf.search.monitor import supervise

WORKLOAD = '''
import json, resource, time
start, cpu = time.monotonic(), time.process_time()
x = 0
for i in range(30000000):
    x = (x + i * 3) % 1000003
print(json.dumps(dict(wall_s=time.monotonic()-start, cpu_s=time.process_time()-cpu,
                      peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss, checksum=x)))
'''


def main():
    cmd = [sys.executable, '-c', WORKLOAD]
    results = {}
    with tempfile.TemporaryDirectory(prefix='issue378-synthetic-') as tmp:
        before = time.monotonic()
        baseline = subprocess.run(cmd, capture_output=True, text=True, check=True)
        results['baseline'] = dict(workload=json.loads(baseline.stdout),
                                   launch_wall_s=time.monotonic()-before)
        for mode in ('monitor', 'profile'):
            path = Path(tmp)/mode
            before = time.monotonic()
            code = supervise(cmd, path, None, profile=mode == 'profile', root=ROOT, interval=.1)
            results[mode] = dict(exit_code=code, workload=json.loads((path/'stdout.txt').read_text()),
                launch_wall_s=time.monotonic()-before,
                summary=json.loads((path/'monitor-summary.json').read_text()),
                profile_stderr=(path/'profile-stderr.txt').read_text() if (path/'profile-stderr.txt').exists() else None)
    print(json.dumps(results, indent=2))


if __name__ == '__main__':
    main()

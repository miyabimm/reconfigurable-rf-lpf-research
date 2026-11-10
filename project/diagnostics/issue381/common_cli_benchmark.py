"""Repeat non-RF loads through the actual develop CLI and common supervisor.

Usage: uv run --frozen python .../common_cli_benchmark.py /tmp/NEW-directory
The temporary sitecustomize executes only in the unmonitored child CLI; it
performs no RF work and then lets the actual CLI reject production (exit 3).
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[3]
SITE = '''
import json, os, resource, sys, time
if os.path.basename(sys.argv[0]) == 'run_rf_search.py' and not any(a.startswith('--monitor-d') for a in sys.argv[1:]):
    def synthetic_load():
        wall, cpu = time.monotonic(), time.process_time()
        value = 0
        for i in range(30000000):
            value = (value + i * 3) % 1000003
        return dict(pid=os.getpid(), wall_s=time.monotonic()-wall, cpu_s=time.process_time()-cpu,
                    peak_rss_kib=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss, checksum=value)
    print('SYNTHETIC ' + json.dumps(synthetic_load()), flush=True)
'''


def main(directory):
    directory = Path(directory).resolve()
    directory.mkdir(exist_ok=False)
    (directory/'sitecustomize.py').write_text(SITE)
    env = dict(os.environ, PYTHONPATH=str(directory) + os.pathsep + os.environ.get('PYTHONPATH', ''))
    results = []
    for repeat in range(3):
        modes = ['baseline', 'monitor', 'profile']
        modes = modes[repeat:] + modes[:repeat]
        for mode in modes:
            logs = directory/f'{repeat}-{mode}'
            cmd = [sys.executable, str(ROOT/'scripts/run_rf_search.py'), 'develop',
                   '--config', 'not-used', '--mode', 'production']
            if mode != 'baseline':
                cmd += ['--monitor-dir', str(logs)]
            if mode == 'profile':
                cmd += ['--profile']
            start = time.monotonic()
            proc = subprocess.run(cmd, env=env, capture_output=True, text=True)
            elapsed = time.monotonic()-start
            stdout = proc.stdout if mode == 'baseline' else (logs/'stdout.txt').read_text()
            stderr = proc.stderr if mode == 'baseline' else (logs/'stderr.txt').read_text()
            values = [json.loads(line.removeprefix('SYNTHETIC ')) for line in stdout.splitlines()
                      if line.startswith('SYNTHETIC ')]
            if proc.returncode != 3 or len(values) != 1 or 'production_not_authorized' not in stderr:
                raise RuntimeError(f'unexpected scientific exit/output: {mode} {proc.returncode} {stdout} {stderr}')
            row = dict(repeat=repeat, mode=mode, exit=proc.returncode, elapsed_s=elapsed, workload=values[0])
            if mode != 'baseline':
                summary = json.loads((logs/'monitor-summary.json').read_text())
                row.update(summary=summary, profiler_stderr=proc.stderr)
                if summary['exit_code'] != 3 or summary['child_pid'] != values[0]['pid']:
                    raise RuntimeError('scientific exit or PID mismatch')
            if mode == 'profile':
                profile = json.loads((logs/'profile.speedscope.json').read_text())
                stats = json.loads((logs/'profile-functions.json').read_text())
                frames = profile['shared']['frames']
                for p in profile['profiles']:
                    for sample in p.get('samples', []):
                        for index in sample:
                            if not 0 <= index < len(frames):
                                raise ValueError('invalid frame index')
                target = summary['profile']
                matching = [x for x in stats if x['name'] == 'synthetic_load']
                if not target['available'] or not matching or target['target_pid'] != values[0]['pid']:
                    raise RuntimeError('CLI samples/function statistics unavailable')
                row['workload_inclusive_samples'] = sum(x['inclusive_samples'] for x in matching)
            results.append(row)
    (directory/'results.json').write_text(json.dumps(results, indent=2) + '\n')
    print(json.dumps(results, indent=2))


if __name__ == '__main__':
    if len(sys.argv) != 2:
        raise SystemExit('one fresh output directory required')
    main(sys.argv[1])

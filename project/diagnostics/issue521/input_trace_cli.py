#!/usr/bin/env python3
"""Separate untimed Worker-vector hash observation via Python's profile hook."""
import json
import os
from pathlib import Path
import subprocess
import sys
from deep_cli import CHECKOUTS, THREADS, save


def main(out, python, inputs):
    assert all(os.environ.get(k) == '1' for k in THREADS)
    assert not out.exists(); out.mkdir(parents=True)
    os.sched_setaffinity(0, {min(os.sched_getaffinity(0))})
    diag = Path(__file__).resolve().parent
    result = {'note': 'trace overhead unmeasured; never use wall for performance', 'runs': []}
    save(out/'summary.json', result)
    for seed in (1001, 1010, 1020):
        for mode in ('base', 'CD1'):
            for level in ('plain', 'deep'):
                directory, head = CHECKOUTS[mode]
                assert subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=directory, text=True).strip() == head
                name = f'{seed}-{mode}-{level}'
                path = out/name; trace = out/(name+'-vector-hashes.json'); timing = out/(name+'-timing.json')
                cmd = [str(python), 'scripts/run_rf_search.py', 'develop', '--config', str(inputs/f'{seed}-config.json'),
                       '--starts', str(inputs/f'{seed}-starts.json'), '--output', str(path),
                       '--spot-checks', '{"terminal":[0,111]}', '--checkpoint-interval-forwards', '1000']
                if level == 'deep': cmd += ['--timing-output', str(timing), '--timing-level', 'deep']
                env = dict(os.environ, PYTHONPATH=f'{diag}:{directory}/src', ISSUE521_TRACE_OUTPUT=str(trace))
                proc = subprocess.run(cmd, cwd=directory, env=env, capture_output=True, text=True)
                (out/(name+'.stdout')).write_text(proc.stdout); (out/(name+'.stderr')).write_text(proc.stderr)
                row = {'seed': seed, 'mode': mode, 'level': level, 'head': head,
                       'exit_code': proc.returncode, 'output': str(path), 'trace': str(trace)}
                result['runs'].append(row); save(out/'summary.json', result)
                print(name, proc.returncode, flush=True)
                if proc.returncode not in (0, 4) or not trace.exists():
                    raise RuntimeError('trace failed; output retained')
                h = json.loads(trace.read_text())
                assert h['count'] == 5000 and h['worker_sources'] == [directory+'/src/lpf/search/_development_worker.py']
    result['complete'] = True; save(out/'summary.json', result)


if __name__ == '__main__':
    out, python, inputs = (Path(v).absolute() for v in sys.argv[1:])
    main(out, python, inputs)

#!/usr/bin/env python3
"""Issue 423: opt-in dB check A/B on the #419 fixed real RF inputs."""
import argparse
import inspect
import json
import os
from pathlib import Path
import subprocess
import sys

import issue419_probe as base

OLD = "    if any(np.any(np.isnan(m)) or np.any(np.isneginf(m)) for m in metrics):\n"
NEW = "    if not np.all(np.concatenate(metrics) > -np.inf):\n"


def candidate():
    source = inspect.getsource(base.ORIGINAL)
    assert source.count(OLD) == 1
    namespace = dict(base.rf.__dict__)
    exec(compile(source.replace(OLD, NEW), '<issue423-candidate>', 'exec'), namespace)
    return namespace['power_response']


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--child', choices=('old', 'new'))
    ap.add_argument('--mode', choices=('local', 'forward', 'equivalence'))
    ap.add_argument('--pairs', type=int, default=12)
    ap.add_argument('--output', type=Path)
    args = ap.parse_args()
    if args.child:
        base.make_candidate = lambda variant: candidate()
        base.child(args.mode, args.child)
        return
    if not args.output or args.output.exists() or args.pairs < 1:
        ap.error('provide a new output and positive pairs')
    env = dict(os.environ, OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1', MKL_NUM_THREADS='1')
    cpu = min(os.sched_getaffinity(0))
    runs = []
    for mode in ('local', 'forward', 'equivalence'):
        for pair in range(args.pairs if mode != 'equivalence' else 1):
            order = ('old', 'new') if pair % 2 == 0 else ('new', 'old')
            if mode == 'equivalence':
                order = ('new',)
            for variant in order:
                cmd = ['taskset', '-c', str(cpu), sys.executable, str(Path(__file__).resolve()),
                       '--child', variant, '--mode', mode]
                proc = subprocess.run(cmd, cwd=base.ROOT, env=env, capture_output=True, text=True)
                row = dict(mode=mode, pair=pair, variant=variant, command=cmd,
                           returncode=proc.returncode, stderr=proc.stderr)
                if proc.returncode == 0:
                    row['report'] = json.loads(proc.stdout)
                else:
                    row['stdout'] = proc.stdout
                runs.append(row)
                args.output.write_text(json.dumps(dict(runs=runs), indent=2, sort_keys=True, allow_nan=False)+'\n')
                if proc.returncode:
                    raise RuntimeError(f'child failed; saved {args.output}')
    print(f'{len(runs)} runs saved to {args.output}')


if __name__ == '__main__':
    main()

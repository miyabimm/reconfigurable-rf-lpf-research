#!/usr/bin/env python3
"""Plain old/new RF timing; fixed inputs, no post-solver forward or retry."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

from lpf.search._job_evaluation import source_identity
from lpf.search.plan import ROOT
from lpf.search.storage import sha

HERE = Path(__file__).resolve().parent
OLD = Path('/tmp/issue401-incidence-baseline')


def save(path, value):
    with path.open('x') as file:
        json.dump(value, file, sort_keys=True, indent=2, allow_nan=False)
        file.write('\n')
        file.flush()
        os.fsync(file.fileno())


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--candidate', choices=('incidence', 'ports'), default='incidence')
    parser.add_argument('--repeat', action='store_true', help='write a distinct second measurement batch')
    args = parser.parse_args()
    suffix = '_repeat' if args.repeat else ''
    out = HERE / f'issue401_{args.candidate}_ab{suffix}_raw'
    changed_file = {'incidence': 'src/lpf/rf_core/coupled_lc.py',
                    'ports': 'src/lpf/rf_core/model.py'}[args.candidate]
    if any(os.environ.get(k) != '1' for k in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS')):
        raise ValueError('Single-thread environment required')
    roots = {'old': OLD, 'new': ROOT}
    identities = {k: source_identity(v) for k, v in roots.items()}
    changed = {k for k in identities['old']['files'] if identities['old']['files'][k] != identities['new']['files'].get(k)}
    if (set(identities['old']['files']) != set(identities['new']['files']) or
            changed != {changed_file} or
            identities['old']['environment'] != identities['new']['environment'] or
            any(v['dirty_patch_sha256'] != hashlib.sha256(b'').hexdigest() for v in identities.values())):
        raise ValueError(f'Source mismatch: {changed}; STOP')
    names = ('issue401_benchmark.py', 'issue401_timing.py')
    scripts = {name: digest(HERE / name) for name in names}
    starts = HERE / 'issue401_starts_1002.json'
    if digest(starts) != '63b671ea269656843df118230b7d920e91515188235809b6dd0efd667ac997ab':
        raise ValueError('Original start bytes mismatch; STOP')
    sources = {k: sha(v) for k, v in identities.items()}
    order = [('old', True), ('new', True)] + [(mode, False) for mode in ('old', 'new', 'new', 'old') * 5]
    out.mkdir(exist_ok=False)
    save(out / 'freeze.json', dict(source_identity=identities, source_sha=sources, scripts=scripts,
         driver_sha=digest(Path(__file__)), order=order, affinity=sorted(os.sched_getaffinity(0)),
         max_nfev_per_run=100, samples_per_forward=70))
    reference = None
    for i, (mode, warmup) in enumerate(order):
        root = roots[mode]
        if (sha(source_identity(root)) != sources[mode] or
                any(digest(HERE / n) != scripts[n] for n in names) or
                digest(starts) != '63b671ea269656843df118230b7d920e91515188235809b6dd0efd667ac997ab'):
            raise RuntimeError('Source changed; STOP, no retry')
        command = [sys.executable, str(HERE / 'issue401_benchmark.py'),
                   '--mode', 'plain', '--source-sha', sources[mode]]
        prefix = f'{i:02d}-{mode}'
        save(out / (prefix + '.started.json'), dict(sequence=i, warmup=warmup, command=command,
             max_forward=100, samples_per_forward=70))
        env = os.environ.copy(); env['PYTHONPATH'] = str(root / 'src')
        env['ISSUE401_STARTS_PATH'] = str(starts)
        result = subprocess.run(command, cwd=root, env=env, text=True, capture_output=True, check=False)
        save(out / (prefix + '.json'), dict(sequence=i, warmup=warmup, mode=mode,
             returncode=result.returncode, stdout=result.stdout, stderr=result.stderr))
        if result.returncode:
            raise RuntimeError(f'{prefix} failed; STOP, retain unknown consumption')
        report = json.loads(result.stdout)
        if report['source_sha'] != sources[mode] or report['affinity'] != sorted(os.sched_getaffinity(0)):
            raise RuntimeError(f'{prefix}: identity mismatch; STOP')
        if reference is None:
            reference = report['solver']
        elif report['solver'] != reference:
            raise RuntimeError(f'{prefix}: solver mismatch; STOP')
        print(prefix, 'ok', flush=True)


if __name__ == '__main__':
    main()

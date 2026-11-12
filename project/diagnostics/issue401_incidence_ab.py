#!/usr/bin/env python3
"""Plain old/new RF timing; fixed inputs, no post-solver forward or retry."""
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
OUT = HERE / 'issue401_incidence_ab_raw'
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
    if any(os.environ.get(k) != '1' for k in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS')):
        raise ValueError('Single-thread environment required')
    roots = {'old': OLD, 'new': ROOT}
    identities = {k: source_identity(v) for k, v in roots.items()}
    changed = {k for k in identities['old']['files'] if identities['old']['files'][k] != identities['new']['files'].get(k)}
    if (set(identities['old']['files']) != set(identities['new']['files']) or
            changed != {'src/lpf/rf_core/coupled_lc.py'} or
            identities['old']['environment'] != identities['new']['environment'] or
            any(v['dirty_patch_sha256'] != hashlib.sha256(b'').hexdigest() for v in identities.values())):
        raise ValueError(f'Source mismatch: {changed}; STOP')
    names = ('issue401_benchmark.py', 'issue401_timing.py')
    scripts = {name: digest(HERE / name) for name in names}
    if any(digest(OLD / 'project/diagnostics' / name) != scripts[name] for name in names):
        raise ValueError('Benchmark scripts differ; STOP')
    sources = {k: sha(v) for k, v in identities.items()}
    order = [('old', True), ('new', True)] + [(mode, False) for mode in ('old', 'new', 'new', 'old') * 5]
    OUT.mkdir(exist_ok=False)
    save(OUT / 'freeze.json', dict(source_identity=identities, source_sha=sources, scripts=scripts,
         driver_sha=digest(Path(__file__)), order=order, affinity=sorted(os.sched_getaffinity(0)),
         max_nfev_per_run=100, samples_per_forward=70))
    reference = None
    for i, (mode, warmup) in enumerate(order):
        root = roots[mode]
        if sha(source_identity(root)) != sources[mode] or any(digest(root / 'project/diagnostics' / n) != scripts[n] for n in names):
            raise RuntimeError('Source changed; STOP, no retry')
        command = [sys.executable, str(root / 'project/diagnostics/issue401_benchmark.py'),
                   '--mode', 'plain', '--source-sha', sources[mode]]
        prefix = f'{i:02d}-{mode}'
        save(OUT / (prefix + '.started.json'), dict(sequence=i, warmup=warmup, command=command,
             max_forward=100, samples_per_forward=70))
        env = os.environ.copy(); env['PYTHONPATH'] = str(root / 'src')
        result = subprocess.run(command, cwd=root, env=env, text=True, capture_output=True, check=False)
        save(OUT / (prefix + '.json'), dict(sequence=i, warmup=warmup, mode=mode,
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

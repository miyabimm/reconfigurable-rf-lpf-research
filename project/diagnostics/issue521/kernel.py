#!/usr/bin/env python3
"""Fixed-vector-only diagnostic source variants; no Runner or search hooks."""
import hashlib
import inspect
import json
import os
from pathlib import Path
import platform
import statistics
import sys
import textwrap
import time

import numpy as np
import numerics
from numerics import HERE, ROOT, SEEDS, THREADS, setup
import lpf.rf_core.model as rf
from lpf.search.plan import grid_from_record
from lpf.search.storage import vector_sha

ORIGINAL = rf.RFEvaluator.evaluate_with_il_jacobian
SOURCE = textwrap.dedent(inspect.getsource(ORIGINAL))
OLD_C = '''        rhs = -50*dR @ (eye + core[:, None])  # [samples, directions, 2, 2]
        samples, directions = rhs.shape[:2]
        packed = rhs.transpose(0, 2, 1, 3).reshape(samples, 2, directions * 2)
        dcore = np.linalg.solve(A, packed).reshape(samples, 2, directions, 2).transpose(0, 2, 1, 3)'''
NEW_C = '''        Q = eye + core[:, None]
        dcore = -25 * (Q @ dR @ Q)'''
OLD_D = '''        z = np.asarray([self.source_ohms, self.load_ohms])
        scale = (2*np.sqrt(z.real))[None, None, :, None]
        da = (np.sqrt(50.) - z[None, None, :, None]/np.sqrt(50.)) * dfull / scale
        db = (np.sqrt(50.) + z.conj()[None, None, :, None]/np.sqrt(50.)) * dfull / scale
        v = np.sqrt(50.) * (eye + full)
        i = (eye - full) / np.sqrt(50.)
        a = (v + z[None, :, None]*i) / (2*np.sqrt(z.real)[None, :, None])
        rhs = (db - data[0][:, None] @ da).swapaxes(-1, -2)
        packed = rhs.transpose(0, 2, 1, 3).reshape(samples, 2, directions * 2)
        ds = np.linalg.solve(a.swapaxes(-1, -2), packed).reshape(
            samples, 2, directions, 2).transpose(0, 2, 3, 1)'''
NEW_D = '''        z = np.asarray([self.source_ohms, self.load_ohms])
        scale = 2*np.sqrt(z.real)
        beta = (np.sqrt(50.) - z/np.sqrt(50.))/scale
        delta = (np.sqrt(50.) + z.conj()/np.sqrt(50.))/scale
        S = data[0]
        P = np.diag(delta) - S*beta[None, None, :]
        Q = np.diag(delta) - beta[None, :, None]*S
        ds = P[:, None] @ dfull @ Q[:, None]'''
NEW_D2 = '''        z = np.asarray([self.source_ohms, self.load_ohms])
        scale = 2*np.sqrt(z.real)
        beta = (np.sqrt(50.) - z/np.sqrt(50.))/scale
        delta = (np.sqrt(50.) + z.conj()/np.sqrt(50.))/scale
        S = data[0]
        P = np.diag(delta) - S*beta[None, None, :]
        Q = np.diag(delta) - beta[None, :, None]*S
        W = P[:, None] @ dfull
        ds11 = np.sum(W[:, :, 0, :]*Q[:, None, :, 0], axis=-1)
        ds21 = np.sum(W[:, :, 1, :]*Q[:, None, :, 0], axis=-1)
        ds22 = np.sum(W[:, :, 1, :]*Q[:, None, :, 1], axis=-1)'''


def replace(src, old, new):
    old = textwrap.indent(textwrap.dedent(old), ' '*8)
    new = textwrap.indent(textwrap.dedent(new), ' '*8)
    assert src.count(old) == 1
    return src.replace(old, new)


def variant(c, d):
    src = SOURCE
    if c:
        # The old D still needs these shape variables after C removes the packed solve.
        new = NEW_C + ('\n        samples, directions = dR.shape[:2]' if not d else '')
        src = replace(src, OLD_C, new)
    if d:
        src = replace(src, OLD_D, NEW_D if d == 'D1' else NEW_D2)
        if d == 'D2':
            assert src.count('ds[:, :, 1, 0] / transmission[:, None]') == 1
            src = src.replace('ds[:, :, 1, 0] / transmission[:, None]', 'ds21 / transmission[:, None]')
    ns = {}
    exec(compile(src, '<issue521-fixed-vector-diagnostic>', 'exec'), rf.__dict__, ns)
    return ns['evaluate_with_il_jacobian'], hashlib.sha256(src.encode()).hexdigest()


def main(out):
    assert all(os.environ.get(k) == '1' for k in THREADS)
    methods = {'base': (ORIGINAL, hashlib.sha256(SOURCE.encode()).hexdigest())}
    for name, c, d in (('C', True, None), ('D1', False, 'D1'), ('D2', False, 'D2'),
                       ('CD1', True, 'D1'), ('CD2', True, 'D2')):
        methods[name] = variant(c, d)
    result = {'baseline': '7957fd60e685b6afb2f62fcdc1551ab8bdbfc43d',
              'model_sha256': hashlib.sha256((ROOT/'src/lpf/rf_core/model.py').read_bytes()).hexdigest(),
              'kernel_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'source_sha256': {k:v[1] for k, v in methods.items()}, 'python': platform.python_version(),
              'numpy': np.__version__, 'cpu_affinity': sorted(os.sched_getaffinity(0)),
              'threads': {k: os.environ[k] for k in THREADS}, 'pairs': 20, 'rows': []}
    fixed = json.loads((HERE.parent/'issue519/vectors.json').read_text())
    for seed in SEEDS:
        _, starts, _, plan, _, model = setup(seed)
        ev = model.evaluator(grid_from_record(plan.data['grids']['baseline/search']))
        vectors = [('initial', starts[str(seed)]['baseline']['vector'])]
        vectors += [(k, v['vector']) for k, v in fixed.items() if k.startswith(str(seed)+'-')]
        for name, x in vectors:
            reference, rjac = ORIGINAL(ev, x)
            row = {'seed': seed, 'vector': name, 'vector_sha256': vector_sha(x), 'variants': {}}
            for mode in ('C', 'D1', 'D2', 'CD1', 'CD2'):
                fn = methods[mode][0]
                response, jac = fn(ev, x)  # warmup and equivalence
                for field in ('s', 'il_db', 'apl_db', 'in_rl_db', 'out_rl_db'):
                    np.testing.assert_allclose(getattr(response, field), getattr(reference, field), rtol=1e-12, atol=1e-12)
                np.testing.assert_allclose(jac, rjac, rtol=1e-4, atol=1e-5)
                ORIGINAL(ev, x)
                times = {'base': [], mode: []}
                for pair in range(20):
                    order = ('base', mode) if pair % 2 == 0 else (mode, 'base')
                    for arm in order:
                        start, cpu = time.perf_counter_ns(), time.process_time_ns()
                        methods[arm][0](ev, x)
                        times[arm].append([time.perf_counter_ns()-start, time.process_time_ns()-cpu])
                diffs = [(b[0]-a[0])/1e6 for a, b in zip(times['base'], times[mode])]
                row['variants'][mode] = {'base_wall_cpu_ns': times['base'], 'candidate_wall_cpu_ns': times[mode],
                    'paired_wall_ms_median': statistics.median(diffs), 'paired_wall_ms_range': [min(diffs), max(diffs)],
                    'jac_max_abs': float(np.max(np.abs(jac-rjac)))}
            result['rows'].append(row)
            print(seed, name, {k: round(v['paired_wall_ms_median'], 3) for k, v in row['variants'].items()}, flush=True)
    out.write_text(json.dumps(result, indent=2, allow_nan=False)+'\n')


if __name__ == '__main__':
    out = Path(sys.argv[1]); assert not out.exists(); main(out)

#!/usr/bin/env python3
"""Issue 419 diagnostic only; no production fast path. Each child is a fresh process."""
import argparse
import hashlib
import inspect
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / p) for p in ('src', 'scripts', 'tests')]
import numpy as np
from test_issue410_c_assembly import fixture
from lpf.rf_core import model as rf
from lpf.search.storage import vector_sha
from lpf.search.performance import compile_requirements, prepare_requirements, evaluate_requirements
from lpf.constraint_versions import rf_input_file
from lpf.timing import TimerCollector

ORIGINAL = rf.power_response
REPLAY = ROOT/'project/diagnostics/issue410_equivalence.json'
CONSTRUCT = '''    eye = np.eye(2)
    v = np.sqrt(50.) * (eye + s)
    i = (eye - s) / np.sqrt(50.)
    a = (v + z[None, :, None] * i) / (2*np.sqrt(z.real)[None, :, None])
    b = (v - z.conj()[None, :, None] * i) / (2*np.sqrt(z.real)[None, :, None])
'''
CONSTRUCT_A = '''    eye = np.eye(2)
    c = np.sqrt(50.)
    zi = z[None, :, None] / c
    den = 2*np.sqrt(z.real)[None, :, None]
    a = ((c + zi) * eye + (c - zi) * s) / den
    zc = z.conj()[None, :, None] / c
    b = ((c - zc) * eye + (c + zc) * s) / den
'''
SOLVE = '''        result = np.linalg.solve(a.transpose(0, 2, 1), b.transpose(0, 2, 1)).transpose(0, 2, 1)
'''
SOLVE_B = '''        det = a[:, 0, 0]*a[:, 1, 1] - a[:, 0, 1]*a[:, 1, 0]
        if np.any(det == 0):
            raise np.linalg.LinAlgError('Singular matrix')
        result = np.empty_like(b)
        result[:, 0, 0] = (b[:, 0, 0]*a[:, 1, 1] - b[:, 0, 1]*a[:, 1, 0])/det
        result[:, 0, 1] = (b[:, 0, 1]*a[:, 0, 0] - b[:, 0, 0]*a[:, 0, 1])/det
        result[:, 1, 0] = (b[:, 1, 0]*a[:, 1, 1] - b[:, 1, 1]*a[:, 1, 0])/det
        result[:, 1, 1] = (b[:, 1, 1]*a[:, 0, 0] - b[:, 1, 0]*a[:, 0, 1])/det
'''


def make_candidate(variant, timer=None):
    source = inspect.getsource(ORIGINAL)
    assert source.count(CONSTRUCT) == source.count(SOLVE) == 1
    if variant == 'A':
        source = source.replace(CONSTRUCT, CONSTRUCT_A)
    if variant == 'B':
        source = source.replace(SOLVE, SOLVE_B)
    if timer is not None:
        # Three coarse non-overlapping regions. Initial argument validation is outside.
        source = source.replace('    eye = np.eye(2)\n', "    _t0 = _clock()\n    eye = np.eye(2)\n", 1)
        source = source.replace('    try:\n', "    _record('construct', _t0)\n    _t0 = _clock()\n    try:\n", 1)
        source = source.replace('    if not np.all(np.isfinite(result)):', "    _record('solve', _t0)\n    _t0 = _clock()\n    if not np.all(np.isfinite(result)):", 1)
        source = source.replace('    return (result, *metrics)', "    _record('metrics', _t0)\n    return (result, *metrics)")
    namespace = dict(rf.__dict__, _clock=time.perf_counter_ns)
    if timer is not None:
        def record(key, start):
            timer.setdefault(key, []).append(time.perf_counter_ns()-start)
        namespace['_record'] = record
    exec(compile(source, f'<issue419-{variant}>', 'exec'), namespace)
    return namespace['power_response']


def setup():
    start, cpu = time.perf_counter(), time.process_time()
    p, model, grid, _ = fixture()
    raw = json.loads(REPLAY.read_text())
    vectors = raw['vectors']
    assert len(vectors) == 100 and [vector_sha(x) for x in vectors] == raw['vector_sha256']
    assert model.policy_id == 'RF-T008' and model.policy_fingerprint == 'e682165c72d3a8b9f1384a2529f71bacfebfc9d17164d4af5af879e4a138b532'
    assert len(grid.frequency_hz) == 70 and len(set(grid.segment)) == 28 and set(grid.setting) == set(range(6))
    evaluator = model.evaluator(grid)
    req = prepare_requirements(compile_requirements(p, rf_input_file(ROOT, p['bands_file']), 'full_lpf'), grid)
    saved = rf.power_response
    waves = []
    def capture(s, zs, zl):
        waves.append((s.copy(), zs, zl))
        return saved(s, zs, zl)
    rf.power_response = capture
    try:
        for x in vectors:
            evaluator.evaluate(x)
    finally:
        rf.power_response = saved
    assert len(waves) == 100
    return model, grid, vectors, evaluator, req, waves, dict(setup_wall_s=time.perf_counter()-start,
        setup_cpu_s=time.process_time()-cpu, head=subprocess.check_output(['git','rev-parse','HEAD'], cwd=ROOT, text=True).strip(),
        replay_sha256=hashlib.sha256(REPLAY.read_bytes()).hexdigest(),
        waves_sha256=hashlib.sha256(b''.join(s.tobytes() for s, _, _ in waves)).hexdigest(),
        python=platform.python_version(), numpy=np.__version__, affinity=sorted(os.sched_getaffinity(0)),
        threads={k:os.environ.get(k) for k in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS')})


def child(mode, variant):
    model, grid, vectors, evaluator, req, waves, report = setup()
    func = rf.power_response if variant == 'old' else make_candidate(variant)
    rf.power_response = func
    if mode in ('forward', 'local', 'detail'):
        def loop():
            if mode == 'forward':
                for x in vectors: evaluator.evaluate(x)
            else:
                for args in waves: func(*args)
        loop()  # identical warmup, outside timing
        timers = {}
        if mode == 'detail':
            func = make_candidate(variant, timers)
        start, cpu = time.perf_counter(), time.process_time()
        loop()
        report.update(wall_s=time.perf_counter()-start, cpu_s=time.process_time()-cpu,
                      timers_ns={k:sum(v) for k,v in timers.items()})
    elif mode == 'equivalence':
        from lpf.rf_core.independent import validate_response
        errors, relative, bits = {}, {}, {}
        independent = []
        for i, x in enumerate(vectors):
            rf.power_response = ORIGINAL
            a = evaluator.evaluate(x)
            rf.power_response = func
            b = evaluator.evaluate(x)
            ar, br = evaluate_requirements(a, req), evaluate_requirements(b, req)
            assert len(ar['mandatory_g']) == len(br['mandatory_g']) == 42
            for k in ('s','il_db','apl_db','in_rl_db','out_rl_db','worst_il_db','mandatory_g'):
                aa = np.asarray(ar[k] if k in ar else getattr(a,k))
                bb = np.asarray(br[k] if k in br else getattr(b,k))
                np.testing.assert_allclose(aa, bb, atol=1e-9, rtol=1e-11)
                delta = np.abs(aa-bb)
                errors[k] = max(errors.get(k,0), float(np.max(delta)))
                relative[k] = max(relative.get(k,0), float(np.max(delta/np.maximum(np.abs(aa),1e-300))))
                bits[k] = bits.get(k,True) and aa.tobytes() == bb.tobytes()
            if i in (0,49,99):
                independent.append(dict(index=i, **validate_response(model,x,b)))
        report.update(max_abs=errors, max_relative=relative, bit_equal=bits, independent=independent)
    print(json.dumps(report, sort_keys=True, allow_nan=False))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--child', choices=('old','A','B'))
    ap.add_argument('--mode', choices=('local','forward','detail','equivalence'))
    ap.add_argument('--pairs', type=int, default=8)
    ap.add_argument('--output', type=Path)
    args = ap.parse_args()
    if args.child:
        child(args.mode, args.child)
        return
    if not args.output or args.output.exists() or args.pairs < 1:
        ap.error('provide a new output and positive pairs')
    env = dict(os.environ, OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1', MKL_NUM_THREADS='1')
    cpu = min(os.sched_getaffinity(0))
    runs = []
    for mode in ('local','forward','detail','equivalence'):
        for candidate in ('A','B'):
            n = args.pairs if mode in ('local','forward') else (3 if mode == 'detail' else 1)
            for pair in range(n):
                order = ('old',candidate) if pair % 2 == 0 else (candidate,'old')
                if mode == 'equivalence': order = (candidate,)
                for variant in order:
                    cmd = ['taskset','-c',str(cpu),sys.executable,str(Path(__file__).resolve()),'--child',variant,'--mode',mode]
                    proc = subprocess.run(cmd, cwd=ROOT, env=env, capture_output=True, text=True)
                    row = dict(mode=mode, candidate=candidate, pair=pair, variant=variant, command=cmd,
                               returncode=proc.returncode, stderr=proc.stderr)
                    if proc.returncode == 0: row['report'] = json.loads(proc.stdout)
                    else: row['stdout'] = proc.stdout
                    runs.append(row)
                    args.output.write_text(json.dumps(dict(runs=runs), indent=2, sort_keys=True, allow_nan=False)+'\n')
                    if proc.returncode: raise RuntimeError(f'child failed; saved {args.output}')
    print(f'{len(runs)} runs saved to {args.output}')

if __name__ == '__main__': main()

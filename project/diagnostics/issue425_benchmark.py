#!/usr/bin/env python3
"""Issue #425 fixed-input development diagnostic; not an EXP or search."""
import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from time import perf_counter, process_time

ROOT = Path(__file__).resolve().parents[2]
BASE = 'c927cb94fba14f97601026d9523b3eed3101e423'
sys.path[:0] = [str(ROOT / p) for p in ('src', 'scripts', 'tests', 'project/diagnostics')]
import numpy as np
from issue413_benchmark import inputs
from lpf.rf_core.independent import validate_response
from lpf.search.performance import evaluate_requirements
from lpf.search.storage import plain


def install_old():
    # Compile the exact methods from the fixed main commit in their original
    # module globals. No wrapper or production flag in either timed path.
    import lpf.rf_core.model as model
    import lpf.rf_core.coupled_lc as lc
    for module, path, cls, method in (
        (lc, 'src/lpf/rf_core/coupled_lc.py', 'ParameterVectorSchema', 'decode'),
        (model, 'src/lpf/rf_core/model.py', 'RFEvaluator', 'evaluate'),
    ):
        source = subprocess.check_output(['git', 'show', f'{BASE}:{path}'], cwd=ROOT, text=True)
        tree = ast.parse(source)
        klass = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == cls)
        node = next(n for n in klass.body if isinstance(n, ast.FunctionDef) and n.name == method)
        namespace = {}
        exec(compile(ast.Module(body=[node], type_ignores=[]), f'{BASE}:{path}', 'exec'), module.__dict__, namespace)
        setattr(getattr(module, cls), method, namespace[method])


def child(mode, variant, capture):
    model, grid, vectors, evaluator, req, report = inputs('baseline')
    assert model.policy_id == 'RF-T008' and model.policy_fingerprint == 'e682165c72d3a8b9f1384a2529f71bacfebfc9d17164d4af5af879e4a138b532'
    assert len(grid.setting) == 70 and len(set(grid.setting)) == 6 and len(set(grid.segment)) == 28
    if variant == 'old':
        install_old()
    if mode in ('decode', 'forward'):
        def once():
            for x in vectors:
                if mode == 'decode':
                    model.decode(x)
                else:
                    evaluator.evaluate(x)
        # Separate per-process warmup; time only whole batches.
        once()
        repeats = 20 if mode == 'decode' else 1
        wall, cpu = perf_counter(), process_time()
        for _ in range(repeats):
            once()
        report.update(wall_s=perf_counter()-wall, cpu_s=process_time()-cpu,
                      repeats=repeats, warmup_calls=100, measured_calls=100*repeats)
    else:
        results, independent = {}, []
        for i, x in enumerate(vectors):
            values = model.decode(x)
            response = evaluator.evaluate(x)
            metrics = evaluate_requirements(response, req)
            assert len(metrics['mandatory_g']) == 42
            for k in ('s', 'il_db', 'apl_db', 'in_rl_db', 'out_rl_db', 'worst_il_db', 'mandatory_g'):
                results.setdefault(k, []).append(metrics[k] if k in metrics else getattr(response, k))
            results.setdefault('encoded', []).append(model.encode(values))
            results.setdefault('rows', []).append(values.capacitors_pf_by_setting)
            if i in (0, 49, 99):
                independent.append(dict(index=i, **validate_response(model, x, response)))
        np.savez_compressed(capture, **{k: np.asarray(v) for k, v in results.items()})
        report['independent'] = independent
        report['forward_count'] = 100
    print(json.dumps(plain(report), allow_nan=False))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path)
    parser.add_argument('--pairs', type=int, default=10)
    parser.add_argument('--child', choices=('decode', 'forward', 'capture'))
    parser.add_argument('--variant', choices=('old', 'new'))
    parser.add_argument('--capture')
    args = parser.parse_args()
    if args.child:
        child(args.child, args.variant, args.capture)
        return
    if not args.output or args.output.exists() or args.pairs < 1:
        parser.error('output must be new and pairs positive')
    env = dict(os.environ, OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1', MKL_NUM_THREADS='1')
    report = dict(base=BASE, driver_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), runs=[], equivalence={})
    def save():
        args.output.write_text(json.dumps(plain(report), indent=2, allow_nan=False)+'\n')
    def run(mode, variant, pair, capture=None):
        cmd = ['taskset', '-c', '2', sys.executable, str(Path(__file__).resolve()), '--child', mode, '--variant', variant]
        if capture:
            cmd += ['--capture', str(capture)]
        result = subprocess.run(cmd, cwd=ROOT, env=env, text=True, capture_output=True)
        record = dict(mode=mode, variant=variant, pair=pair, command=cmd, returncode=result.returncode, stderr=result.stderr)
        if result.returncode == 0:
            record['result'] = json.loads(result.stdout)
        else:
            record['stdout'] = result.stdout
        report['runs'].append(record)
        save()
        if result.returncode:
            raise RuntimeError(f'child failed: {cmd}; see {args.output}')
    with tempfile.TemporaryDirectory(prefix='issue425-capture-') as tmp:
        for variant in ('old', 'new'):
            run('capture', variant, 0, Path(tmp)/f'{variant}.npz')
        with np.load(Path(tmp)/'old.npz') as old, np.load(Path(tmp)/'new.npz') as new:
            for k in old.files:
                np.testing.assert_allclose(old[k], new[k], atol=1e-9, rtol=1e-11)
                report['equivalence'][k] = dict(shape=old[k].shape, max_abs=float(np.max(np.abs(old[k]-new[k]))), bit_equal=old[k].tobytes()==new[k].tobytes())
        save()
    for mode in ('decode', 'forward'):
        for i in range(-1, args.pairs):
            for variant in (('old', 'new') if i % 2 else ('new', 'old')):
                run(mode, variant, i)
    save()


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""Compare actual main and production trees; output is a new JSON file.

Run with the same Python environment for both trees. Each timed run is a fresh
process pinned to CPU 2 with one BLAS thread. No diagnostic RF path is used.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

SCRIPT = Path(__file__).resolve()


def capture(root, dest):
    sys.path[:0] = [str(root / p) for p in ('src', 'scripts', 'tests')]
    import numpy as np
    from test_issue410_c_assembly import fixture
    from lpf.rf_core.independent import validate_response
    from lpf.search.performance import compile_requirements, prepare_requirements, evaluate_requirements
    from lpf.constraint_versions import rf_input_file
    from lpf.search.storage import vector_sha, plain
    p, model, grid, _ = fixture()
    raw = json.loads((root/'project/diagnostics/issue410_equivalence.json').read_text())
    assert [vector_sha(x) for x in raw['vectors']] == raw['vector_sha256'] and len(raw['vectors']) == 100
    req = prepare_requirements(compile_requirements(p, rf_input_file(root, p['bands_file']), 'full_lpf'), grid)
    evaluator = model.evaluator(grid)
    results, independent = {}, []
    for i, x in enumerate(raw['vectors']):
        response = evaluator.evaluate(x)
        metrics = evaluate_requirements(response, req)
        assert len(metrics['mandatory_g']) == 42
        for key in ('s', 'il_db', 'apl_db', 'in_rl_db', 'out_rl_db', 'worst_il_db', 'mandatory_g'):
            results.setdefault(key, []).append(metrics[key] if key in metrics else getattr(response, key))
        if i in (0, 49, 99):
            independent.append(dict(vector_index=i, **validate_response(model, x, response)))
    np.savez_compressed(dest, **{k: np.asarray(v) for k, v in results.items()})
    print(json.dumps(plain(independent), allow_nan=False))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--old', type=Path, required=True)
    parser.add_argument('--new', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--pairs', type=int, default=10)
    parser.add_argument('--capture', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.capture:
        capture(args.new.resolve(), args.output)
        return
    if args.output.exists() or args.pairs < 1:
        parser.error('output must not exist and pairs must be positive')
    roots = {'old': args.old.resolve(), 'new': args.new.resolve()}
    env = dict(os.environ, OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1', MKL_NUM_THREADS='1')
    base = ['taskset', '-c', '2', sys.executable]
    report = {'runs': [], 'commands': {}, 'pairs': args.pairs}
    def run(cmd, root):
        result = subprocess.run(base + cmd, cwd=root, env=env, text=True, capture_output=True)
        if result.returncode:
            raise RuntimeError(f'{cmd}: {result.stderr}\n{result.stdout}')
        return json.loads(result.stdout)
    def save():
        args.output.write_text(json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + '\n')
    with tempfile.TemporaryDirectory(prefix='issue415-compare-') as tmp:
        files = {}
        for label, root in roots.items():
            dest = Path(tmp)/f'{label}.npz'
            report[label + '_independent'] = run([str(SCRIPT), '--old', str(root), '--new', str(root),
                                                  '--output', str(dest), '--capture'], root)
            files[label] = dest
        import numpy as np
        report['equivalence'] = {}
        with np.load(files['old']) as old, np.load(files['new']) as new:
            for key in old.files:
                np.testing.assert_allclose(old[key], new[key], atol=1e-9, rtol=1e-11)
                report['equivalence'][key] = dict(shape=old[key].shape,
                    max_abs=float(np.max(np.abs(old[key]-new[key]))),
                    bit_equal=old[key].tobytes() == new[key].tobytes())
        save()
    for suite in ('forward', 'solver'):
        for i in range(-1, args.pairs):
            for label in (('old', 'new') if i % 2 else ('new', 'old')):
                root = roots[label]
                if suite == 'forward':
                    cmd = [str(root/'project/diagnostics/issue413_benchmark.py'), '--suite', 'forward', '--child', 'baseline']
                    keys = ('head', 'source_sha256', 'policy_id', 'policy_fingerprint', 'environment', 'wall_s', 'cpu_s', 'setup_s', 'setup_cpu_s', 'measured_forward', 'samples_per_forward', 'replay_sha256')
                else:
                    cmd = [str(root/'project/diagnostics/issue413_probe.py'), '--variant', 'baseline', '--config', 'project/diagnostics/issue377/baseline.yaml', '--starts', 'project/diagnostics/issue401_starts_1002.json', '--arm', 'hybrid', '--seed', '1002', '--mode', 'plain']
                    keys = ('head', 'source_sha256', 'policy_id', 'policy_fingerprint', 'environment', 'solver_s', 'solver_cpu_s', 'setup_s', 'setup_cpu_s', 'solver', 'grid_sha256', 'plan_sha256', 'initial_vector_sha256', 'starts_file_sha256')
                result = run(cmd, root)
                report['runs'].append(dict(suite=suite, pair=i, variant=label, **{k: result[k] for k in keys}))
                save()
    report['script_sha256'] = hashlib.sha256(SCRIPT.read_bytes()).hexdigest()
    save()


if __name__ == '__main__':
    main()

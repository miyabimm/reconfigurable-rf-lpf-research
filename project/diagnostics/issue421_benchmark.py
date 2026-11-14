#!/usr/bin/env python3
"""Issue 421 diagnostic only; no production flag. Run --output NEW.json [--pairs 10]."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from time import perf_counter, process_time

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / p) for p in ('src', 'scripts', 'tests', 'project/diagnostics')]
import numpy as np
from issue413_benchmark import inputs
from lpf.rf_core.coupled_lc import CoupledLCTopology
from lpf.rf_core.numerical_diagnostics import CircuitNumericalError
from lpf.rf_core.independent import validate_response
from lpf.search.performance import evaluate_requirements
from lpf.search.storage import plain

def old_port(self, values, omega_rad_s, setting_indices):
    """Exact #421 base implementation, retained for a paired plain baseline."""
    Y = self.node_admittance(values, omega_rad_s, setting_indices)
    ports = (self.inductor_tree.source_node, self.inductor_tree.load_node)
    middle = tuple(i for i in range(self.inductor_tree.node_count) if i not in ports)
    R = Y[:, ports, :][:, :, ports]
    if middle:
        U = Y[:, ports, :][:, :, middle]
        V = Y[:, middle, :][:, :, ports]
        E = Y[:, middle, :][:, :, middle]
        try:
            R = R - U @ np.linalg.solve(E, V)
        except np.linalg.LinAlgError as exc:
            raise CircuitNumericalError('schur_solve_failed', 'Internal-node Schur solve failed') from exc
    if not np.all(np.isfinite(R)):
        raise CircuitNumericalError('schur_nonfinite', 'Non-finite port admittance',
            sample_index=int(np.flatnonzero(~np.all(np.isfinite(R), axis=(1, 2)))[0]))
    return R


def blocks(y, ports, middle, variant):
    if variant == 'old':
        return (y[:, ports, :][:, :, ports], y[:, ports, :][:, :, middle],
                y[:, middle, :][:, :, ports], y[:, middle, :][:, :, middle])
    if variant == 'A':
        p, m = np.asarray(ports), np.asarray(middle)
        return y[:, p[:, None], p], y[:, p[:, None], m], y[:, m[:, None], p], y[:, m[:, None], m]
    order = np.asarray(ports + middle)
    z = y[:, order[:, None], order]
    return z[:, :2, :2], z[:, :2, 2:], z[:, 2:, :2], z[:, 2:, 2:]


def port(variant):
    def candidate(self, values, omega_rad_s, setting_indices):
        y = self.node_admittance(values, omega_rad_s, setting_indices)
        ports = (self.inductor_tree.source_node, self.inductor_tree.load_node)
        middle = tuple(i for i in range(self.inductor_tree.node_count) if i not in ports)
        if not middle:
            # Baseline's R extraction, including the empty-middle branch.
            r = y[:, ports, :][:, :, ports]
        else:
            r, u, v, e = blocks(y, ports, middle, variant)
            try:
                r = r - u @ np.linalg.solve(e, v)
            except np.linalg.LinAlgError as exc:
                raise CircuitNumericalError('schur_solve_failed', 'Internal-node Schur solve failed') from exc
        if not np.all(np.isfinite(r)):
            raise CircuitNumericalError('schur_nonfinite', 'Non-finite port admittance',
                sample_index=int(np.flatnonzero(~np.all(np.isfinite(r), axis=(1, 2)))[0]))
        return r
    return candidate


def child(mode, variant):
    model, grid, vectors, evaluator, req, report = inputs('baseline')
    if variant == 'old':
        CoupledLCTopology.port_admittance = old_port
    elif variant != 'P':
        CoupledLCTopology.port_admittance = port(variant)
    if mode == 'forward':
        for x in vectors:
            evaluator.evaluate(x)
        wall, cpu = perf_counter(), process_time()
        for x in vectors:
            evaluator.evaluate(x)
        report.update(wall_s=perf_counter()-wall, cpu_s=process_time()-cpu,
                      warmup_forward=100, measured_forward=100, samples_per_forward=len(grid.setting))
    elif mode == 'detail':
        # Real Y, calculated outside timers. Each region includes timer overhead;
        # no node, indexing construction, exception dispatch, or whole-forward timing.
        ys = [model.topology.node_admittance(model.decode(x), 2*np.pi*grid.frequency_hz, grid.setting) for x in vectors]
        p = (model.topology.inductor_tree.source_node, model.topology.inductor_tree.load_node)
        m = tuple(i for i in range(model.topology.inductor_tree.node_count) if i not in p)
        sums = np.zeros(4)
        for y in ys:
            t = perf_counter(); r, u, v, e = blocks(y, p, m, variant); t1 = perf_counter()
            solution = np.linalg.solve(e, v); t2 = perf_counter()
            r = r - u @ solution; t3 = perf_counter()
            assert np.all(np.isfinite(r)); t4 = perf_counter()
            sums += np.diff([t, t1, t2, t3, t4])
        empty = []
        for _ in range(10000):
            t = perf_counter(); t1 = perf_counter()
            empty.append(t1-t)
        report['empty_timer_median_s'] = float(np.median(empty))
        report['detail_s'] = dict(zip(('extract', 'solve', 'multiply_subtract', 'finite'), sums))
        report['shape'] = [list(a.shape) for a in (r, u, v, e)]
    else:
        results, independent = {}, []
        for i, x in enumerate(vectors):
            response = evaluator.evaluate(x)
            metrics = evaluate_requirements(response, req)
            for k in ('s', 'il_db', 'apl_db', 'in_rl_db', 'out_rl_db', 'worst_il_db', 'mandatory_g'):
                results.setdefault(k, []).append(metrics[k] if k in metrics else getattr(response, k))
            if i in (0, 49, 99):
                independent.append(dict(index=i, **validate_response(model, x, response)))
        np.savez_compressed(os.environ['ISSUE421_CAPTURE'], **{k: np.asarray(v) for k, v in results.items()})
        report['independent'] = independent
    print(json.dumps(plain(report), allow_nan=False))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path)
    parser.add_argument('--pairs', type=int, default=10)
    parser.add_argument('--child', choices=('forward', 'detail', 'capture'))
    parser.add_argument('--variant', choices=('old', 'A', 'B', 'P'))
    parser.add_argument('--production', action='store_true', help='compare old against actual production P')
    args = parser.parse_args()
    if args.child:
        child(args.child, args.variant)
        return
    if not args.output or args.output.exists() or args.pairs < 1:
        parser.error('output must not exist; pairs must be positive')
    import tempfile
    env = dict(os.environ, OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1', MKL_NUM_THREADS='1')
    report = {'runs': [], 'equivalence': {}, 'script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    def run(mode, variant, pair, capture=None):
        e = dict(env)
        if capture:
            e['ISSUE421_CAPTURE'] = str(capture)
        cmd = ['taskset', '-c', '2', sys.executable, str(Path(__file__).resolve()), '--child', mode, '--variant', variant]
        p = subprocess.run(cmd, cwd=ROOT, env=e, text=True, capture_output=True)
        record = dict(mode=mode, variant=variant, pair=pair, command=cmd, returncode=p.returncode, stderr=p.stderr)
        if p.returncode == 0:
            record['result'] = json.loads(p.stdout)
        else:
            record['stdout'] = p.stdout
        report['runs'].append(record)
        args.output.write_text(json.dumps(plain(report), indent=2, allow_nan=False)+'\n')
        if p.returncode:
            raise RuntimeError(f'child failed: {cmd}; see {args.output}')
    variants = ('P',) if args.production else ('A', 'B', 'P')
    with tempfile.TemporaryDirectory(prefix='issue421-capture-') as tmp:
        for v in ('old', *variants):
            run('capture', v, 0, Path(tmp)/f'{v}.npz')
        with np.load(Path(tmp)/'old.npz') as old:
            for v in variants:
                with np.load(Path(tmp)/f'{v}.npz') as new:
                    report['equivalence'][v] = {}
                    for k in old.files:
                        np.testing.assert_allclose(old[k], new[k], atol=1e-9, rtol=1e-11)
                        report['equivalence'][v][k] = dict(shape=old[k].shape, max_abs=float(np.max(np.abs(old[k]-new[k]))), bit_equal=old[k].tobytes()==new[k].tobytes())
    for v in ('old', *variants):
        for i in range(3):
            run('detail', 'B' if v == 'P' else v, i)
    for v in variants:
        for i in range(-1, args.pairs):
            for arm in (('old', v) if i % 2 else (v, 'old')):
                run('forward', arm, i)
    args.output.write_text(json.dumps(plain(report), indent=2, allow_nan=False)+'\n')

if __name__ == '__main__':
    main()

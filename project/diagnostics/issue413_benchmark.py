#!/usr/bin/env python3
"""Bounded #413 diagnostics: fixed replay, separate instrumented breakdown, plain solve.

Run --suite forward|detail|equivalence|solver --output <new JSON path>.
Solver accepts --candidates (at most two); forward always compares all three.
Every timed child is a fresh process; warmup records are retained, not aggregated.
"""
import argparse
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from time import perf_counter, process_time

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT/'src'), str(ROOT/'scripts'), str(ROOT/'tests'), str(Path(__file__).parent)]
import numpy as np
import issue413_probe as probe
from test_issue410_c_assembly import fixture
from lpf.search.storage import plain, vector_sha
from lpf.search.performance import compile_requirements, prepare_requirements, evaluate_requirements
from lpf.constraint_versions import rf_input_file

REPLAY = ROOT/'project/diagnostics/issue410_equivalence.json'


def inputs(variant):
    from benchmark_minimal_worker import freeze_source
    start, cpu = perf_counter(), process_time()
    source, source_sha, bench_sha = freeze_source(None, None)
    p, model, g, x = fixture()
    t = perf_counter()
    model = probe.probe_model(model, variant)
    stamp_setup = perf_counter()-t
    raw = json.loads(REPLAY.read_text())
    vectors = raw['vectors']
    assert len(vectors) == 100 and [vector_sha(v) for v in vectors] == raw['vector_sha256']
    evaluator = model.evaluator(g)
    req = prepare_requirements(compile_requirements(p, rf_input_file(ROOT, p['bands_file']), 'full_lpf'), g)
    ready, cpu_ready = perf_counter(), process_time()
    report = dict(variant=variant, setup_s=ready-start, setup_cpu_s=cpu_ready-cpu,
        probe_setup_s=stamp_setup, source_identity=source, source_sha256=source_sha,
        benchmark_script_sha256=bench_sha, head=subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(),
        git_status=subprocess.check_output(['git', 'status', '--short'], text=True),
        policy_id=model.policy_id, policy_fingerprint=model.policy_fingerprint,
        replay_sha256=hashlib.sha256(REPLAY.read_bytes()).hexdigest(), vector_sha256=raw['vector_sha256'],
        grid=dict(setting=g.setting, frequency_hz=g.frequency_hz, segment=g.segment),
        environment=dict(python=sys.version, numpy=np.__version__, platform=__import__('platform').platform(),
            affinity=sorted(os.sched_getaffinity(0)), threads={k:os.environ.get(k) for k in
                ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS')}),
        scripts={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in
            (Path(__file__), Path(probe.__file__))})
    return model, g, vectors, evaluator, req, report


def child(mode, variant):
    model, g, vectors, evaluator, req, report = inputs(variant)
    if mode == 'forward':
        # Real complete evaluator, fixed order. No per-forward timers/wrappers,
        # requirements, response digests or trajectory capture in timed region.
        for x in vectors:
            evaluator.evaluate(x)
        start, cpu = perf_counter(), process_time()
        for x in vectors:
            evaluator.evaluate(x)
        wall, cpu_elapsed = perf_counter()-start, process_time()-cpu
        report.update(wall_s=wall, cpu_s=cpu_elapsed, warmup_forward=100,
            measured_forward=100, samples_per_forward=len(g.setting), timers=False)
    elif mode == 'equivalence':
        from lpf.rf_core.independent import validate_response
        base = probe.probe_model(model, 'baseline')  # inputs here uses baseline
        reference = base.evaluator(g)
        report['variants'] = {}
        for v in probe.VARIANTS:
            m = probe.probe_model(base, v)
            ev = m.evaluator(g)
            errors = {k:0. for k in ('s', 'il_db', 'apl_db', 'in_rl_db', 'out_rl_db', 'mandatory_g', 'worst_il_db')}
            bit_equal = {k:True for k in errors}
            independent = []
            for i, x in enumerate(vectors):
                a, b = reference.evaluate(x), ev.evaluate(x)
                ar, br = evaluate_requirements(a, req), evaluate_requirements(b, req)
                assert len(ar['mandatory_g']) == 42
                for k in errors:
                    aa, bb = (ar[k], br[k]) if k in ar else (getattr(a, k), getattr(b, k))
                    aa, bb = np.asarray(aa), np.asarray(bb)
                    np.testing.assert_allclose(aa, bb, atol=1e-9, rtol=1e-11)
                    errors[k] = max(errors[k], float(np.max(abs(aa-bb))))
                    bit_equal[k] &= aa.tobytes() == bb.tobytes()
                if i in (0, 49, 99):
                    independent.append(dict(vector_index=i, **validate_response(m, x, b)))
            report['variants'][v] = dict(max_abs_error=errors, bit_equal=bit_equal, independent=independent)
        report.update(forward_count=600, independent_samples=3*3*len(g.setting))
    else:
        # Instrumented arithmetic only: not a plain RF-forward speed claim.
        from lpf.topology_management.circuit_layout import incidence_matrix
        from lpf.timing import TimerCollector
        timer = TimerCollector()
        n = model.topology.inductor_tree.node_count
        omega, setting = 2*np.pi*g.frequency_hz, g.setting
        for x in vectors:
            values = model.decode(x)
            K, _ = model.topology.matrices(values)
            Y = np.broadcast_to(K, (len(setting), n, n)).copy()/(omega[:, None, None]*1e-9)
            with timer.measure('C_conversion'):
                C = np.asarray(values.capacitors_pf_by_setting, dtype=float)
            if variant == 'baseline':
                with timer.measure('C_gather'):
                    C = C[setting]
                with timer.measure('branch_Q_and_incidence'):
                    yc = omega[:, None]*1e-12*C/(1/np.asarray(model.topology.capacitor_q)[None, :]-1j)
                    b = incidence_matrix(model.topology.capacitor_edges, n)
                with timer.measure('contraction'):
                    D = np.einsum('fb,ib,jb->fij', yc, b, b, optimize=True)
                with timer.measure('Y_combine'):
                    Y += D
            else:
                t = model.topology
                if variant == 'direct-matmul':
                    with timer.measure('C_gather'):
                        C = C[setting]
                with timer.measure('contraction'):
                    if variant == 'six-einsum-no-opt':
                        D = np.einsum('sb,bij->sij', C, t.stamps, optimize=False)
                    else:
                        D = (C @ t.flat).reshape(len(C), n, n)
                if variant != 'direct-matmul':
                    with timer.measure('D_gather'):
                        D = D[setting]
                with timer.measure('Y_combine'):
                    Y += omega[:, None, None]*D
            np.testing.assert_allclose(Y, model.topology.node_admittance(values, omega, setting), atol=1e-12, rtol=1e-12)
        report.update(timers=timer.snapshot(), node_assembly_count=200, rf_forward_count=0,
            limitation='Instrumented subregions with assertion outside timers; not plain performance')
    print(json.dumps(plain(report), sort_keys=True, allow_nan=False))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--suite', choices=('forward', 'detail', 'equivalence', 'solver'), required=True)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--child', choices=('baseline', *probe.VARIANTS))
    parser.add_argument('--candidates', nargs='+', choices=probe.VARIANTS, default=['six-matmul', 'six-einsum-no-opt'])
    parser.add_argument('--pairs', type=int, default=10)
    args = parser.parse_args()
    if args.child:
        child(args.suite, args.child)
        return
    if args.output is None or args.output.exists():
        parser.error('Provide a new --output path')
    if args.pairs < 1 or len(args.candidates) > 2:
        parser.error('positive pairs and at most two solver candidates required')
    env = dict(os.environ, OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1', MKL_NUM_THREADS='1')
    runs = []
    def run(v, warmup=False, batch=0):
        if args.suite == 'solver':
            cmd = [sys.executable, str(Path(probe.__file__)), '--variant', v,
                '--config', 'project/diagnostics/issue377/baseline.yaml',
                '--starts', 'project/diagnostics/issue401_starts_1002.json',
                '--arm', 'hybrid', '--seed', '1002', '--mode', 'plain']
        else:
            cmd = [sys.executable, str(Path(__file__)), '--suite', args.suite, '--child', v]
        cmd = ['taskset', '-c', '2', *cmd]
        result = subprocess.run(cmd, cwd=ROOT, env=env, text=True, capture_output=True)
        record = dict(command=cmd, warmup=warmup, batch=batch, variant=v,
            returncode=result.returncode, stderr=result.stderr)
        if result.returncode == 0:
            record['report'] = json.loads(result.stdout)
        else:
            record['stdout'] = result.stdout
        runs.append(record)
        args.output.write_text(json.dumps(plain(dict(suite=args.suite, runs=runs)), sort_keys=True, indent=2, allow_nan=False)+'\n')
        if result.returncode:
            raise RuntimeError(f'Child failed; preserved in {args.output}')
    if args.suite == 'equivalence':
        run('baseline')
    elif args.suite == 'detail':
        for v in ('baseline', *probe.VARIANTS):
            for i in range(3):
                run(v, batch=i)
    else:
        variants = args.candidates if args.suite == 'solver' else probe.VARIANTS
        for batch, v in enumerate(variants):
            run('baseline', True, batch)
            run(v, True, batch)
            for i in range(args.pairs):
                for a in (('baseline', v) if i % 2 == 0 else (v, 'baseline')):
                    run(a, batch=batch)


if __name__ == '__main__':
    main()

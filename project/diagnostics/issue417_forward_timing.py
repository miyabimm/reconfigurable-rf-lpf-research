#!/usr/bin/env python3
"""Bounded-process timing diagnosis of fixed RF-T008 forward vectors.

This measures the actual RFEvaluator path only. It is not a solver, EXP, or
production optimization runner. Each timing sample runs in a fresh process.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
from time import perf_counter_ns, process_time_ns

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'src'))

import numpy as np
import scipy
from lpf.constraint_versions import constraint_fingerprint, load_constraint
from lpf.search._job_evaluation import source_identity
from lpf.search._minimal_worker_timing import instrument
from lpf.search._worker_next import MinimalWorker
from lpf.search.plan import ROOT, load_preflight
from lpf.search.proposals import definition_from_data
from lpf.search.starts import load_explicit
from lpf.search.storage import sha, vector_sha
from lpf.timing import TimerCollector

EXPECTED_HEAD = '523f3ab8d0d89323fd521c9b6738728f8babc54b'
EXPECTED_PLAN = '8ac7bab9567918ae5c656fd449807ad2c38c1e1cad9e39c8ed217b95a569043e'
EXPECTED_GRID = '6805740a36f6100d7dec3e7308924242e909255f1ea2d287b7c734c400f98f26'
EXPECTED_POLICY = 'e682165c72d3a8b9f1384a2529f71bacfebfc9d17164d4af5af879e4a138b532'
EXPECTED_VECTOR_FILE = 'e87355eb364073a5743062e8e4ee7c90c3012cbfb5e38bef6283860381736ba0'
EXPECTED_STARTS_FILE = '63b671ea269656843df118230b7d920e91515188235809b6dd0efd667ac997ab'
EXPECTED_BANDS = '1b1182e4c947059cb263c1af52ddf64236bd1fd9e83770cc844126576c7865fe'
EXPECTED_INPUT_S2P = 'ad266111ba1dc2b92f235d39f4a647ff271050bc11941c217661dd299ee59945'
EXPECTED_OUTPUT_S2P = 'b3cfc861bc0c8221f49328598c9d7d0766a6e94e42e990b6a50f6c90bf9a84da'


def _file_sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _response_digest(responses, worker):
    h = hashlib.sha256()
    g = hashlib.sha256()
    for response in responses:
        for name in ('s', 'il_db', 'apl_db', 'in_rl_db', 'out_rl_db'):
            array = np.ascontiguousarray(getattr(response, name))
            h.update(name.encode('ascii') + b'\0')
            h.update(str(array.shape).encode('ascii') + b'\0')
            h.update(array.dtype.str.encode('ascii') + b'\0')
            h.update(array.tobytes())
        from lpf.search.performance import evaluate_requirements
        result = evaluate_requirements(response, worker.prepared_requirements)
        mandatory = np.ascontiguousarray(result['mandatory_g'], dtype=np.float64)
        g.update(mandatory.tobytes())
    return h.hexdigest(), g.hexdigest()


def _setup(mode, batch, position):
    start_wall, start_cpu = perf_counter_ns(), process_time_ns()
    head = subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], text=True).strip()
    if head != EXPECTED_HEAD:
        raise ValueError(f'Measurement HEAD mismatch: {head}')
    config_path = ROOT / 'project/diagnostics/issue377/baseline.yaml'
    starts_path = ROOT / 'project/diagnostics/issue401_starts_1002.json'
    vectors_path = ROOT / 'project/diagnostics/issue410_equivalence.json'
    if _file_sha(vectors_path) != EXPECTED_VECTOR_FILE or _file_sha(starts_path) != EXPECTED_STARTS_FILE:
        raise ValueError('Fixed vector/start input fingerprint mismatch')
    vectors_data = json.loads(vectors_path.read_text())
    vectors = vectors_data['vectors']
    expected_vectors = vectors_data['vector_sha256']
    if len(vectors) != 100 or len(expected_vectors) != 100:
        raise ValueError('Expected the complete fixed 100-vector sequence')
    xs = [np.asarray(x, dtype=np.float64) for x in vectors]
    actual_vector_hashes = [vector_sha(x) for x in xs]
    if actual_vector_hashes != expected_vectors:
        raise ValueError('Fixed vector sequence SHA mismatch')

    plan = load_preflight(str(config_path), root=ROOT)
    if plan.sha256 != EXPECTED_PLAN:
        raise ValueError(f'Plan SHA mismatch: {plan.sha256}')
    cfg = plan.data['config']
    if cfg['rf']['constraint_id'] != 'RF-T008' or cfg['rf']['allow_trial'] is not True or cfg['objective'] != 'full_lpf':
        raise ValueError('Expected explicit RF-T008 trial/full_lpf configuration')
    definition_ref = cfg['definition']
    definition = definition_from_data(json.loads((ROOT / definition_ref['path']).read_bytes()))
    policy = load_constraint('RF-T008', root=ROOT, allow_trial=True)
    if constraint_fingerprint(policy) != EXPECTED_POLICY:
        raise ValueError('Resolved RF-T008 effective SHA mismatch')
    starts_sha = _file_sha(starts_path)
    initial = load_explicit(str(starts_path))[1002]
    worker = MinimalWorker(plan, definition, policy, 'hybrid', 1002,
                          initial['vector'], initial['vector_sha256'], root=ROOT)
    grid_sha = plan.data['grids']['hybrid/coarse']['sha256']
    if grid_sha != EXPECTED_GRID or len(worker.grid.frequency_hz) != 70:
        raise ValueError('Expected fixed 70-sample grid')
    if len(set(worker.grid.segment.tolist())) != 28 or set(worker.grid.setting.tolist()) != set(range(6)):
        raise ValueError('Expected all six settings and 28 separate intervals')

    identity = source_identity(ROOT)
    source_sha = sha(identity)
    driver_sha = _file_sha(__file__)
    files = {
        'bands': ('rf/bands.csv', EXPECTED_BANDS),
        'input_s2p': ('rf/parasitics/circuit1_ant_coupler_0_6ghz.s2p', EXPECTED_INPUT_S2P),
        'output_s2p': ('rf/parasitics/circuit2_poc_through_0_6ghz.s2p', EXPECTED_OUTPUT_S2P),
        'trial_constraint': ('rf/constraints/trial/RF-T008.json', None),
        'formal_constraint': ('rf/constraints/formal/RF-F003.json', None),
        'registry': ('rf/constraints/registry.json', None),
        'definition': (definition_ref['path'], definition_ref['source_sha256']),
    }
    fingerprints = {}
    for key, (path, expected) in files.items():
        digest = _file_sha(ROOT / path)
        if expected is not None and digest != expected:
            raise ValueError(f'{key} SHA mismatch: {digest}')
        fingerprints[key] = {'path': path, 'sha256': digest}
    setup_wall, setup_cpu = perf_counter_ns()-start_wall, process_time_ns()-start_cpu
    return worker, xs, dict(kind='issue417_fixed_rf_forward_timing', mode=mode,
        batch=batch, position=position, head=head, git_status=subprocess.check_output(
            ['git', '-C', str(ROOT), 'status', '--short'], text=True),
        source_identity_sha256=source_sha, source_identity_head=identity['head'],
        source_identity_dirty_patch_sha256=identity['dirty_patch_sha256'],
        driver_sha256=driver_sha, config_path=str(config_path.relative_to(ROOT)),
        starts_path=str(starts_path.relative_to(ROOT)), starts_file_sha256=starts_sha,
        vector_file_path=str(vectors_path.relative_to(ROOT)), vector_file_sha256=_file_sha(vectors_path),
        vector_count=len(xs), verified_individual_vector_sha_count=len(actual_vector_hashes),
        vector_sequence_sha256=sha(actual_vector_hashes),
        plan_sha256=plan.sha256, grid_sha256=grid_sha, sample_count_per_forward=len(worker.grid.frequency_hz),
        setting_count=len(set(worker.grid.setting.tolist())), interval_count=len(set(worker.grid.segment.tolist())),
        policy_id=worker.model.policy_id, policy_effective_sha256=worker.model.policy_fingerprint,
        objective=cfg['objective'], rf_input_fingerprints=fingerprints,
        environment=dict(python=platform.python_version(), numpy=np.__version__, scipy=scipy.__version__,
            platform=platform.platform(), affinity=sorted(os.sched_getaffinity(0)) if hasattr(os, 'sched_getaffinity') else None,
            threads={k: os.environ.get(k) for k in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS')}),
        setup_wall_ns=setup_wall, setup_cpu_ns=setup_cpu,
        warmup_forward_count=len(xs), requested_measured_forward_count=len(xs),
        requested_measured_samples=len(xs)*len(worker.grid.frequency_hz),
        timing_boundary='only the ordered 100 calls to RFEvaluator.evaluate; fixed S2P preparation, warmup, response digest and mandatory requirements are outside',
        fixed_system='all six settings, 28 separate intervals, RF-T008 rev3 trial/full_lpf; external fixed S2P included')


def child(mode, batch, position):
    worker, xs, report = _setup(mode, batch, position)
    warmup = [worker.evaluator.evaluate(x) for x in xs]
    if len(warmup) != 100:
        raise ValueError('Warmup forward count mismatch')
    timer = TimerCollector() if mode == 'deep' else None
    context = instrument(worker, timer, deep=True) if timer else _null_context()
    cpu_start, wall_start = process_time_ns(), perf_counter_ns()
    with context:
        responses = [worker.evaluator.evaluate(x) for x in xs]
    wall_ns, cpu_ns = perf_counter_ns()-wall_start, process_time_ns()-cpu_start
    response_sha, mandatory_sha = _response_digest(responses, worker)
    report.update(measured_wall_ns=wall_ns, measured_cpu_ns=cpu_ns,
        response_sha256=response_sha, mandatory_g_sha256=mandatory_sha,
        measured_forward_count=len(responses), timers=timer.snapshot() if timer else {},
        stop_status='all 100 forwards completed; no exception/STOP',
        warmup_response_sha256=_digest_warmup(warmup))
    return report


def _digest_warmup(responses):
    h = hashlib.sha256()
    for response in responses:
        array = np.ascontiguousarray(response.s)
        h.update(array.tobytes())
    return h.hexdigest()


class _null_context:
    def __enter__(self):
        return self
    def __exit__(self, *exc):
        return False


def suite(pairs, output):
    out = Path(output).resolve()
    if out.exists():
        raise FileExistsError(f'Refusing to overwrite timing evidence: {out}')
    rows, failures = [], []
    env = os.environ.copy()
    for name in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS'):
        env[name] = '1'
    for batch in range(pairs):
        order = ('plain', 'deep') if batch % 2 == 0 else ('deep', 'plain')
        for position, mode in enumerate(order):
            command = [sys.executable, str(Path(__file__).resolve()), '--child', '--mode', mode,
                       '--batch', str(batch), '--position', str(position)]
            proc = subprocess.run(command, capture_output=True, text=True, env=env)
            try:
                row = json.loads(proc.stdout) if proc.stdout.strip() else None
            except json.JSONDecodeError:
                row = None
            if proc.returncode or row is None:
                failures.append(dict(batch=batch, position=position, mode=mode,
                    returncode=proc.returncode, stdout=proc.stdout, stderr=proc.stderr, command=command))
            else:
                row['command'] = command
                rows.append(row)
    identity_shas = sorted({r['source_identity_sha256'] for r in rows})
    plain_hashes = [r['response_sha256'] for r in rows if r['mode'] == 'plain']
    deep_hashes = [r['response_sha256'] for r in rows if r['mode'] == 'deep']
    plain_g = [r['mandatory_g_sha256'] for r in rows if r['mode'] == 'plain']
    deep_g = [r['mandatory_g_sha256'] for r in rows if r['mode'] == 'deep']
    comparisons = dict(source_identity_stable=len(identity_shas) == 1,
        plain_response_stable=len(set(plain_hashes)) == 1,
        deep_response_stable=len(set(deep_hashes)) == 1,
        plain_deep_response_equal=bool(plain_hashes and deep_hashes and set(plain_hashes) == set(deep_hashes)),
        plain_mandatory_g_stable=len(set(plain_g)) == 1, deep_mandatory_g_stable=len(set(deep_g)) == 1,
        plain_deep_mandatory_g_equal=bool(plain_g and deep_g and set(plain_g) == set(deep_g)))
    record = dict(kind='issue417_forward_timing_suite', measurement_head=EXPECTED_HEAD,
        requested_pairs=pairs, actual_run_count=len(rows), successful_run_count=len(rows),
        failed_runs=failures, order='balanced adjacent pairs: plain/deep then deep/plain, alternating',
        comparisons=comparisons, source_identity_sha256=identity_shas[0] if len(identity_shas) == 1 else identity_shas,
        runs=rows, timing_notes='Timer regions are inclusive; per-run total wall/CPU is plain or deep as indicated. No outlier excluded.')
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(record, sort_keys=True, indent=2, allow_nan=False) + '\n')
    print(json.dumps(dict(output=str(out), sha256=_file_sha(out), runs=len(rows), failures=len(failures),
                          comparisons=comparisons), sort_keys=True))
    return 0 if not failures and all(comparisons.values()) else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--suite', action='store_true', help='run balanced plain/deep child processes')
    parser.add_argument('--child', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--mode', choices=('plain', 'deep'))
    parser.add_argument('--batch', type=int, default=0)
    parser.add_argument('--position', type=int, default=0)
    parser.add_argument('--pairs', type=int, default=6)
    parser.add_argument('--output')
    args = parser.parse_args()
    if args.child:
        if args.mode is None:
            parser.error('--child requires --mode')
        print(json.dumps(child(args.mode, args.batch, args.position), sort_keys=True, allow_nan=False))
        return 0
    if args.suite:
        if not args.output or args.pairs < 1:
            parser.error('--suite requires --output and --pairs >=1')
        return suite(args.pairs, args.output)
    parser.error('choose --suite or --child')


if __name__ == '__main__':
    raise SystemExit(main())

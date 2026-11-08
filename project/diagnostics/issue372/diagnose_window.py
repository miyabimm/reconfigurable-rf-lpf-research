"""#372: one bounded window100 diagnostic, against preserved legacy bytes.

This is a fixed-vector fixture callback, not a search or an EXP. Never retries.
"""
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import statistics
import sys
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'src'))
import numpy as np
from lpf.constraint_versions import load_constraint
from lpf.rf_core.model import RFEvaluator
from lpf.search import runner
from lpf.search._forward_window import ForwardJournal
from lpf.search._job_evaluation import source_identity
from lpf.search._window_evaluation import WindowJobEvaluation
from lpf.search.plan import load_preflight
from lpf.search.proposals import definition_from_data
from lpf.search.starts import load_explicit
from lpf.search.storage import atomic_verified, plain, sha

LEGACY_SHA = {
    'development-hybrid-1001.json': '2dd174cd1e99bc3970b88f7abf0ddb715f50357c0a116fe466c710eec879feb9',
    'run.json': 'c72138da75a51d8c73463692d98841d7006614faffac890924eb8965eff3654c',
    'summary.json': '0b9848d746c69f9185e91b418daf169e0e64212d58c71135dcaa5175315a1607',
}


def io_record(mode, summary):
    if mode == 'legacy':
        if 'io' in summary:
            raise ValueError('unexpected legacy io schema')
        return {'status': 'not_applicable'}
    if mode != 'window100' or not isinstance(summary.get('io'), dict):
        raise ValueError('window100 summary io is mandatory')
    io = summary['io']
    if io.get('complete_worker_accounting') is not True:
        raise ValueError('incomplete worker io')
    for scope in ('parent', 'worker', 'summary'):
        section = io[scope]
        for key in ('atomic_writes', 'payload_bytes', 'atomic_readbacks', 'readback_bytes'):
            if type(section.get(key)) is not int or section[key] <= 0:
                raise ValueError(f'invalid {scope} {key}')
        if section['atomic_writes'] != section['atomic_readbacks'] or section['payload_bytes'] != section['readback_bytes']:
            raise ValueError(f'io readback mismatch: {scope}')
    return io


def load_legacy(path):
    path = Path(path)
    contents = {}
    for name, expected in LEGACY_SHA.items():
        raw = (path / name).read_bytes()
        if hashlib.sha256(raw).hexdigest() != expected:
            raise ValueError(f'legacy byte SHA mismatch: {name}')
        contents[name] = json.loads(raw)
    worker = contents['development-hybrid-1001.json']
    parent, summary = contents['run.json'], contents['summary.json']
    if (summary['parent_raw_byte_sha256'] != LEGACY_SHA['run.json'] or
        summary['jobs'][0]['raw_byte_sha256'] != LEGACY_SHA['development-hybrid-1001.json'] or
        summary['jobs'][0]['raw_content_sha256'] != sha(worker) or
        parent['campaign']['requested'] != 630 or parent['campaign']['completed'] != 630 or
        worker['requested'] != 630 or worker['completed'] != 630 or
        [b['requested'] for b in worker['batches']] != [70, 84, 476]):
        raise ValueError('legacy ledger mismatch')
    return worker, summary, io_record('legacy', summary)


@dataclass
class Run:
    end_x: list
    success: bool = False

@dataclass
class Result:
    runs: list
    best_x: list
    reason: str = 'diagnostic_fixture_not_optimization'


def main():
    if len(sys.argv) != 3:
        raise SystemExit('usage: diagnose_window.py <preserved legacy directory> <fresh persistent window output>')
    legacy_path, output = map(Path, sys.argv[1:])
    worker, legacy_summary, legacy_io = load_legacy(legacy_path)
    plan = load_preflight(ROOT / 'project/diagnostics/issue372/diagnostic.yaml')
    old_source = json.loads(worker['spec']['frozen_json'])['source']
    current_source = source_identity(ROOT)
    if (plan.sha256 != worker['plan_sha256'] or current_source['files'] != old_source['files'] or
            current_source['environment'] != old_source['environment']):
        raise ValueError('legacy/current plan, implementation bytes or environment mismatch')
    definition = definition_from_data(json.loads((ROOT / 'project/diagnostics/issue361/definition.json').read_bytes()))
    policy = load_constraint('RF-T008', allow_trial=True)
    starts = {1001: load_explicit(ROOT / 'project/diagnostics/issue361/pilot-starts.json')[1001]}
    baseline = worker['batches'][0]
    a = baseline['assessment']
    legacy_objective = float(np.sum(np.r_[np.sqrt(a['worst_il_db']), np.maximum(0., -np.asarray(a['mandatory_g']))] ** 2))
    c = dict(response=None, assessment=None, callback_wall_s=[], callback_cpu_s=[], objectives=[], reservation=None)
    original_eval, original_assess, original_start = RFEvaluator.evaluate, WindowJobEvaluation._assess, ForwardJournal.start
    def capture_response(evaluator, x):
        response = original_eval(evaluator, x)
        if len(evaluator.grid.frequency_hz) == 70 and c['response'] is None:
            c['response'] = dict(s_real=response.s.real.tolist(), s_imag=response.s.imag.tolist(),
                **{k: getattr(response, k).tolist() for k in ('il_db', 'apl_db', 'in_rl_db', 'out_rl_db')})
        return response
    def capture_assess(meter, x):
        result = original_assess(meter, x)
        if meter.stage == 'hybrid/coarse' and c['assessment'] is None:
            c['assessment'] = plain(result['assessment'])
        return result
    def capture_start(journal):
        value = original_start(journal)
        data = journal.path.read_bytes()
        record = json.loads(data)
        if record != journal.last_record or journal.write_calls != 1 or journal.read_calls != 1:
            raise ValueError('reservation atomic/readback mismatch')
        c['reservation'] = dict(sha256=hashlib.sha256(data).hexdigest(), record=record,
                                bytes=len(data), atomic_writes=journal.write_calls, atomic_readbacks=journal.read_calls)
        return value
    def solver(callback, x, bounds, **options):
        for _ in range(20):
            wall, cpu = time.perf_counter(), time.process_time()
            residual = callback(x)
            c['callback_wall_s'].append(time.perf_counter() - wall)
            c['callback_cpu_s'].append(time.process_time() - cpu)
            c['objectives'].append(float(np.sum(residual * residual)))
        return Result([Run(list(x))], list(x))
    wall, cpu = time.perf_counter(), time.process_time()
    with patch.object(RFEvaluator, 'evaluate', capture_response), \
         patch.object(WindowJobEvaluation, '_assess', capture_assess), \
         patch.object(ForwardJournal, 'start', capture_start), \
         patch('lpf.search.worker.hybrid_minimize', side_effect=solver):
        state = runner.run_development(plan, definition, policy, starts, output, storage_mode='window100')
        summary = runner.finalize_development(state, output)
    wall, cpu = time.perf_counter()-wall, time.process_time()-cpu
    io = io_record('window100', summary)
    raw_path = output / summary['jobs'][0]['raw_path']
    raw_bytes = raw_path.read_bytes()
    raw = json.loads(raw_bytes)
    reservation = c['reservation']['record']
    checks = dict(response_exact=c['response'] == baseline['response'],
        assessment_exact=c['assessment'] == baseline['assessment'],
        hybrid_exact=all(v == legacy_objective for v in c['objectives']) and len(c['objectives']) == 20,
        reservation_100=(reservation['confirmed']['forwards'] == 0 and
            reservation['window'] == dict(first_forward=0, end_forward=100, samples_per_forward=70, reserved_samples=7000)),
        ledger=(state['status'] == 'completed' and summary['exit_code'] == 4 and
            summary['campaign']['requested'] == summary['campaign']['completed'] == 1960 and
            summary['campaign']['reserved'] == summary['campaign']['unknown_cost_upper_bound'] == 0),
        raw_readback=(hashlib.sha256(raw_bytes).hexdigest() == summary['jobs'][0]['raw_byte_sha256'] and
            raw['confirmed'] == raw['uncertain_upper'] and raw['window'] is None),
        parent_readback=hashlib.sha256((output/'run.json').read_bytes()).hexdigest() == summary['parent_raw_byte_sha256'],
        summary_io_bytes=io['summary']['payload_bytes'] == len((output/'summary.json').read_bytes()))
    report = dict(kind='independent_bounded_real_rf_diagnostic_not_pilot', plan_sha256=plan.sha256,
        source=current_source, source_sha256=sha(current_source), legacy_sha=LEGACY_SHA,
        legacy_source_sha256=worker['spec']['source_sha256'], legacy_io=legacy_io,
        costs=plan.data['costs'], search_grid_sha256=plan.data['grids']['hybrid/coarse']['sha256'],
        search_forwards=20, selection_samples=84, terminal_samples=476, anytime_samples=0,
        fixture='20 repeated callbacks of the same starting vector; no optimization',
        wall_s=wall, cpu_s=cpu, median_callback_wall_s=statistics.median(c['callback_wall_s']),
        median_callback_cpu_s=statistics.median(c['callback_cpu_s']), io=io, checks=checks,
        legacy_hybrid_objective=legacy_objective, captures=c, raw_byte_sha256=summary['jobs'][0]['raw_byte_sha256'],
        parent_byte_sha256=summary['parent_raw_byte_sha256'],
        summary_byte_sha256=hashlib.sha256((output/'summary.json').read_bytes()).hexdigest())
    saved = atomic_verified(output/'diagnostic-report.json', report)
    print(json.dumps(dict(checks=checks, median_wall=report['median_callback_wall_s'], median_cpu=report['median_callback_cpu_s'],
                          wall=wall, cpu=cpu, io=io, report_sha256=saved['sha256']), sort_keys=True), flush=True)
    if not all(checks.values()):
        raise RuntimeError('STOP: numerical, reservation, ledger or readback mismatch')
    if report['median_callback_wall_s'] > 2:
        raise RuntimeError('STOP: speed gate needs reassessment (>2s/forward)')

if __name__ == '__main__':
    main()

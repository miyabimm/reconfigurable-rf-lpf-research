"""#372 bounded diagnostic only: fixed-vector fixture callbacks with real RF.

Not an optimizer or EXP. Two separate jobs: legacy 1 search forward and
window100 20 search forwards. Each also runs selection and terminal once.
"""
import dataclasses
import hashlib
import json
import os
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
from lpf.search._job_evaluation import FixedJobEvaluation
from lpf.search._window_evaluation import WindowJobEvaluation
from lpf.search.plan import load_preflight
from lpf.search.proposals import definition_from_data
from lpf.search.starts import load_explicit
from lpf.search.storage import plain, sha

@dataclasses.dataclass
class Run:
    end_x: list
    success: bool = False

@dataclasses.dataclass
class Result:
    runs: list
    best_x: list
    reason: str = 'diagnostic_fixture_not_optimization'


def main():
    if len(sys.argv) != 3:
        raise SystemExit('usage: diagnose.py <fresh /tmp legacy output> <fresh persistent window output>')
    legacy, window = map(Path, sys.argv[1:])
    plan = load_preflight(ROOT / 'project/diagnostics/issue372/diagnostic.yaml')
    definition = definition_from_data(json.loads((ROOT / 'project/diagnostics/issue361/definition.json').read_bytes()))
    policy = load_constraint('RF-T008', allow_trial=True)
    all_starts = load_explicit(ROOT / 'project/diagnostics/issue361/pilot-starts.json')
    starts = {1001: all_starts[1001]}
    results, captures = {}, {}
    original_eval = RFEvaluator.evaluate
    original_legacy = FixedJobEvaluation._assess
    original_window = WindowJobEvaluation._assess
    original_start = ForwardJournal.start
    for mode, count, output in [('legacy', 1, legacy), ('window100', 20, window)]:
        captures[mode] = {'responses': [], 'assessments': [], 'durations_s': [], 'objectives': [], 'reservations': []}
        c = captures[mode]
        def capture_response(evaluator, x):
            response = original_eval(evaluator, x)
            if len(evaluator.grid.frequency_hz) == 70 and not c['responses']:
                c['responses'].append(dict(s_real=response.s.real.tolist(), s_imag=response.s.imag.tolist(),
                    **{k: getattr(response, k).tolist() for k in ('il_db', 'apl_db', 'in_rl_db', 'out_rl_db')}))
            return response
        def wrap_assess(original):
            def wrapped(meter, x):
                result = original(meter, x)
                if meter.stage == 'hybrid/coarse' and not c['assessments']:
                    c['assessments'].append(plain(result['assessment']))
                return result
            return wrapped
        def journal_start(journal):
            value = original_start(journal)
            data = journal.path.read_bytes()
            c['reservations'].append(dict(sha256=hashlib.sha256(data).hexdigest(), record=json.loads(data)))
            return value
        def solver(callback, x, bounds, **options):
            for _ in range(count):
                start = time.perf_counter()
                r = callback(x)
                c['durations_s'].append(time.perf_counter() - start)
                c['objectives'].append(float(np.sum(r*r)))
            return Result([Run(list(x))], list(x))
        start, cpu = time.perf_counter(), time.process_time()
        with patch.object(RFEvaluator, 'evaluate', capture_response), \
             patch.object(FixedJobEvaluation, '_assess', wrap_assess(original_legacy)), \
             patch.object(WindowJobEvaluation, '_assess', wrap_assess(original_window)), \
             patch.object(ForwardJournal, 'start', journal_start), \
             patch('lpf.search.worker.hybrid_minimize', side_effect=solver):
            state = runner.run_development(plan, definition, policy, starts, output, storage_mode=mode)
            summary = runner.finalize_development(state, output)
        results[mode] = dict(wall_s=time.perf_counter()-start, cpu_s=time.process_time()-cpu,
            status=state['status'], exit_reason=state.get('exit_reason'), exit_code=summary['exit_code'],
            campaign=summary['campaign'], io=summary['io'], job=summary['jobs'][0], output=str(output))
        if state['status'] != 'completed' or summary['exit_code'] != 4:
            raise RuntimeError(f'{mode}: unexpected diagnostic outcome: {state.get("exit_reason")}')
    a, b = captures['legacy'], captures['window100']
    checks = dict(response_exact=a['responses'][0] == b['responses'][0],
        assessment_exact=a['assessments'][0] == b['assessments'][0],
        hybrid_objective_exact=a['objectives'][0] == b['objectives'][0],
        window_repeated_objective_exact=len(set(b['objectives'])) == 1,
        window_reservation_100=b['reservations'][0]['record']['window']['end_forward'] == 100)
    report = dict(kind='bounded_real_rf_diagnostic_not_pilot', plan_sha256=plan.sha256,
        plan_costs=plan.data['costs'], search_grid_sha256=plan.data['grids']['hybrid/coarse']['sha256'],
        fixture='fixed same vector, no optimization, 1 legacy + 20 window search forwards; each selection 84 + terminal 476 samples',
        results=results, captures=captures, checks=checks,
        window_median_callback_s=statistics.median(b['durations_s']))
    out = window / 'diagnostic-report.json'
    out.write_text(json.dumps(report, indent=2, allow_nan=False)+'\n')
    assert json.loads(out.read_bytes()) == report
    print(json.dumps(dict(checks=checks, median=report['window_median_callback_s'], results=results,
                          report=str(out), report_sha256=hashlib.sha256(out.read_bytes()).hexdigest()), sort_keys=True), flush=True)
    if not all(checks.values()):
        raise RuntimeError('STOP: numerical or reservation mismatch')

if __name__ == '__main__':
    main()

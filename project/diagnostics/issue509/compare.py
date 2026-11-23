#!/usr/bin/env python3
"""Issue 505 development-only wall comparison; never interrupts a solver.

Run one arm per fresh temporary output, with BLAS/OMP/MKL threads set before
Python starts. Solver wrappers are installed only in this process; the actual
DevelopmentWorker, optimizer, checkpoint and receipt paths remain unchanged.
"""
import argparse
import gzip
import hashlib
import io
import json
import os
import platform
from contextlib import redirect_stdout
from pathlib import Path
import sys
from time import monotonic, process_time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'src'))
import numpy as np
from lpf.minimax_profile import signed_margins
from lpf.search import _development_runner as runner, _development_worker as worker_module
from lpf.search.storage import plain, sha, vector_sha
from lpf.search.evaluation import raw_numbers

WINDOWS = (1, 5, 20)


def select(events, seconds):
    """Strict chronological cutoff, first wins ties; no Terminal feedback."""
    eligible = (e for e in events if e['elapsed_s'] <= seconds)
    return min(eligible, key=lambda e: e['objective'], default=None)


def classify(reason, elapsed, window, error=None):
    if error:
        return 'rf_or_execution_stop'
    if elapsed >= window:
        return 'observed'
    if reason in ('evaluation_limit', 'evaluation_budget_exhausted'):
        return 'budget_censored'
    if reason in ('converged', 'all_variables_fixed', 'all_coordinates_fixed'):
        return 'early_convergence_hold'
    return 'early_other_stop'


def config_for(arm, limit):
    config = json.loads((ROOT/'project/diagnostics/issue470/config.json').read_text())
    step = config['arms'][0]['steps'][0]
    if arm == 'hybrid':
        step['options'] = dict(max_search_forwards=limit, batch_fd=True, partial_fd=True, restart_sigma=.1)
        cap = limit + 24
    else:
        step.update(solver='trf', options={'max_evaluations': limit, 'restart_sigma': .1, 'ftol': 1e-8, 'x_scale': 1.0})
        cap = limit
    config['budget'] = dict(rf_samples=70*cap+476, rf_forwards=cap+1, independent_mna_samples=2)
    return config


def run(arm, limit, output, *, observe=True):
    starts = json.loads((ROOT/'project/diagnostics/issue470/starts.json').read_text())
    config = config_for(arm, limit)
    events, context = [], {}
    original_search = worker_module.DevelopmentWorker._search_impl
    original_h, original_t = worker_module.hybrid_minimize, worker_module.least_squares_local

    def search(self, step, x):
        context['worker'] = self
        return original_search(self, step, x)

    def solver(original, callback_name, *args, **kwargs):
        callback = kwargs[callback_name]
        # The worker's residual closure owns the actual evaluator; inspect once,
        # outside the solver window, rather than wrapping any RF calls.
        closure = dict(zip(args[0].__code__.co_freevars, (c.cell_contents for c in args[0].__closure__)))
        evaluator = closure['evaluator']
        start, cpu = context.setdefault('start', monotonic()), context.setdefault('cpu_start', process_time())
        def record(x, value, *more):
            now = monotonic()  # after the objective is available, never batch start
            events.append(dict(elapsed_s=now-start, objective=float(value), vector=x.copy(),
                               forward_count=context['worker'].forward_count))
            return callback(x, value, *more)
        if observe:
            kwargs[callback_name] = record
        try:
            return original(*args, **kwargs)
        finally:
            context['solver_wall_s'] = monotonic()-start
            context['solver_cpu_s'] = process_time()-cpu
            context['cache_stats'] = dict(evaluator.cache_stats)

    spots = {'terminal': [0, 111]}
    load_start = os.getloadavg()
    wall, cpu = monotonic(), process_time()
    error = None
    try:
        with patch.object(worker_module.DevelopmentWorker, '_search_impl', search), \
             patch.object(worker_module, 'hybrid_minimize', lambda *a, **k: solver(original_h, 'progress_callback', *a, **k)), \
             patch.object(worker_module, 'least_squares_local', lambda *a, **k: solver(original_t, 'objective_callback', *a, **k)):
            state = runner.run(config, starts, output, root=ROOT, spot_checks=spots,
                               checkpoint_interval=1000, rf_cache_mode='lk')
    except Exception as exc:
        state = None
        error = f'{type(exc).__name__}: {exc}'
    elapsed, cpu_elapsed = monotonic()-wall, process_time()-cpu
    # Save even partial observations on failures; all expensive hashing is outside Search.
    for index, event in enumerate(events):
        event['sequence'] = index + 1
        event['vector_sha256'] = vector_sha(event['vector'])
        event['vector'] = event['vector'].tolist()
    result_path = output/'job-0001/result.json'
    result = json.loads(result_path.read_text()) if result_path.exists() else None
    step = result['steps'][0] if result else None
    reason = step['stop_reason'] if step else None
    worker = context.get('worker')
    terminal = {}
    extra = 0
    mna_before = worker.audit_samples.get('terminal', 0) if worker else 0
    post_wall = monotonic()
    for window in WINDOWS:
        event = select(events, window)
        status = classify(reason, context.get('solver_wall_s', 0), window, error)
        row = dict(status=status, selected_sequence=event['sequence'] if event else None)
        if event is not None and worker is not None:
            key = event['vector_sha256']
            if key not in terminal:
                # Use the same Terminal forward, physical and MNA checks as the Worker.
                try:
                    worker.forward_count, worker.forward_cap = 0, 1
                    evaluator = worker.model.evaluator(worker.grids['terminal'])
                    response, physical, independent = worker._forward(evaluator, np.asarray(event['vector']), 'terminal')
                    margin, _ = signed_margins(worker.profile, evaluator.grid, response)
                    passed = np.array([worker.profile.records[i]['type'] == 'pass' for i in evaluator.grid.segment])
                    terminal[key] = dict(J=margin, finite_grid_pass=margin <= 0,
                        max_pass_il_db=float(np.max(response.il_db[passed])),
                        min_h2_h3_atten_db=float(np.min(response.il_db[~passed])),
                        physical=plain(physical), independent=plain(independent),
                        external_passivity='checked_on_terminal_grid', power_balance='checked_on_terminal_grid')
                except Exception as exc:
                    terminal[key] = dict(error=f'{type(exc).__name__}: {exc}')
                extra += 1
            row.update(vector_sha256=key, search_objective=event['objective'],
                       observed_s=event['elapsed_s'], terminal=terminal[key])
        row['missing'] = event is None
        row['terminal_selection'] = 'search_objective_only'
        context.setdefault('windows', {})[str(window)] = row
    post_wall = monotonic()-post_wall
    plan = worker.data if worker else None
    blas = io.StringIO()
    with redirect_stdout(blas):
        np.show_config()
    return raw_numbers(dict(arm=arm, limit=limit, observe=observe, error=error, state=state,
        solver_wall_s=context.get('solver_wall_s'), solver_cpu_s=context.get('solver_cpu_s'),
        runner_wall_s=elapsed, runner_cpu_s=cpu_elapsed, post_wall_s=post_wall,
        windows=context.get('windows', {}), events=events, result=result,
        plan_sha256=sha(plan) if plan else None, search_cache_stats=context.get('cache_stats'), additional_terminal_forwards=extra,
        additional_terminal_requested_samples=extra*476,
        additional_terminal_mna_samples=(worker.audit_samples.get('terminal', 0)-mna_before if worker else 0),
        diagnostic_script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        platform=platform.platform(), host=platform.node(), cpu=platform.processor(),
        affinity=sorted(os.sched_getaffinity(0)), numpy_blas_config=blas.getvalue(),
        loadavg_start=load_start, loadavg_end=os.getloadavg(),
        threads={k: os.environ.get(k) for k in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS')}))



def compact_record(raw):
    """Preserve the selected vectors and scientific comparisons, not every probe."""
    result = raw['result']
    step = result['steps'][0] if result else None
    windows = {}
    for seconds, row in raw['windows'].items():
        selected = row['selected_sequence']
        saved = dict(status=row['status'], selected_sequence=selected,
                     terminal_selection=row['terminal_selection'], missing=row['missing'])
        if selected is not None:
            e = raw['events'][selected - 1]
            if (e['sequence'] != selected or e['vector_sha256'] != row['vector_sha256']
                    or e['elapsed_s'] > float(seconds)):
                raise ValueError('Observation/window mismatch')
            t = row['terminal']
            saved.update(observed_s=e['elapsed_s'], forward_count_at_observation=e['forward_count'],
                         search_objective_db2=e['objective'], vector_sha256=e['vector_sha256'],
                         vector=e['vector'],
                         terminal=dict(J=t.get('J'), finite_grid_pass=t.get('finite_grid_pass'),
                             max_pass_il_db=t.get('max_pass_il_db'),
                             min_h2_h3_atten_db=t.get('min_h2_h3_atten_db'),
                             independent_mna=t.get('independent', {}).get('status'),
                             physical=t.get('physical'),
                             external_passivity=t.get('external_passivity'),
                             power_balance=t.get('power_balance'), error=t.get('error')))
        windows[seconds] = saved
    return dict(kind='development_diagnostic_comparison_compact_v1',
        arm=raw['arm'], limit=raw['limit'], error=raw['error'],
        seed=result['seed'] if result else None,
        plan_sha256=raw['plan_sha256'],
        source_sha256=result['source_sha256'] if result else None,
        initial_vector_sha256=result['initial_vector_sha256'] if result else None,
        search_bounds_sha256=result['search_bounds_sha256'] if result else None,
        status=result['status'] if result else None,
        stop_reason=step['stop_reason'] if step else None,
        converged=step['converged'] if step else None,
        search_forwards=step['forward_count'] if step else None,
        search_requested_samples=step['requested_samples'] if step else None,
        search_computed_samples=sum(r['computed_samples'] for r in step['local_run_details']) if step else None,
        actual=raw['state']['jobs'][0]['actual'] if raw['state'] else None,
        trf_diagnostics=step['local_run_details'] if step else None,
        local_runs=step['local_runs'] if step else None,
        restart_count=step['restart_count'] if step else None,
        rf_profile=result['rf_profile'] if result else None,
        plan=result['plan'] if result else None,
        source=result['source'] if result else None,
        final_vector=result['terminal']['candidates'][0]['vector'] if result else None,
        final_vector_sha256=result['terminal']['candidates'][0]['vector_sha256'] if result else None,
        solver_wall_s=raw['solver_wall_s'], solver_cpu_s=raw['solver_cpu_s'],
        runner_wall_s=raw['runner_wall_s'], runner_cpu_s=raw['runner_cpu_s'],
        post_wall_s=raw['post_wall_s'], windows=windows,
        threads=raw['threads'], platform=raw['platform'], host=raw['host'],
        cpu=raw['cpu'], affinity=raw['affinity'], numpy_blas_config=raw['numpy_blas_config'],
        loadavg_start=raw['loadavg_start'], loadavg_end=raw['loadavg_end'],
        diagnostic_script_sha256=raw['diagnostic_script_sha256'])


def main():
    p = argparse.ArgumentParser()
    p.add_argument('arm', choices=['trf'])
    p.add_argument('limit', type=int)
    p.add_argument('output', type=Path, help='fresh Runner directory under system temp')
    p.add_argument('record', type=Path, help='fresh JSON record')
    p.add_argument('--control', action='store_true', help='disable observation callback')
    args = p.parse_args()
    if any(os.environ.get(k) != '1' for k in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS')):
        p.error('OPENBLAS_NUM_THREADS, OMP_NUM_THREADS and MKL_NUM_THREADS must all be 1')
    if args.record.exists():
        p.error('record must not exist')
    payload = compact_record(run(args.arm, args.limit, args.output, observe=not args.control))
    serialized = json.dumps(payload, allow_nan=False, separators=(',', ':'))
    if args.record.suffix == '.gz':
        with gzip.open(args.record, 'xt') as f:
            f.write(serialized + '\n')
    else:
        with args.record.open('x') as f:
            f.write(serialized + '\n')

if __name__ == '__main__':
    main()

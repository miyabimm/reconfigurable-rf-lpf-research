"""Bounded synthetic-only multi-start execution with crash-closed checkpoints.

Not an EXP runner. Interrupted starts require manual investigation and are
never automatically retried. Only an explicitly supplied mock callback is used.
"""
import json
import subprocess
import tempfile
from pathlib import Path

from lpf.checkpoint_io import atomic_write_json, canonical_config_hash
from lpf.slsqp_budget import STANDARD_SLSQP_BUDGET, run_termination_aware_slsqp
import numpy as np
from ._grid import ROOT
from .candidate_records import CandidateRecord, record_candidate, recheck_record
from .staged_optimization import run_c1_staged, scipy_slsqp_stage
from .problem_seed import vector_fingerprint
from .sampled_epigraph import SampledEpigraph
from .staged_optimization import _grid, _observe
from .synthetic_plan import make_synthetic_plan


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate JSON field: ' + key)
        result[key] = value
    return result


def _read(path):
    def invalid(value):
        raise ValueError('Non-finite JSON: ' + value)
    with path.open(encoding='utf-8') as f:
        return json.load(f, object_pairs_hook=_unique, parse_constant=invalid)


def _write(path, body):
    atomic_write_json(path, {'body': body, 'sha256': canonical_config_hash(body)})


def _validate_plan(circuit, envelope):
    if not isinstance(envelope, dict) or set(envelope) != {'plan', 'fingerprint'}:
        raise ValueError('Invalid plan envelope')
    plan = envelope['plan']
    if canonical_config_hash(plan) != envelope['fingerprint']:
        raise ValueError('Plan fingerprint mismatch')
    starts = []
    for item in plan['starts']:
        s = item['seed_record']
        starts.append({'id': item['id'], 'vector': s['input_vector'],
                       'vector_sha256': s['input_vector_sha256'], 'seed': s['seed'],
                       'jitter_fraction': s['jitter_fraction']})
    actual = make_synthetic_plan(circuit, starts, run_id=plan['run_id'],
        coarse_points=plan['grids']['coarse']['points_per_interval'],
        fine_points=plan['grids']['fine']['points_per_interval'],
        input_source=plan['input_source'])
    if actual != envelope:
        raise ValueError('Plan differs from current source, inputs or preflight')
    return plan



def _recheck_failed_calls(circuit, plan, record):
    """Replay failed-start call scheduling against v2, without retrying the start.

    Failed outputs are diagnostics, not solver evidence. Completed preceding
    calls must still have consistent inputs, budgets, status and observations.
    """
    staged = record['staged_record']
    if staged['numerical_state'] != 'failed':
        return
    calls = staged['stage_calls']
    if (not 1 <= len(calls) <= 4 or staged['controller'] is not None or
            not calls[-1]['exception'] or
            any(c['exception'] for c in calls[:-1]) or
            staged['exception'] != calls[-1]['exception']):
        raise ValueError('Failed-start call/exception history mismatch')
    expected_attempts = []
    for a in range(1 + (len(calls) > 2)):
        group = [c for c in calls if c['attempt_index'] == a]
        expected_attempts.append({
            'tier': 'controller_not_returned',
            'stage_call_indices': [c['call_index'] for c in group],
            'state': ('interrupted' if any(c['exception'] for c in group)
                      or len(group) < 2 else 'completed_unclassified')})
    if staged['attempts'] != expected_attempts:
        raise ValueError('Failed-start attempts mismatch')

    coarse = SampledEpigraph(circuit, plan['grids']['coarse']['points_per_interval'])
    fine = SampledEpigraph(circuit, plan['grids']['fine']['points_per_interval'])
    index = 0

    class ExpectedAbort(Exception):
        pass

    def replay(problem, vector, maxiter, target):
        nonlocal index
        if index >= len(calls):
            raise ValueError('Unexpected v2 stage call')
        call = calls[index]
        name = 'coarse' if problem is coarse else 'fine'
        if (target is not None or
                call['call_index'] != index or
                call['attempt_index'] != (0 if index < 2 else 1) or
                call['stage'] != name or
                call['grid'] != _grid(problem) or
                call['maxiter'] != maxiter or
                call['warm_start_source'] !=
                    ('seed' if index == 0 else f'stage_call_{index-1}') or
                call['input_vector'] != vector.tolist() or
                call['input_vector_sha256'] != vector_fingerprint(vector)):
            raise ValueError('Failed-start stage input/budget/grid mismatch')
        index += 1
        if index == len(calls):
            raise ExpectedAbort()
        status = call['status']
        output = np.asarray(call['output_vector'], dtype=float)
        if (output.shape != vector.shape or not np.all(np.isfinite(output)) or
                not isinstance(status, dict) or
                type(status.get('success')) is not bool or
                type(status.get('status')) is not int or
                status['success'] != (status['status'] == 0) or
                not isinstance(status.get('message'), str) or
                any(type(status.get(k)) is not int or status[k] < 0 for k in ('nit', 'nfev')) or
                call['exit_cause'] !=
                    ('success' if status['success'] else f"status_{status['status']}") or
                call['observation'] != _observe(problem, output)):
            raise ValueError('Failed-start preceding stage mismatch')
        return output, {**status, 'converged': status['success'], 'stage_call_index': index - 1}

    try:
        run_termination_aware_slsqp(
            coarse, fine, np.asarray(staged['seed']['vector'], dtype=float),
            None, replay, budget=STANDARD_SLSQP_BUDGET)
    except ExpectedAbort:
        if index != len(calls):
            raise ValueError('Incomplete failed-start stage replay')
    else:
        raise ValueError('Failed start did not terminate at recorded stage')


def run_synthetic(circuit, envelope, checkpoint, *, optimize_stage, max_new_starts=None):
    """Execute an explicit mock callback; checkpoint only under system temp.

    ``max_new_starts`` allows a clean stop at a start boundary. It does not
    alter any v2 budget. A durable in-progress marker precedes each call.
    """
    if not callable(optimize_stage) or optimize_stage is scipy_slsqp_stage:
        raise ValueError('Explicit synthetic mock optimizer required')
    if max_new_starts is not None and (type(max_new_starts) is not int or max_new_starts < 0):
        raise ValueError('Invalid boundary stop count')
    path = Path(checkpoint).resolve()
    if not path.is_relative_to(Path(tempfile.gettempdir()).resolve()) or path.is_relative_to(ROOT.resolve()):
        raise ValueError('Checkpoint must be outside the repository in system temp')
    parent = path.parent
    while not parent.exists():
        parent = parent.parent
    probe = subprocess.run(['git', '-C', str(parent), 'rev-parse', '--is-inside-work-tree'],
                           stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
    if probe.returncode == 0 and probe.stdout.strip() == 'true':
        raise ValueError('Checkpoint must not be in any Git worktree')
    plan = _validate_plan(circuit, envelope)
    ids = [s['id'] for s in plan['starts']]
    if path.exists():
        saved = _read(path)
        if (not isinstance(saved, dict) or set(saved) != {'body', 'sha256'} or
                canonical_config_hash(saved['body']) != saved['sha256']):
            raise ValueError('Corrupt checkpoint')
        body = saved['body']
        if (set(body) != {'schema', 'plan_fingerprint', 'completed', 'in_progress', 'not_started'} or
                body['schema'] != 'synthetic-checkpoint-v1' or
                body['plan_fingerprint'] != envelope['fingerprint'] or
                not isinstance(body['completed'], list) or
                body['not_started'] != len(ids) - len(body['completed']) - (body['in_progress'] is not None)):
            raise ValueError('Checkpoint metadata mismatch')
        completed = body['completed']
        if len(completed) > len(ids) or [r['candidate_id'] for r in completed] != ids[:len(completed)]:
            raise ValueError('Checkpoint start order mismatch')
        for index, record in enumerate(completed):
            checked = recheck_record(CandidateRecord.from_json(json.dumps(record, allow_nan=False))).as_dict()
            _recheck_failed_calls(circuit, plan, checked)
            if (checked['seed_record'] != plan['starts'][index]['seed_record'] or
                    checked['source_provenance']['value'] != _provenance(plan) or
                    checked['staged_record']['grids'] != plan['grids'] or
                    checked['staged_record']['budget'] != plan['budget']):
                raise ValueError('Checkpoint candidate does not match plan')
        if body['in_progress'] is not None:
            if len(completed) >= len(ids) or body['in_progress'] != ids[len(completed)]:
                raise ValueError('Invalid in-progress start')
            raise ValueError('Start execution outcome unknown; automatic retry prohibited: ' + body['in_progress'])
    else:
        body = {'schema': 'synthetic-checkpoint-v1', 'plan_fingerprint': envelope['fingerprint'],
                'completed': [], 'in_progress': None, 'not_started': len(ids)}
        _write(path, body)
    count = 0
    while len(body['completed']) < len(ids) and (max_new_starts is None or count < max_new_starts):
        i = len(body['completed'])
        start = plan['starts'][i]
        body['in_progress'] = start['id']
        body['not_started'] = len(ids) - i - 1
        _write(path, body)
        staged = run_c1_staged(circuit, start['seed_record'],
            coarse_points=plan['grids']['coarse']['points_per_interval'],
            fine_points=plan['grids']['fine']['points_per_interval'],
            optimize_stage=optimize_stage, source_provenance=_provenance(plan))
        vector = (start['seed_record']['vector'][:-1] if staged['numerical_state'] == 'failed'
                  else staged['stage_calls'][-1]['output_vector'][:-1])
        candidate = record_candidate(start['id'], circuit, vector, staged_record=staged,
                                     source_provenance=_provenance(plan))
        # Catch source changes during execution before making the result durable.
        _validate_plan(circuit, envelope)
        body['completed'].append(candidate.as_dict())
        body['in_progress'] = None
        _write(path, body)
        count += 1
    return body


def _provenance(plan):
    return {'kind': 'synthetic', 'optimizer_kind': 'synthetic_callback',
            'git_head': plan['source']['git_head'],
            'dirty_patch_sha256': plan['source']['dirty_patch_sha256'],
            'input_source_sha256': plan['input_source_sha256']}

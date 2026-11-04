"""Finite-budget Sobol -> Hybrid(sum) -> SLP(signed_max) pipeline.

This is a numerical helper, not an RF adapter or a global-optimality claim.
Callback counts are actual invocations, including finite differences and invalid
returns. Caller exceptions propagate; invalid callback values are recorded.
"""
from dataclasses import asdict

import numpy as np
from scipy.stats import qmc

from .hybrid import hybrid_minimize
from .slp import slp_minimize


class _InvalidValue(Exception):
    pass


def minimize_pipeline(residuals, errors, bounds, *, seed, sobol_m, max_evaluations,
                      hybrid_max_evaluations, hybrid_maxiter, hybrid_max_restarts,
                      restart_sigma, slp_max_evaluations, slp_max_iterations,
                      max_slp_candidates, starts=(), constraints=None, weights=None,
                      duplicate_tolerance=1e-9, constraint_tolerance=1e-7,
                      evaluation_hook=None):
    """Run a bounded, serial pipeline; both callbacks' meanings belong to caller.

    Explicit starts precede the 2**sobol_m Sobol points. Duplicates use Euclidean
    distance in normalized free coordinates. Each hybrid's best evaluated point,
    local endpoints and original start form the candidate pool; endpoints and
    best can be unconverged. Selection scores every distinct candidate it can
    afford: feasible first, then violation, then signed maximum. The first SLP
    candidate is best by that ordering; subsequent candidates prefer feasibility,
    then normalized distance from the selected set, then score. Unscored points
    cannot be selected. SLP is attempted only with enough budget for its initial
    evaluation. No hidden reevaluation is performed after SLP: its result already
    contains the evaluated signed score and violation.

    The result is a dict containing starts, candidates, stage records, selection,
    best and actual counts by stage/callback. A best point need not be converged.
    Individual solver caps are per start/candidate; the total is shared across all
    callbacks. An optional evaluation_hook(stage, kind) runs immediately before
    each callback; exceptions propagate and it must not evaluate the objective.
    A selection interrupted by the budget retains partial records.
    """
    box = np.asarray(bounds, dtype=float)
    if box.ndim != 2 or box.shape[1] != 2 or not len(box) or not np.all(np.isfinite(box)):
        raise ValueError('bounds must be finite (n, 2) pairs')
    lo, hi = box[:, 0], box[:, 1]
    with np.errstate(over='ignore', invalid='ignore'):
        width = hi - lo
    if np.any(width < 0) or not np.all(np.isfinite(width)):
        raise ValueError('bounds must be ordered with finite widths')
    for name, value, minimum in (('seed', seed, 0), ('sobol_m', sobol_m, 0),
                                 ('max_evaluations', max_evaluations, 0),
                                 ('hybrid_max_evaluations', hybrid_max_evaluations, 1),
                                 ('hybrid_maxiter', hybrid_maxiter, 1),
                                 ('hybrid_max_restarts', hybrid_max_restarts, 0),
                                 ('slp_max_evaluations', slp_max_evaluations, 1),
                                 ('slp_max_iterations', slp_max_iterations, 1),
                                 ('max_slp_candidates', max_slp_candidates, 1)):
        if type(value) is not int or value < minimum:
            raise ValueError(f'{name} must be an integer >= {minimum}')
    if not callable(residuals) or not callable(errors) or (constraints is not None and not callable(constraints)):
        raise ValueError('callbacks must be callable')
    if evaluation_hook is not None and not callable(evaluation_hook):
        raise ValueError('evaluation_hook must be callable')
    if not np.isfinite(duplicate_tolerance) or duplicate_tolerance < 0:
        raise ValueError('duplicate_tolerance must be finite and nonnegative')
    if not np.isfinite(constraint_tolerance) or constraint_tolerance <= 0:
        raise ValueError('constraint_tolerance must be finite and positive')
    if not np.isfinite(restart_sigma) or restart_sigma <= 0:
        raise ValueError('restart_sigma must be finite and positive')
    free = width > 0
    counts = {s: {'residuals': 0, 'errors': 0, 'constraints': 0}
              for s in ('hybrid', 'selection', 'slp')}
    sizes = {'errors': None, 'constraints': None}

    def total():
        return sum(sum(c.values()) for c in counts.values())

    def call(stage, kind, fun, x):
        # Solver caps and the selection guard ensure no call reaches this at cap.
        if total() >= max_evaluations:
            raise RuntimeError('internal budget guard')
        if evaluation_hook is not None:
            evaluation_hook(stage, kind)
        counts[stage][kind] += 1
        raw = fun(np.asarray(x).copy())
        if kind == 'residuals':
            return raw  # Hybrid owns residual validation, including weights.
        try:
            a = np.asarray(raw, dtype=float)
        except (TypeError, ValueError):
            raise _InvalidValue(f'invalid_{kind}') from None
        if (a.ndim != 1 or (kind == 'errors' and not a.size) or
                not np.all(np.isfinite(a)) or
                (sizes[kind] is not None and a.size != sizes[kind])):
            raise _InvalidValue(f'invalid_{kind}')
        sizes[kind] = a.size
        return a

    def distance(a, b):
        return float(np.linalg.norm((np.asarray(a)[free] - np.asarray(b)[free]) / width[free]))

    def valid_x(x):
        x = np.asarray(x, dtype=float)
        return (x.shape == lo.shape and np.all(np.isfinite(x)) and
                np.all(x >= lo) and np.all(x <= hi))

    start_records = []
    def add_start(x, source, index):
        x = np.asarray(x, dtype=float)
        if not valid_x(x):
            raise ValueError('explicit start outside finite bounds or wrong shape')
        duplicate = next((i for i, r in enumerate(start_records)
                          if r['duplicate_of'] is None and distance(x, r['x']) <= duplicate_tolerance), None)
        start_records.append({'x': x.tolist(), 'source': source, 'sobol_index': index,
                              'duplicate_of': duplicate, 'hybrid': None,
                              'hybrid_state': 'duplicate' if duplicate is not None else 'not_run'})

    for x in starts:
        add_start(x, 'explicit', None)
    # Sobol has no zero-dimensional engine; an all-fixed box yields repeated points.
    samples = (qmc.Sobol(d=int(free.sum()), scramble=True, seed=seed).random_base2(sobol_m)
               if np.any(free) else np.empty((2 ** sobol_m, 0)))
    for i, z in enumerate(samples):
        x = lo.copy()
        x[free] = np.clip(lo[free] + z * width[free], lo[free], hi[free])
        add_start(x, 'sobol', i)

    candidates = []
    def add_candidate(x, source):
        if x is None or not valid_x(x):
            return
        if any(distance(x, c['x']) <= duplicate_tolerance for c in candidates):
            return
        candidates.append({'x': list(x), 'source': source, 'evaluation': None,
                           'evaluation_calls': 0, 'evaluation_state': 'not_run', 'selected': False,
                           'selection_reason': 'not_scored', 'slp': None,
                           'slp_state': 'not_run', 'final': None})

    for i, record in enumerate(start_records):
        if record['duplicate_of'] is not None:
            continue
        add_candidate(record['x'], {'start': i, 'point': 'start'})
        remaining = max_evaluations - total()
        if not remaining:
            record['hybrid_state'] = 'budget_exhausted'
            continue
        h = hybrid_minimize(lambda x: call('hybrid', 'residuals', residuals, x),
                            record['x'], box, seed=seed + i, maxiter=hybrid_maxiter,
                            max_restarts=hybrid_max_restarts,
                            max_evaluations=min(hybrid_max_evaluations, remaining),
                            restart_sigma=restart_sigma, weights=weights, aggregation='sum')
        record['hybrid'] = asdict(h)
        record['hybrid_state'] = 'completed'
        add_candidate(h.best_x, {'start': i, 'point': 'hybrid_best'})
        for j, run in enumerate(h.runs):
            add_candidate(run.end_x, {'start': i, 'point': 'hybrid_endpoint', 'run': j})

    cost = 1 + (constraints is not None)
    for c in candidates:
        if max_evaluations - total() < cost:
            c['evaluation_state'] = 'budget_exhausted'
            continue
        before = total()
        try:
            e = call('selection', 'errors', errors, c['x'])
            g = (call('selection', 'constraints', constraints, c['x'])
                 if constraints is not None else np.empty(0))
            violation = max(0., -float(np.min(g))) if g.size else 0.
            c['evaluation'] = {'x': c['x'], 'signed_max': float(np.max(e)),
                               'max_violation': violation,
                               'feasible': violation <= constraint_tolerance}
            c['evaluation_state'] = 'scored'
            c['final'] = dict(c['evaluation'], origin='before_slp', success=False)
            c['selection_reason'] = 'not_selected'
        except _InvalidValue as exc:
            c['evaluation_state'] = str(exc)
            c['selection_reason'] = 'invalid'
        finally:
            c['evaluation_calls'] = total() - before

    def rank(e):
        return (not e['feasible'], 0. if e['feasible'] else e['max_violation'], e['signed_max'])

    available = [i for i, c in enumerate(candidates) if c['evaluation'] is not None]
    selected = []
    while available and len(selected) < max_slp_candidates:
        if not selected:
            chosen = min(available, key=lambda i: (rank(candidates[i]['evaluation']), i))
            why = 'best_feasibility_then_signed_max'
        else:
            def diverse_key(i):
                e = candidates[i]['evaluation']
                d = min(distance(candidates[i]['x'], candidates[j]['x']) for j in selected)
                return (not e['feasible'], 0. if e['feasible'] else e['max_violation'], -d, e['signed_max'], i)
            chosen = min(available, key=diverse_key)
            why = 'feasibility_then_normalized_diversity_then_signed_max'
        selected.append(chosen)
        available.remove(chosen)
        candidates[chosen]['selected'] = True
        candidates[chosen]['selection_reason'] = why

    for i in selected:
        c = candidates[i]
        remaining = min(slp_max_evaluations, max_evaluations - total())
        if remaining < cost:
            c['slp_state'] = ('budget_exhausted' if max_evaluations - total() < cost
                              else 'slp_budget_insufficient')
            continue
        before = total()
        try:
            s = slp_minimize(lambda x: call('slp', 'errors', errors, x), c['x'], box,
                             constraints=(lambda x: call('slp', 'constraints', constraints, x))
                             if constraints is not None else None,
                             aggregation='signed_max', max_iterations=slp_max_iterations,
                             max_evaluations=remaining, constraint_tolerance=constraint_tolerance)
            after = {'x': s.x.tolist(), 'signed_max': s.objective,
                     'max_violation': s.max_violation, 'feasible': s.feasible,
                     'origin': 'slp', 'success': s.success}
            accepted = rank(after) < rank(c['evaluation'])
            c['slp'] = {'aggregation': s.aggregation, 'result': after,
                        'stage': asdict(s.slp),
                        'score_improved': after['signed_max'] < c['evaluation']['signed_max'],
                        'feasibility_improved': (not c['evaluation']['feasible'] and after['feasible']),
                        'accepted': accepted}
            c['slp_state'] = 'completed'
            if accepted:
                c['final'] = after
        except _InvalidValue as exc:
            c['slp_state'] = str(exc)
            c['slp'] = {'aggregation': 'signed_max', 'evaluations': total() - before,
                        'success': False, 'accepted': False}

    eligible = [c['final'] for c in candidates if c['final'] is not None]
    best = min(eligible, key=rank) if eligible else None
    budget_stopped = (total() >= max_evaluations or
                      any(r['hybrid_state'] == 'budget_exhausted' for r in start_records) or
                      any(c['evaluation_state'] == 'budget_exhausted' or
                          c['slp_state'] == 'budget_exhausted' for c in candidates))
    return {'seed': seed, 'sobol_m': sobol_m, 'starts': start_records,
            'candidates': candidates, 'selected': selected, 'best': best,
            'nfev': total(), 'counts': counts,
            'stop_reason': 'evaluation_budget_exhausted' if budget_stopped else 'completed'}

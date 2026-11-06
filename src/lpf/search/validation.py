"""Common strict finite-grid ranking and explicit independent-validation boundary."""
import numpy as np
from lpf.phase2_models.independent_rf import evaluate_independent_sample


def score(il, role, mandatory):
    il, role = np.asarray(il, float), np.asarray(role)
    if (il.ndim != 1 or il.shape != role.shape or not np.all(np.isfinite(il)) or
            set(role.tolist()) != {0, 1, 2}):
        raise ValueError('Finite IL and all pass/H2/H3 roles required')
    f = float(max(il[role == 0]))
    h2, h3 = (float(min(il[role == r])) for r in (1, 2))
    deficits = [max(0., mandatory - h2), max(0., mandatory - h3)]
    return {'worst_il_db': f, 'min_h2_db': h2, 'min_h3_db': h3,
            'max_violation_db': max(deficits), 'sum_violation_db': sum(deficits),
            'strict_feasible': max(deficits) == 0.}


def rank_key(s):
    return ((0, s['worst_il_db'], 0., 0.) if s['strict_feasible'] else
            (1, s['max_violation_db'], s['sum_violation_db'], s['worst_il_db']))


def select(evaluation, vectors, points, stage, *, on_assessed=None):
    # Fixed best-1 rule: strict RF feasibility, Vmax, Vsum, F; SHA breaks ties.
    from .storage import vector_sha
    unique = {vector_sha(x): x for x in vectors}
    assessed = []
    for digest, x in sorted(unique.items()):
        def completed(il):
            s = score(il, evaluation.grid(points).role, evaluation.mandatory)
            row = {'vector': list(x), 'vector_sha256': digest, 'score': s}
            assessed.append(row)
            if on_assessed is not None:
                on_assessed(row)
        evaluation.forward(x, points, stage, on_completed=completed)
    return sorted(assessed, key=lambda row: (rank_key(row['score']), row['vector_sha256']))


def rank_candidates(candidates):
    """Rank Stage-3 assessed candidates; return invalid/unrun separately.

    Each input has vector, model and assessment (None means unrun). Caller must
    associate the response with that vector; RFResponse does not carry x identity.
    Value legality is rechecked here, without an RF forward. No old score path.
    """
    from .component_constraints import validate_values
    from .storage import vector_sha
    comparable, excluded = [], []
    context = None
    for candidate in candidates:
        row = dict(candidate)
        assessment = row.get('assessment')
        if assessment is None or assessment.get('status') != 'evaluated':
            excluded.append({**row, 'status': 'unrun' if assessment is None else 'not_evaluated'})
            continue
        model = row['model']
        if (assessment['policy_id'], assessment['policy_fingerprint']) != (model.policy_id, model.policy_fingerprint):
            raise ValueError('Candidate model/assessment policy mismatch')
        signature = tuple(assessment[k] for k in ('policy_id', 'policy_fingerprint', 'mode',
                         'grid_fingerprint', 'requirements_fingerprint'))
        if context is not None and signature != context:
            raise ValueError('Cannot compare different policy/mode/grid/requirements')
        context = signature
        try:
            validate_values(model.definition, model.schema, row['vector'], model.resolved_policy)
            digest = vector_sha(row['vector'])
        except ValueError as exc:
            excluded.append({**row, 'status': 'invalid', 'reason': str(exc)})
            continue
        if (row.get('vector_sha256', digest) != digest or
                row.get('grid_sha256', assessment['grid_fingerprint']) != assessment['grid_fingerprint']):
            raise ValueError('Candidate vector/grid identity mismatch')
        a = assessment
        if a['strict_feasible']:
            key = (0, a['worst_il_db'], digest)
        else:
            key = (1, a['max_violation_db'], a['sum_violation_db'], a['worst_il_db'], digest)
        comparable.append({**row, 'status': 'pass' if a['strict_feasible'] else 'fail',
                           'vector_sha256': digest, 'rank_key': key})
    return {'ranked': sorted(comparable, key=lambda row: row['rank_key']), 'excluded': excluded}


def pending():
    return {'dense1001': 'not_run', 'independent_mna': 'not_run',
            'passivity': 'not_run', 'power_balance': 'not_run',
            'candidate_promotion_blocked': True}


def dense_candidate(evaluation, candidate):
    """Explicit selected-candidate API; caller owns separate validation budget."""
    if candidate is None or not candidate['score']['strict_feasible']:
        return {'status': 'not_run', 'reason': 'no_strict_candidate'}
    rows = select(evaluation, [candidate['vector']], 1001, 'dense1001')
    return {**pending(), 'status': 'completed', 'dense1001': 'completed',
            'candidate': rows[0]}


def independent_sample(circuit, vector, frequency_hz, setting):
    """Raw independent MNA/power evidence, NOT an aggregate acceptance gate."""
    circuit.validate_components(vector)
    return evaluate_independent_sample(circuit, vector, frequency_hz, setting)

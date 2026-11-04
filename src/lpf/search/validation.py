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


def select(evaluation, vectors, points, stage):
    # Fixed best-1 rule: strict RF feasibility, Vmax, Vsum, F; SHA breaks ties.
    from .storage import vector_sha
    unique = {vector_sha(x): x for x in vectors}
    assessed = []
    for digest, x in sorted(unique.items()):
        il = evaluation.forward(x, points, stage)
        s = score(il, evaluation.grid(points).role, evaluation.mandatory)
        assessed.append({'vector': list(x), 'vector_sha256': digest, 'score': s})
    return sorted(assessed, key=lambda row: (rank_key(row['score']), row['vector_sha256']))


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

"""Strict finite-grid ranking for assessed schema2 candidates."""
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

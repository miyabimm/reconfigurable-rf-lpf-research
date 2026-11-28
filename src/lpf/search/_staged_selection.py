"""Pure selection and reproducibility decisions for staged development runs.

Inputs must already have been checked against phase receipts and the frozen grid.
These functions do not run RF or certify continuous-band compliance.
"""
import math

import numpy as np


def rank_candidates(candidates):
    """Rank on a common Terminal grid, with deterministic seed tie-breaking."""
    def key(row):
        margins = np.asarray(row['terminal_margins'], dtype=float)
        if margins.ndim != 1 or not margins.size or not np.all(np.isfinite(margins)):
            raise ValueError('Invalid Terminal signed margins')
        seed = row['seed']
        if type(seed) is not int or seed < 0:
            raise ValueError('Invalid original seed')
        return (float(np.max(margins)), float(np.dot(np.maximum(margins, 0),
                                                      np.maximum(margins, 0))), seed)
    if len({r['seed'] for r in candidates}) != len(candidates):
        raise ValueError('Duplicate original seed')
    if len({r['terminal_grid_sha256'] for r in candidates}) > 1:
        raise ValueError('Cannot rank different Terminal grids')
    return sorted(candidates, key=key)


def select_discovery(candidates, *, target_objective, terminal_max_margin, count):
    """Never fill unused slots with candidates which failed either threshold."""
    if (type(count) is not int or count < 1 or type(target_objective) not in (int, float)
            or not math.isfinite(target_objective) or target_objective < 0
            or type(terminal_max_margin) not in (int, float) or not math.isfinite(terminal_max_margin)):
        raise ValueError('Invalid discovery selection settings')
    if any(type(r['search_objective']) not in (int, float) or not math.isfinite(r['search_objective'])
           or r['search_objective'] < 0 for r in candidates):
        raise ValueError('Invalid saved Search objective')
    return [r for r in rank_candidates(candidates)
            if r['search_objective'] <= target_objective
            and max(r['terminal_margins']) <= terminal_max_margin][:count]


def assess_reproducibility(candidates, bounds, *, tolerances, required_seeds):
    """Compare numerical convergence and performance against Terminal rank 1."""
    ranked = rank_candidates(candidates)
    if not ranked:
        raise ValueError('No refinement candidates')
    metrics = ('search_objective', 'worst_il_db', 'min_h2_db', 'min_h3_db')
    if (set(tolerances) != set(metrics) or any(type(tolerances[k]) not in (int, float)
            or not math.isfinite(tolerances[k]) or tolerances[k] < 0 for k in metrics)
            or type(required_seeds) is not int or required_seeds < 1):
        raise ValueError('Invalid reproducibility tolerances or seed count')
    box = np.asarray(bounds, dtype=float)
    if box.ndim != 2 or box.shape[1] != 2 or not np.all(np.isfinite(box)) or np.any(box[:, 1] < box[:, 0]):
        raise ValueError('Invalid search bounds')
    free = box[:, 1] > box[:, 0]
    ref = ranked[0]
    ref_vector = np.asarray(ref['vector'], dtype=float)
    def validate(row):
        x = np.asarray(row['vector'], dtype=float)
        if (x.shape != (len(box),) or not np.all(np.isfinite(x)) or np.any(x < box[:, 0])
                or np.any(x > box[:, 1]) or type(row['converged']) is not bool
                or any(type(row[k]) not in (int, float) or not math.isfinite(row[k]) for k in metrics)):
            raise ValueError('Invalid refinement candidate')
        return x
    validate(ref)
    comparisons = []
    for row in ranked:
        x = validate(row)
        delta = (x[free] - ref_vector[free]) / (box[free, 1] - box[free, 0])
        matches = (ref['converged'] and row['converged'] and
                   all(abs(row[k] - ref[k]) <= tolerances[k] for k in metrics))
        comparisons.append(dict(seed=row['seed'], matches=matches,
                                vector_distance_max=float(np.max(np.abs(delta))) if delta.size else 0.,
                                vector_distance_rms=float(np.sqrt(np.mean(delta**2))) if delta.size else 0.))
    matched = [r['seed'] for r in comparisons if r['matches']]
    return dict(reference_seed=ref['seed'], converged=ref['converged'], matching_seeds=matched,
                required_seeds=required_seeds, reproducible=len(matched) >= required_seeds,
                comparisons=comparisons, finite_grid_only=True, rf_compliance_certified=False)

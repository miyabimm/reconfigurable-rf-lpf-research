"""One scrambled Sobol point per seed, without repair, retry or RF forward."""
import numpy as np
from scipy.stats import qmc

from .component_constraints import physical_bounds, validate_search_box, validate_values
from .storage import vector_sha


def physical_box(circuit):
    return physical_bounds(circuit.definition, circuit.schema, circuit.resolved_policy)


def validate(circuit, vector, bounds):
    x = np.asarray(vector, float)
    box = np.asarray(bounds, float)
    hard = physical_box(circuit)
    validate_search_box(box, hard)
    if (x.shape != (len(box),) or not np.all(np.isfinite(x)) or
            np.any(x < box[:, 0]) or np.any(x > box[:, 1])):
        raise ValueError('Illegal physical vector: shape/finite/closed box')
    report = validate_values(circuit.definition, circuit.schema, vector, circuit.resolved_policy)
    if not report['component_policy_pass'] or report['connection_role_evidence_incomplete']:
        raise ValueError('Illegal components/SPD/connection role')
    return x


class IllegalStart(ValueError):
    def __init__(self, record, cause):
        self.record = {**record, 'status': 'failed', 'reason': str(cause)}
        super().__init__(f'Illegal Sobol point; STOP without retry: {cause}')


def generate(circuit, seed, bounds=None):
    hard = physical_box(circuit)
    bounds = hard if bounds is None else bounds
    box = np.asarray(bounds)
    free = box[:, 1] > box[:, 0]
    x = box[:, 0].copy()
    if np.any(free):
        z = qmc.Sobol(int(sum(free)), scramble=True, seed=seed).random_base2(0)[0]
        x[free] += z * (box[free, 1] - box[free, 0])
    record = {'seed': seed, 'method': 'scrambled_sobol_single_point', 'sobol_index': 0,
              'vector': x.tolist(), 'vector_sha256': vector_sha(x)}
    try:
        validate(circuit, x, bounds)
    except ValueError as exc:
        raise IllegalStart(record, exc) from exc
    return {**record, 'status': 'legal'}

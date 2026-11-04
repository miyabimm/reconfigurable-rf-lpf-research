"""One scrambled Sobol point per seed, without repair, retry or RF forward."""
import numpy as np
from scipy.stats import qmc

from lpf.phase2_models.nominal_inductors import nominal_inductor_series
from .storage import vector_sha


def physical_box(circuit):
    # Policy-derived physical bounds, migrated from problem_seed.circuit_box.
    d, p = circuit.definition, circuit.resolved_policy
    bounds, opened = [], []

    def add(lo, hi, strict=False):
        if strict:
            opened.append(len(bounds))
        bounds.append((float(lo), float(hi)))

    for kind in d.inductor_types:
        _, lo, hi = nominal_inductor_series(p, kind)
        add(lo, hi, kind == 'PCB_L')
    for kind, edge in zip(d.fixed_c_types, d.capacitor_placement.fixed_edges):
        if kind == 'GJM01':
            add(0, p['components']['GJM01']['max_pf_per_component'], True)
        else:
            spec = p['trial_pcb_pattern_c_by_connection']['grounded' if -1 in edge else 'non_ground']
            add(spec['min_pf_per_component'], spec['max_pf_per_component'])
    limits = p['coupling_limits']
    adjacent = {frozenset(pair) for pair in zip(d.physical_order, d.physical_order[1:])}
    for a, b in d.coupling_pairs:
        ta, tb = d.inductor_types[a], d.inductor_types[b]
        if ta == tb == 'PCB_L':
            limit = limits['pcb_pcb_abs_k_max_default']
        elif 'PCB_L' in (ta, tb):
            limit = limits['chip_pcb_abs_k_max']
        elif frozenset((a, b)) in adjacent:
            limit = limits['chip_chip_strong_adjacent_abs_k_max']
        else:
            limit = 0.
        add(-limit, limit)
    spec = p['trial_ic_fixed_c_by_connection']
    for edge in d.capacitor_placement.ic_fixed_edges:
        rule = spec['grounded' if -1 in edge else 'non_ground']
        add(rule['min_pf_per_branch'], rule['max_pf_per_branch'])
    for _ in range(6 * circuit.schema.n_variable):
        add(*spec['variable_capacitance_pf_range'])
    if len(bounds) != circuit.schema.vector_length:
        raise ValueError('Incomplete physical box')
    return tuple(bounds), tuple(opened)


def validate(circuit, vector, bounds, opened):
    x = np.asarray(vector, float)
    box = np.asarray(bounds, float)
    hard, hard_open = physical_box(circuit)
    hard = np.asarray(hard)
    if (box.shape != hard.shape or not np.all(np.isfinite(box)) or
            np.any(box[:, 0] < hard[:, 0]) or np.any(box[:, 1] > hard[:, 1]) or
            np.any(box[:, 0] > box[:, 1]) or tuple(opened) != hard_open):
        raise ValueError('Search box must be a physical sub-box with unchanged open endpoints')
    if (x.shape != (len(box),) or not np.all(np.isfinite(x)) or
            np.any(x < box[:, 0]) or np.any(x > box[:, 1]) or
            any(x[i] <= hard[i, 0] for i in opened)):
        raise ValueError('Illegal physical vector: shape/finite/box/open endpoint')
    report = circuit.validate_components(x)
    if not report['component_policy_pass'] or report['connection_role_evidence_incomplete']:
        raise ValueError('Illegal components/SPD/connection role')
    return x


# Fixed existing development input from tests/test_phase2_problem_seed.py make(T008, 4).
# Not a candidate, a generated seed, or a production initialization policy.
DEVELOPMENT_DEFINITION_SHA = 'bef3173906b3674bbe116083782dede8ccdffb56e8fc906c613e2bde451cff2d'
DEVELOPMENT_VECTOR = (2., 2., 2., 2., 1., .1, .02, -.03, .01, .5, .2) + (0., 3.) * 6


def development_start(circuit, seed, bounds, opened):
    x = list(DEVELOPMENT_VECTOR)
    record = {'seed': seed, 'method': 'fixed_existing_4L_development_fixture',
              'source': 'tests/test_phase2_problem_seed.py:make(RF-T008,4)',
              'vector': x, 'vector_sha256': vector_sha(x)}
    try:
        validate(circuit, x, bounds, opened)
    except ValueError as exc:
        raise IllegalStart(record, exc) from exc
    return {**record, 'status': 'legal'}


class IllegalStart(ValueError):
    def __init__(self, record, cause):
        self.record = {**record, 'status': 'failed', 'reason': str(cause)}
        super().__init__(f'Illegal Sobol point; STOP without retry: {cause}')


def generate(circuit, seed, bounds=None):
    hard, opened = physical_box(circuit)
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
        validate(circuit, x, bounds, opened)
    except ValueError as exc:
        raise IllegalStart(record, exc) from exc
    return {**record, 'status': 'legal'}

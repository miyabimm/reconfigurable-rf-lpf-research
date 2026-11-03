"""Opt-in adapter connecting frequency exchange to the existing C1/v2 path.

Not an experiment runner: callers must supply durable sinks and G0/G1 gates.
The exchange scan is not independent final validation.
"""
import numpy as np

from .frequency_exchange import run_frequency_exchange
from .staged_optimization import run_c1_staged, scipy_slsqp_stage, _check_guard_source
from .sampled_epigraph import SEARCH_GUARD_DB


def run_c1_frequency_exchange(circuit, seed_record, *, cost_meter,
                              optimize_stage=scipy_slsqp_stage, source_provenance=None,
                              exchange_sink=None, stage_sink=None,
                              scan_points=17, max_additions=4, max_rounds=3,
                              search_guard=False, warm_start_vector=None):
    """Use unchanged v2 for each exchange round, preserving the physical x and t."""
    if type(search_guard) is not bool:
        raise TypeError('search_guard must be bool')
    if search_guard:
        _check_guard_source(source_provenance)
    mandatory = float(circuit.resolved_policy['evaluation']['full_phase2']['minimum_h2_h3_db'])
    evaluator = circuit.forward_evaluator(scan_points)
    segments = []
    for segment in sorted(set(evaluator.segment.tolist())):
        idx = np.flatnonzero(evaluator.segment == segment)
        if len(set(evaluator.role[idx].tolist())) != 1:
            raise ValueError('Inconsistent scan segment role')
        segments.append((int(segment), int(evaluator.role[idx[0]]),
                         float(evaluator.f[idx[0]]), float(evaluator.f[idx[-1]])))
    expected = tuple((int(s), float(f)) for s, f in zip(evaluator.segment, evaluator.f))
    first = True

    def inner(c, vector, extras, meter):
        nonlocal first
        record = run_c1_staged(c, seed_record, coarse_points=2, fine_points=3,
            optimize_stage=optimize_stage, cost_meter=meter,
            source_provenance=source_provenance, record_sink=stage_sink,
            extra_frequencies=extras,
            warm_start_vector=(None if first and warm_start_vector is None else vector),
            search_guard=search_guard)
        first = False
        if record['numerical_state'] not in ('converged', 'not_converged'):
            return vector, record
        calls = record['stage_calls']
        if not calls or calls[-1]['output_vector'] is None:
            raise ValueError('Missing final stage vector')
        if warm_start_vector is not None:
            observation = calls[-1]['observation']
            component = observation['component_policy']
            detail = component.get('detail', {})
            if (observation['box']['state'] != 'pass' or component['state'] != 'pass' or
                    detail.get('component_policy_pass') is False or
                    detail.get('connection_role_evidence_incomplete') is True):
                raise ValueError('Final exchange returned an illegal physical vector')
        return calls[-1]['output_vector'], record

    def scan(c, physical, points, meter):
        if points != expected:
            raise ValueError('Exchange scan grid mismatch')
        with meter.timed():
            return meter.forward(evaluator, physical)

    initial = seed_record['vector'] if warm_start_vector is None else warm_start_vector
    return run_frequency_exchange(circuit, initial, segments,
        inner=inner, scan=scan, cost_meter=cost_meter, scan_points=scan_points,
        max_additions=max_additions, max_rounds=max_rounds,
        stop_db=mandatory + (SEARCH_GUARD_DB if search_guard else 0.0),
        mandatory_stop_db=mandatory,
        record_sink=exchange_sink)

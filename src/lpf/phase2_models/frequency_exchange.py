"""Opt-in finite-grid frequency exchange; no RF solver or experiment runner.

Callbacks must use the supplied shared meter for every forward. Scan values are
external-port IL/attenuation in the exact requested point order. This controller
is not independent final validation and cannot certify RF compliance.
"""
from copy import deepcopy
import math

import numpy as np

from .evaluation_cost import SampleBudgetCost, SampleBudgetExceeded


class FrequencyExchangeError(RuntimeError):
    """Callback or input failure, with the partial trace retained for inspection."""
    def __init__(self, message, trace):
        super().__init__(message)
        self.trace = deepcopy(trace)


def run_frequency_exchange(circuit, initial, segments, *, inner, scan, cost_meter,
                           coarse_points=2, fine_points=3, scan_points=17,
                           max_additions=4, max_rounds=3, stop_db=30., record_sink=None):
    """Run callback-driven exchange. No retries; all coordinates remain physical.

    segments: iterable of (integer ID, role 0/1/2, low MHz, high MHz).
    inner(circuit, vector, extras, meter) returns (full vector incl. t, trace).
    scan(circuit, physical_vector, [(segment_id, frequency), ...], meter) returns
    one finite IL/attenuation value per point, preserving order. Both callbacks
    are responsible for charging their actual RF requests to the shared meter.
    """
    if not isinstance(cost_meter, SampleBudgetCost):
        raise TypeError('A shared SampleBudgetCost is required')
    if not callable(inner) or not callable(scan):
        raise TypeError('inner and scan must be callable')
    for name, value, minimum in (('coarse_points', coarse_points, 2),
                                  ('fine_points', fine_points, 2),
                                  ('scan_points', scan_points, 2),
                                  ('max_additions', max_additions, 1),
                                  ('max_rounds', max_rounds, 1)):
        if type(value) is not int or value < minimum:
            raise ValueError(f'Invalid {name}')
    if not math.isfinite(stop_db):
        raise ValueError('Invalid stopband threshold')
    metadata = {}
    for seg, role, low, high in segments:
        if (type(seg) is not int or seg < 0 or seg in metadata or
                type(role) is not int or role not in (0, 1, 2) or
                not np.isfinite(low) or not np.isfinite(high) or not 0 < low < high):
            raise ValueError('Invalid or duplicate segment metadata')
        metadata[seg] = (role, float(low), float(high))
    if not metadata or {v[0] for v in metadata.values()} != {0, 1, 2}:
        raise ValueError('Pass, H2 and H3 segments required')
    points = [(seg, float(f)) for seg, (_, lo, hi) in sorted(metadata.items())
              for f in np.linspace(lo, hi, scan_points)]
    working = {(seg, float(f)) for seg, (_, lo, hi) in metadata.items()
               for count in (coarse_points, fine_points) for f in np.linspace(lo, hi, count)}
    vector = np.asarray(initial, dtype=float)
    if vector.ndim != 1 or len(vector) < 2 or not np.all(np.isfinite(vector)):
        raise ValueError('Complete finite physical vector and t required')
    circuit.validate_components(vector[:-1])
    trace = {'rounds': [], 'added_frequencies': [], 'stop_reason': None,
             'rf_compliance_certified': False, 'final_validation': 'not_run'}

    def persist():
        trace['evaluation_cost'] = cost_meter.snapshot()
        if record_sink is not None:
            record_sink(deepcopy(trace))

    def measure(v):
        values = np.asarray(scan(circuit, v[:-1].copy(), tuple(points), cost_meter), dtype=float)
        if values.shape != (len(points),) or not np.all(np.isfinite(values)):
            raise ValueError('Scan must return one finite value per requested point')
        roles = np.asarray([metadata[seg][0] for seg, _ in points])
        violations = np.where(roles == 0, values - v[-1], stop_db - values)
        return values, roles, violations

    try:
        persist()
        initial_values, initial_roles, _ = measure(vector)
        baseline = float(np.max(initial_values[initial_roles == 0]))
        trace['initial_worst_il_db'] = baseline
        trace['initial_scan_strict30'] = bool(np.all(initial_values[initial_roles != 0] >= stop_db))
        trace['first_strict_scan'] = ({'round': 0, 'evaluation_cost': cost_meter.snapshot()}
                                      if trace['initial_scan_strict30'] else None)
        persist()
        extras = []
        for round_index in range(max_rounds):
            row = {'round': round_index + 1, 'input_vector': vector.tolist(),
                   'working_extras': [list(p) for p in extras], 'state': 'running'}
            trace['rounds'].append(row)
            persist()
            output, inner_trace = inner(circuit, vector.copy(), tuple(extras), cost_meter)
            output = np.asarray(output, dtype=float)
            if output.shape != vector.shape or not np.all(np.isfinite(output)):
                raise ValueError('Inner optimizer returned invalid vector')
            row['inner'] = inner_trace
            if not isinstance(inner_trace, dict) or inner_trace.get('numerical_state') not in (
                    'converged', 'not_converged', 'budget_exhausted'):
                raise ValueError('Inner optimizer did not complete successfully')
            if inner_trace['numerical_state'] == 'budget_exhausted':
                raise SampleBudgetExceeded('Inner optimizer exhausted shared budget')
            vector = output.copy()
            row['output_vector'] = vector.tolist()
            persist()
            values, roles, violations = measure(vector)
            worst_il = float(np.max(values[roles == 0]))
            ranked = sorted(((float(violations[i]), *points[i]) for i in range(len(points))
                             if violations[i] > 0), key=lambda p: (-p[0], p[1], p[2]))
            new = [p for p in ranked if (p[1], p[2]) not in working]
            row.update(state='scanned', worst_il_db=worst_il,
                       min_h2_db=float(np.min(values[roles == 1])),
                       min_h3_db=float(np.min(values[roles == 2])),
                       delta_il_db=worst_il - baseline,
                       low_il_maintained=bool(worst_il - baseline <= 0.05),
                       scan_strict30=bool(np.all(values[roles != 0] >= stop_db)),
                       max_violation_db=ranked[0][0] if ranked else 0.,
                       worst_violation=list(ranked[0]) if ranked else None,
                       positive_violations=[list(p) for p in ranked], selected=[])
            row['evaluation_cost_after_scan'] = cost_meter.snapshot()
            if row['scan_strict30'] and trace['first_strict_scan'] is None:
                trace['first_strict_scan'] = {'round': round_index + 1,
                                              'evaluation_cost': cost_meter.snapshot()}
            if not ranked:
                trace['stop_reason'] = 'scan_no_new_violation'
            elif not new:
                trace['stop_reason'] = 'stalled_existing_constraint'
            elif round_index + 1 == max_rounds:
                trace['stop_reason'] = 'max_rounds'
            else:
                selected = [(seg, f) for _, seg, f in new[:max_additions]]
                row['selected'] = [list(p) for p in selected]
                extras.extend(selected)
                working.update(selected)
                trace['added_frequencies'] = [list(p) for p in extras]
            persist()
            if trace['stop_reason']:
                break
    except SampleBudgetExceeded:
        trace['stop_reason'] = 'budget_exhausted'
        persist()
    except Exception as exc:
        trace['stop_reason'] = 'failed'
        trace['exception'] = {'type': type(exc).__name__, 'message': str(exc)}
        persist()
        raise FrequencyExchangeError(str(exc), trace) from exc
    trace['final_vector'] = vector.tolist()
    persist()
    return trace

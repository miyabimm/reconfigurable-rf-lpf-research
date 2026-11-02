"""Explicit, candidate-bound post-search finite-grid validation.

This is not an experiment runner or a storage/finalization gate. The caller
must persist each sink snapshot under its already approved G0--G4 protocol.
No candidate is automatically selected and no historical evidence is modified.
"""
from copy import deepcopy
from dataclasses import asdict
import csv
import math

import numpy as np

from lpf.constraint_versions import rf_input_file
from ._grid import ROOT, validated_band_segments
from .evaluation_cost import SampleBudgetCost, SampleBudgetExceeded
from .independent_rf import evaluate_independent_sample
from .independent_scan import scan_independent_rf
from .limited_candidate_evidence import _identity
from .problem_seed import circuit_box, definition_fingerprint, vector_fingerprint
from .sampled_epigraph import SEARCH_GUARD_DB


def _grid(circuit, evaluator, points):
    with rf_input_file(ROOT, circuit.resolved_policy['bands_file']).open(newline='', encoding='utf-8') as f:
        segments = validated_band_segments(list(csv.DictReader(f)))
    if len(evaluator.f) != 28 * points:
        raise ValueError('incomplete forward grid')
    for i, (setting, role, low, high) in enumerate(segments):
        sl = slice(i * points, (i + 1) * points)
        if (not np.array_equal(evaluator.segment[sl], np.full(points, i)) or
                not np.array_equal(evaluator.setting[sl], np.full(points, setting)) or
                not np.array_equal(evaluator.role[sl], np.full(points, role)) or
                not np.array_equal(evaluator.f[sl], np.linspace(low, high, points))):
            raise ValueError('forward grid or band assignment mismatch')
    return segments


def _forward(circuit, x, points, meter, mandatory):
    evaluator = circuit.forward_evaluator(points)
    segments = _grid(circuit, evaluator, points)
    with meter.timed():
        values = np.asarray(meter.forward(evaluator, x), float)
    if values.shape != (28 * points,) or not np.all(np.isfinite(values)):
        raise ValueError('nonfinite or incomplete forward values')
    rows = []
    for i, (setting, role, low, high) in enumerate(segments):
        sl = slice(i * points, (i + 1) * points)
        v = values[sl]
        j = int(np.argmax(v) if role == 0 else np.argmin(v))
        rows.append({'segment': i, 'setting': setting, 'role': role,
                     'frequencies_mhz': evaluator.f[sl].tolist(),
                     'worst_frequency_mhz': float(evaluator.f[sl][j]),
                     'worst_il_db': float(v[j]),
                     'mandatory_pass': bool(v[j] >= mandatory) if role else None,
                     'guard_achieved': bool(v[j] >= mandatory + SEARCH_GUARD_DB) if role else None})
    return {'state': 'pass' if all(r['mandatory_pass'] is not False for r in rows) else 'fail',
            'points_per_interval': points, 'segments': rows,
            'mandatory_stop_db': mandatory, 'search_guard_db': SEARCH_GUARD_DB,
            'guard_achieved': all(r['guard_achieved'] is not False for r in rows),
            'worst_pass_il_db': max(r['worst_il_db'] for r in rows if r['role'] == 0),
            'min_h2_db': min(r['worst_il_db'] for r in rows if r['role'] == 1),
            'min_h3_db': min(r['worst_il_db'] for r in rows if r['role'] == 2)}


def _independent(circuit, x, forward_meter, mna_meter):
    evaluator = circuit.forward_evaluator(3)
    _grid(circuit, evaluator, 3)
    with forward_meter.timed():
        reference = np.asarray(forward_meter.forward(evaluator, x), float)
    if reference.shape != (84,) or not np.all(np.isfinite(reference)):
        raise ValueError('independent reference incomplete')
    samples = []
    losses = ('inductor_loss_w', 'capacitor_loss_w', 'input_s2p_loss_w',
              'output_s2p_loss_w', 'load_power_w', 'input_power_w')

    class OneSample:
        f = (0.,)
        def __init__(self, c, v, frequency, setting):
            self.args = c, v, frequency, setting
        def il(self, unused):
            return evaluate_independent_sample(*self.args)

    def execute(c, v, frequency, setting):
        with mna_meter.timed():
            return mna_meter.forward(OneSample(c, v, frequency, setting), None)

    def observe(segment, setting, frequency, result):
        i = len(samples)
        if (i >= 84 or int(evaluator.segment[i]) != segment or
                int(evaluator.setting[i]) != setting or
                not math.isclose(float(evaluator.f[i]) * 1e6, frequency, rel_tol=0, abs_tol=1e-6)):
            raise ValueError('independent grid mismatch')
        numbers = {k: float(result[k]) for k in ('gain', 'il_db', 'power_residual_w', *losses)}
        if not all(math.isfinite(v) for v in numbers.values()) or numbers['gain'] <= 0:
            raise ValueError('independent sample nonfinite')
        if any(numbers[k] < -1e-12 for k in losses) or abs(numbers['power_residual_w']) > 1e-12:
            raise ValueError('independent passivity or power balance failed')
        if abs(numbers['il_db'] - float(reference[i])) > 1e-9:
            raise ValueError('independent forward IL mismatch')
        if abs(numbers['gain'] - 10 ** (-float(reference[i]) / 10)) > 1e-9:
            raise ValueError('independent forward gain mismatch')
        samples.append({'segment': segment, 'setting': setting, 'frequency_hz': frequency,
                        'forward_il_db': float(reference[i]), **numbers})

    scan = scan_independent_rf(circuit, x, points_per_interval=3, coverage='canonical',
                               _sample_observer=observe, _sample_executor=execute)
    if len(samples) != 84 or len(scan['segments']) != 28:
        raise ValueError('independent coverage incomplete')
    return {'state': 'pass', 'samples': samples, 'segments': scan['segments'],
            'summary': scan['summary']['grid_worst'],
            'mna_dimension': circuit.topology.inductor_tree.node_count + len(circuit.topology.inductor_tree.edges),
            'independent_spd': 'checked_by_branch_mna_each_sample',
            'il_tolerance_db': 1e-9, 'gain_absolute_tolerance': 1e-9,
            'power_tolerance_w': 1e-12}


def validate_post_search(circuit, vector, *, optimization_record, source_provenance,
                         budgets, run_dense, run_independent, record_sink):
    """Run one explicitly selected candidate; emit raw and every gate to sink.

    budgets gives separate maximum requested samples for separate17, dense1001,
    independent_forward84 and independent_mna84. Selection of dense/MNA is
    explicit, and a preceding mandatory failure or exception always blocks it.
    The sink must durably preserve snapshots or raise; this function does not
    manipulate EXP manifests, storage records or historical evidence.
    """
    if not callable(record_sink) or type(run_dense) is not bool or type(run_independent) is not bool:
        raise ValueError('explicit selection and durable record_sink required')
    keys = ('separate17', 'dense1001', 'independent_forward84', 'independent_mna84')
    if not isinstance(budgets, dict) or set(budgets) != set(keys):
        raise ValueError('all four explicit sample budgets required')
    meters = {k: SampleBudgetCost(budgets[k]) for k in keys}
    x = np.asarray(vector, float)
    if x.shape != (circuit.schema.vector_length,) or not np.all(np.isfinite(x)):
        raise ValueError('complete finite physical vector required')
    if not isinstance(source_provenance, dict) or not source_provenance:
        raise ValueError('explicit source provenance required')
    if (not isinstance(optimization_record, dict) or
            optimization_record.get('numerical_state') not in ('converged', 'not_converged') or
            not isinstance(optimization_record.get('evaluation_cost'), dict)):
        raise ValueError('completed metered optimization record required')
    calls = optimization_record.get('stage_calls', [])
    if (not calls or calls[-1].get('output_vector') is None or
            vector_fingerprint(calls[-1]['output_vector'][:-1]) != vector_fingerprint(x) or
            optimization_record.get('policy_fingerprint') != circuit.policy_fingerprint or
            optimization_record.get('definition_sha256') != definition_fingerprint(circuit.definition) or
            optimization_record.get('source_provenance') != {'state': 'provided', 'value': source_provenance}):
        raise ValueError('optimization vector or provenance mismatch')
    identity = _identity(circuit, x)
    identity_keys = ('git_head', 'source_tree_sha256', 'source_worktree_dirty', 'input_sha256', 'environment')
    if any(source_provenance.get(k) != identity[k] for k in identity_keys):
        raise ValueError('optimization source, environment or inputs mismatch')
    record = {'schema': 'post-search-validation-1', 'optimization_record': deepcopy(optimization_record),
              'source_provenance': deepcopy(source_provenance), 'identity': identity,
              'definition': asdict(circuit.definition), 'vector': x.tolist(),
              'vector_sha256': vector_fingerprint(x), 'budgets': dict(budgets),
              'separate17': {'state': 'not_run'}, 'dense1001': {'state': 'not_run'},
              'independent84': {'state': 'not_run'}, 'rf_compliance_certified': False,
              'candidate_promotion_blocked': True,
              'limitations': ['finite grids only; no continuous-frequency guarantee',
                              'SRF, Q(f), EM, tolerances and measurements not verified',
                              'EXP manifest and storage gates not executed']}
    def persist():
        record['evaluation_cost'] = {k: v.snapshot() for k, v in meters.items()}
        record_sink(deepcopy(record))
    def check_identity():
        if _identity(circuit, x) != identity:
            raise ValueError('identity_changed_during_validation')

    persist()  # raw optimization result and provenance before any validation
    try:
        check_identity()
        box = circuit_box(circuit)
        outside = [i for i, (v, (lo, hi)) in enumerate(zip(x, box.bounds[:-1]))
                   if (lo is not None and v < lo) or (hi is not None and v > hi)]
        outside += [i for i in box.open_lower if x[i] <= box.bounds[i][0]]
        component = circuit.validate_components(x)
        if outside or component.get('component_policy_pass') is not True or component.get('connection_role_evidence_incomplete') is not False:
            raise ValueError('box, component, role or model SPD validation failed')
        record['component'] = {'state': 'pass', 'detail': component}
        record['separate17'] = _forward(circuit, x, 17, meters['separate17'],
            float(circuit.resolved_policy['evaluation']['full_phase2']['minimum_h2_h3_db']))
        check_identity()
    except SampleBudgetExceeded as exc:
        record['separate17'] = {'state': 'budget_exhausted', 'reason': str(exc)}
    except Exception as exc:
        record['separate17'] = {'state': 'failed', 'reason': str(exc), 'exception_type': type(exc).__name__}
    persist()
    if (record['separate17']['state'] == 'pass' and run_dense and
            optimization_record['numerical_state'] == 'converged'):
        try:
            check_identity()
            record['dense1001'] = _forward(circuit, x, 1001, meters['dense1001'],
                float(circuit.resolved_policy['evaluation']['full_phase2']['minimum_h2_h3_db']))
            check_identity()
        except SampleBudgetExceeded as exc:
            record['dense1001'] = {'state': 'budget_exhausted', 'reason': str(exc)}
        except Exception as exc:
            record['dense1001'] = {'state': 'failed', 'reason': str(exc), 'exception_type': type(exc).__name__}
    else:
        record['dense1001']['reason'] = ('not_selected' if not run_dense else
            'optimization_not_converged' if optimization_record['numerical_state'] != 'converged'
            else 'separate17_not_passed')
    persist()
    if record['dense1001']['state'] == 'pass' and run_independent:
        try:
            check_identity()
            record['independent84'] = _independent(circuit, x, meters['independent_forward84'], meters['independent_mna84'])
            check_identity()
        except SampleBudgetExceeded as exc:
            record['independent84'] = {'state': 'budget_exhausted', 'reason': str(exc)}
        except Exception as exc:
            record['independent84'] = {'state': 'failed', 'reason': str(exc), 'exception_type': type(exc).__name__}
    else:
        record['independent84']['reason'] = 'not_selected' if not run_independent else 'dense1001_not_passed'
    persist()
    return record

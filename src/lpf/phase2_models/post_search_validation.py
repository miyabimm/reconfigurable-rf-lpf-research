"""Explicit, candidate-bound post-search finite-grid validation.

This is not an experiment runner or a storage/finalization gate. The caller
must persist each sink snapshot under its already approved G0--G4 protocol.
No candidate is automatically selected and no historical evidence is modified.
"""
from copy import deepcopy
from dataclasses import asdict
import csv
import math
import re
import subprocess

import numpy as np

from lpf.constraint_versions import rf_input_file
from ._grid import ROOT, validated_band_segments
from .evaluation_cost import SampleBudgetCost, SampleBudgetExceeded
from .independent_rf import evaluate_independent_sample
from .independent_scan import scan_independent_rf
from .limited_candidate_evidence import _identity
from .numerical_diagnostics import CircuitNumericalError
from .problem_seed import circuit_box, definition_fingerprint, vector_fingerprint
from .sampled_epigraph import SEARCH_GUARD_DB


class RecordSinkFailure(RuntimeError):
    """A snapshot write/readback failed; never reinterpret as an RF result."""


class ValidationCounterexample(ValueError):
    """A completed check observed a concrete numerical or physical violation."""

    def __init__(self, reason, *, evidence=None):
        super().__init__(reason)
        self.evidence = evidence


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
    if meter.frequency_samples_requested + 28 * points > meter.max_samples:
        raise SampleBudgetExceeded(f'RF sample budget {meter.max_samples}: '
                                   f'{meter.frequency_samples_requested} consumed, {28 * points} requested')
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


def _independent(circuit, x, forward_meter, mna_meter, samples=None, progress=None):
    evaluator = circuit.forward_evaluator(3)
    _grid(circuit, evaluator, 3)
    with forward_meter.timed():
        reference = np.asarray(forward_meter.forward(evaluator, x), float)
    if reference.shape != (84,) or not np.all(np.isfinite(reference)):
        raise ValueError('independent reference incomplete')
    if samples is None:
        samples = []
    losses = ('inductor_loss_w', 'capacitor_loss_w', 'input_s2p_loss_w',
              'output_s2p_loss_w', 'load_power_w', 'input_power_w')

    class OneSample:
        f = (0.,)
        def __init__(self, c, v, frequency, setting):
            self.args = c, v, frequency, setting
        def il(self, unused):
            return evaluate_independent_sample(*self.args)

    def notify(attempt):
        if progress is not None:
            progress(samples, attempt)

    def execute(c, v, frequency, setting):
        attempt = {'segment': len(samples) // 3, 'setting': setting,
                   'frequency_hz': float(frequency), 'state': 'dispatching'}
        notify(attempt)
        try:
            with mna_meter.timed():
                return mna_meter.forward(OneSample(c, v, frequency, setting), None)
        except CircuitNumericalError as exc:
            attempt.update(state='exception', exception_type=type(exc).__name__, code=exc.code)
            notify(attempt)
            if exc.code == 'mutual_not_spd':
                raise ValidationCounterexample('independent inductance matrix not SPD',
                    evidence={'code': exc.code, 'segment': len(samples) // 3,
                              'setting': setting, 'frequency_hz': float(frequency)}) from exc
            raise
        except Exception as exc:
            attempt.update(state='exception', exception_type=type(exc).__name__, message=str(exc))
            notify(attempt)
            raise

    def observe(segment, setting, frequency, result):
        i = len(samples)
        if (i >= 84 or int(evaluator.segment[i]) != segment or
                int(evaluator.setting[i]) != setting or
                not math.isclose(float(evaluator.f[i]) * 1e6, frequency, rel_tol=0, abs_tol=1e-6)):
            raise ValueError('independent grid mismatch')
        numbers = {k: float(result[k]) for k in ('gain', 'il_db', 'power_residual_w', *losses)}
        if not all(math.isfinite(v) for v in numbers.values()):
            notify({'segment': segment, 'setting': setting, 'frequency_hz': frequency,
                    'state': 'nonfinite', 'values': {k: v if math.isfinite(v) else repr(v)
                                                     for k, v in numbers.items()}})
            raise ValueError('independent sample nonfinite')
        samples.append({'segment': segment, 'setting': setting, 'frequency_hz': frequency,
                        'forward_il_db': float(reference[i]), **numbers})
        notify({'segment': segment, 'setting': setting, 'frequency_hz': frequency, 'state': 'observed'})
        if numbers['gain'] <= 0:
            raise ValidationCounterexample('independent nonpositive gain')
        if any(numbers[k] < -1e-12 for k in losses) or abs(numbers['power_residual_w']) > 1e-12:
            raise ValidationCounterexample('independent passivity or power balance failed')
        if abs(numbers['il_db'] - float(reference[i])) > 1e-9:
            raise ValidationCounterexample('independent forward IL mismatch')
        if abs(numbers['gain'] - 10 ** (-float(reference[i]) / 10)) > 1e-9:
            raise ValidationCounterexample('independent forward gain mismatch')

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
                         budgets, run_dense, run_independent, record_sink,
                         exchange_record=None, validation_identity=None):
    """Run one explicitly selected candidate; emit raw and every gate to sink.

    budgets gives separate maximum requested samples for separate17, dense1001,
    independent_forward84 and independent_mna84. Selection of dense/MNA is
    explicit, and a preceding mandatory failure or exception always blocks it.
    The sink must durably preserve snapshots or raise; this function does not
    manipulate EXP manifests, storage records or historical evidence.
    """
    if not callable(record_sink) or type(run_dense) is not bool or type(run_independent) is not bool:
        raise ValueError('explicit selection and durable record_sink required')
    # Preserve the caller's raw result before identity checks, including cases
    # rejected at the boundary. This is not evidence of a valid candidate.
    record_sink({'schema': 'post-search-validation-preflight-1',
                 'optimization_record': deepcopy(optimization_record),
                 'exchange_record': deepcopy(exchange_record),
                 'source_provenance': deepcopy(source_provenance),
                 'validation_identity': deepcopy(validation_identity),
                 'separate17': {'state': 'not_run'},
                 'dense1001': {'state': 'not_run'},
                 'independent84': {'state': 'not_run'},
                 'candidate_promotion_blocked': True, 'rf_compliance_certified': False})
    keys = ('separate17', 'dense1001', 'independent_forward84', 'independent_mna84')
    if not isinstance(budgets, dict) or set(budgets) != set(keys):
        raise ValueError('all four explicit sample budgets required')
    meters = {k: SampleBudgetCost(budgets[k]) for k in keys}
    x = np.asarray(vector, float)
    if x.shape != (circuit.schema.vector_length,) or not np.all(np.isfinite(x)):
        raise ValueError('complete finite physical vector required')
    if not isinstance(source_provenance, dict) or not source_provenance:
        raise ValueError('explicit source provenance required')
    if optimization_record is None:
        # An AFE scan can exhaust its budget or fail before the first C1
        # stage. Preserve that terminal trace, but never validate or promote it.
        if not isinstance(exchange_record, dict) or exchange_record.get('stop_reason') not in ('failed', 'budget_exhausted'):
            raise ValueError('terminal metered optimization record required')
        state = exchange_record['stop_reason']
    else:
        if (not isinstance(optimization_record, dict) or
                optimization_record.get('numerical_state') not in ('converged', 'not_converged', 'failed', 'budget_exhausted') or
                not isinstance(optimization_record.get('evaluation_cost'), dict)):
            raise ValueError('terminal metered optimization record required')
        calls = optimization_record.get('stage_calls', [])
        state = optimization_record['numerical_state']
        if (optimization_record.get('policy_fingerprint') != circuit.policy_fingerprint or
                optimization_record.get('definition_sha256') != definition_fingerprint(circuit.definition) or
                optimization_record.get('source_provenance') != {'state': 'provided', 'value': source_provenance}):
            raise ValueError('optimization vector or provenance mismatch')
        if state in ('converged', 'not_converged') and (
                not calls or calls[-1].get('output_vector') is None or
                vector_fingerprint(calls[-1]['output_vector'][:-1]) != vector_fingerprint(x)):
            raise ValueError('optimization vector or provenance mismatch')
    if exchange_record is not None:
        if (not isinstance(exchange_record, dict) or exchange_record.get('stop_reason') not in
                ('scan_no_new_violation', 'stalled_existing_constraint', 'max_rounds', 'budget_exhausted', 'failed') or
                not isinstance(exchange_record.get('evaluation_cost'), dict)):
            raise ValueError('terminal metered exchange record required')
        final_vector = exchange_record.get('final_vector')
        if final_vector is not None and vector_fingerprint(final_vector[:-1]) != vector_fingerprint(x):
            raise ValueError('exchange vector mismatch')
        if exchange_record['stop_reason'] not in ('failed', 'budget_exhausted'):
            rounds = exchange_record.get('rounds')
            inner = rounds[-1].get('inner') if isinstance(rounds, list) and rounds else None
            comparable = lambda row: {k: v for k, v in row.items()
                                      if k not in ('evaluation_cost', 'elapsed_seconds')}
            if (final_vector is None or not isinstance(inner, dict) or
                    comparable(inner) != comparable(optimization_record)):
                raise ValueError('exchange and final staged record mismatch')
    identity = _identity(circuit, x)
    identity_keys = ('git_head', 'source_tree_sha256', 'source_worktree_dirty', 'input_sha256', 'environment')
    identity_source = source_provenance if validation_identity is None else validation_identity
    if not isinstance(identity_source, dict) or any(identity_source.get(k) != identity[k] for k in identity_keys):
        raise ValueError('optimization source, environment or inputs mismatch')
    if validation_identity is not None:
        source_head = source_provenance.get('git_head')
        paths = ('src', 'scripts', 'project', 'rf', 'pyproject.toml', 'uv.lock')
        if (not isinstance(source_head, str) or re.fullmatch(r'[0-9a-f]{40}', source_head) is None or
                subprocess.run(['git', 'merge-base', '--is-ancestor', source_head, 'HEAD'], cwd=ROOT,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode or
                subprocess.run(['git', 'diff', '--quiet', source_head, 'HEAD', '--', *paths], cwd=ROOT).returncode):
            raise ValueError('optimization and validation source revisions differ')
    record = {'schema': 'post-search-validation-1', 'optimization_record': deepcopy(optimization_record),
              'exchange_record': deepcopy(exchange_record),
              'source_provenance': deepcopy(source_provenance),
              'validation_identity': deepcopy(validation_identity), 'identity': identity,
              'definition': asdict(circuit.definition), 'vector': x.tolist(),
              'vector_sha256': vector_fingerprint(x), 'budgets': dict(budgets),
              'separate17': {'state': 'not_run'}, 'dense1001': {'state': 'not_run'},
              'independent84': {'state': 'not_run'}, 'rf_compliance_certified': False,
              'candidate_promotion_blocked': True,
              'cost_semantics': {'optimization': 'optimization_record.evaluation_cost when available; exchange_record includes exchange scans when present',
                  'independent_mna84': 'EvaluationCost RF_forward_calls counts independent MNA sample invocations, not forward-kernel calls',
                  'independent_forward84': 'separate forward reference calls for independent comparison'},
              'limitations': ['finite grids only; no continuous-frequency guarantee',
                              'SRF, Q(f), EM, tolerances and measurements not verified',
                              'EXP manifest and storage gates not executed']}
    def persist():
        record['evaluation_cost'] = {k: v.snapshot() for k, v in meters.items()}
        try:
            record_sink(deepcopy(record))
        except Exception as exc:
            raise RecordSinkFailure(str(exc)) from exc
    def check_identity():
        if _identity(circuit, x) != identity:
            raise ValueError('identity_changed_during_validation')

    persist()  # raw optimization result and provenance before any validation
    stop_reason = exchange_record.get('stop_reason') if exchange_record else None
    if state in ('failed', 'budget_exhausted') or stop_reason in ('failed', 'budget_exhausted'):
        reason = f'optimization_{stop_reason if stop_reason in ("failed", "budget_exhausted") else state}'
        for key in ('separate17', 'dense1001', 'independent84'):
            record[key] = {'state': 'not_run', 'reason': reason}
        persist()
        return record
    try:
        check_identity()
        box = circuit_box(circuit)
        outside = [i for i, (v, (lo, hi)) in enumerate(zip(x, box.bounds[:-1]))
                   if (lo is not None and v < lo) or (hi is not None and v > hi)]
        outside += [i for i in box.open_lower if x[i] <= box.bounds[i][0]]
        if outside:
            raise ValidationCounterexample('vector outside policy box')
        try:
            component = circuit.validate_components(x)
        except ValueError as exc:
            raise ValidationCounterexample(str(exc)) from exc
        if component.get('component_policy_pass') is False:
            raise ValidationCounterexample('component policy failed')
        if (component.get('component_policy_pass') is not True or
                component.get('connection_role_evidence_incomplete') is not False):
            raise ValueError('component or connection-role evidence incomplete')
        record['component'] = {'state': 'pass', 'detail': component}
        record['separate17'] = _forward(circuit, x, 17, meters['separate17'],
            float(circuit.resolved_policy['evaluation']['full_phase2']['minimum_h2_h3_db']))
        check_identity()
    except SampleBudgetExceeded as exc:
        record['separate17'] = {'state': 'budget_exhausted', 'reason': str(exc)}
    except ValidationCounterexample as exc:
        record['component'] = {'state': 'fail', 'reason': str(exc)}
        record['separate17'] = {'state': 'not_run', 'reason': 'component_validation_failed'}
    except RecordSinkFailure:
        raise
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
        except RecordSinkFailure:
            raise
        except Exception as exc:
            record['dense1001'] = {'state': 'failed', 'reason': str(exc), 'exception_type': type(exc).__name__}
    else:
        record['dense1001']['reason'] = ('not_selected' if not run_dense else
            'optimization_not_converged' if optimization_record['numerical_state'] != 'converged'
            else 'separate17_not_passed')
    persist()
    if record['dense1001']['state'] == 'pass' and run_independent:
        partial_samples = []
        last_attempt = {}
        def progress(samples, attempt):
            last_attempt.clear()
            last_attempt.update(attempt)
            record['independent84'] = {'state': 'running', 'completed_samples': deepcopy(samples),
                                       'last_attempt': deepcopy(attempt)}
            persist()
        try:
            check_identity()
            record['independent84'] = _independent(circuit, x, meters['independent_forward84'],
                meters['independent_mna84'], partial_samples, progress)
            check_identity()
        except SampleBudgetExceeded as exc:
            record['independent84'] = {'state': 'budget_exhausted', 'reason': str(exc),
                                       'completed_samples': partial_samples, 'last_attempt': deepcopy(last_attempt)}
        except ValidationCounterexample as exc:
            record['independent84'] = {'state': 'fail', 'reason': str(exc),
                                       'samples_including_failure': partial_samples,
                                       'failure_evidence': exc.evidence, 'last_attempt': deepcopy(last_attempt)}
        except RecordSinkFailure:
            raise
        except Exception as exc:
            record['independent84'] = {'state': 'failed', 'reason': str(exc),
                                       'exception_type': type(exc).__name__, 'completed_samples': partial_samples,
                                       'last_attempt': deepcopy(last_attempt)}
    else:
        record['independent84']['reason'] = 'not_selected' if not run_independent else 'dense1001_not_passed'
    persist()
    return record

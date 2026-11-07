"""Static, candidate-bound checks before post-search evidence can be packaged.

These checks do not rerun RF or authenticate a fabricated input. They reject
incomplete/contradictory stored observations; the G0/G1/source and journal
checks remain necessary before their results are used by a preservation gate.
"""
from dataclasses import asdict
import csv
import math

import numpy as np

from lpf.checkpoint_io import canonical_config_hash
from lpf.constraint_versions import rf_input_file
from lpf.policy_schema import harmonic_limit_db
from lpf.rf_core._grid import ROOT, validated_band_segments
from .limited_candidate_evidence import _identity
from .problem_seed import circuit_box, definition_fingerprint, vector_fingerprint
from .sampled_epigraph import SEARCH_GUARD_DB


def _segments(circuit):
    with rf_input_file(ROOT, circuit.resolved_policy['bands_file']).open(newline='', encoding='utf-8') as f:
        rows = list(csv.DictReader(f))
    return validated_band_segments(rows), rows


def _verify_grid(grid, points, segments, mandatory):
    state = grid.get('state')
    if state not in ('pass', 'fail'):
        return
    rows = grid.get('segments')
    if (grid.get('points_per_interval') != points or not isinstance(rows, list) or len(rows) != 28 or
            grid.get('mandatory_stop_db') != mandatory or grid.get('search_guard_db') != SEARCH_GUARD_DB):
        raise ValueError('Incomplete grid evidence')
    values = {0: [], 1: [], 2: []}
    guard = []
    for i, ((setting, role, low, high), row) in enumerate(zip(segments, rows)):
        frequencies = np.linspace(low, high, points)
        if (row.get('segment') != i or row.get('setting') != setting or row.get('role') != role or
                not np.array_equal(np.asarray(row.get('frequencies_mhz'), float), frequencies)):
            raise ValueError('Grid segment, setting or frequencies mismatch')
        value = row.get('worst_il_db')
        frequency = row.get('worst_frequency_mhz')
        if (type(value) not in (int, float) or not math.isfinite(value) or
                type(frequency) not in (int, float) or frequency not in frequencies):
            raise ValueError('Grid worst point missing or nonfinite')
        values[role].append(value)
        if role:
            if (row.get('mandatory_pass') is not (value >= mandatory) or
                    row.get('guard_achieved') is not (value >= mandatory + SEARCH_GUARD_DB)):
                raise ValueError('Grid threshold flag mismatch')
            guard.append(value >= mandatory + SEARCH_GUARD_DB)
        elif row.get('mandatory_pass') is not None or row.get('guard_achieved') is not None:
            raise ValueError('Unexpected passband threshold flag')
    strict = all(v >= mandatory for role in (1, 2) for v in values[role])
    if (state != ('pass' if strict else 'fail') or grid.get('guard_achieved') is not all(guard) or
            grid.get('worst_pass_il_db') != max(values[0]) or grid.get('min_h2_db') != min(values[1]) or
            grid.get('min_h3_db') != min(values[2])):
        raise ValueError('Grid summary or status mismatch')


def _sample_violation(sample):
    losses = ('inductor_loss_w', 'capacitor_loss_w', 'input_s2p_loss_w',
              'output_s2p_loss_w', 'load_power_w', 'input_power_w')
    names = ('gain', 'il_db', 'forward_il_db', 'power_residual_w', *losses)
    if any(type(sample.get(k)) not in (int, float) or not math.isfinite(sample[k]) for k in names):
        raise ValueError('Incomplete or nonfinite independent sample')
    computed_residual = sample['input_power_w'] - sum(sample[k] for k in losses if k != 'input_power_w')
    return (sample['gain'] <= 0 or any(sample[k] < -1e-12 for k in losses) or
            abs(sample['power_residual_w']) > 1e-12 or abs(computed_residual) > 1e-12 or
            abs(computed_residual - sample['power_residual_w']) > 1e-12 or
            abs(sample['il_db'] - sample['forward_il_db']) > 1e-9 or
            abs(sample['gain'] - 10 ** (-sample['forward_il_db'] / 10)) > 1e-9)


def _verify_independent(result, segments, band_rows, circuit, vector):
    state = result.get('state')
    if state not in ('pass', 'fail'):
        return
    samples = result.get('samples' if state == 'pass' else 'samples_including_failure')
    spd_failure = state == 'fail' and isinstance(result.get('failure_evidence'), dict)
    if not isinstance(samples, list) or len(samples) > 84 or (not samples and not spd_failure):
        raise ValueError('Independent sample evidence incomplete')
    for i, sample in enumerate(samples):
        segment = i // 3
        setting, _, low, high = segments[segment]
        frequency = float(np.linspace(low, high, 3)[i % 3] * 1e6)
        if (sample.get('segment') != segment or sample.get('setting') != setting or
                not math.isclose(sample.get('frequency_hz', float('nan')), frequency, rel_tol=0, abs_tol=1e-6)):
            raise ValueError('Independent sample grid mismatch')
        violation = _sample_violation(sample)
        if violation != (state == 'fail' and not spd_failure and i == len(samples) - 1):
            raise ValueError('Independent outcome contradicts sample')
    if spd_failure:
        i = len(samples)
        if i >= 84:
            raise ValueError('Independent SPD failure outside grid')
        segment = i // 3
        setting, _, low, high = segments[segment]
        evidence = result['failure_evidence']
        frequency = float(np.linspace(low, high, 3)[i % 3] * 1e6)
        if (evidence.get('code') != 'mutual_not_spd' or evidence.get('segment') != segment or
                evidence.get('setting') != setting or
                not math.isclose(evidence.get('frequency_hz', float('nan')), frequency, rel_tol=0, abs_tol=1e-6)):
            raise ValueError('Independent SPD failure location mismatch')
        values = circuit.decode(vector)
        inductances = np.asarray(values.inductances_nh) * 1e-9
        matrix = np.diag(inductances.copy())
        for (a, b), k in zip(circuit.topology.coupling_pairs, values.coupling_k):
            matrix[a, b] = matrix[b, a] = k * np.sqrt(inductances[a] * inductances[b])
        eigenvalues = np.linalg.eigvalsh(matrix)
        if not np.all(np.isfinite(eigenvalues)) or eigenvalues[0] > eigenvalues[-1] * 1e-12:
            raise ValueError('Independent SPD failure not reproduced')
    if state == 'pass':
        rows = result.get('segments')
        if (len(samples) != 84 or not isinstance(rows, list) or len(rows) != 28 or
                result.get('independent_spd') != 'checked_by_branch_mna_each_sample' or
                result.get('mna_dimension') != circuit.topology.inductor_tree.node_count + len(circuit.topology.inductor_tree.edges)):
            raise ValueError('Independent PASS lacks full MNA/SPD coverage')
        worsts = []
        for i, (band, (setting, role, _, _), row) in enumerate(zip(band_rows, segments, rows)):
            # Match the scan's tie rule: earliest frequency in the segment.
            chosen = min(samples[i * 3:i * 3 + 3], key=lambda s: (-1 if role == 0 else 1) * s['il_db'])
            grid = {k: chosen[k] for k in ('frequency_hz', 'il_db')}
            identity = {'segment': i, 'case': band['case'], 'region': band['region'],
                        'subband': band.get('note', ''), 'setting': setting, 'canonical_setting': setting}
            if (not isinstance(row, dict) or any(row.get(k) != v for k, v in identity.items()) or
                    row.get('grid_worst') != grid):
                raise ValueError('Independent segment worst point mismatch')
            worsts.append(identity | grid)
        # Match the scan's tie rule: CSV order for equal segment extrema.
        summary = {}
        for name, regions, maximize in (('pass_il', ('UL', 'DL'), True), ('UL', ('UL',), True),
                                       ('DL', ('DL',), True), ('H2', ('H2',), False), ('H3', ('H3',), False)):
            subset = [row for row in worsts if row['region'] in regions]
            summary[name] = min(subset, key=lambda row: (-1 if maximize else 1) * row['il_db'])
        if result.get('summary') != summary:
            raise ValueError('Independent summary worst point mismatch')


def verify_candidate_evidence(circuit, binding, report):
    """Reject incomplete or contradictory candidate evidence without RF calls."""
    if not isinstance(report, dict) or report.get('schema') != 'post-search-validation-1':
        raise ValueError('Completed post-search report required')
    anchor_mode = binding.get('validate_terminal_anchor', False)
    if (type(anchor_mode) is not bool or
            report.get('validation_mode') != ('terminal_physical_anchor' if anchor_mode else None)):
        raise ValueError('Validation mode differs from frozen binding')
    identity = report.get('identity', {})
    vector = report.get('vector')
    if (binding.get('policy_id') != circuit.policy_id or binding.get('policy_sha256') != circuit.policy_fingerprint or
            binding.get('definition_sha256') != definition_fingerprint(circuit.definition) or
            report.get('vector_sha256') != binding.get('vector_sha256') or
            vector_fingerprint(vector) != binding.get('vector_sha256') or
            canonical_config_hash(vector) != canonical_config_hash(binding.get('vector')) or
            canonical_config_hash(report.get('definition')) != canonical_config_hash(asdict(circuit.definition)) or
            identity.get('constraint_id') != circuit.policy_id or
            identity.get('constraint_fingerprint') != circuit.policy_fingerprint or
            identity != _identity(circuit, vector) or
            canonical_config_hash(report.get('optimization_record')) != binding.get('optimization_sha256') or
            canonical_config_hash(report.get('exchange_record')) != binding.get('exchange_sha256') or
            canonical_config_hash(report.get('source_provenance')) != binding.get('source_sha256') or
            canonical_config_hash(report.get('validation_identity')) != binding.get('validation_identity_sha256') or
            report.get('budgets') != binding.get('budgets') or
            report.get('candidate_promotion_blocked') is not True or report.get('rf_compliance_certified') is not False):
        raise ValueError('Candidate identity or frozen binding mismatch')
    costs = report.get('evaluation_cost', {})
    for key, budget in binding['budgets'].items():
        counter = costs.get(key, {})
        requested = counter.get('frequency_samples_requested')
        completed = counter.get('frequency_samples_completed')
        if (type(requested) is not int or type(completed) is not int or
                not 0 <= completed <= requested <= budget):
            raise ValueError('Candidate validation cost mismatch')
    segments, band_rows = _segments(circuit)
    mandatory = float(harmonic_limit_db(circuit.resolved_policy))
    component = report.get('component', {})
    if component.get('state') in ('pass', 'fail'):
        box = circuit_box(circuit)
        outside = any((lo is not None and v < lo) or (hi is not None and v > hi)
                      for v, (lo, hi) in zip(vector, box.bounds[:-1])) or any(
                          vector[i] <= box.bounds[i][0] for i in box.open_lower)
        try:
            check = circuit.validate_components(vector)
            counterexample = outside or check.get('component_policy_pass') is False
            complete = check.get('component_policy_pass') is True and check.get('connection_role_evidence_incomplete') is False
        except ValueError:
            counterexample, complete = True, False
        if ((component['state'] == 'pass' and (counterexample or not complete)) or
                (component['state'] == 'fail' and not counterexample)):
            raise ValueError('Candidate component evidence mismatch')
    for key, points in (('separate17', 17), ('dense1001', 1001)):
        grid = report.get(key)
        if not isinstance(grid, dict):
            raise ValueError('Missing validation stage')
        _verify_grid(grid, points, segments, mandatory)
        if grid.get('state') in ('pass', 'fail') and (
                component.get('state') != 'pass' or
                costs[key]['frequency_samples_requested'] != 28 * points or
                costs[key]['frequency_samples_completed'] != 28 * points):
            raise ValueError('Grid evidence lacks component checks or metered coverage')
    independent = report.get('independent84')
    if not isinstance(independent, dict):
        raise ValueError('Missing independent stage')
    _verify_independent(independent, segments, band_rows, circuit, vector)
    if independent.get('state') == 'pass' and any(
            costs[k]['frequency_samples_completed'] != 84 for k in ('independent_forward84', 'independent_mna84')):
        raise ValueError('Independent PASS lacks metered coverage')
    if report['dense1001'].get('state') in ('pass', 'fail') and (
            report['separate17'].get('state') != 'pass' or not binding['run_dense'] or
            (not anchor_mode and (report.get('optimization_record') or {}).get('numerical_state') != 'converged')):
        raise ValueError('Dense evidence bypasses the 17-point selection gate')
    if independent.get('state') in ('pass', 'fail') and (
            report['dense1001'].get('state') != 'pass' or not binding['run_independent']):
        raise ValueError('Independent evidence bypasses dense selection gate')
    return True

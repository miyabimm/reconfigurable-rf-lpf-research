"""Recompute small, candidate-bound RF evidence; never authenticate input reports.

This deliberately accepts no serialized result or caller-supplied PASS flag.
It is a limited regression diagnostic, not a dense run or certification.
"""
from dataclasses import asdict
from hashlib import sha256
import json
import math
import platform
import subprocess

import numpy as np
import scipy

from lpf.constraint_versions import constraint_fingerprint, load_constraint, rf_input_file
from ._grid import ROOT
from .api import NominalCircuit, build_nominal_circuit
from .independent_scan import scan_independent_rf


class EvidenceFailure(ValueError):
    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason


def _digest(value):
    return sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                             allow_nan=False).encode()).hexdigest()


def _file_hash(path):
    return sha256(path.read_bytes()).hexdigest()


def _identity(circuit, vector):
    if not isinstance(circuit, NominalCircuit):
        raise EvidenceFailure('unsupported_circuit')
    policy = circuit._adapter.policy
    approved = load_constraint(circuit.policy_id, allow_trial=True)
    if (constraint_fingerprint(policy) != circuit.policy_fingerprint or
            constraint_fingerprint(approved) != circuit.policy_fingerprint):
        raise EvidenceFailure('policy_mismatch')
    if build_nominal_circuit(approved, circuit.definition) != circuit:
        raise EvidenceFailure('circuit_definition_mismatch')
    source = {}
    for path in sorted((ROOT / 'src/lpf').rglob('*.py')):
        source[str(path.relative_to(ROOT))] = _file_hash(path)
    inputs = {policy['bands_file']: _file_hash(rf_input_file(ROOT, policy['bands_file']))}
    for role in ('input_parasitic', 'output_parasitic'):
        spec = policy['external_port_parasitics'][role]
        path = rf_input_file(ROOT, spec['path'])
        if not path.is_relative_to(ROOT.resolve()):
            raise EvidenceFailure('s2p_path_invalid')
        actual = _file_hash(path)
        if actual != spec['sha256']:
            raise EvidenceFailure('s2p_sha_mismatch')
        inputs[spec['path']] = actual
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT,
                                   text=True, stderr=subprocess.DEVNULL).strip()
    dirty = subprocess.check_output(
        ['git', 'status', '--porcelain', '--untracked-files=all', '--', 'src/lpf'],
        cwd=ROOT, text=True, stderr=subprocess.DEVNULL)
    return {'constraint_id': circuit.policy_id,
            'constraint_status': policy['active_constraint_status'],
            'constraint_fingerprint': circuit.policy_fingerprint,
            'definition_fingerprint': _digest(asdict(circuit.definition)),
            'vector_fingerprint': _digest(list(map(float, vector))),
            'git_head': head, 'source_tree_sha256': _digest(source),
            'source_worktree_dirty': bool(dirty),
            'input_sha256': inputs,
            # The vector is identified by content, not asserted to originate
            # from any historical EXP/checkpoint. Python sources only; this
            # does not attest imported in-memory code or historical execution.
            'source_provenance_scope': 'current_src_lpf_python_files',
            'historical_fixture_provenance': 'not_checked',
            'environment': {'python': platform.python_version(),
                            'numpy': np.__version__, 'scipy': scipy.__version__}}


def compare_recomputed_evidence(saved, actual):
    """Compare an untrusted record to a fresh result; never trust its flags.

    This comparison is not a signature and must only be used after a complete
    independent recomputation. Unknown or omitted fields are rejected.
    """
    if not isinstance(saved, dict) or set(saved) != set(actual):
        raise EvidenceFailure('evidence_incomplete')
    old, new = saved.get('identity'), actual['identity']
    if not isinstance(old, dict) or set(old) != set(new):
        raise EvidenceFailure('identity_incomplete')
    for fields, reason in (
        (('constraint_id', 'constraint_status', 'constraint_fingerprint'), 'policy_mismatch'),
        (('definition_fingerprint',), 'circuit_definition_mismatch'),
        (('vector_fingerprint',), 'vector_mismatch'),
        (('git_head', 'source_tree_sha256', 'source_worktree_dirty', 'environment',
          'source_provenance_scope', 'historical_fixture_provenance'), 'source_mismatch'),
        (('input_sha256',), 'input_mismatch'),
    ):
        if any(old[key] != new[key] for key in fields):
            raise EvidenceFailure(reason)
    if any(saved[key] != actual[key] for key in
           ('coverage', 'points_per_interval', 'grid', 'grid_fingerprint', 'segments')):
        raise EvidenceFailure('grid_or_coverage_mismatch')
    if saved != actual:
        raise EvidenceFailure('observation_mismatch')


def recompute_limited_evidence(circuit, vector, points_per_interval):
    """Compare the canonical 28-interval grid with independent MNA and power.

    Only 2 or 3 points per interval are permitted, so this cannot be used to
    launch a production dense run. Input snapshots and actual code/input
    hashes are recorded before and after the calculation. No persisted report
    is accepted as proof: rerunning is required even for an unchanged candidate.
    """
    if type(points_per_interval) is not int or points_per_interval not in (2, 3):
        raise ValueError('limited evidence requires 2 or 3 points per interval')
    snapshot = tuple(map(float, circuit.encode(circuit.decode(vector))))
    identity = _identity(circuit, snapshot)
    forward = circuit.forward_evaluator(points_per_interval)
    reference = forward.il(snapshot)
    if len(reference) != 28 * points_per_interval or not np.all(np.isfinite(reference)):
        raise EvidenceFailure('forward_nonfinite_or_incomplete')
    samples = []
    max_error = 0.0
    max_residual = 0.0
    losses = ('inductor_loss_w', 'capacitor_loss_w', 'input_s2p_loss_w',
              'output_s2p_loss_w', 'load_power_w', 'input_power_w')

    def observe(segment, setting, frequency, result):
        nonlocal max_error, max_residual
        i = len(samples)
        if (i >= len(reference) or int(forward.segment[i]) != segment or
                int(forward.setting[i]) != setting or
                not math.isclose(float(forward.f[i]) * 1e6, frequency, rel_tol=0, abs_tol=1e-6)):
            raise EvidenceFailure('grid_mismatch')
        try:
            numbers = {key: float(result[key]) for key in
                       ('gain', 'il_db', 'power_residual_w', *losses)}
        except (KeyError, TypeError, ValueError, OverflowError) as exc:
            raise EvidenceFailure('sample_incomplete') from exc
        if not all(math.isfinite(v) for v in numbers.values()) or numbers['gain'] <= 0:
            raise EvidenceFailure('sample_nonfinite')
        if any(numbers[key] < -1e-12 for key in losses):
            raise EvidenceFailure('non_passive_power')
        residual = abs(numbers['power_residual_w'])
        if residual > 1e-12:
            raise EvidenceFailure('power_balance_failed')
        error = abs(numbers['il_db'] - float(reference[i]))
        if error > 1e-9:
            raise EvidenceFailure('forward_mna_mismatch')
        max_error, max_residual = max(max_error, error), max(max_residual, residual)
        samples.append({'segment': segment, 'setting': setting, 'frequency_hz': frequency})

    scan = scan_independent_rf(circuit, snapshot, points_per_interval=points_per_interval,
                               coverage='canonical', _sample_observer=observe)
    if len(samples) != len(reference) or len(scan['segments']) != 28:
        raise EvidenceFailure('coverage_incomplete')
    if _identity(circuit, snapshot) != identity:
        raise EvidenceFailure('identity_changed_during_audit')
    return {'identity': identity, 'coverage': 'canonical',
            'points_per_interval': points_per_interval, 'grid': samples,
            'grid_fingerprint': _digest(samples),
            'max_forward_il_error_db': max_error, 'forward_il_tolerance_db': 1e-9,
            'max_abs_power_residual_w': max_residual, 'power_tolerance_w': 1e-12,
            'threshold_policy_scope': 'full_lpf',
            'threshold_observations': scan['threshold_observations'],
            'summary': scan['summary']['grid_worst'],
            'segments': scan['segments'], 'finite_grid_only': True}

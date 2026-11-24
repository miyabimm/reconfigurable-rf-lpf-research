"""Explicit opt-in minimax trial profile; separate from schema-2 policy/Worker.

The score is only a finite-grid performance calculation, not physical validation.
SPD, connectivity, passivity, power balance and independent MNA remain separate gates.
"""
import csv
import hashlib
import json
import math
import re
from dataclasses import dataclass, replace
from pathlib import Path

import numpy as np

from lpf.constraint_versions import (ROOT, _read, constraint_fingerprint, load_constraint,
                                     rf_input_file, validate_registry)
from lpf.rf_core._grid import validated_band_segments
from lpf.rf_core.model import EvaluationGrid, RFResponse, build_rf_model
from lpf.rf_core.port_parasitics import get_two_port_s

_KEYS = {'UL': 'ul_il_max', 'DL': 'dl_il_max', 'H2': 'h2_atten_min', 'H3': 'h3_atten_min'}
_FORMAT = {'header': '# Hz S RI R 50', 'z0_ohms': 50, 'points': 6001,
           'f_start_hz': 0, 'f_stop_hz': 6000000000, 'f_step_hz': 1000000}


def _number(value):
    return type(value) in (int, float) and math.isfinite(value)


def _hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


@dataclass(frozen=True)
class MinimaxProfile:
    """Immutable serialized inputs and CSV records, with effective input fingerprint."""
    profile_json: str
    base_json: str
    records_json: str
    fingerprint: str
    bands_sha256: str
    base_sha256: str
    root: Path

    @property
    def profile(self):
        return json.loads(self.profile_json)

    @property
    def records(self):
        return json.loads(self.records_json)

    def rf_input_policy(self):
        """Only RF input values, not a schema-2 performance policy."""
        p = self.profile
        return {'source_ohms': p['source_ohms'], 'load_ohms': p['load_ohms'],
                'external_port_parasitics': {'format': dict(_FORMAT),
                    'input_parasitic': p['external_s2p']['input'],
                    'output_parasitic': p['external_s2p']['output']}}

    def build_model(self, definition):
        """Build physical stamps from the approved base; use only profile RF inputs.

        No solver or old Worker integration is implied. RF evaluator cascades
        input P1->P2, LPF, output P1->P2 and uses external transducer power.
        """
        if self.root.resolve() != ROOT.resolve():
            raise ValueError('RFModel evaluator requires the current checkout root')
        model = build_rf_model(definition, json.loads(self.base_json))
        return replace(model, policy_json=json.dumps(self.rf_input_policy(), sort_keys=True),
                       policy_id=self.profile['constraint_id'], policy_fingerprint=self.fingerprint)


def load_minimax_profile(constraint_id, *, allow_trial=False, root=ROOT):
    if not allow_trial:
        raise ValueError('Minimax trial requires explicit opt-in')
    root = Path(root)
    registry = validate_registry(root=root)
    entry = registry.get('minimax_profiles', {}).get(constraint_id)
    if entry is None:
        raise ValueError('Unknown minimax profile')
    p = _read(rf_input_file(root, entry['file']))
    if (set(p) != {'schema_version', 'kind', 'constraint_id', 'base_physical_constraint_id',
                   'bands_file', 'source_ohms', 'load_ohms', 'external_s2p', 'limits_db'}
            or type(p['schema_version']) is not int or p['schema_version'] != 1
            or p['kind'] != 'rf_performance_profile' or p['constraint_id'] != constraint_id
            or p['base_physical_constraint_id'] != entry['base_physical_constraint_id']
            or p['bands_file'] != 'rf/bands.csv'):
        raise ValueError('Invalid minimax profile schema/identity')
    base = load_constraint(p['base_physical_constraint_id'], root=root, allow_trial=True)
    base_sha = constraint_fingerprint(base)
    if base_sha != entry['base_constraint_sha256']:
        raise ValueError('Physical base fingerprint mismatch')
    for name in ('source_ohms', 'load_ohms'):
        z = p[name]
        if (not isinstance(z, dict) or set(z) != {'real', 'imag'}
                or not all(_number(v) for v in z.values()) or z['real'] <= 0):
            raise ValueError('Invalid source/load impedance')
    band_path = rf_input_file(root, p['bands_file'])
    band_sha = _hash(band_path)
    if band_sha != entry['bands_sha256']:
        raise ValueError('Bands fingerprint mismatch')
    with band_path.open(encoding='utf-8', newline='') as f:
        reader = csv.DictReader(f)
        if reader.fieldnames != ['case', 'region', 'type', 'low_mhz', 'high_mhz', 'note']:
            raise ValueError('Invalid bands CSV columns')
        rows = list(reader)
    segments = validated_band_segments(rows)
    bands = {row['note'] or row['case'] for row in rows}
    limits = p['limits_db']
    if not isinstance(limits, dict) or set(limits) != bands:
        raise ValueError('Profile bands do not match CSV')
    for v in limits.values():
        if not isinstance(v, dict) or set(v) != set(_KEYS.values()) or not all(_number(x) for x in v.values()):
            raise ValueError('Invalid band limits')
    ext = p['external_s2p']
    if not isinstance(ext, dict) or set(ext) != {'input', 'output'}:
        raise ValueError('Invalid fixed S2P roles')
    for role in ('input', 'output'):
        spec = ext[role]
        if (not isinstance(spec, dict) or set(spec) != {'path', 'sha256'}
                or not isinstance(spec['path'], str) or not spec['path'].startswith('rf/parasitics/')
                or not isinstance(spec['sha256'], str) or not re.fullmatch('[0-9a-f]{64}', spec['sha256'])):
            raise ValueError('Invalid S2P specification')
        if _hash(rf_input_file(root, spec['path'])) != spec['sha256']:
            raise ValueError('S2P fingerprint mismatch')
    policy = {'external_port_parasitics': {'format': _FORMAT,
              'input_parasitic': ext['input'], 'output_parasitic': ext['output']}}
    for role in ('input_parasitic', 'output_parasitic'):
        for _, _, lo, hi in segments:
            for f in (lo * 1e6, hi * 1e6):
                get_two_port_s(policy, role, f, root=root)
    fingerprint = constraint_fingerprint({'profile': p, 'base_constraint_sha256': base_sha,
                                          'bands_sha256': band_sha})
    if fingerprint != entry['effective_constraint_sha256']:
        raise ValueError('Minimax effective fingerprint mismatch')
    return MinimaxProfile(json.dumps(p, sort_keys=True), json.dumps(base, sort_keys=True),
                          json.dumps(rows), fingerprint, band_sha, base_sha, root.resolve())


def _margin_parameters(profile, grid):
    """Signed IL offset and direction in the order of an already frozen grid."""
    limits = profile.profile['limits_db']
    rows = profile.records
    threshold = np.array([limits[r['note'] or r['case']][_KEYS[r['region']]] for r in rows])
    direction = np.array([1 if r['type'] == 'pass' else -1 for r in rows])
    return threshold[grid.segment], direction[grid.segment]


def least_squares_residual_and_jacobian(profile, response, il_jacobian):
    """Unweighted sum residual and physical Jacobian; at kink use zero.

    At m=0 the positive-part residual is nondifferentiable. The zero row is
    the chosen one-sided convention, not a claim of differentiability.
    """
    if (response.policy_id != profile.profile['constraint_id'] or
            response.policy_fingerprint != profile.fingerprint):
        raise ValueError('Response profile mismatch')
    threshold, direction = _margin_parameters(profile, response.grid)
    jac = np.asarray(il_jacobian, dtype=float)
    margin = direction * (response.il_db - threshold)
    if jac.ndim != 2 or jac.shape[0] != len(margin) or not np.all(np.isfinite(jac)) or not np.all(np.isfinite(margin)):
        raise ValueError('Non-finite or mismatched margin sensitivity')
    residual = np.sqrt(2.) * np.maximum(margin, 0)
    return residual, np.sqrt(2.) * direction[:, None] * jac * (margin > 0)[:, None]


def signed_margins(profile, expected_grid, response):
    """Return (J, per-sample margins) on the exact requested, complete grid.

    RFResponse.s is the external-port power-wave matrix produced by RFModel;
    IL is checked against its S21. All endpoints and 28 individual segments
    must be present, and all samples must lie inside their own interval.
    """
    if not isinstance(profile, MinimaxProfile) or not isinstance(expected_grid, EvaluationGrid) or not isinstance(response, RFResponse):
        raise ValueError('Expected profile, grid and completed RF response')
    p, rows = profile.profile, profile.records
    if response.policy_id != p['constraint_id'] or response.policy_fingerprint != profile.fingerprint:
        raise ValueError('Response profile mismatch')
    g = response.grid
    if not isinstance(g, EvaluationGrid) or any(not np.array_equal(getattr(g, x), getattr(expected_grid, x))
                                                for x in ('frequency_hz', 'setting', 'segment')):
        raise ValueError('Response grid mismatch')
    intervals = validated_band_segments(rows)
    if set(g.segment.tolist()) != set(range(len(rows))):
        raise ValueError('Missing or unknown interval')
    il = np.asarray(response.il_db)
    s = np.asarray(response.s)
    if (il.shape != g.frequency_hz.shape or il.dtype.kind not in 'fiu'
            or np.any(np.isnan(il)) or np.any(np.isneginf(il))
            or s.shape != (len(il), 2, 2) or not np.all(np.isfinite(s))):
        raise ValueError('Invalid RF response')
    if np.any(np.linalg.svd(s, compute_uv=False)[:, 0] > 1 + 1e-8):
        raise ValueError('Non-passive external power-wave response')
    with np.errstate(divide='ignore', invalid='ignore'):
        measured = -20*np.log10(np.abs(s[:, 1, 0]))
    if not np.allclose(il, measured, rtol=1e-10, atol=1e-10):
        raise ValueError('IL does not match external power-wave S21')
    for i, (setting, _, lo, hi) in enumerate(intervals):
        mask = g.segment == i
        f = g.frequency_hz[mask]
        if (np.any(g.setting[mask] != setting) or len(f) < 2 or len(np.unique(f)) != len(f)
                or np.min(f) != lo*1e6 or np.max(f) != hi*1e6
                or np.any(f < lo*1e6) or np.any(f > hi*1e6)):
            raise ValueError(f'Invalid interval grid: {i}')
    threshold, direction = _margin_parameters(profile, g)
    margins = direction * (il - threshold)
    return float(np.max(margins)), margins

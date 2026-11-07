"""Issue #235 bounded forward-only diagnosis of the nine saved #233 starts.

Requires the historical evidence checkout; no optimizer or EXP writer is used.
Prints JSON to stdout. Run with OPENBLAS_NUM_THREADS=1 PYTHONPATH=src uv run
--frozen python scripts/diagnose_phase2_scaling.py > /tmp/issue235.json
"""
import hashlib
import inspect
import json
from pathlib import Path
import subprocess

import numpy as np
import scipy
from scipy.optimize._slsqp_py import _minimize_slsqp

from lpf.phase2_models.candidate_records import _circuit
from lpf.phase2_models.problem_seed import definition_fingerprint, vector_fingerprint
from lpf.phase2_models.sampled_epigraph import SampledEpigraph

ROOT = Path(__file__).resolve().parents[1]


def diagnose(root=ROOT):
    defaults = inspect.signature(_minimize_slsqp).parameters
    eps, ftol = float(defaults['eps'].default), float(defaults['ftol'].default)
    rows = []
    for number in range(86, 95):
        path = Path(f'experiments/chatgpt_topology_search/runs/EXP-{number:03}/manifest.json')
        raw = (root / path).read_bytes()  # missing evidence fails, never substitutes
        m = json.loads(raw)
        source = m['search_scope']['input_source']
        saved = m['search_scope']['input_source_origin']['generated_start']['seed_record']
        c = _circuit({'definition': source['definition'], 'policy_id': 'RF-T008'})
        p = SampledEpigraph(c, 2)
        if (m['constraints']['effective_constraint_sha256'] != p.policy_fingerprint
                or saved['definition_sha256'] != definition_fingerprint(c.definition)
                or source['vector_sha256'] != vector_fingerprint(source['vector'])):
            raise ValueError('Saved input provenance mismatch')
        replay = p.seed(source['vector'], policy_id=p.policy_id,
            policy_fingerprint=p.policy_fingerprint,
            definition_sha256=saved['definition_sha256'],
            input_sha256=source['vector_sha256'], seed=23)
        if json.loads(json.dumps(replay)) != saved:
            raise ValueError('Saved seed replay mismatch')
        x = np.array(saved['vector'])
        base = p.residuals(x)
        coordinates = []
        for i, (lo, hi) in enumerate(p.box.bounds[:-1]):
            width = hi - lo
            entry = {'index': i, 'bounds': [lo, hi], 'value': float(x[i]),
                     'default_eps_over_width': eps / width if width else None}
            if width:
                gradients = []
                # One-sided inward steps, same direction at all scales.
                sign = 1 if hi - x[i] >= x[i] - lo else -1
                for h in (eps, 1e-6 * width, 1e-4 * width):
                    y = x.copy()
                    y[i] += sign * h
                    gradients.append((p.residuals(y) - base) / (sign * h) * width)
                reference = max(float(np.max(np.abs(gradients[1]))), 1e-15)
                entry['max_abs_dr_dz'] = [float(np.max(np.abs(g))) for g in gradients]
                entry['relative_delta_vs_width_1e6'] = [
                    float(np.max(np.abs(g - gradients[1]))) / reference for g in gradients]
            coordinates.append(entry)
        overlay_path = Path(f'data/validation/issue233_multistart_pilot/EXP-{number:03}-17pt.json')
        overlay_raw = (root / overlay_path).read_bytes()
        overlay = json.loads(overlay_raw)
        expected_overlay_sha = next(e['sha256'] for e in m['evidence']
                                    if e['path'] == str(overlay_path))
        if hashlib.sha256(overlay_raw).hexdigest() != expected_overlay_sha:
            raise ValueError('Saved stage evidence hash mismatch')
        rows.append({'experiment_id': m['experiment_id'],
            'class_name': m['search_scope']['input_source_origin']['class_name'],
            'manifest': str(path), 'manifest_sha256': hashlib.sha256(raw).hexdigest(),
            'saved_stages_source': str(overlay_path),
            'saved_stages_source_sha256': hashlib.sha256(overlay_raw).hexdigest(),
            'policy_sha256': p.policy_fingerprint, 'definition_sha256': saved['definition_sha256'],
            'vector_sha256': source['vector_sha256'], 'complete_vector_with_t_db': x.tolist(),
            'minimum_initial_residual_db': float(base.min()),
            'saved_stages': overlay['stages'], 'coordinates': coordinates})
    return {'issue': 235, 'kind': 'forward_only_no_optimization',
        'source_main': subprocess.check_output(['git', 'rev-parse', 'origin/main'], cwd=root, text=True).strip(),
        'diagnostic_script_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'numpy': np.__version__, 'scipy': scipy.__version__,
        'scipy_default_ftol': ftol, 'scipy_default_absolute_eps': eps,
        'steps': ['physical eps', 'width * 1e-6', 'width * 1e-4'],
        'gradient': 'dr/dz = width * dr/dx; one-sided inward, max over 56 RF residuals',
        'grid': {'points_per_interval': 2, 'settings': 6, 'intervals': 28},
        't': 'unscaled dB; objective gradient 1, passband residual gradient 1, stopband 0',
        'validation': {k: 'not_run' for k in ('dense1001', 'independent_mna', 'power', 'passivity')},
        'starts': rows}


if __name__ == '__main__':
    print(json.dumps(diagnose(), indent=2, allow_nan=False))

#!/usr/bin/env python3
"""Issue 433: one-time baseline and deterministic frozen inputs; no optimizer."""
import hashlib
import json
from pathlib import Path

import numpy as np
from lpf.constraint_versions import constraint_fingerprint, load_constraint, rf_input_file
from lpf.rf_core import build_rf_model
from lpf.rf_core.independent import validate_response
from lpf.search.component_constraints import physical_bounds, validate_search_box, validate_values
from lpf.search.performance import (build_evaluation_grid, compile_requirements, evaluate_requirements,
                                    grid_fingerprint)
from lpf.search.proposals import definition_from_data
from lpf.search.storage import sha, vector_sha

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
checkpoint_path = ROOT / 'experiments/chatgpt_topology_search/runs/EXP-062/checkpoints/a6_best.json'
definition_path = ROOT / 'project/diagnostics/issue361/definition.json'
checkpoint = json.loads(checkpoint_path.read_bytes())
def_data = json.loads(definition_path.read_bytes())
assert hashlib.sha256(checkpoint_path.read_bytes()).hexdigest() == '4fbd86e8b46ad7bcb550ba327672b0983e8b58e9ce4b2a9364f8c6557a812b4b'
assert hashlib.sha256(definition_path.read_bytes()).hexdigest() == 'e8ac857c063e0b9d2eb8eaf629c2e4b700a694e9241f3bbc596d99f6374487f6'
assert sha(def_data) == 'bc50042a1b0b1ebf19c0272fb2ee944b52cd76e14eb8d44673bfa57f6033c068'
assert checkpoint['candidate_id'] == 'EXP062-A6-grounded-best'
x = np.asarray(checkpoint['vector'])
assert x.shape == (25,) and vector_sha(x) == '4131fa4e677afd364c8e448325d2971f05214284047c349bf2f794585668313c'
f = checkpoint['fixed_values']
expected = f['L_nH'] + f['GJM_C_pf'] + f['PCB_C_pf'] + f['k_signed'] + f['IC_fixed_C_pf']
for case in ('B71', 'B12', 'B28', 'B13+B14', 'B26', 'B8'):
    expected += checkpoint['ic_variable_C_pf_by_setting'][case]
assert np.array_equal(x, expected)
p = load_constraint('RF-T008', allow_trial=True)
assert constraint_fingerprint(p) == 'e682165c72d3a8b9f1384a2529f71bacfebfc9d17164d4af5af879e4a138b532'
d = definition_from_data(def_data)
model = build_rf_model(d, p)
physical = validate_values(d, model.schema, x, p, frozen_model=model)
req = compile_requirements(p, rf_input_file(ROOT, p['bands_file']), 'full_lpf')
assert len(req.intervals) == 28

def evaluate(v, n, independent=False):
    grid = build_evaluation_grid(req, n)
    response = model.evaluator(grid).evaluate(v)
    a = evaluate_requirements(response, req, requested_grid=grid)
    rows = {}
    for interval in req.intervals:
        ix = grid.segment == interval.segment
        entry = rows.setdefault(interval.case, {'worst_il_db': -1.0, 'min_h2_db': float('inf'), 'min_h3_db': float('inf')})
        if interval.type == 'pass':
            entry['worst_il_db'] = max(entry['worst_il_db'], float(np.max(response.il_db[ix])))
        else:
            key = 'min_' + interval.region.lower() + '_db'
            entry[key] = min(entry[key], float(np.min(response.il_db[ix])))
    result = {k: a[k] for k in ('strict_feasible', 'worst_il_db', 'max_violation_db', 'sum_violation_db')}
    result.update(samples=len(grid.frequency_hz), grid_sha256=grid_fingerprint(grid), settings=rows)
    if independent:
        result['independent'] = validate_response(model, v, response)
    return result

# Baseline must finish and agree with #361 before any solver starts.
base17 = evaluate(x, 17)
basedense = evaluate(x, 1001)
mna84 = evaluate(x, 3, independent=True)
assert abs(base17['worst_il_db'] - 0.827841148462847) < 1e-8
assert abs(min(r['min_h2_db'] for r in base17['settings'].values()) - 30.004999999866506) < 1e-8
assert abs(min(r['min_h3_db'] for r in base17['settings'].values()) - 30.00499999993071) < 1e-8
base = {'source_vector_sha256': vector_sha(x), 'physical': physical, 'grid17': base17,
        'dense1001': basedense, 'selection84_independent': mna84,
        'requested_completed_samples': 476 + 28028 + 84}
(OUT / 'baseline.json').write_text(json.dumps(base, indent=2, allow_nan=False) + '\n')

hard = np.asarray(physical_bounds(d, model.schema, p))
for name in 'ABC':
    widths = np.zeros(25)
    widths[13:25] = 0.2
    if name in 'BC':
        widths[0:4] = x[0:4] * 0.1
        widths[8:11] = 0.02
    if name == 'C':
        widths[4:8] = x[4:8] * 0.1
        widths[11:13] = x[11:13] * 0.1
    box = np.column_stack((np.maximum(hard[:, 0], x - widths), np.minimum(hard[:, 1], x + widths)))
    validate_search_box(box, hard)
    lower, upper = x - box[:, 0], box[:, 1] - x
    start = x + np.where(upper >= lower, upper * 0.25, -lower * 0.25)
    report = {'box': box.tolist(), 'box_sha256': sha(box.tolist()), 'vector': start.tolist(),
              'vector_sha256': vector_sha(start), 'physical': None}
    try:
        report['physical'] = validate_values(d, model.schema, start, p, frozen_model=model)
        report['initial_grid17'] = evaluate(start, 17)
    finally:
        (OUT / f'{name}.json').write_text(json.dumps(report, indent=2, allow_nan=False) + '\n')
    assert int(np.sum(box[:, 1] > box[:, 0])) == {'A': 12, 'B': 19, 'C': 25}[name]

#!/usr/bin/env python3
"""Issue 529 single fixed-reference evaluation; never a search or Runner input."""
import hashlib
import json
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'src'))
import numpy as np
from lpf.minimax_profile import load_minimax_profile, signed_margins
from lpf.rf_core.independent import evaluate_independent_response
from lpf.search.component_constraints import _check_vector_box, validate_values
from lpf.search.evaluation import raw_numbers
from lpf.search.performance import compile_profile_grid, build_evaluation_grid, grid_fingerprint
from lpf.search.proposals import definition_from_data
from lpf.search.source import source_identity
from lpf.search.storage import sha, vector_sha

OUT = ROOT / 'project/diagnostics/issue529'
REFERENCE = ROOT / 'experiments/chatgpt_topology_search/runs/EXP-062/checkpoints/a6_best.json'

def main():
    assert all(os.environ.get(k) == '1' for k in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS'))
    output = OUT / 'reference.json'
    marker = OUT / 'reference_started.json'
    assert not output.exists() and not marker.exists(), 'No retry: reference already attempted'
    profile = load_minimax_profile('RF-T010', root=ROOT, allow_trial=True)
    assert profile.fingerprint == 'd50e6c9fef3e41b8258c00cbd14436a3bcb1d84444d50cf4a445ccf5d288e417'
    data = json.loads((ROOT/'project/diagnostics/issue361/definition.json').read_text())
    assert sha(data) == 'bc50042a1b0b1ebf19c0272fb2ee944b52cd76e14eb8d44673bfa57f6033c068'
    d, c = definition_from_data(data), json.loads(REFERENCE.read_text())
    t, v, cv, x = c['topology'], c['fixed_values'], c['ic_variable_C_pf_by_setting'], c['vector']
    assert data['inductor_tree']['edges'] == t['L_edges']
    assert data['capacitor_placement']['fixed_edges'] == t['fixed_GJM_edges'] + t['PCB_C_edges']
    assert data['capacitor_placement']['variable_edges'] == t['variable_C_edges']
    assert data['capacitor_placement']['ic_fixed_edges'] == t['IC_fixed_C_parallel_edges']
    assert data['inductor_types'] == [item['type'] for item in c['components'][:4]]
    assert data['fixed_c_types'] == [item['type'] for item in c['components'][4:8]]
    assert data['physical_order'] == [0, 1, 3, 2] and data['coupling_pairs'] == [[0, 1], [1, 3], [3, 2]]
    assert x == v['L_nH'] + v['GJM_C_pf'] + v['PCB_C_pf'] + v['k_signed'] + v['IC_fixed_C_pf'] + sum((cv[k] for k in ('B71','B12','B28','B13+B14','B26','B8')), [])
    assert [item['k'] for item in c['couplings']] == v['k_signed']
    assert all(item.get('L_nH', item.get('C_pF')) == x[i] for i, item in enumerate(c['components'][:8]))
    box = json.loads((OUT/'stage1-inputs/bounds.json').read_text())
    _check_vector_box(x, box)
    policy = json.loads(profile.base_json)
    model = profile.build_model(d)
    physical = validate_values(d, model.schema, x, policy)
    assert physical['component_policy_pass'] and physical['checked_settings'] == 6 and physical['min_L_eigenvalue_H'] > 0
    assert not physical['connection_role_evidence_incomplete']
    requirements = compile_profile_grid(profile)
    grid = build_evaluation_grid(requirements, 1001)
    assert len(grid.frequency_hz) == 28028 and set(grid.segment) == set(range(28)) and set(grid.setting) == set(range(6))
    indices = []
    for segment in range(28):
        idx = np.flatnonzero(grid.segment == segment)
        assert len(idx) == 1001 and np.all(grid.setting[idx] == requirements.intervals[segment].setting)
        indices.extend([int(idx[0]), int(idx[500]), int(idx[-1])])
    assert len(set(indices)) == 84
    source = source_identity(ROOT)
    evidence = dict(source=source, source_sha256=sha(source), reference_file_sha256=hashlib.sha256(REFERENCE.read_bytes()).hexdigest(), vector=x, vector_sha256=vector_sha(x), rf_profile=profile.fingerprint, definition_sha256=sha(data), bounds_sha256=sha(box), grid_sha256=grid_fingerprint(grid), indices=indices, physical=physical, declared_cost={'rf_forwards': 1, 'rf_samples': 28028, 'independent_mna_samples': 84})
    marker.write_text(json.dumps(raw_numbers(evidence), indent=2, allow_nan=False)+'\n')
    start = time.monotonic()
    response = model.evaluator(grid).evaluate(x, check_power=True)
    assert response.policy_fingerprint == profile.fingerprint and response.grid is grid
    spots = []
    for i in indices:
        ref = evaluate_independent_response(model, x, float(grid.frequency_hz[i]), int(grid.setting[i]))
        for key in ('s','il_db','apl_db','in_rl_db','out_rl_db'):
            assert np.allclose(getattr(response, key)[i], ref[key], rtol=0, atol=1e-9), (i,key)
        spots.append(dict(index=i, reference=ref))
    regions = np.array([requirements.intervals[int(i)].region for i in grid.segment])
    types = np.array([requirements.intervals[int(i)].type for i in grid.segment])
    metrics = dict(worst_il_db=float(np.max(response.il_db[types == 'pass'])), min_h2_db=float(np.min(response.il_db[regions == 'H2'])), min_h3_db=float(np.min(response.il_db[regions == 'H3'])))
    _, margins = signed_margins(profile, grid, response)
    evidence.update(metrics=metrics, signed_margins_db=margins, max_signed_margin_db=float(np.max(margins)), positive_violation_squared_sum_db2=float(np.square(np.maximum(margins,0)).sum()), response=response, independent=dict(status='pass', sample_indices=indices, spots=spots), external_passivity='checked_on_terminal_grid', power_balance='checked_on_terminal_grid', wall_seconds=time.monotonic()-start)
    output.write_text(json.dumps(raw_numbers(evidence), indent=2, allow_nan=False)+'\n')
    print(json.dumps(metrics))
    if metrics['min_h2_db'] < 30 or metrics['min_h3_db'] < 30:
        raise SystemExit('STOP: reference does not meet 30 dB')

if __name__ == '__main__':
    main()

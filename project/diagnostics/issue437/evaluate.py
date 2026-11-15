#!/usr/bin/env python3
"""Issue 437 bounded, read-only RF evaluations; never launches a solver."""
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
from lpf.constraint_versions import constraint_fingerprint, load_constraint, rf_input_file
from lpf.rf_core import build_rf_model
from lpf.rf_core.independent import validate_response
from lpf.search._development_runner import _weighted_plan
from lpf.search.component_constraints import validate_values, physical_bounds, validate_search_box
from lpf.search.performance import build_evaluation_grid, compile_requirements, evaluate_requirements, grid_fingerprint
from lpf.search.proposals import definition_from_data
from lpf.search.storage import sha, vector_sha
from lpf.search.starts import load_explicit

ROOT = Path(__file__).resolve().parents[3]
OLD = ROOT / 'project/diagnostics/issue433'
CAP = 4400000

def file_sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

p = load_constraint('RF-T008', allow_trial=True)
assert constraint_fingerprint(p) == 'e682165c72d3a8b9f1384a2529f71bacfebfc9d17164d4af5af879e4a138b532'
dpath = ROOT/'project/diagnostics/issue361/definition.json'
defdata = json.loads(dpath.read_bytes())
assert file_sha(dpath) == 'e8ac857c063e0b9d2eb8eaf629c2e4b700a694e9241f3bbc596d99f6374487f6'
assert sha(defdata) == 'bc50042a1b0b1ebf19c0272fb2ee944b52cd76e14eb8d44673bfa57f6033c068'
d = definition_from_data(defdata)
model = build_rf_model(d, p)
req = compile_requirements(p, rf_input_file(ROOT, p['bands_file']), 'full_lpf')
assert len(req.intervals) == 28 and len({i.case for i in req.intervals}) == 6

def evaluate(v, points, stop_points=None, audit=False):
    physical = validate_values(d, model.schema, v, p, frozen_model=model)
    grid = build_evaluation_grid(req, points, stop_points)
    response = model.evaluator(grid).evaluate(v)
    a = evaluate_requirements(response, req, requested_grid=grid)
    harmonics = np.concatenate([response.il_db[grid.segment == i.segment] for i in req.intervals if i.region in ('H2','H3')])
    ilterm = max(0., a['worst_il_db'] - .30)**2
    hterm = float(100 * np.mean(np.maximum(0., 30.01 - harmonics)**2))
    out = {k: a[k] for k in ('strict_feasible','worst_il_db','max_violation_db','sum_violation_db')}
    out.update(vector_sha256=vector_sha(v), samples=len(grid.frequency_hz), grid_sha256=grid_fingerprint(grid),
               min_h2_db=min(float(np.min(response.il_db[grid.segment == i.segment])) for i in req.intervals if i.region == 'H2'),
               min_h3_db=min(float(np.min(response.il_db[grid.segment == i.segment])) for i in req.intervals if i.region == 'H3'),
               objective_j=ilterm+hterm, il_term=ilterm, harmonic_term=hterm,
               harmonic_target_30_01=bool(np.all(harmonics >= 30.01)), physical=physical)
    if audit:
        out['independent'] = validate_response(model, v, response)
    return out

def preflight():
    cp = ROOT/'experiments/chatgpt_topology_search/runs/EXP-062/checkpoints/a6_best.json'
    assert file_sha(cp) == '4fbd86e8b46ad7bcb550ba327672b0983e8b58e9ce4b2a9364f8c6557a812b4b'
    checkpoint = json.loads(cp.read_bytes()); x = checkpoint['vector']
    assert checkpoint['candidate_id'] == 'EXP062-A6-grounded-best'
    assert vector_sha(x) == '4131fa4e677afd364c8e448325d2971f05214284047c349bf2f794585668313c'
    f = checkpoint['fixed_values']
    expected = f['L_nH'] + f['GJM_C_pf'] + f['PCB_C_pf'] + f['k_signed'] + f['IC_fixed_C_pf']
    for case in ('B71','B12','B28','B13+B14','B26','B8'):
        expected += checkpoint['ic_variable_C_pf_by_setting'][case]
    assert np.array_equal(x, expected)
    assert file_sha(ROOT/'rf/bands.csv') == '1b1182e4c947059cb263c1af52ddf64236bd1fd9e83770cc844126576c7865fe'
    plan = _weighted_plan(OLD/'hybrid.json', ROOT, 'hybrid', 20000)
    step = plan.data['config']['arms'][0]['steps'][0]
    assert step['options']['maxiter'] == step['options']['max_evaluations'] == 20000 and step['options']['max_restarts'] == 0
    costs = plan.data['costs']['jobs']['hybrid']
    assert (costs['stages']['search']['upper_reservation'], costs['selection_upper_reservation'], costs['terminal_fixed_reservation'], costs['total_upper_reservation']) == (1400000,84,476,1400560)
    expected_shas = ['a3927e5f43eb5b912e1bcebb4a9c497d3bdafe62a49b046c4d35e9db65611da5','ab8a974680bc787d33bf6835693b2769a7563c7fe89c591164cc026f1d6b2743','d957b121e10ab9a409e0a41443a5071842a6d65656bf9f296ee3a008e734512c']
    inputs = {}
    for name, digest, dof in zip('ABC', expected_shas, (12,19,25)):
        bp = OLD/f'{name}-box.json'; sp = OLD/f'{name}-starts.json'
        box = json.loads(bp.read_bytes()); start = load_explicit(sp)[1001]
        assert vector_sha(start['vector']) == start['vector_sha256'] == digest
        validate_search_box(box, physical_bounds(d, model.schema, p))
        assert sum(hi > lo for lo,hi in box) == dof and all(lo <= v <= hi for v,(lo,hi) in zip(start['vector'],box))
        validate_values(d, model.schema, start['vector'], p, frozen_model=model)
        inputs[name] = dict(box_byte_sha=file_sha(bp), box_canonical_sha=sha(box), starts_byte_sha=file_sha(sp), start_sha=digest, dof=dof)
    base70 = evaluate(x, 2, 3); base17 = evaluate(x,17)
    old = json.loads((OLD/'baseline.json').read_bytes())['grid17']
    assert base17['strict_feasible'] and old['strict_feasible']
    for key in ('worst_il_db','max_violation_db','sum_violation_db'):
        assert abs(base17[key]-old[key]) < 1e-9, (key,base17[key],old[key])
    for region in ('h2','h3'):
        assert abs(base17['min_'+region+'_db'] - min(s['min_'+region+'_db'] for s in old['settings'].values())) < 1e-9
    starts = {n:evaluate(load_explicit(OLD/f'{n}-starts.json')[1001]['vector'],2,3) for n in 'ABC'}
    return dict(plan_sha=plan.sha256, costs=costs, inputs=inputs, baseline70=base70, baseline17=base17, starts70=starts,
                primary_samples=70+476+3*70, checkpoint_byte_sha=file_sha(cp), config_byte_sha=file_sha(OLD/'hybrid.json'))

def post(paths, pre):
    old = json.loads((OLD/'results.json').read_bytes())['jobs']
    results = {}; oldcmp = {}; total = pre['primary_samples']; independent = 0
    for name, path in zip('ABC', paths):
        job = Path(path)/'job'; inp = json.loads((job/'input.json').read_bytes()); r = json.loads((job/'result.json').read_bytes())
        s = r['steps'][0]; best = s['rf_best']; v = best['vector']; digest = vector_sha(v)
        assert digest == best['vector_sha256'] == r['selection']['ranked'][0]['vector_sha256'] == r['terminal']['candidates'][0]['vector_sha256']
        assert s['forward_count'] == s['solver_result']['nfev'] <= 20000
        assert inp['plan_sha256'] == pre['plan_sha'] and inp['start']['vector_sha256'] == pre['inputs'][name]['start_sha']
        assert inp['search_bounds_sha256'] == pre['inputs'][name]['box_canonical_sha']
        g70 = evaluate(v,2,3); g84 = evaluate(v,3); g17 = evaluate(v,17)
        assert abs(g70['objective_j']-best['objective_j']) < 1e-9
        assert abs(g84['objective_j']-r['selection']['ranked'][0]['objective_j']) < 1e-9
        terminal = r['terminal']['candidates'][0]
        assert abs(g17['worst_il_db']-terminal['assessment']['worst_il_db']) < 1e-9
        assert g17['strict_feasible'] == terminal['assessment']['strict_feasible'] and terminal['independent']['status'] == 'pass'
        cost = r['costs']; total += cost['search_requested_samples']+cost['selection_requested_samples']+cost['terminal_requested_samples']+70+84+476
        independent += 2
        events = [{'file':f.name,'sha256':file_sha(f),'forward_count':json.loads(f.read_bytes())['forward_count']} for f in sorted((job/'checkpoints').glob('*.json'))]
        assert events and json.loads((job/'checkpoints'/events[-1]['file']).read_bytes())['best']['vector_sha256'] == digest
        results[name] = dict(path=str(path), input_sha=file_sha(job/'input.json'), result_sha=file_sha(job/'result.json'), checkpoints=events,
                             vector=v, status=r['status'], step=s, selection=r['selection'], terminal=r['terminal'], costs=cost,
                             grid70=g70, grid84=g84, grid17=g17)
        oldcmp[name] = {}
        for role, v in [('terminal',old[name+'-hybrid']['terminal'][0]['vector']),('rf_best',old[name+'-hybrid']['rf_best_search']['vector'])]:
            g = evaluate(v,17); total += 476
            oldcmp[name][role] = dict(vector=v, grid17=g)
    ranked = sorted((r['grid17']['worst_il_db'], r['grid17']['vector_sha256'], name) for name,r in results.items() if r['grid17']['strict_feasible'])
    dense = []
    for _, _, name in ranked[:2]:
        assert total+28028+84 <= CAP
        v = results[name]['vector']; g = evaluate(v,1001); mna = evaluate(v,3,audit=True)
        total += 28028+84; independent += 84
        dense.append(dict(name=name, dense1001=g, mna84=mna))
    assert total <= CAP
    return dict(jobs=results, old_comparison=oldcmp, dense=dense, primary_samples=total, independent_mna_samples=independent,
                accounting='preflight + job search/selection/terminal + each best 70/84/476 + six old 476 + dense/MNA primary')

if __name__ == '__main__':
    if sys.argv[1] == 'preflight':
        out = preflight()
    elif sys.argv[1] == 'post':
        out = post(sys.argv[3:], json.loads(Path(sys.argv[2]).read_bytes()))
    else:
        raise ValueError('expected preflight or post')
    print(json.dumps(out, indent=2, allow_nan=False))

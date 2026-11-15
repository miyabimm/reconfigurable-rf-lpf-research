#!/usr/bin/env python3
"""One-time, bounded post-job validation and compact provenance extraction."""
import hashlib
import json
import re
from pathlib import Path

import numpy as np
from lpf.constraint_versions import load_constraint, rf_input_file
from lpf.rf_core import build_rf_model
from lpf.rf_core.independent import validate_response
from lpf.search.component_constraints import validate_values
from lpf.search.performance import build_evaluation_grid, compile_requirements, evaluate_requirements, grid_fingerprint
from lpf.search.proposals import definition_from_data
from lpf.search.storage import vector_sha

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
JOBS = {
 'A-slsqp': '/tmp/issue433-A-slsqp-VeSI4end',
 'A-hybrid': '/tmp/issue433-A-hybrid-eiK70sY4',
 'B-slsqp': '/tmp/issue433-B-slsqp-SwLXLelq',
 'B-hybrid': '/tmp/issue433-B-hybrid-5PzsWpGE',
 'C-slsqp': '/tmp/issue433-C-slsqp-EykH3UuS',
 'C-hybrid': '/tmp/issue433-C-hybrid-K4uiXLRY',
}
p = load_constraint('RF-T008', allow_trial=True)
d = definition_from_data(json.loads((ROOT/'project/diagnostics/issue361/definition.json').read_bytes()))
model = build_rf_model(d, p)
req = compile_requirements(p, rf_input_file(ROOT, p['bands_file']), 'full_lpf')

def file_sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def evaluate(v, points, audit=False):
    physical = validate_values(d, model.schema, v, p, frozen_model=model)
    g = build_evaluation_grid(req, points)
    r = model.evaluator(g).evaluate(v)
    a = evaluate_requirements(r, req, requested_grid=g)
    result = {k: a[k] for k in ('strict_feasible', 'worst_il_db', 'max_violation_db', 'sum_violation_db')}
    result.update(samples=len(g.frequency_hz), grid_sha256=grid_fingerprint(g), physical=physical)
    for region in ('H2', 'H3'):
        result['min_'+region.lower()+'_db'] = min(float(np.min(r.il_db[g.segment == i.segment])) for i in req.intervals if i.region == region)
    if audit:
        result['independent'] = validate_response(model, v, r)
    return result

summary = {'source_head': '38736b563e652a910c3263c38dbfe7590a6d44bf', 'jobs': {}, 'dense': [], 'sample_accounting': {}}
search_samples = job_samples = 0
candidates = {}
for name, directory in JOBS.items():
    base = Path(directory); job = base/'job'
    result = json.loads((job/'result.json').read_bytes())
    inp = json.loads((job/'input.json').read_bytes())
    step = result['steps'][0]; opt = step['solver_result']
    assert result['forward_count'] == step['forward_count'] + result['selection']['forward_count'] + result['terminal']['forward_count']
    assert step['forward_count'] == (opt['evaluations'] if name.endswith('slsqp') else opt['nfev']) <= 20000
    times = (base/'time.txt').read_text()
    m = re.search(r'wall=([\d.]+) user=([\d.]+) sys=([\d.]+) maxrss_kb=(\d+) exit=(\d+)', times)
    assert m
    wall, user, system, rss, code = m.groups()
    assert int(code) == (0 if result['status'] == 'converged' else 4)
    samples = step['forward_count']*70 + result['selection']['forward_count']*84 + result['terminal']['forward_count']*476
    search_samples += step['forward_count']*70; job_samples += samples
    events = []
    for file in sorted((job/'checkpoints').glob('*.json')):
        event = json.loads(file.read_bytes())
        events.append({'file': file.name, 'sha256': file_sha(file), 'forward_count': event['forward_count'], 'best': event['best']})
    best = step['rf_best']; assert vector_sha(best['vector']) == best['vector_sha256']
    best17 = evaluate(best['vector'], 17)
    candidates[best['vector_sha256']] = (best['vector'], best17, name+'/rf_best')
    terminal = []
    for row in result['terminal']['candidates']:
        ranked = next(v for v in result['selection']['ranked'] if v['vector_sha256'] == row['vector_sha256'])
        assert vector_sha(ranked['vector']) == row['vector_sha256']
        a = row['assessment']
        a17 = {k: a[k] for k in ('strict_feasible', 'worst_il_db', 'max_violation_db', 'sum_violation_db', 'grid_fingerprint')}
        candidates[row['vector_sha256']] = (ranked['vector'], a17, name+'/terminal')
        terminal.append({'vector': ranked['vector'], 'vector_sha256': row['vector_sha256'], 'grid17': a17, 'independent': row['independent']})
    first = next((e['forward_count'] for e in events if e['best']['strict_feasible']), None)
    summary['jobs'][name] = {'tmp': directory, 'input_sha256': file_sha(job/'input.json'),
        'result_sha256': file_sha(job/'result.json'), 'source': inp['source'], 'source_sha256': inp['source_sha256'],
        'plan_sha256': inp['plan_sha256'], 'search_bounds_sha256': inp['search_bounds_sha256'],
        'start_sha256': inp['start']['vector_sha256'], 'status': result['status'], 'stop_reason': step['stop_reason'],
        'converged': step['converged'], 'nfev': opt['nfev'], 'ncev': opt.get('ncev'),
        'nit': opt.get('nit', opt.get('runs', [{}])[0].get('nit')), 'solver_message': opt.get('message', opt.get('runs', [{}])[0].get('message')),
        'search_forwards': step['forward_count'], 'selection_forwards': result['selection']['forward_count'],
        'terminal_forwards': result['terminal']['forward_count'], 'requested_completed_samples': samples,
        'wall_s': float(wall), 'cpu_user_s': float(user), 'cpu_system_s': float(system), 'maxrss_kb': int(rss), 'exit': int(code),
        'rf_best_search': best, 'rf_best_grid17': best17, 'terminal': terminal,
        'first_observed_strict_checkpoint_forward_upper_bound': first, 'checkpoints': events}

# Baseline + three initial 17s + the extra primary 84 used to compare MNA.
baseline_samples = 476+28028+84+3*476
best_samples = 6*476
ranked = sorted(((v[1]['worst_il_db'], digest, v) for digest, v in candidates.items() if v[1]['strict_feasible']))
for _, digest, (vector, grid17, origin) in ranked[:2]:
    # Count both primary 84-sample response and separate independent 84 MNA calls.
    dense = evaluate(vector, 1001)
    mna = evaluate(vector, 3, audit=True)
    summary['dense'].append({'origin': origin, 'vector': vector, 'vector_sha256': digest,
                             'grid17': grid17, 'dense1001': dense, 'selection84_mna': mna})
extra_samples = len(summary['dense'])*(28028+84)
total = baseline_samples + job_samples + best_samples + extra_samples
assert search_samples <= 8400000 and total <= 8600000
summary['sample_accounting'] = {'baseline_and_initial_primary': baseline_samples, 'job_search': search_samples,
    'job_total': job_samples, 'six_best_grid17': best_samples, 'dense_and_primary_mna_grid': extra_samples,
    'primary_requested_completed_total': total, 'independent_mna_samples': 84 + 2*6 + 84*len(summary['dense']),
    'sample_cap': 8600000}
(OUT/'results.json').write_text(json.dumps(summary, indent=2, allow_nan=False)+'\n')
print(json.dumps({'accounting':summary['sample_accounting'], 'dense':[(i['origin'],i['dense1001']['strict_feasible'],i['dense1001']['worst_il_db'],i['dense1001']['max_violation_db']) for i in summary['dense']]},indent=2))

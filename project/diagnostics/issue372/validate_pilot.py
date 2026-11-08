"""Bounded #372 read-only RF re-evaluation; separate from Pilot solver budget."""
import hashlib
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'src'))
import numpy as np
from lpf.constraint_versions import load_constraint
from lpf.rf_core.model import build_rf_model
from lpf.search._job_evaluation import source_identity
from lpf.search.component_constraints import validate_values
from lpf.search.performance import compile_requirements, evaluate_requirements
from lpf.search.plan import load_preflight
from lpf.search.proposals import definition_from_data
from lpf.search.storage import atomic_verified, plain, sha, vector_sha

RAW_SHA = {1001: '08d8eb09c6f0eb945ae8aff5a36b049fd4476fc8834e788fcf1d171f4ea42f4c',
           1002: 'ee8fcfc6177172c8d35c90bc6b558565b49796eabba19463656ec2da193b1782'}
CHECKPOINT_SHA = '4fbd86e8b46ad7bcb550ba327672b0983e8b58e9ce4b2a9364f8c6557a812b4b'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def metrics(il, grid, requirements):
    regions = np.array([requirements.intervals[int(i)].region for i in grid.segment])
    values = np.asarray(il)
    return dict(worst_il_db=float(np.max(values[np.isin(regions, ['UL', 'DL'])])),
                min_h2_db=float(np.min(values[regions == 'H2'])),
                min_h3_db=float(np.min(values[regions == 'H3'])))


def main():
    if len(sys.argv) != 3:
        raise SystemExit('usage: validate_pilot.py <pilot raw dir> <fresh validation dir>')
    pilot, output = map(Path, sys.argv[1:])
    if output.exists() or not output.parent.is_dir():
        raise ValueError('validation output must be fresh with existing parent')
    plan = load_preflight(ROOT/'project/diagnostics/issue372/pilot.yaml')
    definition_data = json.loads((ROOT/'project/diagnostics/issue361/definition.json').read_bytes())
    definition = definition_from_data(definition_data)
    policy = load_constraint('RF-T008', allow_trial=True)
    model = build_rf_model(definition, policy)
    req = compile_requirements(policy, ROOT/'rf/bands.csv', 'full_lpf')
    checkpoint = ROOT/'experiments/chatgpt_topology_search/runs/EXP-062/checkpoints/a6_best.json'
    if digest(checkpoint) != CHECKPOINT_SHA:
        raise ValueError('benchmark source SHA mismatch')
    c = json.loads(checkpoint.read_bytes()); t = c['topology']; x = c['vector']
    if (definition_data['inductor_tree']['edges'] != t['L_edges'] or
        definition_data['capacitor_placement']['fixed_edges'] != t['fixed_GJM_edges'] + t['PCB_C_edges'] or
        definition_data['capacitor_placement']['variable_edges'] != t['variable_C_edges'] or
        definition_data['capacitor_placement']['ic_fixed_edges'] != t['IC_fixed_C_parallel_edges'] or
        x != c['fixed_values']['L_nH'] + c['fixed_values']['GJM_C_pf'] + c['fixed_values']['PCB_C_pf'] +
        c['fixed_values']['k_signed'] + c['fixed_values']['IC_fixed_C_pf'] +
        sum([c['ic_variable_C_pf_by_setting'][k] for k in ['B71','B12','B28','B13+B14','B26','B8']], [])):
        raise ValueError('benchmark definition/vector mismatch')
    work = [('benchmark_70', 'hybrid/coarse', x), ('benchmark_17', 'terminal', x)]
    terminal = {}
    for seed in (1001, 1002):
        path = pilot/f'development-hybrid-{seed}.json'
        if digest(path) != RAW_SHA[seed]:
            raise ValueError('pilot worker byte SHA mismatch')
        raw = json.loads(path.read_bytes()); payload = raw['payload']
        if raw['window'] is not None or raw['confirmed']['requested'] != 210896:
            raise ValueError('pilot incomplete')
        best = payload['best_observed_by_stage']['hybrid/coarse']
        work.append((f'science_best_{seed}_17', 'terminal', best['vector']))
        row = next(b for b in payload['batches'] if b['stage'] == 'terminal')
        terminal[str(seed)] = dict(vector_sha256=row['vector_sha256'],
            metrics=metrics(row['response']['il_db'], plan.requested_grid('terminal'), req),
            strict_feasible=row['assessment']['strict_feasible'], physical_checks=row['physical_checks'],
            scientific_best_70_sha256=best['vector_sha256'],
            solver_output_sha256=payload['steps'][0]['output_vector_sha256'])
    for _, _, v in work:
        checks = validate_values(definition, model.schema, v, policy, frozen_model=model)
        if checks['component_policy_pass'] is not True or checks['min_L_eigenvalue_H'] <= 0:
            raise ValueError('invalid physical vector')
    output.mkdir(exist_ok=False)
    description = dict(kind='read_only_validation_not_pilot_or_exp', source=source_identity(ROOT),
        pilot_plan_sha256=plan.sha256, benchmark_checkpoint_sha256=CHECKPOINT_SHA, pilot_raw_sha256=RAW_SHA,
        dense='not_run', independent_mna='not_run', requested_upper=1498,
        operations=[dict(name=name, grid=grid, grid_sha256=plan.data['grids'][grid]['sha256'],
                         requested=plan.data['grids'][grid]['requested_samples_per_forward'],
                         vector=vector, vector_sha256=vector_sha(vector)) for name, grid, vector in work])
    assert sum(o['requested'] for o in description['operations']) == 1498
    atomic_verified(output/'plan.json', description)
    results = []
    for index, (name, grid_name, vector) in enumerate(work):
        grid = plan.requested_grid(grid_name); n = len(grid.frequency_hz)
        file = output/f'{index+1:02d}-{name}.json'
        atomic_verified(file, dict(status='unknown', requested=n, completed=0, operation=description['operations'][index]))
        start, cpu = time.perf_counter(), time.process_time()
        response = model.evaluator(grid).evaluate(vector)
        assessment = plain(evaluate_requirements(response, req, requested_grid=grid))
        record = dict(status='completed', requested=n, completed=n, operation=description['operations'][index],
            metrics=metrics(response.il_db, grid, req), assessment=assessment,
            physical_checks=plain(validate_values(definition, model.schema, vector, policy, frozen_model=model)),
            response=dict(s_real=response.s.real.tolist(), s_imag=response.s.imag.tolist(),
                **{k: getattr(response, k).tolist() for k in ('il_db','apl_db','in_rl_db','out_rl_db')}),
            wall_s=time.perf_counter()-start, cpu_s=time.process_time()-cpu)
        saved = atomic_verified(file, record)
        results.append(dict(name=name, requested=n, completed=n, metrics=record['metrics'],
            strict_feasible=assessment['strict_feasible'], vector_sha256=vector_sha(vector),
            min_L_eigenvalue_H=record['physical_checks']['min_L_eigenvalue_H'], file=file.name, sha256=saved['sha256']))
    summary = dict(status='completed', requested=1498, completed=1498, plan_sha256=digest(output/'plan.json'),
                   results=results, pilot_terminal_from_raw=terminal, dense='not_run', independent_mna='not_run')
    saved = atomic_verified(output/'summary.json', summary)
    print(json.dumps(dict(summary=summary, summary_sha256=saved['sha256']), sort_keys=True))

if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""Reproduce one bounded old/new RF-T010 comparison arm; never a formal EXP.

Usage: python compare.py ROOT old|new ARM EXISTING_OUTPUT_DIR
ARM: trf-single, trf-restart, trf-free, sequential, batch, partial,
     sequential-free, batch-free, partial-free, slp, slsqp.
Each invocation creates a fresh run directory and summary in OUTPUT_DIR.
Use the same Python/environment with ROOT at the corresponding Git revision.
"""
import json
from pathlib import Path
import sys
from unittest.mock import patch

root = Path(sys.argv[1]).resolve()
mode, name = sys.argv[2:4]
assert mode in ('old', 'new')
assert name in ('trf-single', 'trf-restart', 'trf-free', 'sequential', 'batch', 'partial',
                'sequential-free', 'batch-free', 'partial-free', 'slp', 'slsqp')
sys.path.insert(0, str(root / 'src'))
from lpf.search import _development_runner as runner, _development_worker as worker
from lpf.search.storage import vector_sha

config = json.loads((root / 'project/diagnostics/issue470/config.json').read_text())
starts = json.loads((root / 'project/diagnostics/issue470/starts.json').read_text())
step = config['arms'][0]['steps'][0]
n = 30
if name.startswith('trf'):
    options = dict(max_evaluations=n, ftol=1e-6, x_scale=1.0)
    if name in ('trf-restart', 'trf-free'):
        options['restart_sigma'] = .1
    elif mode == 'new':
        options['restart_sigma'] = None
    step.update(solver='trf', options=options)
elif name in ('slp', 'slsqp'):
    step.update(solver=name, aggregation='signed_max' if name == 'slp' else 'sum',
                options=dict(max_iterations=20, max_evaluations=n))
else:
    options = {'max_evaluations' if mode == 'new' else 'max_search_forwards': n,
               'restart_sigma': .1, 'batch_fd': not name.startswith('sequential'),
               'partial_fd': name.startswith('partial'), 'ftol': 1e-7}
    step.update(solver='lbfgsb' if mode == 'new' else 'hybrid', options=options)
cap = n + (24 if name.startswith(('batch', 'partial')) else 0)
config['budget'] = dict(rf_samples=70*cap+476, rf_forwards=cap+1, independent_mna_samples=2)

# Intercept objective notifications, including batch probes, after RF completion.
key = (name + '_minimize' if name in ('slp', 'slsqp') else
       'trf_minimize' if mode == 'new' and name.startswith('trf') else
       'least_squares_local' if name.startswith('trf') else
       'lbfgsb_minimize' if mode == 'new' else 'hybrid_minimize')
optimizer = getattr(worker, key)
trace = []


def wrapped(*args, **kwargs):
    callback_key = 'objective_callback' if kwargs.get('objective_callback') else 'progress_callback'
    callback = kwargs[callback_key]

    def record(x, value, *extra):
        trace.append([vector_sha(x), value])
        return callback(x, value, *extra)

    kwargs[callback_key] = record
    return optimizer(*args, **kwargs)


bounds = None
if name.endswith('-free'):
    from lpf.search.proposals import definition_from_data
    from lpf.minimax_profile import load_minimax_profile
    from lpf.search.component_constraints import physical_bounds
    definition = definition_from_data(json.loads((root / 'project/diagnostics/issue361/definition.json').read_text()))
    profile = load_minimax_profile('RF-T010', root=root, allow_trial=True)
    model = profile.build_model(definition)
    bounds = physical_bounds(definition, model.schema, json.loads(profile.base_json))
    vector = starts['1013']['baseline']['vector']
    bounds = [[x, x] if i != 0 else list(bounds[i]) for i, x in enumerate(vector)]

output = Path(sys.argv[4])
run_dir = output / f'{mode}-{name}'
with patch.object(worker, key, wrapped):
    runner.run(config, starts, run_dir, root=root, spot_checks={'terminal': [0, 111]},
               checkpoint_interval=5, search_bounds=bounds)
result = json.loads((run_dir / 'job-0001/result.json').read_text())
step = result['steps'][0]
summary = dict(name=name, trace=trace, result=step['solver_result'], forward_count=step['forward_count'],
               terminal_sha=result['terminal']['candidates'][0]['vector_sha256'],
               local_runs=step.get('local_runs', 1), details=step.get('local_run_details', []),
               constraint=result['rf_profile']['effective_sha256'])
(output / f'{mode}-{name}-summary.json').write_text(json.dumps(summary, sort_keys=True))
print(mode, name, 'forwards', step['forward_count'], 'runs', summary['local_runs'], 'reason', step['stop_reason'])

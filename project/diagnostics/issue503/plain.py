#!/usr/bin/env python3
"""One bounded TRF development diagnostic; output must be a fresh temporary path."""
import json
from pathlib import Path
import sys
from time import perf_counter, process_time

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT/'src'))
import numpy as np
from lpf.minimax_profile import signed_margins
from lpf.search import _development_runner as runner
from lpf.search.plan import grid_from_record

config = json.loads((ROOT/'project/diagnostics/issue470/config.json').read_text())
starts = json.loads((ROOT/'project/diagnostics/issue470/starts.json').read_text())
config['arms'][0]['steps'][0].update(solver='trf', options={'max_evaluations': 3})
config['budget'] = dict(rf_samples=70*3+476, rf_forwards=4, independent_mna_samples=5)
spots = {'baseline/search': [0], 'terminal': [0, 111]}
out = Path(sys.argv[1])
wall, cpu = perf_counter(), process_time()
state = runner.run(config, starts, out, root=ROOT, spot_checks=spots, checkpoint_interval=1)
wall, cpu = perf_counter()-wall, process_time()-cpu
result = json.loads((out/'job-0001/result.json').read_text())
plan, _, profile, model, _ = runner.freeze_run(config, starts, root=ROOT, spot_checks=spots,
                                                search_bounds=None, checkpoint_interval=1)
step = result['steps'][0]; terminal = result['terminal']['candidates'][0]
grid = grid_from_record(plan.data['grids']['baseline/search'])
# One additional scalar diagnostic forward, outside the Runner reservation.
response = model.evaluator(grid).evaluate(step['solver_result']['x'])
search_j, _ = signed_margins(profile, grid, response)
def metrics(grid, il):
    passed = np.array([profile.records[i]['type'] == 'pass' for i in grid.segment])
    return dict(worst_pass_il_db=float(np.max(np.asarray(il)[passed])),
                minimum_h2_h3_atten_db=float(np.min(np.asarray(il)[~passed])))
tgrid = grid_from_record(plan.data['grids']['terminal'])
summary = dict(plan_sha256=plan.sha256, source_sha256=state['source_sha256'], source=result['source'],
    rf_profile=plan.data['rf_profile'], grids={k: v['sha256'] for k, v in plan.data['grids'].items()},
    seed=1013, initial_vector_sha256=result['initial_vector_sha256'],
    selected_vector_sha256=terminal['vector_sha256'], actual=state['jobs'][0]['actual'],
    additional_diagnostic_forwards=1, additional_diagnostic_samples=len(grid.frequency_hz),
    status=result['status'], stop_reason=step['stop_reason'], trf_details=step['trf_details'],
    search=dict(signed_max_margin_db=search_j, **metrics(grid, response.il_db)),
    terminal=dict(signed_max_margin_db=terminal['terminal_signed_max_margin_db'],
                  independent=terminal['independent']['status'], **metrics(tgrid, terminal['response']['il_db'])),
    run_wall_s=wall, run_cpu_s=cpu)
print(json.dumps(summary, indent=2, sort_keys=True))

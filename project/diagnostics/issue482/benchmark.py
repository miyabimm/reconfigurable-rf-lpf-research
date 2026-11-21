"""Bounded development A/B; writes verified raw runs under a fresh system-temp directory."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import time
import tracemalloc

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT/'src'))
from lpf.search import _development_runner as runner

config = json.loads((ROOT/'project/diagnostics/issue470/config.json').read_text())
starts = json.loads((ROOT/'project/diagnostics/issue470/starts.json').read_text())
root = Path(tempfile.mkdtemp(prefix='issue482-ab-'))
print('raw:', root, flush=True)


def run(batch, name, memory=False, timing=False):
    cfg = copy.deepcopy(config)
    opts = cfg['arms'][0]['steps'][0]['options']
    opts.update(max_search_forwards=312, batch_fd=batch)
    cfg['budget'] = dict(rf_samples=70*(312+24) + 476, rf_forwards=337, independent_mna_samples=2)
    if memory:
        tracemalloc.start()
    start = time.perf_counter()
    runner.run(cfg, starts, root/name, root=ROOT, spot_checks={'terminal': [0, 111]},
               checkpoint_interval=1000, rf_cache_mode='lk',
               **({'timing_output': root/(name+'-timing.json'), 'timing_level': 'timed'} if timing else {}))
    wall = time.perf_counter()-start
    peak = tracemalloc.get_traced_memory()[1] if memory else None
    if memory:
        tracemalloc.stop()
    result = json.loads((root/name/'job-0001/result.json').read_text())
    step = result['steps'][0]
    term = result['terminal']['candidates'][0]
    return dict(mode='batch' if batch else 'scalar', name=name, wall_s=wall, peak_bytes=peak,
                plan_sha256=result['plan_sha256'], rf=result['rf_profile'], costs=result['costs'],
                grid_sha256=step['grid_sha256'], terminal_grid_sha256=result['terminal_grid_sha256'],
                best=step['solver_result'], local_runs=step['local_run_details'],
                terminal_j=term['terminal_signed_max_margin_db'], terminal=term)


# Warmup is excluded; alternate order for all plain observations.
for batch in (False, True):
    run(batch, 'warmup-'+str(batch))
rows = []
for i in range(4):
    for batch in ((False, True) if i % 2 == 0 else (True, False)):
        rows.append(run(batch, f'plain-{i}-{batch}'))
        print(rows[-1]['name'], rows[-1]['wall_s'], flush=True)
for batch in (False, True):
    rows.append(run(batch, f'timed-{batch}', timing=True))
    rows.append(run(batch, f'memory-{batch}', memory=True))
# Full records remain in raw; keep the JSON output small.
for r in rows:
    r.pop('terminal')
(root/'summary.json').write_text(json.dumps(rows, indent=2, allow_nan=False)+'\n')
print('summary:', root/'summary.json')

"""Issue 484 development-only A/B; temporary runner output is disposable."""
import copy
import hashlib
import json
import os
import platform
import statistics
import subprocess
import sys
import tempfile
import time
import tracemalloc
from pathlib import Path

import numpy as np
import scipy
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT/'src'))
from lpf.minimax_profile import _margin_parameters
from lpf.search import _development_runner as runner
from lpf.search.development_plan import freeze_run
from lpf.search.plan import grid_from_record

cfg = json.loads((ROOT/'project/diagnostics/issue470/config.json').read_text())
starts = json.loads((ROOT/'project/diagnostics/issue470/starts.json').read_text())
plan, _, profile, model, bounds = freeze_run(cfg, starts, root=ROOT,
    spot_checks={'terminal': [0, 111]}, search_bounds=None, checkpoint_interval=1000)
grid = grid_from_record(plan.data['grids']['baseline/search'])
x = np.array(plan.data['jobs'][0]['vector'])
lo, hi = np.asarray(bounds).T
free = hi > lo
z = (x[free]-lo[free])/(hi[free]-lo[free])
xs = []
for j in range(len(z)):
    zj = z.copy(); zj[j] += 1e-8 if z[j] + 1e-8 <= 1 else -1e-8
    y = lo.copy(); y[free] = np.clip(lo[free] + zj*(hi[free]-lo[free]), lo[free], hi[free])
    xs.append(y)
xs = np.array(xs)
schema = model.schema
start = schema.vector_length - 6 * schema.n_variable
mask = np.ones((len(xs), len(grid.setting)), bool)
for i, y in enumerate(xs):
    changed = np.flatnonzero(y != x)
    if len(changed) == 1 and start <= changed[0] < schema.vector_length:
        mask[i] = grid.setting == (changed[0]-start)//schema.n_variable

summary = dict(head=subprocess.check_output(['git','rev-parse','HEAD'], cwd=ROOT, text=True).strip(),
    diff_sha256=hashlib.sha256(subprocess.check_output(['git','diff'], cwd=ROOT)).hexdigest(),
    profile=profile.fingerprint, grid=plan.data['grids']['baseline/search']['sha256'],
    candidates_sha256=hashlib.sha256(xs.astype('<f8').tobytes()).hexdigest(),
    python=platform.python_version(), numpy=np.__version__, scipy=scipy.__version__,
    platform=platform.platform(), threads={k:os.environ.get(k) for k in ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS')},
    mask_samples=mask.sum(axis=1).tolist())

def rf(mode):
    ev = model.evaluator(grid, cache_mode='lk')
    base = ev.evaluate(x)  # all paths get identical warmed L/k and base outside timing
    def call():
        if mode == 'scalar': return tuple(ev.evaluate(y) for y in xs)
        if mode == 'batch': return ev.evaluate_batch(xs)
        return ev.evaluate_partial_batch(xs, base, mask)
    return call

reference = rf('batch')(); partial = rf('partial')()
threshold, direction = _margin_parameters(profile, grid)
residuals = lambda rr: np.array([direction*(r.il_db-threshold) for r in rr])
objectives = lambda rr: np.sum(np.maximum(residuals(rr), 0)**2, axis=1)
f0 = np.sum(np.maximum(direction*(model.evaluator(grid).evaluate(x).il_db-threshold), 0)**2)
summary['equivalence'] = {k: dict(equal=bool(np.array_equal(np.array([getattr(r,k) for r in reference]), np.array([getattr(r,k) for r in partial]))),
    max_abs=float(np.max(np.abs(np.array([getattr(r,k) for r in reference])-np.array([getattr(r,k) for r in partial])))))
    for k in ('s','il_db','apl_db','in_rl_db','out_rl_db')}
summary['equivalence']['residual_equal'] = bool(np.array_equal(residuals(reference), residuals(partial)))
summary['equivalence']['objective_equal'] = bool(np.array_equal(objectives(reference), objectives(partial)))
summary['equivalence']['gradient_max_abs'] = float(np.max(np.abs((objectives(reference)-f0)/1e-8 - (objectives(partial)-f0)/1e-8)))
for mode in ('scalar','batch','partial'): rf(mode)()
times = {k:[] for k in ('scalar','batch','partial')}
for i in range(6):
    for mode in (('scalar','batch','partial') if i%2 == 0 else ('partial','batch','scalar')):
        calls = [rf(mode) for _ in range(5)]
        t = time.perf_counter()
        for call in calls: call()
        times[mode].append((time.perf_counter()-t)*200)
peaks = {}
for mode in times:
    call = rf(mode); tracemalloc.start(); call(); peaks[mode] = tracemalloc.get_traced_memory()[1]; tracemalloc.stop()
summary['rf'] = dict(ms=times, peak_bytes=peaks)

with tempfile.TemporaryDirectory(prefix='issue484-ab-') as tmp:
    tmp = Path(tmp)
    def run(partial, name, measurement=None):
        config = copy.deepcopy(cfg)
        config['arms'][0]['steps'][0]['options'].update(max_search_forwards=312, batch_fd=True, partial_fd=partial)
        config['budget'] = dict(rf_samples=70*(312+24)+476, rf_forwards=337, independent_mna_samples=2)
        timing = tmp/(name+'-timing.json')
        if measurement == 'memory': tracemalloc.start()
        t = time.perf_counter()
        runner.run(config, starts, tmp/name, root=ROOT, spot_checks={'terminal':[0,111]},
            checkpoint_interval=1000, rf_cache_mode='lk',
            **(dict(timing_output=timing, timing_level='deep') if measurement == 'deep' else {}))
        wall = time.perf_counter()-t
        peak = tracemalloc.get_traced_memory()[1] if measurement == 'memory' else None
        if measurement == 'memory': tracemalloc.stop()
        result = json.loads((tmp/name/'job-0001/result.json').read_text())
        checkpoints = [json.loads(p.read_text()) for p in sorted((tmp/name/'job-0001/checkpoints').glob('*.json'))]
        diagnostics = json.loads(timing.read_text()) if measurement == 'deep' else None
        return dict(wall_s=wall, peak_bytes=peak, plan_sha256=result['plan_sha256'],
                    costs=result['costs'], ledger=result['ledger'], step=result['steps'][0],
                    terminal=result['terminal'], checkpoints=[(c['forward_count'], c['observation']) for c in checkpoints],
                    deep=diagnostics)
    for p in (False, True): run(p, f'warm-{p}')
    results = {False:[], True:[]}
    for i in range(4):
        for p in ((False,True) if i%2 == 0 else (True,False)):
            results[p].append(run(p, f'plain-{i}-{p}'))
    a, b = results[False][0], results[True][0]
    summary['runner'] = dict(wall_s={str(p):[r['wall_s'] for r in results[p]] for p in results},
        plans=[a['plan_sha256'], b['plan_sha256']], costs=[a['costs'],b['costs']],
        solver_equal=a['step']['solver_result']==b['step']['solver_result'],
        local_runs_equal=a['step']['local_run_details']==b['step']['local_run_details'],
        terminal_equal=a['terminal']==b['terminal'], checkpoints_equal=a['checkpoints']==b['checkpoints'],
        ledger_equal=a['ledger']==b['ledger'], solver=[a['step']['solver_result'],b['step']['solver_result']])
    for p in (False,True):
        r = run(p, f'memory-{p}', 'memory'); summary['runner'].setdefault('peak_bytes', {})[str(p)] = r['peak_bytes']
        r = run(p, f'deep-{p}', 'deep'); summary['runner'].setdefault('deep', {})[str(p)] = dict(wall_s=r['wall_s'], data=r['deep'])
print(json.dumps(summary, indent=2, allow_nan=False))

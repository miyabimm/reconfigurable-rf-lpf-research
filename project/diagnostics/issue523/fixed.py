#!/usr/bin/env python3
"""Fixed-vector RF-core diagnostic; no Runner, search or production patching."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import resource
import subprocess
import sys
import time

p = argparse.ArgumentParser()
p.add_argument('root', type=Path)
p.add_argument('output', type=Path)
p.add_argument('--repetitions', type=int, default=30)
a = p.parse_args()
root = a.root.resolve()
sys.path.insert(0, str(root/'src'))
sys.path.insert(0, str(root/'project/diagnostics/issue517'))
import numpy as np
import lpf.rf_core.model as model_module
from measure import setup, SEEDS, THREADS
from lpf.search.plan import grid_from_record
from lpf.search.storage import vector_sha
from lpf.search._rf_deep_timing import search_rf_timing
from lpf.timing import TimerCollector

assert all(os.environ.get(k) == '1' for k in THREADS)
assert not a.output.exists()
fixed_path = root/'project/diagnostics/issue519/vectors.json'
fixed = json.loads(fixed_path.read_text())
result = dict(commit=subprocess.check_output(['git', '-C', str(root), 'rev-parse', 'HEAD'], text=True).strip(),
              model_import=model_module.__file__, python=platform.python_version(), numpy=np.__version__,
              affinity=sorted(os.sched_getaffinity(0)), threads={k: os.environ[k] for k in THREADS},
              vectors_sha256=hashlib.sha256(fixed_path.read_bytes()).hexdigest(), repetitions=a.repetitions, rows=[])
arrays = {}
for seed in SEEDS:
    _, starts, _, plan, _, model = setup(seed)
    ev = model.evaluator(grid_from_record(plan.data['grids']['baseline/search']))
    vectors = [('initial', starts[str(seed)]['baseline']['vector'])]
    vectors += [(k, v['vector']) for k, v in fixed.items() if k.startswith(str(seed)+'-')]
    assert len(vectors) == 3
    for name, x in vectors:
        key = f'{seed}-{name}'
        response, jac = ev.evaluate_with_il_jacobian(x)
        for field in ('s', 'il_db', 'apl_db', 'in_rl_db', 'out_rl_db'):
            arrays[key+'-'+field] = getattr(response, field)
        arrays[key+'-jac'] = jac
        wall = []; cpu = []
        for _ in range(a.repetitions):
            t, c = time.perf_counter_ns(), time.process_time_ns()
            ev.evaluate_with_il_jacobian(x)
            wall.append(time.perf_counter_ns()-t); cpu.append(time.process_time_ns()-c)
        timer = TimerCollector()
        with search_rf_timing(timer, 'search'):
            deep_response, deep_jac = ev.evaluate_with_il_jacobian(x)
        np.testing.assert_array_equal(deep_jac, jac)
        for field in ('s', 'il_db', 'apl_db', 'in_rl_db', 'out_rl_db'):
            np.testing.assert_array_equal(getattr(deep_response, field), getattr(response, field))
        result['rows'].append(dict(seed=seed, vector=name, vector_sha256=vector_sha(x), plan_sha256=plan.sha256,
                                   wall_ns=wall, cpu_ns=cpu, deep=timer.snapshot()))
result['peak_rss_kib'] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
np.savez_compressed(a.output.with_suffix('.npz'), **arrays)
a.output.write_text(json.dumps(result, indent=2, allow_nan=False)+'\n')

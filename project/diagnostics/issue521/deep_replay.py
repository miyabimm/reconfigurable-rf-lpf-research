#!/usr/bin/env python3
"""Replay nine fixed vectors in one fixed checkout; no optimization or search runner."""
import hashlib
import json
import os
from pathlib import Path
import platform
import sys
import time

import numpy as np
import scipy
CHECKOUT = Path.cwd().resolve()
sys.path.insert(0, str(CHECKOUT/'project/diagnostics/issue517'))
from measure import SEEDS, THREADS, setup
from lpf.rf_core import model, coupled_lc
from lpf.optimizers import trf
from lpf.search.plan import grid_from_record
from lpf.search._rf_deep_timing import search_rf_timing
from lpf.search.storage import vector_sha
from lpf.timing import TimerCollector


def fingerprint(response, jac):
    h = hashlib.sha256()
    for a in (response.s, response.il_db, response.apl_db, response.in_rl_db, response.out_rl_db, jac):
        h.update(np.ascontiguousarray(a).tobytes())
    return h.hexdigest()


def main(out, repetitions):
    assert all(os.environ.get(k) == '1' for k in THREADS)
    checkout = Path.cwd().resolve()
    assert Path(model.__file__).is_relative_to(checkout/'src')
    result = {'cwd': str(checkout), 'model_import': model.__file__, 'coupled_import': coupled_lc.__file__,
              'trf_import': trf.__file__, 'python': platform.python_version(), 'numpy': np.__version__,
              'scipy': scipy.__version__, 'affinity': sorted(os.sched_getaffinity(0)),
              'threads': {k: os.environ[k] for k in THREADS}, 'repetitions': repetitions, 'rows': []}
    fixed = json.loads((CHECKOUT/'project/diagnostics/issue519/vectors.json').read_text())
    for seed in SEEDS:
        _, starts, _, plan, _, rf_model = setup(seed)
        ev = rf_model.evaluator(grid_from_record(plan.data['grids']['baseline/search']))
        vectors = [('initial', starts[str(seed)]['baseline']['vector'])]
        vectors += [(k, v['vector']) for k, v in fixed.items() if k.startswith(str(seed)+'-')]
        for name, x in vectors:
            for _ in range(2): ev.evaluate_with_il_jacobian(x)
            reference = fingerprint(*ev.evaluate_with_il_jacobian(x))
            timings = {}; timer = TimerCollector()
            for mode in ('plain', 'deep'):
                rows = []
                def execute():
                    for _ in range(repetitions):
                        wall, cpu = time.perf_counter_ns(), time.process_time_ns()
                        response, jac = ev.evaluate_with_il_jacobian(x)
                        rows.append([time.perf_counter_ns()-wall, time.process_time_ns()-cpu])
                        assert fingerprint(response, jac) == reference
                if mode == 'deep':
                    with search_rf_timing(timer, 'replay'):
                        execute()
                else:
                    execute()
                timings[mode] = rows
            result['rows'].append({'seed': seed, 'vector': name, 'vector_sha256': vector_sha(x),
                                   'response_jac_sha256': reference, 'timings_ns': timings, 'regions': timer.snapshot()})
            print(checkout.name, seed, name, flush=True)
    out.write_text(json.dumps(result, indent=2, allow_nan=False)+'\n')


if __name__ == '__main__':
    out = Path(sys.argv[1]); assert not out.exists(); main(out, int(sys.argv[2]))

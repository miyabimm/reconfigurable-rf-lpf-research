#!/usr/bin/env python3
"""Compare every RF input, response and Jacobian between observed plain/deep Runs.

Hashing adds overhead in both modes, so do not use these runs for speed. Both
modes retain the production evaluation path and identical frozen settings.
"""
import hashlib
import json
import os
from pathlib import Path
import sys
import numpy as np
from measure import ROOT, SEEDS, THREADS, setup, save
from lpf.rf_core.model import RFEvaluator
from lpf.search import _development_runner as runner


def run(out):
    assert all(os.environ.get(k) == '1' for k in THREADS)
    out = Path(out).resolve()
    assert out.parent == Path('/tmp') and not out.exists()
    out.mkdir()
    result = dict(note='Additional intrusive hash observation; not plain timing', runs=[])
    save(out/'summary.json', result)
    for seed in SEEDS:
        config, starts, spots, plan, _, _ = setup(seed)
        for mode in ('plain', 'deep'):
            digest, count = hashlib.sha256(), [0]
            original = RFEvaluator.evaluate_with_il_jacobian
            def observed(ev, vector):
                response, jac = original(ev, vector)
                for value in (vector, response.s, response.il_db, response.apl_db,
                              response.in_rl_db, response.out_rl_db, jac):
                    digest.update(np.ascontiguousarray(value).tobytes())
                count[0] += 1
                return response, jac
            RFEvaluator.evaluate_with_il_jacobian = observed
            kwargs = dict(root=ROOT, spot_checks=spots, checkpoint_interval=1000)
            if mode == 'deep': kwargs.update(timing_output=out/f'{seed}-timing.json', timing_level='deep')
            try:
                state = runner.run(config, starts, out/f'{seed}-{mode}', **kwargs)
            finally:
                RFEvaluator.evaluate_with_il_jacobian = original
            step = json.loads((out/f'{seed}-{mode}'/'job-0001/result.json').read_text())['steps'][0]
            result['runs'].append(dict(seed=seed, mode=mode, trace_sha256=digest.hexdigest(), count=count[0],
                actual=state['jobs'][0]['actual'], selected=step['solver_result']))
            save(out/'summary.json', result)
            print(seed, mode, count[0], digest.hexdigest(), flush=True)
        a, b = result['runs'][-2:]
        assert all(a[k] == b[k] for k in ('trace_sha256', 'count', 'actual', 'selected'))
    result['equivalence'] = 'PASS'
    save(out/'summary.json', result)

if __name__ == '__main__': run(sys.argv[1])

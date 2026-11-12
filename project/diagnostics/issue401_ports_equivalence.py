#!/usr/bin/env python3
"""Three named real-RF vectors: compare response/requirement array digests."""
import hashlib
import json
import os
from pathlib import Path

import numpy as np
from lpf.constraint_versions import load_constraint
from lpf.search._job_evaluation import source_identity
from lpf.search._worker_next import MinimalWorker
from lpf.search.plan import ROOT, load_preflight
from lpf.search.proposals import definition_from_data
from lpf.search.starts import load_explicit
from lpf.search.storage import sha, vector_sha


def digest(a):
    a = np.ascontiguousarray(a)
    return dict(dtype=a.dtype.str, shape=list(a.shape), sha256=hashlib.sha256(a.tobytes()).hexdigest())


def main():
    if any(os.environ.get(k) != '1' for k in ('OPENBLAS_NUM_THREADS', 'OMP_NUM_THREADS', 'MKL_NUM_THREADS')):
        raise ValueError('Single-thread required')
    identity = source_identity(ROOT)
    if sha(identity) != os.environ.get('ISSUE401_EXPECTED_SOURCE_SHA'):
        raise ValueError('Source identity mismatch before forward')
    plan = load_preflight('project/diagnostics/issue377/baseline.yaml')
    ref = plan.data['config']['definition']
    definition = definition_from_data(json.loads((ROOT / ref['path']).read_bytes()))
    policy = load_constraint('RF-T008', root=ROOT, allow_trial=True)
    start = load_explicit(ROOT / 'project/diagnostics/issue401_starts_1002.json')[1002]
    if (plan.sha256 != '8ac7bab9567918ae5c656fd449807ad2c38c1e1cad9e39c8ed217b95a569043e' or
            start['vector_sha256'] != '6203467121a4e37baaa51c471aaecb3174f3374f9ab955d6fbf101f7b5ce935f' or
            vector_sha(start['vector']) != start['vector_sha256']):
        raise ValueError('Plan/vector mismatch')
    worker = MinimalWorker(plan, definition, policy, 'hybrid', 1002, start['vector'], start['vector_sha256'], root=ROOT)
    if (len(worker.grid.frequency_hz) != 70 or
            worker.model.policy_fingerprint != 'e682165c72d3a8b9f1384a2529f71bacfebfc9d17164d4af5af879e4a138b532'):
        raise ValueError('Grid/policy mismatch')
    vectors = [np.asarray(start['vector'], dtype=float)]
    for index in (0, -1):
        v = vectors[0].copy(); lo, hi = worker.bounds[index]; v[index] = (lo + hi) / 2
        vectors.append(v)
    rows = []
    for v in vectors:
        response, assessment = worker.evaluate(v)
        rows.append(dict(vector=v.tolist(), vector_sha=vector_sha(v),
            response={name: digest(getattr(response, name)) for name in ('s', 'il_db', 'apl_db', 'in_rl_db', 'out_rl_db')},
            mandatory_g=digest(assessment['mandatory_g']), worst_il_db=assessment['worst_il_db']))
    if source_identity(ROOT) != identity:
        raise ValueError('Source identity changed during comparison')
    print(json.dumps(dict(source=identity, source_sha=sha(identity), plan_sha=plan.sha256,
                          grid_sha=plan.data['grids']['hybrid/coarse']['sha256'], rows=rows),
                     sort_keys=True, allow_nan=False))


if __name__ == '__main__':
    main()

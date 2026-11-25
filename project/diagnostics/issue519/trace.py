#!/usr/bin/env python3
"""Intrusive separate search vector hashes; never use these times for benchmarking."""
import hashlib
import json
import os
from pathlib import Path
import sys
import numpy as np
from probe import activate, restore
from measure import ROOT, SEEDS, THREADS, setup, save
from lpf.rf_core.model import RFEvaluator
from lpf.search import _development_runner as runner


def main(out):
    assert all(os.environ.get(k) == '1' for k in THREADS)
    out = Path(out).resolve(); assert out.parent == Path('/tmp') and not out.exists(); out.mkdir()
    summary = {'note':'intrusive trace; separate from plain measurements', 'runs': []}
    for seed in SEEDS:
        config, starts, spots, plan, _, _ = setup(seed)
        ref_vectors = None
        for mode in ('base','A','B','AB'):
            activate(mode)
            original = RFEvaluator.evaluate_with_il_jacobian
            vectors, digest = [], hashlib.sha256()
            def observed(ev, vector):
                v = np.asarray(vector, dtype='<f8').copy(); vectors.append(v); digest.update(v.tobytes())
                return original(ev, vector)
            RFEvaluator.evaluate_with_il_jacobian = observed
            try:
                state = runner.run(config, starts, out/f'{seed}-{mode}', root=ROOT,
                                   spot_checks=spots, checkpoint_interval=1000)
            finally:
                RFEvaluator.evaluate_with_il_jacobian = original
            vectors = np.asarray(vectors)
            if ref_vectors is None:
                ref_vectors = vectors
                first = None
            else:
                differing = np.flatnonzero(np.any(vectors != ref_vectors, axis=1))
                first = int(differing[0]) if len(differing) else None
            summary['runs'].append({'seed':seed,'mode':mode,'count':len(vectors),
                'vector_sequence_sha256':digest.hexdigest(),'first_different_zero_based':first,
                'actual':state['jobs'][0]['actual']})
            save(out/'summary.json', summary)
            print(seed,mode,len(vectors),first,flush=True)

if __name__ == '__main__':
    try: main(sys.argv[1])
    finally: restore()

#!/usr/bin/env python3
"""Intrusive production vector-sequence SHA vs the prior AB trace, not timing."""
import hashlib
import json
import os
from pathlib import Path
import sys
import numpy as np
from compare20 import ROOT, THREADS, prepare, save
from lpf.rf_core.model import RFEvaluator
from lpf.search import _development_runner as runner


def main(directory):
    assert all(os.environ.get(k)=='1' for k in THREADS)
    out=Path(directory).resolve(); assert out.parent==Path('/tmp') and not out.exists(); out.mkdir()
    previous=json.loads((ROOT/'project/diagnostics/issue519/results.json').read_text())['trace']
    summary={'note':'intrusive observer, not plain timing','runs':[]}
    save(out/'summary.json',summary)
    for seed in (1001,1010,1020):
        config,starts,spots,plan=prepare(seed,5000)
        reference=next(row for row in previous if row['seed']==seed and row['mode']=='AB')
        digest,count=hashlib.sha256(),[0]
        original=RFEvaluator.evaluate_with_il_jacobian
        def observed(ev,vector):
            value=np.asarray(vector,dtype='<f8').copy()
            digest.update(value.tobytes()); count[0]+=1
            return original(ev,vector)
        RFEvaluator.evaluate_with_il_jacobian=observed
        try:
            state=runner.run(config,starts,out/str(seed),root=ROOT,spot_checks=spots,checkpoint_interval=1000)
        finally:
            RFEvaluator.evaluate_with_il_jacobian=original
        sha=digest.hexdigest()
        assert count[0]==reference['count']==5000 and sha==reference['vector_sequence_sha256']
        summary['runs'].append({'seed':seed,'count':count[0],'vector_sequence_sha256':sha,
                                'historical_sha256':reference['vector_sequence_sha256'],
                                'actual':state['jobs'][0]['actual'],'plan_sha256':plan.sha256})
        save(out/'summary.json',summary)
        print(seed,count[0],sha,flush=True)
    summary['status']='PASS'; save(out/'summary.json',summary)

if __name__=='__main__': main(sys.argv[1])

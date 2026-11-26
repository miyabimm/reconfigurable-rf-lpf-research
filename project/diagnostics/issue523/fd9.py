#!/usr/bin/env python3
"""All columns of nine fixed vectors: independent normalized IL and complex S FD."""
import json
from pathlib import Path
import sys
import numpy as np
root, out = Path(sys.argv[1]).resolve(), Path(sys.argv[2]); assert not out.exists()
sys.path[:0] = [str(root/'src'), str(root/'project/diagnostics/issue517')]
from measure import setup, SEEDS
from lpf.search.plan import grid_from_record
from lpf.search.storage import vector_sha
fixed = json.loads((root/'project/diagnostics/issue519/vectors.json').read_text())
rows=[]
for seed in SEEDS:
    _, starts, _, plan, _, model = setup(seed)
    ev=model.evaluator(grid_from_record(plan.data['grids']['baseline/search']))
    bounds=np.asarray(plan.data['search_bounds']); width=bounds[:,1]-bounds[:,0]
    vectors=[('initial', starts[str(seed)]['baseline']['vector'])]
    vectors += [(k,v['vector']) for k,v in fixed.items() if k.startswith(str(seed)+'-')]
    for name,vector in vectors:
        x=np.array(vector); response,jac=ev.evaluate_with_il_jacobian(x)
        # Capture all four compact external S derivatives via the existing cascade hook.
        import lpf.rf_core.model as rf
        from unittest.mock import patch
        capture=[]; old=rf._cascade_jacobian
        def observe(a,da,b,db):
            v=old(a,da,b,db)
            if db is None: capture.append((rf._cascade(a,b),v.copy()))
            return v
        with patch.object(rf,'_cascade_jacobian',observe): ev.evaluate_with_il_jacobian(x)
        full,df=capture[0]; z=np.array([ev.source_ohms,ev.load_ohms]); beta=(np.sqrt(50)-z/np.sqrt(50))/(2*np.sqrt(z.real)); delta=(np.sqrt(50)+z.conj()/np.sqrt(50))/(2*np.sqrt(z.real)); s=response.s
        P=np.diag(delta)-s*beta[None,None,:]; Q=np.diag(delta)-beta[None,:,None]*s
        ds=P[:,None]@df@Q[:,None]; shared=len(x)-6*model.schema.n_variable
        restored=np.zeros((len(s),len(x),2,2),complex); restored[:,:shared]=ds[:,:shared]
        cols=shared+ev.grid.setting[:,None]*model.schema.n_variable+np.arange(model.schema.n_variable)
        restored[np.arange(len(s))[:,None],cols]=ds[:,shared:]
        fails={'il':0,'s11':0,'s21':0,'s22':0,'s12':0}; worst={k:0. for k in fails}; h=1e-6
        for j in range(len(x)):
            step=h*width[j]
            if x[j]-step>=bounds[j,0] and x[j]+step<=bounds[j,1]:
                xp=x.copy(); xm=x.copy();xp[j]+=step;xm[j]-=step
                a,b=ev.evaluate(xp),ev.evaluate(xm); di=(a.il_db-b.il_db)/(2*h); dS=(a.s-b.s)/(2*h)
            else:
                sign=1 if x[j]-step<bounds[j,0] else -1
                x1=x.copy();x2=x.copy();x1[j]+=sign*step;x2[j]+=sign*2*step
                a,b=ev.evaluate(x1),ev.evaluate(x2)
                di=sign*(-3*response.il_db+4*a.il_db-b.il_db)/(2*h)
                dS=sign*(-3*response.s+4*a.s-b.s)/(2*h)
            pairs=[('il',jac[:,j]*width[j],di,1e-5)]
            pairs += [(key,restored[:,j,r,c]*width[j],dS[:,r,c],1e-7) for key,r,c in [('s11',0,0),('s21',1,0),('s22',1,1),('s12',0,1)]]
            for key,exact,fd,atol in pairs:
                delta=np.abs(exact-fd); tol=atol+1e-4*np.abs(fd)
                fails[key]+=int(np.count_nonzero(delta>tol)); worst[key]=max(worst[key],float(delta.max()))
        rows.append(dict(seed=seed,vector=name,vector_sha256=vector_sha(x),h_normalized=h,failed_samples=fails,max_abs=worst))
out.write_text(json.dumps(rows,indent=2,allow_nan=False)+'\n')

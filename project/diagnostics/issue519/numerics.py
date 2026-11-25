#!/usr/bin/env python3
"""Compare Schur and cascade derivatives on retained #517 vectors and edge cases."""
import json
import os
from pathlib import Path
import sys
import numpy as np
from probe import HERE, SEEDS, THREADS, setup, cascade_one_side, OLD_CASCADE
from lpf.rf_core.model import _cascade, power_response
from lpf.minimax_profile import _margin_parameters
from lpf.search.plan import grid_from_record
from lpf.search.storage import vector_sha


def compare(a,b):
    d = np.abs(a-b)
    return {'max_abs':float(np.max(d)), 'max_relative_global':float(np.max(d)/max(np.max(np.abs(a)),1e-300))}


def main(out):
    assert all(os.environ.get(k) == '1' for k in THREADS)
    fixed = json.loads((HERE/'vectors.json').read_text()); result={'schur':[],'cascade_edges':[]}
    for seed in SEEDS:
        _, starts, _, plan, profile, model = setup(seed)
        width=np.diff(np.asarray(plan.data['search_bounds']),axis=1).ravel()
        ev = model.evaluator(grid_from_record(plan.data['grids']['baseline/search']))
        vectors = [('initial', starts[str(seed)]['baseline']['vector'])] + [(k,v['vector']) for k,v in fixed.items() if k.startswith(str(seed)+'-')]
        for name,x in vectors:
            top = model.topology; values = model.decode(x); omega = 2*np.pi*ev.grid.frequency_hz
            Y,dY = top.node_admittance_with_jacobian(values,model.schema,omega,ev.grid.setting)
            ports=(top.inductor_tree.source_node,top.inductor_tree.load_node)
            order=np.asarray(ports+tuple(i for i in range(Y.shape[1]) if i not in ports))
            Y=Y[:,order[:,None],order]; dY=dY[:,:,order[:,None],order]
            U,V,E=Y[:,:2,2:],Y[:,2:,:2],Y[:,2:,2:]; X=np.linalg.solve(E,V)
            dU,dV,dE=dY[:,:,:2,2:],dY[:,:,2:,:2],dY[:,:,2:,2:]
            rhs=dV-dE@X[:,None]; n,p,k,_=rhs.shape
            dX=np.linalg.solve(E,rhs.transpose(0,2,1,3).reshape(n,k,2*p)).reshape(n,k,p,2).transpose(0,2,1,3)
            old=dY[:,:,:2,:2]-dU@X[:,None]-U[:,None]@dX
            T=np.concatenate((np.broadcast_to(np.eye(2),(n,2,2)),-X),axis=1)
            new=T.swapaxes(-1,-2)[:,None]@dY@T[:,None]
            R=Y[:,:2,:2]-U@X; eye=np.eye(2); A=eye+50*R
            core=np.linalg.solve(A,eye-50*R); first=_cascade(ev.pre,core); full=_cascade(first,ev.post)
            data=power_response(full,ev.source_ohms,ev.load_ohms)
            def propagate(dR, variant):
                rhs=-50*dR@(eye+core[:,None]); packed=rhs.transpose(0,2,1,3).reshape(n,2,2*p)
                dc=np.linalg.solve(A,packed).reshape(n,2,p,2).transpose(0,2,1,3)
                if variant:
                    dfirst=cascade_one_side(ev.pre,None,core,dc)
                    dfull=cascade_one_side(first,dfirst,ev.post,None)
                else:
                    z=np.zeros_like(dc); dfirst=OLD_CASCADE(ev.pre,z,core,dc); dfull=OLD_CASCADE(first,dfirst,ev.post,z)
                z=np.asarray([ev.source_ohms,ev.load_ohms]); scale=(2*np.sqrt(z.real))[None,None,:,None]
                da=(np.sqrt(50.)-z[None,None,:,None]/np.sqrt(50.))*dfull/scale
                db=(np.sqrt(50.)+z.conj()[None,None,:,None]/np.sqrt(50.))*dfull/scale
                v=np.sqrt(50.)*(eye+full); i=(eye-full)/np.sqrt(50.)
                wave=(v+z[None,:,None]*i)/(2*np.sqrt(z.real)[None,:,None])
                rhs=(db-data[0][:,None]@da).swapaxes(-1,-2)
                ds=np.linalg.solve(wave.swapaxes(-1,-2),rhs.transpose(0,2,1,3).reshape(n,2,2*p)).reshape(n,2,p,2).transpose(0,2,3,1)
                return dc,dfirst,dfull,ds
            reference=propagate(old,False)
            threshold,direction=_margin_parameters(profile,ev.grid)
            active=direction*(data[1]-threshold)>0
            def il_jac(ds):
                return (-20/np.log(10)*np.real(ds[:,:,1,0]/data[0][:,None,1,0]))*width[None,:]
            ref_il=il_jac(reference[-1])
            derivatives={}
            for mode,dR,variant in (('A',new,False),('B',old,True),('AB',new,True)):
                current=propagate(dR,variant)
                derivatives[mode]={key:compare(a,b) for key,a,b in zip(('dcore','dfirst','dfull','ds'),reference,current)}
                derivatives[mode]['ds_normalized']=compare(reference[-1]*width[None,:,None,None],current[-1]*width[None,:,None,None])
                actual_il=il_jac(current[-1])
                derivatives[mode]['il_jac_normalized']=compare(ref_il,actual_il)
                derivatives[mode]['residual_jac_normalized']=compare(np.sqrt(2)*active[:,None]*direction[:,None]*ref_il,np.sqrt(2)*active[:,None]*direction[:,None]*actual_il)
            result['schur'].append({'seed':seed,'vector':name,'sha256':vector_sha(x),
                'condition_max':float(np.max(np.linalg.cond(E))), 'dR':compare(old,new), 'derivatives':derivatives,
                'Y_asymmetry':float(np.max(np.abs(Y-Y.swapaxes(-1,-2)))),
                'dY_asymmetry':float(np.max(np.abs(dY-dY.swapaxes(-1,-2))))})
    rng=np.random.default_rng(519)
    a=rng.normal(size=(5,2,2))+1j*rng.normal(size=(5,2,2))
    b=rng.normal(size=(5,2,2))+1j*rng.normal(size=(5,2,2))
    a[0,0,1]=0; b[1,1,0]=0; a[2,1,1]=0; b[3,0,0]=0
    a[4,1,1]=1; b[4,0,0]=1-1e-8
    d=rng.normal(size=(5,25,2,2))+1j*rng.normal(size=(5,25,2,2))
    z=np.zeros_like(d)
    for side in ('left_fixed','right_fixed'):
        old=OLD_CASCADE(a,z,b,d) if side=='left_fixed' else OLD_CASCADE(a,d,b,z)
        new=cascade_one_side(a,None,b,d) if side=='left_fixed' else cascade_one_side(a,d,b,None)
        result['cascade_edges'].append({'side':side,'all':compare(old,new),
            'per_sample':[compare(old[i],new[i]) for i in range(len(a))]})
        np.testing.assert_allclose(new,old,rtol=1e-6,atol=1e-8)
    Path(out).write_text(json.dumps(result,indent=2)+'\n')

if __name__ == '__main__':
    assert not Path(sys.argv[1]).exists(); main(sys.argv[1])

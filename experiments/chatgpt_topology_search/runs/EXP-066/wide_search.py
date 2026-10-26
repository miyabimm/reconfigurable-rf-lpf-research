#!/usr/bin/env python3
"""EXP-066 | Phase 2 RF-T005 4L+1 GJM01 wide-topology explorer.

Always run in repository checkout; uses the shared RF-T005 model extracted from EXP-042.
This file performs *finite-grid* screening/refinement, never physical qualification.
Census mode is topology-only and requires no proprietary artifacts.
"""
import argparse
import csv
import itertools as it
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3] if 'experiments' in HERE.parts else HERE
BASE_DIR = ROOT / 'experiments/chatgpt_topology_search/runs/EXP-042'
CASES = ('B71','B12','B28','B13+B14','B26','B8')
BASE_L = ((0,1),(1,3),(1,4),(1,2))
BASE_F = ((0,1),(4,-1),(1,2),(0,3))
BASE_V = ((3,-1),(4,-1),(1,2))
BASE_ORDER = (0,1,3,2)
GJM_EDGES = ((0,1),(1,2),(1,3),(0,2),(0,3),(2,3),(1,-1),(3,-1),(4,-1))
PCB_SETS = (
    ((4,-1),(1,2),(0,3)),
    ((1,-1),(2,-1),(3,-1)),
    ((0,2),(0,3),(2,4)),
    ((0,1),(1,2),(3,4)),
    ((4,-1),(3,-1),(0,2)),
)
CV_SETS = (
    BASE_V,
    ((1,-1),(3,-1),(4,-1)),
    ((3,-1),(0,2),(1,2)),
    ((2,-1),(4,-1),(0,3)),
    ((1,-1),(0,4),(2,3)),
)

def edge(a,b):
    return tuple(sorted((a,b),reverse=True)) if b >= 0 else (a,-1)

def prufer_tree(code):
    degree = [1] * 5
    for x in code:
        degree[x] += 1
    out = []
    for x in code:
        leaf = next(i for i in range(5) if degree[i] == 1)
        out.append(edge(leaf,x))
        degree[leaf] -= 1
        degree[x] -= 1
    x,y = (i for i in range(5) if degree[i] == 1)
    out.append(edge(x,y))
    return tuple(sorted(out))

def topo(L=BASE_L,F=BASE_F,V=BASE_V,order=BASE_ORDER):
    return {'L': [list(x) for x in L], 'F':[list(x) for x in F],
            'V':[list(x) for x in V], 'row':list(order)}

def signatures(t):
    # PCB component indices 1..3 interchangeable; V indices 0..2 interchangeable.
    return (tuple(sorted(tuple(edge(*x)) for x in t['L'])),
            tuple(edge(*x) for x in t['F'][:1]),
            tuple(sorted(edge(*x) for x in t['F'][1:])),
            tuple(sorted(edge(*x) for x in t['V'])),
            tuple(tuple(edge(*t['L'][i]) for i in t['row'][j:j+2]) for j in range(3)))

def enumerated_trees():
    seen = {tuple(sorted(edge(*e) for e in BASE_L))}
    yield tuple(BASE_L)
    for p in it.product(range(5), repeat=3):
        t=prufer_tree(p)
        if t not in seen:
            seen.add(t)
            yield t

def rows_orders():
    # Each physical row and its reversal have exactly the same adjacent pairs.
    return tuple(p for p in it.permutations(range(4)) if p < p[::-1])

def stage_a():
    for L in enumerated_trees():
        yield topo(L=L,order=BASE_ORDER)

def stage_b(L_choices):
    for t0 in L_choices:
        for f0 in GJM_EDGES:
            for pcb in PCB_SETS:
                for cv in CV_SETS:
                    yield topo(L=t0['L'], F=(f0,*pcb),V=cv,order=t0['row'])

def stage_c(c_choices):
    for t0 in c_choices:
        for row in rows_orders():
            yield topo(L=t0['L'],F=t0['F'],V=t0['V'],order=row)

def distinct(seq):
    seen=set()
    for t in seq:
        key=signatures(t)
        if key not in seen:
            seen.add(key)
            yield t

def census():
    a=list(distinct(stage_a()))
    assert len(a)==125, len(a)
    b=list(distinct(stage_b(a[:8])))
    assert b
    return {'prufer_labeled_tree_count':125,'stage_A_graphs':len(a),
            'stage_B_8_trees_candidates':len(b),'row_order_choices':len(rows_orders()),
            'max_gjm01':1,'pcb_c_count':3,'variable_c_branches':3,'cost_units':4+2/3,
            'note':'Graph census ONLY; no IL/stopband evaluation performed.'}

def engine_imports():
    import numpy as np
    from scipy.optimize import minimize
    sys.path.insert(0, str(ROOT/'src'))
    from lpf.phase2_models import exp042 as base
    from lpf.constraint_versions import load_constraint
    from lpf.slsqp_budget import run_termination_aware_slsqp
    p=load_constraint('RF-T005',allow_trial=True)
    assert p['components']['IC_VARIABLE_C']['max_branches_principle']==3
    assert p['coupling_limits']['chip_chip_strong_adjacent_abs_k_max']==.1
    doc=json.loads((BASE_DIR/'checkpoints/pcb_both.json').read_text())
    assert doc['constraint_id']=='RF-T005'
    return np,minimize,base,run_termination_aware_slsqp,p,np.array(doc['vector'],float)

def build_evaluator(base,np,t,policy,points):
    class Eval(base.Evaluator):
        def __init__(self):
            super().__init__(policy,points)
            self.BL=base.incidence(t['L']);self.BC=base.incidence(t['F']+t['V'])
            self.prev=None;self.prev_il=None
        def matrix(self,x):
            L=np.asarray(x[:4],float);M=np.diag(L)
            for k,(u,v) in zip(x[8:11],zip(t['row'][:-1],t['row'][1:])):
                M[u,v]=M[v,u]=k*np.sqrt(L[u]*L[v])
            eig=float(np.linalg.eigvalsh(M).min())
            if eig<=0: raise ValueError('Inductance not SPD')
            H=np.diag(L/25)+1j*M
            return self.BL@np.linalg.solve(H,self.BL.T),eig
        def il(self,x):
            x=np.asarray(x,float)
            if self.prev is not None and np.array_equal(self.prev,x):
                return self.prev_il
            K,_=self.matrix(x);n=len(self.f)
            Y=np.broadcast_to(K,(n,5,5)).copy()/(self.omega[:,None,None]*1e-9)
            cv=x[11:].reshape((6,3))[self.setting]
            cap=np.column_stack((np.broadcast_to(x[4:8],(n,4)),cv))
            q=np.asarray((80.,40.,40.,40.,35.,35.,35.))
            y=self.omega[:,None]*1e-12*cap/(1/q[None,:]-1j)
            Y+=np.einsum('nb,ib,jb->nij',y,self.BC,self.BC,optimize=True)
            ports=[0,2];inner=[1,3,4]
            P=Y[:,ports,:][:,:,ports];U=Y[:,ports,:][:,:,inner]
            V=Y[:,inner,:][:,:,ports];E=Y[:,inner,:][:,:,inner]
            R=P-U@np.linalg.solve(E,V)
            a,b,c,d=R[:,0,0],R[:,0,1],R[:,1,0],R[:,1,1]
            if np.any(np.abs(c)<1e-17): raise ValueError('Undefined LPF ABCD')
            abcd=np.empty((n,2,2),complex)
            abcd[:,0,0]=-d/c;abcd[:,0,1]=-1/c
            abcd[:,1,0]=-(a*d-b*c)/c;abcd[:,1,1]=-a/c
            system=self.pre@abcd@self.post
            zl=60-40j;zs=50.
            den=system[:,0,0]*zl+system[:,0,1]+zs*(system[:,1,0]*zl+system[:,1,1])
            result=-10*np.log10(np.maximum(4*zs*zl.real/np.abs(den)**2,1e-300))
            self.prev,self.prev_il=x.copy(),result
            return result
        def summary(self,x):
            v=self.il(x);ii=[]
            for j in range(3):
                m=np.flatnonzero(self.role==j)
                ii.append(int(m[np.argmax(v[m]) if j==0 else np.argmin(v[m])]))
            return {'worst_il_db':float(v[ii[0]]),'min_h2_db':float(v[ii[1]]),
                    'min_h3_db':float(v[ii[2]]),'m_min_eig_nH':self.matrix(x)[1]}
    return Eval()

def screen_score(s):
    # Prioritize near-feasibility, retain other structural families separately.
    violation=max(0,30.02-s['min_h2_db'],30.02-s['min_h3_db'])
    return violation*2.0+s['worst_il_db']

def screen_one(base,np,t,p,x,points):
    ev=build_evaluator(base,np,t,p,points)
    try:
        z=ev.summary(x)
        return {'topology':t,'screen':z,'score':screen_score(z),'failed':False}
    except (ValueError,np.linalg.LinAlgError,FloatingPointError) as err:
        return {'topology':t,'failed':True,'reason':str(err),'score':1e9}

def selected(rows,count,seed):
    # Return both best harmonic-feasibility ranking AND diverse L graph families.
    ok=sorted((r for r in rows if not r['failed']),key=lambda r:r['score'])
    rng=__import__('random').Random(seed)
    result=[];used=set()
    for subset in (ok[:count//2],sorted(ok,key=lambda r:r['screen']['worst_il_db'])[:count//4],
                   rng.sample(ok,min(len(ok),count))):
        for r in subset:
            s=json.dumps(signatures(r['topology']))
            if s not in used and len(result)<count:
                result.append(r);used.add(s)
    return result

def optimize_one(np,minimize,base,staged,p,seedx,t,target=30.02):
    ev0=build_evaluator(base,np,t,p,9)
    ev1=build_evaluator(base,np,t,p,31)
    bounds=list(base.BOUNDS)
    for i in (5,6,7):bounds[i]=(.02,.2)
    bounds[4]=(.0001,100.)
    def op(ev,vec,maxiter,goal):
        def slack(z):
            v=ev.il(z[:-1]);return np.where(ev.role==0,z[-1]-v,v-goal)
        opt=minimize(lambda z:z[-1],vec,method='SLSQP',bounds=bounds+[(0,10)],
            constraints={'type':'ineq','fun':slack},options={'maxiter':maxiter,'ftol':1e-8})
        status={'converged':bool(opt.success),'status':int(opt.status),
                'message':str(opt.message),'nit':int(opt.nit),'nfev':int(opt.nfev),
                'minimum_slack':float(slack(opt.x).min())}
        return np.asarray(opt.x,float),status
    start=np.r_[seedx,ev0.summary(seedx)['worst_il_db']]
    res=staged(ev0,ev1,start,target,op)
    out=[]
    for a in res['attempts']:
        x=np.asarray(a['vector'][:-1],float)
        s=ev1.summary(x)
        out.append({k:(v.tolist() if hasattr(v,'tolist') else v) for k,v in a.items() if k!='vector'} |
                   {'vector':x.tolist(),'fine_metrics':s})
    return {'topology':t,'attempts':out,'policy':res['iteration_policy']}

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--phase',choices=('census','screen','optimize'),default='census')
    parser.add_argument('--input',type=Path,help='Stage screen JSON for optimize')
    parser.add_argument('--out',type=Path,default=Path('results/EXP-066/stage.json'))
    parser.add_argument('--limit',type=int,default=24)
    parser.add_argument('--shard',type=int,default=0)
    parser.add_argument('--shards',type=int,default=1)
    parser.add_argument('--target',type=float,default=30.02)
    a=parser.parse_args()
    if a.shards<1 or not 0<=a.shard<a.shards:parser.error('bad shard')
    if a.phase=='census':
        obj={'experiment':'EXP-066','phase':'Phase 2','constraint_id':'RF-T005',**census()}
    else:
        np,minimize,base,staged,p,seedx=engine_imports()
        if a.phase=='screen':
            aa=list(stage_a()); A=[screen_one(base,np,t,p,seedx,5) for t in aa]
            winners=selected(A,8,66001)
            BB=list(distinct(stage_b([r['topology'] for r in winners])))
            B=[screen_one(base,np,t,p,seedx,5) for t in BB]
            finalists=selected(B,60,66002)
            CC=list(distinct(stage_c([r['topology'] for r in finalists])))
            C=[screen_one(base,np,t,p,seedx,5) for t in CC]
            obj={'experiment':'EXP-066','phase':'screen','constraint_id':'RF-T005',
                 'counts':{'A':len(A),'B':len(B),'C':len(C)},
                 'selected':selected(C,max(a.limit,24),66003),
                 'benchmark':A[0], 'all_steps_finite_grid_only':True,
                 'note':'SLSQP and dense MNA not executed in screen phase.'}
        else:
            if not a.input:parser.error('--input required for optimize')
            sr=json.loads(a.input.read_text());assert sr['constraint_id']=='RF-T005'
            chosen=sr['selected'][a.shard::a.shards]
            records=[]
            for row in chosen[:a.limit]:
                try:records.append(optimize_one(np,minimize,base,staged,p,seedx,row['topology'],a.target))
                except (ValueError,np.linalg.LinAlgError,FloatingPointError) as e:
                    records.append({'topology':row['topology'],'failure':str(e)})
            obj={'experiment':'EXP-066','phase':'optimization','constraint_id':'RF-T005',
                 'shard':a.shard,'shards':a.shards,'results':records,
                 'status':'requires_dense_28x7001_and_independent_MNA_before_Pareto_claim'}
    a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_text(json.dumps(obj,indent=2,ensure_ascii=False)+'\n')
    print(json.dumps({'out':str(a.out),'phase':a.phase,'status':'done'}))

if __name__=='__main__':main()

#!/usr/bin/env python3
"""EXP-055: adapt the RF-F003 EXP-047 four-L, area 5+1/3 seed to RF-T007.

One grounded tunable Cv0=(3,GND) always has DISTINCT fixed 0.5pF/Q40
Cpar in T007, including OFF. Cv2=(1,2) and optional Cv1 non-ground
receive no such parasitic. Phase 2 nominal constant-Q finite-grid only.
Historical F003 vector is first reproduced with *no* T007 Cpar, then
evaluated and optimized under T007. No RF-T006 3-6 GHz requirement.
"""
import argparse
import json
import math
import subprocess
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
SRC = ROOT / "experiments/chatgpt_topology_search/runs/EXP-047/area5p333_g2_independent_28x1001_20261017.json"
sys.path.insert(0, str(ROOT / "experiments/chatgpt_topology_search/runs/EXP-053"))
sys.path.insert(0, str(ROOT / "src"))
import sweep_4l_inductor_graphs as base
from lpf.constraint_versions import load_constraint, constraint_fingerprint
from lpf.trial_shunt_dtc import shunt_dtc_parasitic_branches

# Branch L0,L1,L2,L3; single physical row L0-L1-L3-L2.
L_EDGES = ((0,1),(1,3),(1,4),(1,2))
K_PAIRS = ((0,1),(1,3),(3,2))
# Optional third DTC is ALWAYS between two non-ground signal nodes.
VARIANTS = {
    "two_dtc": None,
    "cv1_input_output": (0,2),
    "cv1_input_parallel_L0": (0,1),
    "cv1_input_tip": (0,3),
    "cv1_tip_output": (3,2),
    "cv1_output_shunt_tip": (2,4),
}
# Cf0 GJM, Cf1 GJM, Cf2 PCB, Cp PCB, Cv0/Cv1/Cv2 Q35, Cpar Q40.
Q_C = np.array([80.,80.,40.,40.,35.,35.,35.,40.])
CASES = base.CASES

def incidence(edges):
    return base.exp51.incidence(edges)

def capacitor_edges(name):
    if name not in VARIANTS:
        raise KeyError(name)
    cv1 = VARIANTS[name] if VARIANTS[name] is not None else (0,2)
    return ((0,1),(4,-1),(1,2),(0,3),
            (3,-1),cv1,(1,2),(3,-1))

def bounds(name):
    x = np.array([(0.4,27.)]*4 + [(0.02,100.),(0.02,100.),
            (0.02,0.2),(0.02,0.2)] + [(-0.1,0.1)]*3
            + [(0.,3.)]*18, float)
    if name == "two_dtc":
        for i in range(6):
            x[12+3*i] = (0.,0.)  # source-vector Cv1 slots are placeholders.
    assert x.shape == (29,2)
    return x

def inductance(x):
    L = np.asarray(x[:4],float)
    M = np.diag(L.copy())
    for (a,b),k in zip(K_PAIRS,x[8:11]):
        M[a,b] = M[b,a] = k*math.sqrt(L[a]*L[b])
    eig = float(np.linalg.eigvalsh(M)[0])
    if eig <= 0:
        raise ValueError("Non-positive inductance matrix")
    H = np.diag(L/25.) + 1j*M
    BL = incidence(L_EDGES)
    return BL@np.linalg.solve(H,BL.T), M, H, BL

class Evaluator(base.Evaluator):
    def __init__(self,policy,points,name,with_parasitic=True):
        super().__init__(policy,points,"reference")
        self.name = name
        self.with_parasitic = bool(with_parasitic)
        self.L_edges = L_EDGES
        self.BC = incidence(capacitor_edges(name))
        self.bounds = bounds(name)
        self.cache_x = self.cache_il = None

    def il(self,x):
        x = np.asarray(x,float)
        if x.shape != (29,):
            raise ValueError("Expected EXP-047 full 29 element parameter vector")
        if self.cache_x is not None and np.array_equal(self.cache_x,x):
            return self.cache_il
        K,_,_,_ = inductance(x)
        n = len(self.f)
        Y = np.broadcast_to(K,(n,5,5)).copy()/(self.omega[:,None,None]*1e-9)
        cv = x[11:].reshape(6,3)[self.setting]
        caps = np.column_stack((np.broadcast_to(x[4:8],(n,4)),
                                 cv,np.full(n,0.5 if self.with_parasitic else 0.0)))
        y = self.omega[:,None]*1e-12*caps/(1/Q_C[None,:]-1j)
        Y += np.einsum("nb,ib,jb->nij",y,self.BC,self.BC,optimize=True)
        outer=[0,2]; mid=[1,3,4]
        A=Y[:,outer,:][:,:,outer]
        B=Y[:,outer,:][:,:,mid]
        C=Y[:,mid,:][:,:,outer]
        D=Y[:,mid,:][:,:,mid]
        R=A-B@np.linalg.solve(D,C)
        a,b,c,d=R[:,0,0],R[:,0,1],R[:,1,0],R[:,1,1]
        if np.any(abs(c)<1e-21):
            raise ValueError("Singular two port")
        T=np.empty((n,2,2),complex)
        T[:,0,0]=-d/c; T[:,0,1]=-1/c
        T[:,1,0]=-(a*d-b*c)/c; T[:,1,1]=-a/c
        chain=self.pre@T@self.post
        zl=60-40j
        den=chain[:,0,0]*zl+chain[:,0,1]+50*(chain[:,1,0]*zl+chain[:,1,1])
        value=-10*np.log10(np.maximum(200*zl.real/abs(den)**2,1e-300))
        self.cache_x=x.copy(); self.cache_il=value
        return value

    def summary(self,x):
        v=self.il(x); idx=[]
        for role in (0,1,2):
            w=np.flatnonzero(self.role==role)
            idx.append(int(w[np.argmax(v[w]) if role==0 else np.argmin(v[w])]))
        mineig=float(np.linalg.eigvalsh(inductance(np.asarray(x,float))[1])[0])
        return {"worst_IL_db":float(v[idx[0]]),
                "min_H2_db":float(v[idx[1]]),"min_H3_db":float(v[idx[2]]),
                "locations":[{"setting":CASES[self.setting[i]],
                              "MHz":float(self.f[i]),"segment":int(self.segment[i])}
                             for i in idx],
                "min_M_eigenvalue_nH":mineig,
                "finite_H2H3_30dB_pass":bool(v[idx[1]]>=30 and v[idx[2]]>=30)}

def independent_mna(policy,x,name,points):
    """Independent explicit 5-node / 4-coupled-L-current 9x9 MNA."""
    ev=Evaluator(policy,points,name,True)
    fast=ev.il(x)
    _,M,H,BL=inductance(x)
    BC=ev.BC
    max_delta=max_residual=0.
    minimum_passive=float("inf")
    for j,(f,case) in enumerate(zip(ev.f,ev.setting)):
        w=2e6*np.pi*f
        values=np.r_[x[4:8],x[11+3*case:14+3*case],0.5]
        yc=w*1e-12*values/(1/Q_C-1j)
        pre,post=ev.pre[j],ev.post[j]
        zl=60-40j
        din=pre[0,1]+50*pre[1,1]
        Ys=(pre[0,0]+50*pre[1,0])/din
        source=1/din
        dout=post[0,0]*zl+post[0,1]
        Yload=(post[1,0]*zl+post[1,1])/dout
        A=np.zeros((9,9),complex)
        A[:5,:5]=BC@np.diag(yc)@BC.T
        A[0,0]+=Ys; A[2,2]+=Yload
        A[:5,5:]=BL; A[5:,:5]=BL.T
        A[5:,5:]=-w*1e-9*H
        rhs=np.zeros(9,complex); rhs[0]=source
        ans=np.linalg.solve(A,rhs)
        v,curr=ans[:5],ans[5:]
        Pload=zl.real*abs(v[2]/dout)**2
        il=-10*np.log10(max(200*Pload,1e-300))
        max_delta=max(max_delta,abs(il-fast[j]))
        iin=source-Ys*v[0]
        vext=pre[0,0]*v[0]+pre[0,1]*iin
        iext=pre[1,0]*v[0]+pre[1,1]*iin
        refl=abs(1-100*iext)**2/200
        ppre=float(np.real(vext*np.conj(iext)-v[0]*np.conj(iin)))
        ppost=float(np.real(v[2]*np.conj(Yload*v[2]))-Pload)
        pl=float(np.sum(w*1e-9*x[:4]/25*abs(curr)**2))
        pc_each=yc.real*abs(BC.T@v)**2
        pc=float(np.sum(pc_each))
        max_residual=max(max_residual,abs(.005-(refl+ppre+ppost+pl+pc+Pload)))
        minimum_passive=min(minimum_passive,refl,ppre,ppost,pl,pc,Pload,
                            *[float(q) for q in pc_each])
    return {"method":"independent 9x9 KCL/KVL coupled-L MNA",
            "probes":int(len(ev.f)),
            "max_IL_difference_db":float(max_delta),
            "max_power_balance_W":float(max_residual),
            "minimum_passive_W":float(minimum_passive),
            "min_L_eigenvalue_nH":float(np.linalg.eigvalsh(M)[0]),
            "pass":bool(max_delta<1e-8 and max_residual<1e-9
                        and minimum_passive>-1e-10 and np.linalg.eigvalsh(M)[0]>0)}

def make_starts(seed,name,n,rng):
    starts=[seed.copy()]
    compensated=seed.copy()
    for s in range(6):
        compensated[11+3*s]=max(0.,seed[11+3*s]-.5)
        if name!="two_dtc":
            compensated[12+3*s]=0.10
    if n>=2:
        starts.append(compensated)
    for j in range(2,n):
        x=compensated.copy()
        x[:4]*=np.exp(rng.normal(0,.08 if j==2 else .16,4))
        x[4:8]*=np.exp(rng.normal(0,.10 if j==2 else .20,4))
        x[8:11]+=rng.normal(0,.012 if j==2 else .023,3)
        x[11:]+=rng.normal(0,.10 if j==2 else .20,18)
        starts.append(np.clip(x,bounds(name)[:,0],bounds(name)[:,1]))
    return starts

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--starts",type=int,default=3)
    p.add_argument("--maxiter",type=int,default=160)
    p.add_argument("--coarse",type=int,default=7)
    p.add_argument("--fine",type=int,default=17)
    p.add_argument("--dense",type=int,default=1001)
    p.add_argument("--mna",type=int,default=3)
    p.add_argument("--target",type=float,default=30.005)
    p.add_argument("--variants",nargs="*",choices=list(VARIANTS),default=list(VARIANTS))
    p.add_argument("--out",type=Path)
    a=p.parse_args()
    if min(a.starts,a.maxiter,a.coarse,a.fine,a.dense,a.mna)<1 or a.target<30:
        raise ValueError("Invalid EXP-055 run parameters")
    policy=load_constraint("RF-T007",allow_trial=True)
    parasitics=shunt_dtc_parasitic_branches(policy,[
        {"a":4,"b":0,"role":"shunt_to_ground"},
        {"a":1,"b":2,"role":"bridge"},
        {"a":2,"b":3,"role":"bridge"}])
    assert len(parasitics)==1 and parasitics[0]["node"]==4
    source=json.loads(SRC.read_text(encoding="utf-8"))
    assert source["condition"]=="RF-F003" and abs(source["chip_area"]-5-1/3)<1e-8
    seed=np.asarray(source["vector"],float)
    assert seed.shape==(29,) and np.all(seed[12::3]==0)
    # Exact original RF-F003 source S2P model must reproduce BEFORE applying Cpar.
    f003=Evaluator(policy,a.dense,"two_dtc",False)
    historical=f003.summary(seed)
    expected=float(source["grid"]["verified"]["worst"])
    if abs(historical["worst_IL_db"]-expected)>1e-6:
        raise AssertionError(f"F003 source reproduction failed {historical['worst_IL_db']} != {expected}")
    rng=np.random.default_rng(20261020+55)
    report={"experiment_id":"EXP-055","constraint_id":"RF-T007","phase":"Phase 2",
        "source_F003":str(SRC.relative_to(ROOT)),
        "source_F003_reproduced":historical,
        "source_F003_reference_IL_db":expected,
        "source_F003_reproduction_error_db":abs(historical["worst_IL_db"]-expected),
        "constraint_fingerprint":constraint_fingerprint(policy),
        "execution_sha":subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip(),
        "L_edges":L_EDGES,"physical_L_row":["L0","L1","L3","L2"],
        "K_pairs":K_PAIRS,"fixed_C_edges":capacitor_edges("two_dtc")[:4],
        "C_Q":Q_C.tolist(),"Cpar_pF_Q40":{"edge":(3,-1),"C":.5,"Q":40},
        "chip_area_units":5+1/3,"GJM_count":2,"PCB_PATTERN_C_count":2,
        "hard_min_H2H3_db":30,"internal_guard_db":a.target,
        "grid":{"intervals":28,"coarse":a.coarse,"fine":a.fine,"dense":a.dense,"MNA":a.mna},
        "variants":{},"limitations":["Finite grid/local SLSQP only, not global optimum",
        "Physical k realizability, continuous extremes, Q(f), SRF, EM, tolerance and Phase3 not tested"]}
    ranked=[]
    for name in a.variants:
        coarse=Evaluator(policy,a.coarse,name)
        fine=Evaluator(policy,a.fine,name)
        dense=Evaluator(policy,a.dense,name)
        old_vector=dense.summary(seed)
        trials=[]
        for j,start in enumerate(make_starts(seed,name,a.starts,rng)):
            try:
                xc,c0=base.exp51.optimize_stage(coarse,start,a.maxiter,a.target)
                xf,c1=base.exp51.optimize_stage(fine,xc,max(80,a.maxiter//2),a.target)
                m=dense.summary(xf)
                trial={"start":j,"vector":xf.tolist(),"coarse":c0,"fine":c1,
                       "converged":bool(c0["converged"] and c1["converged"]),
                       "metrics":m}
            except (ValueError,np.linalg.LinAlgError,OverflowError) as error:
                trial={"start":j,"failed":str(error),"converged":False}
            trials.append(trial)
            print("TRY",name,j,trial.get("metrics",{}).get("worst_IL_db"),
                  trial.get("metrics",{}).get("min_H2_db"),
                  trial.get("metrics",{}).get("min_H3_db"),
                  trial["converged"],flush=True)
        compliant=[t for t in trials if t.get("metrics",{}).get("finite_H2H3_30dB_pass")]
        best=min(compliant,key=lambda q:q["metrics"]["worst_IL_db"]) if compliant else None
        verification=independent_mna(policy,np.asarray(best["vector"]),name,a.mna) if best else None
        if verification and not verification["pass"]:
            raise AssertionError("Independent MNA fails for "+name)
        report["variants"][name]={"cv1_installed":name!="two_dtc",
            "Cv1_edge":VARIANTS[name],"original_F003_vector_T007_metrics":old_vector,
            "trials":trials,"best_compliant":best,"independent_MNA":verification}
        if best:
            ranked.append({"variant":name,"worst_IL_db":best["metrics"]["worst_IL_db"],
                "H2_db":best["metrics"]["min_H2_db"],"H3_db":best["metrics"]["min_H3_db"],
                "solver_converged":best["converged"],"MNA_pass":verification["pass"]})
    ranked.sort(key=lambda q:q["worst_IL_db"])
    report["summary"]={"ranked":ranked,"reference_EXP053_T007_IL_db":.8757946642355757}
    dest=a.out or ROOT/"results/EXP-055/f003_fourL_adapt.json"
    dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("FINAL",dest,"RANKED",ranked,flush=True)

if __name__=="__main__":
    main()

#!/usr/bin/env python3
"""EXP-058 RF-T008 v3 area4: 4 LQP02HV + 0 GJM + 3 PCB-C + 2 composite IC branches.
Fixed IC C/Q60 and variable C/Q35 are separate lossy admittance stamps.
Finite-grid Phase 2 topology search, not global optimum or actual RF layout.
"""
import argparse
import json
import math
import subprocess
import sys
from pathlib import Path
import numpy as np

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
sys.path.insert(0,str(HERE))
sys.path.insert(0,str(ROOT/"experiments/chatgpt_topology_search/runs/EXP-055"))
sys.path.insert(0,str(ROOT/"src"))
import sweep_area3 as optim
import adapt_f003_4l as old4
from lpf.constraint_versions import load_constraint,constraint_fingerprint
from lpf.trial_pcb_pattern_c import validate_trial_pcb_pattern_c_branches
from lpf.trial_ic_fixed_c import validate_ic_fixed_c_settings

CASES=old4.CASES
SOURCE=ROOT/"experiments/chatgpt_topology_search/runs/EXP-047/area5p333_g2_independent_28x1001_20261017.json"
ALL_FIXED=((0,1),(4,-1),(1,2),(0,3))
DTC={
    "shunt_output":((3,-1),(1,2)),
    "shunt_input":((3,-1),(0,3)),
    "input_output":((0,3),(1,2)),
}
REMOVE={"cf0":0,"cf1":1,"cf2":2,"cp":3}


def norm(e):
    return {"a":e[0]+1,"b":e[1]+1}


def inductance(v):
    L=np.asarray(v[:4],float)
    M=np.diag(L.copy())
    for (a,b),k in zip(old4.K_PAIRS,v[7:10]):
        M[a,b]=M[b,a]=k*math.sqrt(L[a]*L[b])
    eig=float(np.linalg.eigvalsh(M)[0])
    if eig<=0:raise ValueError("Inductor matrix not SPD")
    H=np.diag(L/25.)+1j*M
    BL=old4.incidence(old4.L_EDGES)
    return BL@np.linalg.solve(H,BL.T),M,H,BL


class Evaluator(old4.Evaluator):
    def __init__(self,policy,variant,removed,points):
        super().__init__(policy,points,"two_dtc",False)
        self.variant,self.removed=variant,removed
        self.fixed_edges=tuple(e for i,e in enumerate(ALL_FIXED) if i!=REMOVE[removed])
        self.var_edges=DTC[variant]
        self.cap_edges=self.fixed_edges+self.var_edges+self.var_edges
        self.BC=old4.incidence(self.cap_edges)
        self.Q_C=np.array([60 if -1 in e else 40 for e in self.fixed_edges]+[35,35,60,60],float)
        self.bounds=np.array(
            [(0.4,27.)]*4
            + [(0.02,1.) if -1 in e else (0.02,0.2) for e in self.fixed_edges]
            + [(-0.1,0.1)]*3
            + [(0.5,3.) if -1 in e else (0.2,3.) for e in self.var_edges]
            + [(0.,3.)]*12,float)
        self.cache_x=self.cache_il=None
        pcbs=[dict(norm(e),capacitance_pf=0.1,q=(60 if -1 in e else 40))
              for e in self.fixed_edges]
        validate_trial_pcb_pattern_c_branches(policy,pcbs)

    def il(self,x):
        x=np.asarray(x,float)
        if x.shape!=(24,):raise ValueError("Four-L area4 vector must be 24 elements")
        if self.cache_x is not None and np.array_equal(self.cache_x,x):return self.cache_il
        K,_,_,_=inductance(x)
        n=len(self.f)
        Y=np.broadcast_to(K,(n,5,5)).copy()/(self.omega[:,None,None]*1e-9)
        cv=x[12:].reshape(6,2)[self.setting]
        caps=np.column_stack((np.broadcast_to(x[4:7],(n,3)),cv,
                              np.broadcast_to(x[10:12],(n,2))))
        adm=self.omega[:,None]*1e-12*caps/(1/self.Q_C[None,:]-1j)
        Y+=np.einsum("nb,ib,jb->nij",adm,self.BC,self.BC,optimize=True)
        port=[0,2];interior=[1,3,4]
        P=Y[:,port,:][:,:,port]
        U=Y[:,port,:][:,:,interior]
        V=Y[:,interior,:][:,:,port]
        E=Y[:,interior,:][:,:,interior]
        R=P-U@np.linalg.solve(E,V)
        a,b,c,d=R[:,0,0],R[:,0,1],R[:,1,0],R[:,1,1]
        if np.any(abs(c)<1e-21):raise ValueError("Singular transfer matrix")
        T=np.empty((n,2,2),complex)
        T[:,0,0]=-d/c;T[:,0,1]=-1/c
        T[:,1,0]=-(a*d-b*c)/c;T[:,1,1]=-a/c
        chain=self.pre@T@self.post
        zl=60-40j
        den=chain[:,0,0]*zl+chain[:,0,1]+50*(chain[:,1,0]*zl+chain[:,1,1])
        val=-10*np.log10(np.maximum(200*zl.real/abs(den)**2,1e-300))
        self.cache_x,self.cache_il=x.copy(),val
        return val

    def summary(self,x):
        y=self.il(x);ext=[]
        for role in (0,1,2):
            indices=np.flatnonzero(self.role==role)
            ext.append(int(indices[np.argmax(y[indices]) if role==0 else np.argmin(y[indices])]))
        return {"worst_IL_db":float(y[ext[0]]),"min_H2_db":float(y[ext[1]]),
            "min_H3_db":float(y[ext[2]]),
            "locations":[{"setting":CASES[self.setting[i]],"mhz":float(self.f[i]),
                          "segment":int(self.segment[i])} for i in ext],
            "L_eig_min_nH":float(np.linalg.eigvalsh(inductance(x)[1])[0])}


def seed(ev,oldseed,randomized=False):
    x=np.zeros(24)
    x[:4]=oldseed[:4]
    x[4:7]=[oldseed[4+i] for i in range(4) if i!=REMOVE[ev.removed]]
    x[7:10]=oldseed[8:11]
    x[10:12]=[0.5 if -1 in e else 0.2 for e in ev.var_edges]
    for s in range(6):
        for j,e in enumerate(ev.var_edges):
            if e==(3,-1):v=oldseed[11+3*s]
            elif e==(1,2):v=oldseed[13+3*s]
            else:v=0.55*oldseed[13+3*s]
            x[12+2*s+j]=max(0,v-x[10+j])
    if randomized:
        rg=np.random.default_rng(20261020+24+len(ev.variant)+REMOVE[ev.removed])
        x[:4]*=np.exp(rg.normal(0,0.07,4))
        x[4:7]*=np.exp(rg.normal(0,0.2,3))
        x[7:10]+=rg.normal(0,0.01,3)
        x[10:12]+=rg.normal(0,0.12,2)
        x[12:]+=rg.normal(0,0.12,12)
    return np.clip(x,ev.bounds[:,0],ev.bounds[:,1])


def independent_mna(policy,variant,removed,x):
    ev=Evaluator(policy,variant,removed,3)
    expected=ev.il(x)
    _,M,H,BL=inductance(x)
    B=ev.BC
    err=res=0.
    minpassive=float("inf")
    for j,(mhz,setting) in enumerate(zip(ev.f,ev.setting)):
        w=2e6*math.pi*mhz
        cap=np.r_[x[4:7],x[12+2*setting:14+2*setting],x[10:12]]
        adm=w*1e-12*cap/(1/ev.Q_C-1j)
        pre,post=ev.pre[j],ev.post[j]
        zl=60-40j
        din=pre[0,1]+50*pre[1,1]
        Ysrc=(pre[0,0]+50*pre[1,0])/din
        source=1/din
        dout=post[0,0]*zl+post[0,1]
        Yload=(post[1,0]*zl+post[1,1])/dout
        A=np.zeros((9,9),complex)
        A[:5,:5]=B@np.diag(adm)@B.T
        A[0,0]+=Ysrc;A[2,2]+=Yload
        A[:5,5:]=BL;A[5:,:5]=BL.T
        A[5:,5:]=-w*1e-9*H
        right=np.zeros(9,complex);right[0]=source
        ans=np.linalg.solve(A,right)
        v,i=ans[:5],ans[5:]
        Pload=zl.real*abs(v[2]/dout)**2
        il=-10*np.log10(max(200*Pload,1e-300))
        err=max(err,abs(il-expected[j]))
        iin=source-Ysrc*v[0]
        vext=pre[0,0]*v[0]+pre[0,1]*iin
        iext=pre[1,0]*v[0]+pre[1,1]*iin
        reflected=abs(1-100*iext)**2/200
        ppre=float(np.real(vext*np.conj(iext)-v[0]*np.conj(iin)))
        ppost=float(np.real(v[2]*np.conj(Yload*v[2]))-Pload)
        pl=float(np.real(np.vdot(i,w*1e-9*H@i)))
        pc_each=adm.real*abs(B.T@v)**2
        pc=float(pc_each.sum())
        res=max(res,abs(.005-(reflected+ppre+ppost+pl+pc+Pload)))
        minpassive=min(minpassive,reflected,ppre,ppost,pl,pc,Pload,*pc_each)
    eig=float(np.linalg.eigvalsh(M)[0])
    return {"probes":len(ev.f),"max_IL_difference_db":float(err),
        "max_power_residual_W":float(res),"min_component_dissipation_W":float(minpassive),
        "L_matrix_min_eigenvalue_nH":eig,
        "pass":bool(err<1e-8 and res<1e-9 and minpassive>-1e-10 and eig>0)}


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--variant",choices=tuple(DTC),required=True)
    ap.add_argument("--remove",choices=tuple(REMOVE),required=True)
    ap.add_argument("--starts",type=int,default=2)
    ap.add_argument("--coarse",type=int,default=7)
    ap.add_argument("--fine",type=int,default=17)
    ap.add_argument("--dense",type=int,default=1001)
    ap.add_argument("--target",type=float,default=30.005)
    ap.add_argument("--out",type=Path)
    a=ap.parse_args()
    if min(a.starts,a.coarse,a.fine,a.dense)<1 or a.target<30 or a.dense<101:
        raise ValueError("Invalid experiment budget")
    policy=load_constraint("RF-T008",allow_trial=True)
    src=json.loads(SOURCE.read_text())
    oldseed=np.array(src["vector"],float)
    if oldseed.shape!=(29,):raise ValueError("Invalid four-L EXP047 checkpoint")
    ec=Evaluator(policy,a.variant,a.remove,a.dense)
    coarse=Evaluator(policy,a.variant,a.remove,a.coarse)
    fine=Evaluator(policy,a.variant,a.remove,a.fine)
    trials=[]
    for i in range(a.starts):
        v,st=optim.staged(coarse,fine,seed(ec,oldseed,bool(i)),a.target)
        m=ec.summary(v)
        eligible=bool(m["min_H2_db"]>=30 and m["min_H3_db"]>=30)
        trials.append({"start":i,"vector":v.tolist(),"solver":st,"dense":m,"finite_30db_pass":eligible})
        print("TRY",a.variant,a.remove,i,"IL",m["worst_IL_db"],
              "H2",m["min_H2_db"],"H3",m["min_H3_db"],flush=True)
    good=[q for q in trials if q["finite_30db_pass"]]
    best=min(good,key=lambda q:q["dense"]["worst_IL_db"]) if good else None
    chk=independent_mna(policy,a.variant,a.remove,np.array(best["vector"])) if best else None
    if chk is not None and not chk["pass"]:raise AssertionError("9x9 independent MNA failed")
    if best is not None:
        bs=[dict(norm(e),role="shunt_to_ground" if -1 in e else "bridge") for e in ec.var_edges]
        values=[float(v) for v in best["vector"][10:12]]
        cv=np.array(best["vector"][12:]).reshape(6,2).tolist()
        validate_ic_fixed_c_settings(policy,bs,values,dict(zip(CASES,cv)))
    report={"experiment_id":"EXP-058","phase":"Phase 2","constraint_id":"RF-T008",
        "revision":3,"chip_area":4,"variant":a.variant,"removed_C_edge":a.remove,
        "L_edges":old4.L_EDGES,"physical_L_row":["L0","L1","L3","L2"],
        "k_pairs":old4.K_PAIRS,"fixed_C_edges":ec.fixed_edges,
        "variable_C_edges":ec.var_edges,"parallel_IC_fixed_C_edges":ec.var_edges,
        "capacitor_Q":ec.Q_C.tolist(),"LQP02HV_Q":25,
        "constraint_SHA256":constraint_fingerprint(policy),
        "source_f003":str(SOURCE.relative_to(ROOT)),
        "code_execution_sha":subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip(),
        "grid":{"intervals":28,"coarse":a.coarse,"fine":a.fine,"dense":a.dense,"MNA_per_interval":3},
        "starts":trials,"best_finite_30db":best,"independent_MNA":chk,
        "limitations":["Local SLSQP only","Finite grid","No SRF/Q(f)/EM/physical k/temperature/cap tolerance/Phase3"]}
    out=a.out or ROOT/"results/EXP-058"/("fourl_"+a.remove+"_"+a.variant+".json")
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False)+"\n")
    print("RESULT",out,"candidate",best["dense"] if best else "NONE",flush=True)


if __name__=="__main__":
    main()

#!/usr/bin/env python3
"""EXP-052 RF-T007 Phase2: alternative 4L DTC electrical connections.

Only IL minimization subject to mandatory H2,H3>=30dB; no requested extra
harmonic margin or physical k realization study. 4L area=5+1/3, four
LQP02HV/Q25, Cf0/Cp GJM Q80, Cf1 PCB Q40, three programmable C Q35.
Exactly one grounded programmable Cv0 always gets a separate 0.5pF/Q40
ground parasitic (even at zero). Cv1/Cv2 never connect to GND.

Graph L0(0,1), L1(1,2), LsA(1,3), LsB(3,4), with row
L0-LsA-LsB-L1, nominal neighbor |k|<=0.10 per T007 base RF-F003.
Fixed capacitors Cf0(0,1), Cf1(1,2), Cp(4,GND).
Enumerate non-ground Cv1,Cv2 connection edges and shunt Cv0 node3/4.
"""
import argparse
import json
import math
import subprocess
import sys
from pathlib import Path
import numpy as np
from scipy.optimize import minimize

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
BASE=ROOT/"experiments/chatgpt_topology_search/runs/EXP-051"
CP=BASE/"checkpoints/one_shunt_4l_plain_best.json"
sys.path.insert(0,str(BASE))
sys.path.insert(0,str(ROOT/"src"))
import optimize_one_shunt_4l as exp51
from lpf.constraint_versions import load_constraint,constraint_fingerprint
from lpf.trial_shunt_dtc import shunt_dtc_parasitic_branches

# Each variant changes a physical connection, not merely a lumped C setting.
# Grounded Cv0 has one and only one fixed Cpar (same two terminals).
# Cv1 and Cv2 are non-ground branches and do not incur Cpar.
VARIANTS={
  "reference": ((4,-1),(0,1),(1,2)),
  "cv2_input_output": ((4,-1),(0,1),(0,2)),
  "cv2_input_tip": ((4,-1),(0,1),(0,4)),
  "cv2_output_tip": ((4,-1),(0,1),(2,4)),
  "cv2_shunt_bottom": ((4,-1),(0,1),(3,4)),
  "cv1_input_output": ((4,-1),(0,2),(1,2)),
  "cv1_input_tip": ((4,-1),(0,4),(1,2)),
  "cv0_at_shunt_mid": ((3,-1),(0,1),(1,2)),
  "cv0_mid_output_tip": ((3,-1),(0,1),(2,4)),
}

Q=np.array([80.,40.,80.,35.,35.,35.,40.],float)
# In contrast to EXP-051 trial optional trap, this is a true 7-capacitor graph.
CF_EDGES=((0,1),(1,2),(4,-1))
BOUNDS=exp51.bounds(False)
BASE_WORST_IL=0.8889928948043828
CASES=exp51.CASES

class Evaluator(exp51.Evaluator):
    def __init__(self,policy,samples,variant):
        if variant not in VARIANTS:raise KeyError("Unknown variant: "+variant)
        super().__init__(policy,samples,False)
        self.variant=variant
        self.cv_edges=VARIANTS[variant]
        self.cap_edges=CF_EDGES+self.cv_edges+(self.cv_edges[0],)
        self.cap_inc=exp51.incidence(self.cap_edges)
        self.cache_x=None
        self.cache_il=None

    def il(self,x):
        x=np.asarray(x,float)
        if x.shape!=(29,):
            raise ValueError("29 elements including zero absent trap")
        if self.cache_x is not None and np.array_equal(x,self.cache_x):
            return self.cache_il
        Yind,M,H=exp51.circuit_matrix(x)
        n=len(self.f)
        Y=np.broadcast_to(Yind,(n,5,5)).copy()/(self.omega[:,None,None]*1e-9)
        cv=x[11:].reshape(6,3)[self.setting]
        caps=np.column_stack((np.broadcast_to(x[4:7],(n,3)),cv,
                              np.full(n,0.5)))
        yc=self.omega[:,None]*1e-12*caps/(1/Q[None,:]-1j)
        Y+=np.einsum("nb,ib,jb->nij",yc,self.cap_inc,self.cap_inc,optimize=True)
        outer=[0,2];inner=[1,3,4]
        P=Y[:,outer,:][:,:,outer]
        U=Y[:,outer,:][:,:,inner]
        V=Y[:,inner,:][:,:,outer]
        E=Y[:,inner,:][:,:,inner]
        R=P-U@np.linalg.solve(E,V)
        a,b,c,d=R[:,0,0],R[:,0,1],R[:,1,0],R[:,1,1]
        if np.any(np.abs(c)<1e-20):raise ValueError("Singular 2 port")
        T=np.empty((n,2,2),complex)
        T[:,0,0]=-d/c;T[:,0,1]=-1/c
        T[:,1,0]=-(a*d-b*c)/c;T[:,1,1]=-a/c
        whole=self.pre@T@self.post
        zl=60-40j
        den=whole[:,0,0]*zl+whole[:,0,1]+50*(whole[:,1,0]*zl+whole[:,1,1])
        answer=-10*np.log10(np.maximum(200*zl.real/np.abs(den)**2,1e-300))
        self.cache_x=x.copy();self.cache_il=answer
        return answer

def strict(m):
    return bool(m["min_H2_db"]>=30 and m["min_H3_db"]>=30)

def description(ev,x):
    m=ev.summary(x)
    return {**m,"strict_30dB_H2H3":strict(m),
        "area":5+1/3,"parasitic_count":1,"fixed_C_Q":[80,40,80],
        "DTC_edges":ev.cv_edges,"DTC_parasitic_edge":ev.cv_edges[0],
        "PCB_C_count":1}

def independent_mna(policy,x,variant,points):
    """9x9 KCL + inductor KVL, distinct from 2-port elimination evaluator."""
    ev=Evaluator(policy,points,variant)
    ref=ev.il(x)
    _,M,H=exp51.circuit_matrix(x)
    eig=float(np.linalg.eigvalsh(M)[0])
    bc=ev.cap_inc
    maxerror=maxbalance=0.
    minloss=float("inf")
    for j,(mhz,setting) in enumerate(zip(ev.f,ev.setting)):
        omega=2e6*np.pi*mhz
        vals=np.r_[x[4:7],x[11+3*setting:14+3*setting],0.5]
        y=omega*1e-12*vals/(1/Q-1j)
        pre,post=ev.pre[j],ev.post[j]
        zl=60-40j
        din=pre[0,1]+50*pre[1,1]
        ys=(pre[0,0]+50*pre[1,0])/din
        source=1/din
        dout=post[0,0]*zl+post[0,1]
        yl=(post[1,0]*zl+post[1,1])/dout
        A=np.zeros((9,9),complex)
        A[:5,:5]=bc@np.diag(y)@bc.T
        A[0,0]+=ys;A[2,2]+=yl
        A[:5,5:]=exp51.BL
        A[5:,:5]=exp51.BL.T
        A[5:,5:]=-omega*1e-9*H
        b=np.zeros(9,complex);b[0]=source
        solution=np.linalg.solve(A,b)
        v,ind=solution[:5],solution[5:]
        power_load=zl.real*abs(v[2]/dout)**2
        il=-10*np.log10(max(power_load*200,1e-300))
        maxerror=max(maxerror,abs(il-ref[j]))
        inp=source-ys*v[0]
        external_v=pre[0,0]*v[0]+pre[0,1]*inp
        external_i=pre[1,0]*v[0]+pre[1,1]*inp
        reflected=abs(1-100*external_i)**2/200
        pin=float(np.real(external_v*np.conj(external_i)-v[0]*np.conj(inp)))
        pout=float(np.real(v[2]*np.conj(yl*v[2]))-power_load)
        pL=float(np.sum(omega*1e-9*x[:4]/25*abs(ind)**2))
        pCs=y.real*abs(bc.T@v)**2
        pc=float(pCs.sum())
        maxbalance=max(maxbalance,abs(.005-(reflected+pin+pout+pL+pc+power_load)))
        minloss=min(minloss,reflected,pin,pout,pL,pc,power_load,*[float(a) for a in pCs])
    return {"method":"independent explicit 9x9 4L KCL+KVL (single Q40 parasitic)",
       "probes":int(len(ev.f)),"max_IL_delta_dB":float(maxerror),
       "max_power_balance_error_W":float(maxbalance),
       "min_passive_dissipation_W":float(minloss),
       "min_L_eigenvalue_nH":eig,
       "pass":bool(maxerror<1e-8 and maxbalance<1e-9 and minloss>-1e-10 and eig>0)}

def optimize_stage(ev,seed,iters,target):
    start=np.r_[seed,ev.summary(seed)["worst_IL_db"]]
    bounds=[tuple(v) for v in BOUNDS]+[(0,100)]
    def constraint(v):
        level=ev.il(v[:-1])
        return np.where(ev.role==0,v[-1]-level,level-target)
    result=minimize(lambda v:float(v[-1]),start,method="SLSQP",
     bounds=bounds,constraints={"type":"ineq","fun":constraint},
     options={"maxiter":iters,"ftol":2e-9})
    x=np.clip(result.x[:-1],BOUNDS[:,0],BOUNDS[:,1])
    return x,{"converged":bool(result.success),"message":str(result.message),
      "iterations":int(result.nit),"calls":int(result.nfev),
      "coarse_min_constraint_slack_db":float(np.min(constraint(result.x)))}

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--starts",type=int,default=2)
    parser.add_argument("--maxiter",type=int,default=140)
    parser.add_argument("--coarse",type=int,default=7)
    parser.add_argument("--fine",type=int,default=17)
    parser.add_argument("--dense",type=int,default=1001)
    parser.add_argument("--mna",type=int,default=3)
    parser.add_argument("--target",type=float,default=30.005)
    parser.add_argument("--variants",nargs="*",choices=list(VARIANTS),default=list(VARIANTS))
    parser.add_argument("--out",type=Path)
    a=parser.parse_args()
    if min(a.starts,a.maxiter,a.coarse,a.fine,a.dense,a.mna)<1 or a.target<30:
        raise ValueError("Invalid search budget or mandatory limit")
    if len(set(a.variants))!=len(a.variants) or not a.variants:
        raise ValueError("Variant list duplicates or empty")
    policy=load_constraint("RF-T007",allow_trial=True)
    original=np.asarray(json.loads(CP.read_text())["vector"],float)
    if original.shape!=(29,) or original[7]!=0:raise ValueError("Base checkpoint wrong")
    for variant,edges in VARIANTS.items():
        assert edges[0][1]==-1 and edges[1][1]!=-1 and edges[2][1]!=-1
        paras=shunt_dtc_parasitic_branches(policy,[
            {"a":edges[0][0]+1,"b":0,"role":"shunt_to_ground"},
            {"a":edges[1][0]+1,"b":edges[1][1]+1,"role":"bridge"},
            {"a":edges[2][0]+1,"b":edges[2][1]+1,"role":"bridge"}])
        assert len(paras)==1 and paras[0]["node"]==edges[0][0]+1
    ref51=exp51.Evaluator(policy,a.dense,False)
    ctrl=Evaluator(policy,a.dense,"reference")
    ctrl_error=float(np.max(np.abs(ref51.il(original)-ctrl.il(original))))
    ctrl_IL=description(ctrl,original)
    if ctrl_error>1e-8 or abs(ctrl_IL["worst_IL_db"]-BASE_WORST_IL)>1e-6:
        raise AssertionError("Original EXP-051 4L checkpoint cannot be reproduced")
    result={"experiment_id":"EXP-052","constraint_id":"RF-T007","phase":"Phase 2",
      "source_checkpoint":str(CP.relative_to(ROOT)),
      "source_reference_IL_db":BASE_WORST_IL,
      "reference_reproduction_max_difference_db":ctrl_error,
      "reference_metrics":ctrl_IL,
      "study_goal":"additional 4L circuit connections; reduce worst IL with only mandatory H2/H3 >=30 dB",
      "internal_target_db":a.target,
      "chip_area":5+1/3,
      "fixed_C_edges":CF_EDGES,"fixed_C_Q":Q[:3].tolist(),
      "nominal_only":True,
      "models":{},"constraint_fingerprint":constraint_fingerprint(policy),
      "code_execution_sha":subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip(),
      "grid":{"segments":28,"coarse":a.coarse,"fine":a.fine,"dense":a.dense,"independent_mna":a.mna},
      "limitations":["Finite grid; no continuous band/global optimality proof",
        "No H2/H3 margin research beyond RF-T007 mandatory >=30dB",
        "No study of physical k realism, Q(f), SRF, EM or part variability"]}
    rng=np.random.default_rng(20261019+52)
    all_best=[]
    for variant in a.variants:
        dense=Evaluator(policy,a.dense,variant)
        coarse=Evaluator(policy,a.coarse,variant)
        fine=Evaluator(policy,a.fine,variant)
        seeds=[original.copy()]
        for j in range(a.starts-1):
            z=original.copy()
            z[:4]*=np.exp(rng.normal(0,.07 if j==0 else .14,4))
            z[4:7]*=np.exp(rng.normal(0,.09 if j==0 else .2,3))
            z[8:11]+=rng.normal(0,.012 if j==0 else .025,3)
            z[11:]+=rng.normal(0,.11 if j==0 else .25,18)
            seeds.append(np.clip(z,BOUNDS[:,0],BOUNDS[:,1]))
        trials=[]
        original_ev=description(dense,original)
        for startidx,z in enumerate(seeds):
            try:
                first,a1=optimize_stage(coarse,z,a.maxiter,a.target)
                final,a2=optimize_stage(fine,first,max(80,a.maxiter//2),a.target)
                outcome={"start":startidx,"coarse":a1,"fine":a2,
                    "converged":bool(a1["converged"] and a2["converged"]),
                    "vector":final.tolist(),"dense":description(dense,final)}
            except (np.linalg.LinAlgError,ValueError,OverflowError) as e:
                outcome={"start":startidx,"failed":str(e),"converged":False}
            trials.append(outcome)
            print("TRY",variant,startidx,
                  outcome.get("dense",{}).get("worst_IL_db"),
                  outcome.get("dense",{}).get("min_H2_db"),
                  outcome.get("dense",{}).get("min_H3_db"),
                  "converged",outcome.get("converged"),flush=True)
        passed=[t for t in trials if t.get("dense",{}).get("strict_30dB_H2H3")]
        best=min(passed,key=lambda o:o["dense"]["worst_IL_db"]) if passed else None
        # Never silently treat a design below 30dB as feasible.
        candidateMNA=independent_mna(policy,np.asarray(best["vector"]),variant,a.mna) if best else None
        if candidateMNA and not candidateMNA["pass"]:
            raise AssertionError("Independent 9x9 MNA failed for "+variant)
        result["models"][variant]={"cv_edges":VARIANTS[variant],
          "original_baseline_vector_metrics":original_ev,
          "runs":trials,"selected_strict_30dB":best,
          "independent_MNA":candidateMNA,
          "status":"finite_grid_30dB_pass" if best else "no_verified_feasible_local_point"}
        if best:
            all_best.append({"variant":variant,"metrics":best["dense"],"converged":best["converged"]})
        print("VARIANT",variant,"BEST",
              None if not best else best["dense"]["worst_IL_db"],
              "MNA",None if not candidateMNA else candidateMNA["pass"],flush=True)
    result["summary"]={
       "evaluated_variant_count":len(a.variants),
       "attempted_starts":len(a.variants)*a.starts,
       "passed_variants":len(all_best),
       "ranked_by_best_worst_IL":sorted(all_best,key=lambda z:z["metrics"]["worst_IL_db"])}
    dest=a.out or ROOT/"results/EXP-052/topology_sweep.json"
    dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("FINAL",str(dest),"LEADERBOARD",result["summary"]["ranked_by_best_worst_IL"],flush=True)

if __name__=="__main__":
    main()

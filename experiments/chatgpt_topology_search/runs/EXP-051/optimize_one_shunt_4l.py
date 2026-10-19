#!/usr/bin/env python3
"""EXP-051: RF-T007 4L/one-shunt-DTC topology and split-L/trap experiment.

Source: verified RF-T007 EXP-050 area4+1/3 3L checkpoint. New 4L graph:
 L0 (0,1), L1 (1,2), LsA (1,3), LsB (3,4), physical row
 [L0,LsA,LsB,L1], coupling allowed only (0,2),(2,3),(3,1).
 Fixed C: Cf0 GJM Q80 (0,1); Cf1 PCB Q40 (1,2);
 Cp GJM Q80 (4,GND); optional Ctrap PCB Q40 (3,4).
 DTC C0 Q35 (4,GND), C1 Q35 (0,1), C2 Q35 (1,2).
 Exactly one unavoidable Cpar=0.5pF/Q40 (4,GND), always present.

Plain variant: Ctrap=0 (NO installed PCB Ctrap), chip area 5+1/3.
Trap variant: Ctrap 0.02..0.2pF installed as second PCB C, same chip area.
A special exact-source seed splits the original 3L shunt inductance into
two series inductors. Its physical coupling values are adjusted so that the
complete lossy 4L admittance agrees with the 3L circuit. This is a controlled
topological re-expression of the RF-T007 3L baseline, NOT a new Pareto gain.
Any further reduction in 4L worst IL must come from actual optimization.
"""
import argparse
import json
import math
import subprocess
import sys
from pathlib import Path

import numpy as np
from scipy.optimize import minimize

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
SOURCE_SCRIPT = ROOT / "experiments/chatgpt_topology_search/runs/EXP-050"
SOURCE_VECTOR = SOURCE_SCRIPT / "checkpoints/area4p333_rft007_best.json"
sys.path.insert(0, str(SOURCE_SCRIPT))
sys.path.insert(0, str(ROOT / "src"))
import area4p333_rft007 as src3
from lpf.constraint_versions import load_constraint, constraint_fingerprint
from lpf.trial_shunt_dtc import shunt_dtc_parasitic_branches

L_EDGES = ((0,1),(1,2),(1,3),(3,4))   # L0,L1,LsA,LsB
CAP_EDGES = ((0,1),(1,2),(4,-1),       # Cf0,Cf1,Cp
             (4,-1),(0,1),(1,2),       # Cv0,Cv1,Cv2
             (4,-1),(3,4))             # Cpar,optional PCB trap
Q_C = np.array([80.,40.,80.,35.,35.,35.,40.,40.],float)
L_COUPLING_EDGES = ((0,2),(2,3),(3,1)) # physical single-row neighbors
CASES = src3.SETTINGS

def incidence(edges,nodes=5):
    mat=np.zeros((nodes,len(edges)),float)
    for j,(a,b) in enumerate(edges):
        mat[a,j]=1.
        if b>=0: mat[b,j]=-1.
    return mat

BL=incidence(L_EDGES)
BC=incidence(CAP_EDGES)

def bounds(trap):
    b=np.array([(0.4,27.)]*4+[(.02,100.),(.02,.2),(.02,100.)]+
               ([(.02,.2)] if trap else [(0.,0.)])+
               [(-.1,.1)]*3+[(0.,3.)]*18,float)
    assert b.shape==(29,2)
    return b

def circuit_matrix(x):
    L=np.asarray(x[:4],float)
    M=np.diag(L)
    for (a,b),k in zip(L_COUPLING_EDGES,x[8:11]):
        M[a,b]=M[b,a]=k*math.sqrt(L[a]*L[b])
    if float(np.linalg.eigvalsh(M)[0])<=0:
        raise ValueError("Inductance M not SPD")
    H=np.diag(L/25.)+1j*M
    return BL @ np.linalg.solve(H,BL.T),M,H

class Evaluator(src3.Evaluator):
    def __init__(self,policy,points,trap):
        # Reuse only the 28-band sampling + verified external S2P generation.
        super().__init__(policy,points,parasitic_pf=0.5)
        self.trap=bool(trap)
        self.bounds=bounds(self.trap)
        self.area=5+1/3
        self.cache_x=None
        self.cache_il=None

    def il(self,x):
        x=np.asarray(x,float)
        if x.shape!=(29,):
            raise ValueError("EXP-051 expected complete 29-parameter 4L circuit")
        if self.cache_x is not None and np.array_equal(x,self.cache_x):
            return self.cache_il
        K,M,H=circuit_matrix(x)
        n=len(self.f)
        Y=np.broadcast_to(K,(n,5,5)).copy()/(self.omega[:,None,None]*1e-9)
        Cvar=x[11:].reshape(6,3)[self.setting]
        C=np.column_stack((np.broadcast_to(x[4:7],(n,3)),Cvar,
                           np.full(n,.5),np.full(n,x[7])))
        yc=self.omega[:,None]*1e-12*C/(1/Q_C[None,:]-1j)
        Y+=np.einsum("nb,ib,jb->nij",yc,BC,BC,optimize=True)
        outer=[0,2]
        inner=[1,3,4]
        P=Y[:,outer,:][:,:,outer]
        U=Y[:,outer,:][:,:,inner]
        V=Y[:,inner,:][:,:,outer]
        E=Y[:,inner,:][:,:,inner]
        R=P-U@np.linalg.solve(E,V)
        a,b,c,d=R[:,0,0],R[:,0,1],R[:,1,0],R[:,1,1]
        if np.any(np.abs(c)<1e-20):
            raise ValueError("Undefined two port")
        T=np.empty((n,2,2),complex)
        T[:,0,0]=-d/c;T[:,0,1]=-1/c
        T[:,1,0]=-(a*d-b*c)/c;T[:,1,1]=-a/c
        full=self.pre@T@self.post
        zl=60-40j
        den=full[:,0,0]*zl+full[:,0,1]+50*(full[:,1,0]*zl+full[:,1,1])
        result=-10*np.log10(np.maximum(4*50*zl.real/np.abs(den)**2,1e-300))
        self.cache_x=x.copy()
        self.cache_il=result
        return result

def from_threeL(x,trap=False):
    """Series split with SAME effective L, winding loss and port mutual flux."""
    x=np.asarray(x,float)
    if x.shape!=(26,): raise ValueError("3L frozen vector wrong length")
    L0,L1,Ls=x[:3]
    La=Ls/2;Lb=Ls-La
    new=np.r_[L0,L1,La,Lb,x[3:6],.02 if trap else 0.,
              x[6]*math.sqrt(Ls/La),0.,x[7]*math.sqrt(Ls/Lb),x[8:]]
    assert new.shape==(29,)
    return new

def summarize(ev,x):
    r=ev.summary(x)
    return {**r,"mandatory_30dB_PASS":bool(r["min_H2_db"]>=30 and r["min_H3_db"]>=30),
      "chip_area_units":5+1/3,"shunt_fixed_parasitic_count":1,
      "PCB_pattern_C_count":2 if ev.trap else 1,
      "Ctrap_real_pf":float(x[7]),"GJM_C_fixed_pf":[float(x[4]),float(x[6])]}

def optimize_stage(ev,start,maxiter,target):
    z=np.asarray(start,float)
    vmax=ev.summary(z)["worst_IL_db"]
    initial=np.r_[z,vmax]
    limits=[tuple(v) for v in ev.bounds]+[(0.,100.)]
    def slack(w):
        values=ev.il(w[:-1])
        return np.where(ev.role==0,w[-1]-values,values-target)
    sol=minimize(lambda w:float(w[-1]),initial,method="SLSQP",
      bounds=limits,constraints={"type":"ineq","fun":slack},
      options={"maxiter":maxiter,"ftol":2e-9})
    vec=np.clip(sol.x[:-1],ev.bounds[:,0],ev.bounds[:,1])
    return vec,{"converged":bool(sol.success),"message":str(sol.message),
      "iterations":int(sol.nit),"function_evaluations":int(sol.nfev),
      "coarse_min_slack_dB":float(np.min(slack(sol.x)))}

def independent_MNA(policy,x,points,trap):
    """Independent 9x9 MNA: five node voltages + four branch currents."""
    ev=Evaluator(policy,points,trap)
    reference=ev.il(x)
    _,M,H=circuit_matrix(x)
    eigen=float(np.linalg.eigvalsh(M)[0])
    max_error,max_residual=0.,0.
    min_dissipation=float("inf")
    for j,(MHz,setting) in enumerate(zip(ev.f,ev.setting)):
        w=2e6*math.pi*MHz
        caps=np.r_[x[4:7],x[11+3*setting:14+3*setting],0.5,x[7]]
        Yc=w*1e-12*caps/(1/Q_C-1j)
        pre,post=ev.pre[j],ev.post[j]
        zl=60-40j
        din=pre[0,1]+50*pre[1,1]
        ys=(pre[0,0]+50*pre[1,0])/din
        source=1/din
        dout=post[0,0]*zl+post[0,1]
        yl=(post[1,0]*zl+post[1,1])/dout
        A=np.zeros((9,9),complex)
        A[:5,:5]=BC@np.diag(Yc)@BC.T
        A[0,0]+=ys
        A[2,2]+=yl
        A[:5,5:]=BL
        A[5:,:5]=BL.T
        A[5:,5:]=-w*1e-9*H
        rhs=np.zeros(9,complex)
        rhs[0]=source
        vi=np.linalg.solve(A,rhs)
        volt,cur=vi[:5],vi[5:]
        load_p=zl.real*abs(volt[2]/dout)**2
        il=-10*np.log10(max(200*load_p,1e-300))
        max_error=max(max_error,abs(il-reference[j]))
        iin=source-ys*volt[0]
        vext=pre[0,0]*volt[0]+pre[0,1]*iin
        iext=pre[1,0]*volt[0]+pre[1,1]*iin
        reflected=abs(1-100*iext)**2/200
        input_loss=float(np.real(vext*np.conj(iext)-volt[0]*np.conj(iin)))
        output_loss=float(np.real(volt[2]*np.conj(yl*volt[2]))-load_p)
        induct_loss=float(np.sum(w*1e-9*x[:4]/25*abs(cur)**2))
        capacitor_each=Yc.real*abs(BC.T@volt)**2
        cap_loss=float(capacitor_each.sum())
        residual=0.005-(reflected+input_loss+output_loss+induct_loss+cap_loss+load_p)
        max_residual=max(max_residual,abs(residual))
        min_dissipation=min(min_dissipation,reflected,input_loss,output_loss,
                            induct_loss,cap_loss,load_p,*[float(v) for v in capacitor_each])
    return {"method":"independent 9x9 coupled-L branch-current MNA with one distinct 0.5pF/Q40 grounded parasitic",
      "probes":int(len(ev.f)),"max_IL_error_db":float(max_error),
      "max_power_balance_residual_W":float(max_residual),
      "min_component_dissipation_W":float(min_dissipation),
      "min_M_eigenvalue_nH":eigen,
      "PASS":bool(max_error<1e-8 and max_residual<1e-9 and
                  min_dissipation>-1e-10 and eigen>0)}

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--starts",type=int,default=3)
    ap.add_argument("--maxiter",type=int,default=150)
    ap.add_argument("--coarse",type=int,default=7)
    ap.add_argument("--fine",type=int,default=17)
    ap.add_argument("--dense",type=int,default=1001)
    ap.add_argument("--mna",type=int,default=3)
    ap.add_argument("--target",type=float,default=30.02)
    ap.add_argument("--out",type=Path)
    a=ap.parse_args()
    if min(a.starts,a.maxiter,a.coarse,a.fine,a.dense,a.mna)<1 or a.target<30:
        raise ValueError("Invalid search arguments")
    policy=load_constraint("RF-T007",allow_trial=True)
    grounds=shunt_dtc_parasitic_branches(policy,[
       {"a":5,"b":0,"role":"shunt_to_ground"},
       {"a":1,"b":2,"role":"bridge"},
       {"a":2,"b":3,"role":"bridge"}])
    if len(grounds)!=1 or grounds[0]["node"]!=5:
        raise AssertionError("RF-T007 one grounded DTC expected")
    checkpoint=json.loads(SOURCE_VECTOR.read_text(encoding="utf-8"))
    prior=np.asarray(checkpoint.get("vector",checkpoint.get("best_vector")),float)
    assert prior.shape==(26,)
    src_dense=src3.Evaluator(policy,a.dense,0.5)
    original=src_dense.summary(prior)
    if abs(original["worst_IL_db"]-0.8918270109628332)>1e-6:
        raise AssertionError("Original T007 area4+1/3 checkpoint not reproduced")
    frozen_plain=from_threeL(prior,False)
    frozen_trap=from_threeL(prior,True)
    empty=Evaluator(policy,a.dense,False)
    projected=summarize(empty,frozen_plain)
    electrical_error=float(np.max(np.abs(src_dense.il(prior)-empty.il(frozen_plain))))
    if electrical_error>1e-8:
        raise AssertionError("Exact split-L 3L-to-4L no-Ctrap equivalence failed: "+str(electrical_error))
    if not projected["mandatory_30dB_PASS"]:
        raise AssertionError("Exact source seed must remain RF-T007 H2/H3 compliant")
    rng=np.random.default_rng(20261019+51)
    report={
       "experiment_id":"EXP-051","constraint_id":"RF-T007",
       "phase":"Phase 2","objective":"full_lpf",
       "effective_constraint_sha256":constraint_fingerprint(policy),
       "source_checkpoint":str(SOURCE_VECTOR.relative_to(ROOT)),
       "source_3L_frozen_vector":prior.tolist(),
       "source_3L_frozen_metrics":original,
       "exact_split_4L_frozen_vector":frozen_plain.tolist(),
       "exact_split_4L_frozen_metrics":projected,
       "max_full_28xN_IL_difference_between_3L_and_4L_db":electrical_error,
       "chip_area":5+1/3,
       "fixed_C_types":["GJM01 Q80 Cf0","PCB Q40 Cf1","GJM01 Q80 Cp"],
       "inductor_order":["L0","LsA","LsB","L1"],
       "variable_C_edges":[[4,-1],[0,1],[1,2]],
       "parasitic":[{"DTC":"Cv0","nodes":[4,-1],"C_pf":.5,"Q":40}],
       "variants":{},
       "execution_sha":subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip(),
       "limitations":["All candidates finite-grid local Phase2 model, not a global Pareto bound",
         "Fixed input/output S2P model; no Q(f)/SRF/PCB EM/tolerances",
         "Changing shunt topology is not a proof about all 4L designs"]}
    for variant in ("plain","trap"):
        trap=variant=="trap"
        ec=Evaluator(policy,a.coarse,trap)
        ef=Evaluator(policy,a.fine,trap)
        ed=empty if not trap else Evaluator(policy,a.dense,True)
        baseline=frozen_trap if trap else frozen_plain
        variants=[{"tag":"frozen_seed","vector":baseline.tolist(),"metrics":summarize(ed,baseline),
                   "converged":None}]
        starts=[baseline]
        for j in range(a.starts-1):
            z=baseline.copy()
            z[:4]*=np.exp(rng.normal(0,.04 if j==0 else .10,4))
            z[4:7]*=np.exp(rng.normal(0,.04 if j==0 else .10,3))
            if trap: z[7]=min(.2,max(.02,.02*np.exp(rng.normal(.1,.8))))
            z[8:11]+=rng.normal(0,.007 if j==0 else .02,3)
            z[11:]+=rng.normal(0,.05 if j==0 else .15,18)
            starts.append(np.clip(z,ed.bounds[:,0],ed.bounds[:,1]))
        for j,z in enumerate(starts):
            try:
                xc,cs=optimize_stage(ec,z,a.maxiter,a.target)
                xf,fs=optimize_stage(ef,xc,max(70,a.maxiter//2),a.target)
                v={"tag":"optimized","start":j,"coarse":cs,"fine":fs,
                   "converged":bool(cs["converged"] and fs["converged"]),
                   "vector":xf.tolist(),"metrics":summarize(ed,xf)}
            except (np.linalg.LinAlgError,ValueError) as error:
                v={"tag":"failed","start":j,"error":str(error)}
            variants.append(v)
            print("TRIAL",variant,j,v.get("metrics"),
                  "SOLVED",v.get("converged"),flush=True)
        eligible=[v for v in variants if v.get("metrics",{}).get("mandatory_30dB_PASS")]
        chosen=min(eligible,key=lambda v:v["metrics"]["worst_IL_db"]) if eligible else None
        check=independent_MNA(policy,np.asarray(chosen["vector"]),a.mna,trap) if chosen else None
        if check and not check["PASS"]:
            raise AssertionError("Independent MNA failed for "+variant)
        report["variants"][variant]={
            "PCB_extra_C_installed":trap,
            "attempts":variants,
            "best_strict_H2H3_30dB":chosen,
            "independent_MNA":check,
            "status":"finite_grid_H2H3_pass" if chosen else "no_compliant_local_candidate_found"}
    report["grid"]={"segments":28,"dense_points_per_segment":a.dense,
        "independent_points_per_segment":a.mna,"starts_per_variant":a.starts,
        "maxiter":a.maxiter,"target_db":a.target}
    dest=a.out or ROOT/"results/EXP-051/one_shunt_4L.json"
    dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_text(json.dumps(report,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print("FINAL",str(dest),"PLAIN",report["variants"]["plain"]["best_strict_H2H3_30dB"]["metrics"],
          "TRAP",report["variants"]["trap"]["best_strict_H2H3_30dB"]["metrics"] if report["variants"]["trap"]["best_strict_H2H3_30dB"] else None,
          flush=True)

if __name__=="__main__":
    main()

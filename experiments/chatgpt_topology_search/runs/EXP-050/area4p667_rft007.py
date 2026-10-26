#!/usr/bin/env python3
"""EXP-050 step4/6: EXP-042 area 4+2/3 4L from RF-T005 to RF-T007.

Exactly two grounded DTCs Cv0(3,GND), Cv1(4,GND): two permanent 0.5pF/Q40
branches. Cv2(1,2) is a non-ground bridge with no such branch.
Cf0 GJM01 Q80; Cf1, Cf2 and Cp PCB_PATTERN_C Q40, 0.02..0.2pF each.
Four LQP02HV Q25 with physical order L0-L1-L3-L2 and adjacent |k|<=0.1.
Independent 9x9 coupled-L branch-current MNA stamps all nine C elements
separately and verifies numerical IL and nonnegative circuit losses.
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
OLD = ROOT / "experiments/chatgpt_topology_search/runs/EXP-042"
CHECKPOINT = OLD / "checkpoints/pcb_both.json"
sys.path.insert(0, str(ROOT / "src"))
from lpf.phase2_models import exp042 as t005
from lpf.constraint_versions import load_constraint, constraint_fingerprint
from lpf.trial_shunt_dtc import shunt_dtc_parasitic_branches

FIXED_PARASITIC_PF=0.5
PHYSICAL_COMPONENT_Q=np.array([80.,40.,40.,40.,35.,35.,35.,40.,40.])
CAP_EDGES=t005.C_EDGES+((3,-1),(4,-1))
BC=t005.incidence(CAP_EDGES)
PHYSICAL_BOUNDS=np.array(t005.BOUNDS,float)
PHYSICAL_BOUNDS[5:7]=[0.02,0.2]  # Cf1 and Cf2 must be real PCB-pattern C, not GJM

class Evaluator(t005.Evaluator):
    def __init__(self,policy,points,parasitic_pf):
        super().__init__(policy,points)
        self.parasitic_pf=float(parasitic_pf)

    def il(self,x):
        x=np.asarray(x,float)
        if x.shape!=(29,):
            raise ValueError("EXP-042 vector must have 29 parameters")
        if self.prev is not None and np.array_equal(self.prev,x):
            return self.prev_il
        K,_=t005.matrices(x)
        n=len(self.f)
        Y=np.broadcast_to(K,(n,5,5)).copy()/(self.omega[:,None,None]*1e-9)
        variable_C=x[11:].reshape((6,3))[self.setting]
        caps=np.column_stack((np.broadcast_to(x[4:8],(n,4)),variable_C,
                              np.full(n,self.parasitic_pf),np.full(n,self.parasitic_pf)))
        cap_ad=self.omega[:,None]*1e-12*caps/(1/PHYSICAL_COMPONENT_Q[None,:]-1j)
        Y+=np.einsum("nb,ib,jb->nij",cap_ad,BC,BC,optimize=True)
        ports=[0,2]; interior=[1,3,4]
        P=Y[:,ports,:][:,:,ports]
        U=Y[:,ports,:][:,:,interior]
        V=Y[:,interior,:][:,:,ports]
        E=Y[:,interior,:][:,:,interior]
        reduced=P-U@np.linalg.solve(E,V)
        a,b,c,d=reduced[:,0,0],reduced[:,0,1],reduced[:,1,0],reduced[:,1,1]
        if np.any(np.abs(c)<1e-17):
            raise ValueError("Singular LPF 2-port")
        lpf=np.empty((n,2,2),complex)
        lpf[:,0,0]=-d/c
        lpf[:,0,1]=-1/c
        lpf[:,1,0]=-(a*d-b*c)/c
        lpf[:,1,1]=-a/c
        full=self.pre@lpf@self.post
        zl=60-40j; zs=50.
        den=full[:,0,0]*zl+full[:,0,1]+zs*(full[:,1,0]*zl+full[:,1,1])
        result=-10*np.log10(np.maximum(4*zs*zl.real/np.abs(den)**2,1e-300))
        self.prev,self.prev_il=x.copy(),result
        return result

def metrics(e,x):
    q=e.summary(x)
    return {**q,
      "H2H3_30_pass":bool(q["min_h2_db"]>=30 and q["min_h3_db"]>=30),
      "C_fix_pf":np.asarray(x[4:8]).tolist(),
      "C_variable_max_pf":float(np.max(x[11:])),
      "C_parasitic_pf_each":float(e.parasitic_pf),
      "C_parasitic_count":2,
      "chip_area":4+2/3}

def independent(policy,x,points):
    """Explicit 9x9 KCL + coupled inductor KVL; external S2Ps from input data."""
    e=Evaluator(policy,points,FIXED_PARASITIC_PF)
    x=np.asarray(x,float)
    reference=e.il(x)
    L=x[:4]
    M=np.diag(L.copy())
    for j,k in enumerate(x[8:11]):
        a,b=t005.L_ORDER[j:j+2]
        M[a,b]=M[b,a]=k*math.sqrt(L[a]*L[b])
    eig=float(np.linalg.eigvalsh(M)[0])
    if eig<=0:
        raise ValueError("Full 4L mutual inductance matrix is not SPD")
    H=np.diag(L/25.)+1j*M
    max_err,max_balance=0.,0.
    min_passive=float("inf")
    for j,(mhz,si) in enumerate(zip(e.f,e.setting)):
        w=2e6*math.pi*mhz
        values=np.r_[x[4:8],x[11+3*si:14+3*si],FIXED_PARASITIC_PF,FIXED_PARASITIC_PF]
        Yc=w*1e-12*values/(1/PHYSICAL_COMPONENT_Q-1j)
        ti,to=e.pre[j],e.post[j]
        zl=60-40j
        di=ti[0,1]+50*ti[1,1]
        ys=(ti[0,0]+50*ti[1,0])/di
        src=1/di
        do=to[0,0]*zl+to[0,1]
        yl=(to[1,0]*zl+to[1,1])/do
        A=np.zeros((9,9),complex)
        A[:5,:5]=BC@np.diag(Yc)@BC.T
        A[0,0]+=ys; A[2,2]+=yl
        A[:5,5:]=t005.BL
        A[5:,:5]=t005.BL.T
        A[5:,5:]=-w*1e-9*H
        rhs=np.zeros(9,complex);rhs[0]=src
        solution=np.linalg.solve(A,rhs)
        v,I=solution[:5],solution[5:]
        p_load=zl.real*abs(v[2]/do)**2
        il=-10*np.log10(max(200*p_load,1e-300))
        max_err=max(max_err,abs(il-reference[j]))
        i_in=src-ys*v[0]
        vext=ti[0,0]*v[0]+ti[0,1]*i_in
        iext=ti[1,0]*v[0]+ti[1,1]*i_in
        reflected=abs(1-100*iext)**2/200
        p_input=float(np.real(vext*np.conj(iext)-v[0]*np.conj(i_in)))
        p_output=float(np.real(v[2]*np.conj(yl*v[2]))-p_load)
        p_ind=float(np.sum(w*1e-9*L/25*abs(I)**2))
        cap_each=Yc.real*abs(BC.T@v)**2
        p_cap=float(cap_each.sum())
        residual=0.005-(reflected+p_input+p_output+p_ind+p_cap+p_load)
        max_balance=max(max_balance,abs(residual))
        min_passive=min(min_passive,reflected,p_input,p_output,p_ind,p_cap,p_load,*[float(q) for q in cap_each])
    return {"probe_count":int(len(e.f)),"method":"independent 9x9 coupled-inductor branch-current MNA with two explicit 0.5pF/Q40 grounded C branches",
            "max_IL_difference_db":float(max_err),
            "max_power_balance_residual_W":float(max_balance),
            "min_component_dissipation_W":float(min_passive),
            "min_L_eigenvalue_nH":eig,
            "pass":bool(max_err<1e-8 and max_balance<1e-9 and min_passive>-1e-10)}

def optimize_stage(e,start,target,maxiter):
    initial=np.r_[start,e.summary(start)["worst_il_db"]]
    bounds=[tuple(v) for v in PHYSICAL_BOUNDS]+[(0,10)]
    def slack(z):
        il=e.il(z[:-1])
        return np.where(e.role==0,z[-1]-il,il-target)
    opt=minimize(lambda z:float(z[-1]),initial,bounds=bounds,
        constraints={"type":"ineq","fun":slack},method="SLSQP",
        options={"maxiter":maxiter,"ftol":4e-9})
    x=np.clip(opt.x[:-1],PHYSICAL_BOUNDS[:,0],PHYSICAL_BOUNDS[:,1])
    return x,{"success":bool(opt.success),"message":str(opt.message),
      "nit":int(opt.nit),"nfev":int(opt.nfev),"min_coarse_slack_db":float(np.min(slack(opt.x)))}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--starts",type=int,default=2)
    p.add_argument("--maxiter",type=int,default=100)
    p.add_argument("--coarse",type=int,default=9)
    p.add_argument("--refine",type=int,default=21)
    p.add_argument("--dense",type=int,default=1001)
    p.add_argument("--mna",type=int,default=3)
    p.add_argument("--target",type=float,default=30.02)
    p.add_argument("--out",type=Path)
    a=p.parse_args()
    if min(a.starts,a.maxiter,a.coarse,a.refine,a.dense,a.mna)<1 or a.target<30:
        raise ValueError("Invalid search parameters")
    policy=load_constraint("RF-T007",allow_trial=True)
    got=shunt_dtc_parasitic_branches(policy,[
      {"a":4,"b":0,"role":"shunt_to_ground"},
      {"a":5,"b":0,"role":"shunt_to_ground"},
      {"a":2,"b":3,"role":"bridge"}])
    assert len(got)==2 and [q["node"] for q in got]==[4,5]
    old=json.loads(CHECKPOINT.read_text(encoding="utf-8"))
    seed=np.asarray(old["vector"],float)
    if seed.shape!=(29,):
        raise ValueError("Incomplete EXP-042 4L checkpoint")
    if np.any(seed<PHYSICAL_BOUNDS[:,0]-1e-8) or np.any(seed>PHYSICAL_BOUNDS[:,1]+1e-8):
        raise ValueError("Historical vector exceeds physical component bounds")
    basepolicy=load_constraint("RF-T005",allow_trial=True)
    oldev=Evaluator(basepolicy,a.dense,0.)
    historical=metrics(oldev,seed)
    if abs(historical["worst_il_db"]-old["verification"]["worst_IL_db"])>1e-6:
        raise AssertionError("Historical RF-T005 candidate reproduction mismatch")
    dense=Evaluator(policy,a.dense,FIXED_PARASITIC_PF)
    unchanged=metrics(dense,seed)
    compensated=seed.copy()
    compensated[11::3]=np.maximum(0,compensated[11::3]-0.5)
    compensated[12::3]=np.maximum(0,compensated[12::3]-0.5)
    compensated_metrics=metrics(dense,compensated)
    starts=[seed,compensated]
    if a.starts>2:
        rng=np.random.default_rng(20261019+4)
        for i in range(a.starts-2):
            z=compensated.copy()
            z[:4]*=np.exp(rng.normal(0,.04,4))
            z[8:11]+=rng.normal(0,.008,3)
            z[11:]+=rng.normal(0,.05,18)
            starts.append(np.clip(z,PHYSICAL_BOUNDS[:,0],PHYSICAL_BOUNDS[:,1]))
    coarse=Evaluator(policy,a.coarse,FIXED_PARASITIC_PF)
    fine=Evaluator(policy,a.refine,FIXED_PARASITIC_PF)
    candidates=[
       {"stage":"unchanged_frozen", "vector":seed.tolist(),"dense":unchanged},
       {"stage":"Cv0_Cv1_compensated", "vector":compensated.tolist(),"dense":compensated_metrics}
    ]
    attempts=[]
    for j,first in enumerate(starts[:a.starts]):
        try:
            interim,cs=optimize_stage(coarse,first,a.target,a.maxiter)
            vec,fs=optimize_stage(fine,interim,a.target,max(60,a.maxiter//2))
            row={"start":j,"stage":"SLSQP_reoptimized","coarse":cs,"refined":fs,
                  "vector":vec.tolist(),"dense":metrics(dense,vec)}
            candidates.append(row)
        except (ValueError,np.linalg.LinAlgError) as err:
            row={"start":j,"stage":"failed","error":str(err)}
        attempts.append(row)
        print("TRY",j,row.get("dense"),flush=True)
    admissible=[q for q in candidates if q.get("dense",{}).get("H2H3_30_pass")]
    best=min(admissible,key=lambda q:q["dense"]["worst_il_db"]) if admissible else None
    independent_result=independent(policy,np.asarray(best["vector"]),a.mna) if best else None
    if independent_result and not independent_result["pass"]:
        raise AssertionError("Independent 9x9 MNA disagreeing with optimizer")
    report={"experiment_id":"EXP-050","constraint_id":"RF-T007",
      "source_experiment":"EXP-042","step":"4_of_6_area4p667","phase":"Phase 2",
      "source_checkpoint":str(CHECKPOINT.relative_to(ROOT)),
      "source_original_vector":seed.tolist(),
      "fixed_C_types":["GJM01 Q80","PCB_PATTERN_C Q40","PCB_PATTERN_C Q40","PCB_PATTERN_C Q40"],
      "physical_L_order":list(t005.L_ORDER),
      "variable_C_edges":list(t005.C_EDGES[4:]),
      "added_parasitics":[{"node":3,"to_GND":True,"C_pf":0.5,"Q":40},
                          {"node":4,"to_GND":True,"C_pf":0.5,"Q":40}],
      "constraint_fingerprint":constraint_fingerprint(policy),
      "historical_T005":historical,"frozen_T007":unchanged,
      "compensated_T007":compensated_metrics,"attempts":attempts,"selected":best,
      "independent_MNA":independent_result,
      "finite_grid":{"segments":28,"points_per_segment":a.dense},
      "code_sha":subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip(),
      "status":"H2H3_30dB_finite_grid_candidate" if best else "no_pass_candidate_found",
      "limitations":["Finite-grid local candidate, not global nor continuous extrema proof",
                     "No EM/Q(f)/SRF/switch tolerance validation",
                     "Two later T005 Pareto checkpoints not analyzed by this step"]}
    dest=a.out or ROOT/"results/EXP-050/area4p667_rft007.json"
    dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n")
    print("FINAL",dest,"BEST",best["dense"] if best else None,"MNA",independent_result,flush=True)

if __name__=="__main__":
    main()

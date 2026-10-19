#!/usr/bin/env python3
"""EXP-050 step 2/6: EXP-045 area=3+2/3 3L T005 Pareto -> RF-T007.

Correct topology: 3 LQP02HV Q25, PCB Cf0/Cf1 Q40 and fixed extra PCB Q40
on Cf1's (junction,OUT) edge, GJM Cp Q80 from shunt tip to GND, variable
Cv0 shunt tip to GND, Cv1/Cv2 across L0/L1. ONLY Cv0 has a separate
always-present 0.5pF Q40 parasitic branch. Do not combine Cp Q80 with
parasitic Q40 (the capacitor loss model would become incorrect).
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
SOURCE = ROOT / "experiments/chatgpt_topology_search/runs/EXP-043"
CHECKPOINT = ROOT / "experiments/chatgpt_topology_search/runs/EXP-045/checkpoints/t3l_extra_pcb_out_0p2_prelim.json"
sys.path.insert(0, str(SOURCE))
sys.path.insert(0, str(ROOT / "src"))
import search_3l as base
from lpf.constraint_versions import load_constraint, constraint_fingerprint
from lpf.trial_shunt_dtc import shunt_dtc_parasitic_branches

SETTINGS = base.CASES
ELECTRICAL_CONFIG = "zero_gjm_double"
EXTRA_PCB_PF = 0.2

class Evaluator(base.Evaluator):
    """Four-node nodal-Y independent 2-port plus frozen external S2P."""

    def __init__(self, policy, samples, parasitic_pf):
        super().__init__(policy, ELECTRICAL_CONFIG, samples)
        self.parasitic_pf = float(parasitic_pf)
        self.bounds[5, 1] = 100.  # Cp physically GJM01 rather than PCB
        self.Q_C[2] = 80.
        self.area = 3. + 2. / 3.
        self.cap_edges = base.CF_EDGES + base.CONFIGS[ELECTRICAL_CONFIG][1] + ((1, 2), (3, -1))
        self.cap_matrix = base.incidence(self.cap_edges)
        self.cap_Q = np.array([40., 40., 80., 35., 35., 35., 40., 40.])
        self.cache_x = None
        self.cache_il = None

    def il(self, x):
        x = np.asarray(x, float)
        if x.shape != (26,):
            raise ValueError("26-parameter three-L circuit vector required")
        if self.cache_x is not None and np.array_equal(x, self.cache_x):
            return self.cache_il
        n = len(self.f)
        K, M, H = self.matrices(x)
        if float(np.linalg.eigvalsh(M)[0]) <= 0:
            raise ValueError("Non-positive coupled inductance matrix")
        y_matrix = np.broadcast_to(K, (n,4,4)).copy() / (self.omega[:,None,None]*1e-9)
        variable_C = x[8:].reshape(6,3)[self.setting]
        C = np.column_stack((np.broadcast_to(x[3:6], (n,3)), variable_C,
                             np.full((n,), EXTRA_PCB_PF),
                             np.full((n,), self.parasitic_pf)))
        yc = self.omega[:,None]*1e-12*C/(1/self.cap_Q[None,:]-1j)
        B = self.cap_matrix
        y_matrix += np.einsum("nb,ib,jb->nij",yc,B,B,optimize=True)
        outer = [0,2]
        inner = [1,3]
        P = y_matrix[:,outer,:][:,:,outer]
        U = y_matrix[:,outer,:][:,:,inner]
        V = y_matrix[:,inner,:][:,:,outer]
        E = y_matrix[:,inner,:][:,:,inner]
        reduced = P - U @ np.linalg.solve(E,V)
        a,b,c,d = reduced[:,0,0],reduced[:,0,1],reduced[:,1,0],reduced[:,1,1]
        if np.any(np.abs(c)<1e-20): raise ValueError("Singular LPF two-port")
        lpf = np.empty((n,2,2),complex)
        lpf[:,0,0]=-d/c
        lpf[:,0,1]=-1/c
        lpf[:,1,0]=-(a*d-b*c)/c
        lpf[:,1,1]=-a/c
        full = self.pre @ lpf @ self.post
        zl=60.-40j
        zs=50.
        denom=full[:,0,0]*zl+full[:,0,1]+zs*(full[:,1,0]*zl+full[:,1,1])
        GT=4*zs*zl.real/np.abs(denom)**2
        answer=-10*np.log10(np.maximum(GT,1e-300))
        self.cache_x=x.copy()
        self.cache_il=answer
        return answer


def summary(ev,x):
    m=ev.summary(x)
    return {**m,
       "H2H3_strict_30dB_pass": bool(m["min_H2_db"]>=30 and m["min_H3_db"]>=30),
       "PCB_C_physical_values_pF": [float(x[3]),float(x[4]),EXTRA_PCB_PF],
       "GJM_C_physical_pF":float(x[5]),
       "shunt_dtc_parasitic_pf":ev.parasitic_pf,
       "shunt_dtc_parasitic_Q":40,
       "area":float(ev.area)}


def independent_mna(policy,x,points=3):
    """Explicit full 7x7 MNA with eight distinct lossy capacitor elements."""
    ev=Evaluator(policy,points,0.5)
    x=np.asarray(x,float)
    orig_il=ev.il(x)
    B=ev.cap_matrix
    L=np.asarray(x[:3],float)
    M=np.diag(L)
    for (a,b),k in zip(((0,2),(2,1)),x[6:8]):
        M[a,b]=M[b,a]=k*math.sqrt(L[a]*L[b])
    eig=float(np.linalg.eigvalsh(M)[0])
    if eig<=0: raise ValueError("L matrix must be positive-definite")
    H=np.diag(L/25.)+1j*M
    max_diff,max_residual=0.,0.
    min_loss=float("inf")
    for i,(mhz,setting) in enumerate(zip(ev.f,ev.setting)):
        omega=2e6*math.pi*mhz
        values=np.r_[x[3:6],x[8+3*setting:11+3*setting],EXTRA_PCB_PF,0.5]
        yc=omega*1e-12*values/(1/ev.cap_Q-1j)
        ti,to=ev.pre[i],ev.post[i]
        zl=60.-40j
        din=ti[0,1]+50*ti[1,1]
        ys=(ti[0,0]+50*ti[1,0])/din
        drive=1/din
        dout=to[0,0]*zl+to[0,1]
        yl=(to[1,0]*zl+to[1,1])/dout
        matrix=np.zeros((7,7),complex)
        matrix[:4,:4]=B@np.diag(yc)@B.T
        matrix[0,0]+=ys
        matrix[2,2]+=yl
        matrix[:4,4:]=base.BL
        matrix[4:,:4]=base.BL.T
        matrix[4:,4:]=-omega*1e-9*H
        rhs=np.zeros(7,complex);rhs[0]=drive
        sol=np.linalg.solve(matrix,rhs)
        volt,ind=sol[:4],sol[4:]
        load_p=zl.real*abs(volt[2]/dout)**2
        il=-10*np.log10(max(200*load_p,1e-300))
        max_diff=max(max_diff,abs(il-orig_il[i]))
        inp=drive-ys*volt[0]
        vext=ti[0,0]*volt[0]+ti[0,1]*inp
        iext=ti[1,0]*volt[0]+ti[1,1]*inp
        reflected=abs(1-100*iext)**2/200
        input_loss=float(np.real(vext*np.conj(iext)-volt[0]*np.conj(inp)))
        output_loss=float(np.real(volt[2]*np.conj(yl*volt[2]))-load_p)
        inductor_loss=float(np.real(np.vdot(ind,omega*1e-9*H@ind)))
        C_losses=yc.real*np.abs(B.T@volt)**2
        cap_loss=float(C_losses.sum())
        res=.005-(reflected+input_loss+output_loss+inductor_loss+cap_loss+load_p)
        max_residual=max(max_residual,abs(res))
        min_loss=min(min_loss,reflected,input_loss,output_loss,inductor_loss,cap_loss,load_p,*[float(t) for t in C_losses])
    return {
      "probes":int(len(ev.f)),
      "independent_method":"7x7 branch-current MNA with GJM Cp Q80, extra PCB Q40 and DTC parasitic Q40 independently stamped",
      "max_IL_difference_dB":float(max_diff),
      "max_power_balance_residual_W":float(max_residual),
      "min_component_loss_W":float(min_loss),
      "min_L_matrix_eigenvalue_nH":eig,
      "PASS":bool(max_diff<1e-8 and max_residual<1e-9 and min_loss>-1e-10 and eig>0)}


def run_opt(ev,start,iterations,required_db):
    start=np.asarray(start,float)
    bounds=[tuple(v) for v in ev.bounds]+[(0.,100.)]
    y=np.r_[start,ev.summary(start)["worst_IL_db"]]
    def constr(z):
        levels=ev.il(z[:-1])
        return np.where(ev.role==0,z[-1]-levels,levels-required_db)
    result=minimize(lambda z:float(z[-1]),y,method="SLSQP",
      bounds=bounds,constraints={"type":"ineq","fun":constr},
      options={"maxiter":iterations,"ftol":2e-9})
    vec=np.clip(result.x[:-1],ev.bounds[:,0],ev.bounds[:,1])
    return vec,{"success":bool(result.success),"message":str(result.message),
        "iterations":int(result.nit),"function_evaluations":int(result.nfev),
        "coarse_min_slack_dB":float(np.min(constr(result.x)))}


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--starts",type=int,default=2)
    p.add_argument("--coarse",type=int,default=9)
    p.add_argument("--refine",type=int,default=21)
    p.add_argument("--dense",type=int,default=1001)
    p.add_argument("--mna",type=int,default=3)
    p.add_argument("--maxiter",type=int,default=100)
    p.add_argument("--target",type=float,default=30.02)
    p.add_argument("--out",type=Path)
    a=p.parse_args()
    if min(a.starts,a.coarse,a.refine,a.dense,a.mna,a.maxiter)<1 or a.target<30:
        raise ValueError("Invalid run budget")
    policy=load_constraint("RF-T007",allow_trial=True)
    parasitics=shunt_dtc_parasitic_branches(policy,[
       {"a":4,"b":0,"role":"shunt_to_ground"},
       {"a":1,"b":2,"role":"bridge"},
       {"a":2,"b":3,"role":"bridge"}])
    assert len(parasitics)==1 and parasitics[0]["node"]==4
    original=json.loads(CHECKPOINT.read_text())
    initial=np.asarray(original["vector"],float)
    if len(initial)!=26:
        raise ValueError("Incomplete frozen EXP-045 vector")
    old=Evaluator(load_constraint("RF-T005",allow_trial=True),a.dense,0.)
    historical=summary(old,initial)
    if abs(historical["worst_IL_db"]-original["metrics"]["worst_IL_db"])>1e-6:
        raise AssertionError("EXP-045 T005 frozen original circuit failed to reproduce")
    dense=Evaluator(policy,a.dense,0.5)
    frozen=summary(dense,initial)
    compensated=initial.copy()
    compensated[8::3]=np.maximum(0,compensated[8::3]-0.5)
    precompensated=summary(dense,compensated)
    seeds=[initial,compensated]
    if a.starts>2:
        rng=np.random.default_rng(20261019+2)
        for _ in range(a.starts-2):
            z=compensated.copy()
            z[:3]*=np.exp(rng.normal(0,.06,3))
            z[6:8]+=rng.normal(0,.008,2)
            z[8:]+=rng.normal(0,.06,18)
            seeds.append(np.clip(z,dense.bounds[:,0],dense.bounds[:,1]))
    coarse=Evaluator(policy,a.coarse,0.5)
    fine=Evaluator(policy,a.refine,0.5)
    run_records=[]
    candidates=[
      {"stage":"unmodified_frozen","vector":initial.tolist(),"metrics":frozen},
      {"stage":"heuristic_compensation","vector":compensated.tolist(),"metrics":precompensated}
    ]
    for idx,seed in enumerate(seeds[:a.starts]):
        try:
            c,report_c=run_opt(coarse,seed,a.maxiter,a.target)
            r,report_r=run_opt(fine,c,max(60,a.maxiter//2),a.target)
            candidate={"start":idx,"stage":"locally_optimized","vector":r.tolist(),
                       "coarse":report_c,"refined":report_r,"metrics":summary(dense,r)}
            candidates.append(candidate)
        except (ValueError,np.linalg.LinAlgError) as exc:
            candidate={"start":idx,"stage":"failed","error":str(exc)}
        run_records.append(candidate)
        print("TRY",idx,candidate.get("metrics"),flush=True)
    eligible=[v for v in candidates if v.get("metrics",{}).get("H2H3_strict_30dB_pass")]
    selected=min(eligible,key=lambda e:e["metrics"]["worst_IL_db"]) if eligible else None
    independent=independent_mna(policy,np.array(selected["vector"]),a.mna) if selected else None
    if independent and not independent["PASS"]:
        raise AssertionError("Independent 7x7 MNA failed")
    output={
      "experiment_id":"EXP-050","constraint_id":"RF-T007",
      "phase":"Phase 2","step":"2_of_6_area3p667",
      "constraint_hash":constraint_fingerprint(policy),
      "source_EXP":"EXP-045",
      "source_path":str(CHECKPOINT.relative_to(ROOT)),
      "source_original_vector":initial.tolist(),
      "topology":"3L, PCB Cf0/Cf1/extra PCB(1,2), GJM Cp(3,GND) Q80, DTC Cv0 shunt with additional 0.5pF/Q40, Cv1/Cv2 non-ground",
      "all_six_settings":list(SETTINGS),
      "physical_parasitic_branch":{"for_variable":"Cv0","nodes":[3,-1],"pF":0.5,"Q":40},
      "component_values_include_distinct_GJM_Q80_and_parasitic_Q40":True,
      "chip_area":3+2/3,
      "historical_t005_metrics":historical,
      "t007_old_vector_frozen":frozen,
      "t007_compensated_initial":precompensated,
      "optimizer_attempts":run_records,
      "selected":selected,
      "independent_mna":independent,
      "dense_segments":28,
      "dense_points_per_segment":a.dense,
      "code_commit":subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip(),
      "status":"T007_30dB_finite_grid_best_found" if selected else "no_finite_grid_feasible_candidate_found",
      "limitations":["Numerical local SLSQP only, no global optimality guarantee",
          "All-band mesh finite, physical EM/Q(f)/SRF and C tolerances unverified",
          "Other four Pareto checkpoints not analyzed by this script"]
    }
    path=a.out or ROOT/"results/EXP-050/area3p667_rft007.json"
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(output,ensure_ascii=False,indent=2)+"\n")
    print("FINAL",str(path),"STATUS",output["status"],
        "BEST",selected["metrics"] if selected else None,
        "INDEPENDENT",independent,flush=True)

if __name__=="__main__":
    main()

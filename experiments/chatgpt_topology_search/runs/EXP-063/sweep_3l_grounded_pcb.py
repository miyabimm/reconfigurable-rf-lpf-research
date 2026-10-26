#!/usr/bin/env python3
"""EXP-063 RF-T008 rev3: transfer grounded PCB-C shunt insight to 3L, 0-2 GJM.
Finite-grid local SLSQP v2, full external fixed S2P, independent 7x7 MNA.
"""
import argparse
import json
import sys
import subprocess
from pathlib import Path
import numpy as np

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
sys.path.insert(0,str(ROOT/"src"))
from lpf.phase2_models import exp058_area3 as parent
from lpf.slsqp_budget import run_termination_aware_slsqp
from lpf.constraint_versions import load_constraint,constraint_fingerprint
from lpf.trial_pcb_pattern_c import validate_trial_pcb_pattern_c_branches
from lpf.trial_ic_fixed_c import validate_ic_fixed_c_settings

# Fixed chip area: 3 LQP02HV + (2/3)*number of GJM.
# Three fixed-C locations; PCB grounded Q60, hot-hot Q40.
# Three-L electrical tree and 2 composite DTCs remain unchanged.
LAYOUTS={
  "a3_control":([],[(0,1),(1,2),(3,-1)]),
  "a3_ground_n1":([],[(0,1),(3,-1),(1,-1)]),
  "a3_ground_n2":([],[(1,2),(3,-1),(2,-1)]),
  "a3_ground_dual":([],[(3,-1),(1,-1),(2,-1)]),
  "a367_control":([(0,1)],[(1,2),(3,-1)]),
  "a367_ground_n1":([(0,1)],[(3,-1),(1,-1)]),
  "a367_ground_n2":([(0,1)],[(3,-1),(2,-1)]),
  "a367_gjm_cp":([(3,-1)],[(0,1),(1,-1)]),
  "a433_control":([(0,1),(3,-1)],[(1,2)]),
  "a433_ground_n1":([(0,1),(3,-1)],[(1,-1)]),
  "a433_ground_n2":([(0,1),(3,-1)],[(2,-1)]),
  "a433_gjm_both":([(0,1),(1,2)],[(3,-1)]),
}
ACTIVE=None
BASE=parent.Evaluator
SOURCE_LOW=ROOT/"data/pareto_snapshots/rf_t008_exp058_area3_to_3p667_20261020.json"
SOURCE_HIGH=ROOT/"data/pareto_snapshots/rf_t008_exp058_area4p333_20261020.json"

def get_base(area):
    if area<4:
        j=json.loads(SOURCE_LOW.read_text())
        cid="A3-3L" if area<3.3 else "A3P667-3L"
        q=next(x for x in j["observed_nondominated"] if cid in x["candidate_id"])
        return np.asarray(q["vector"],float)
    q=json.loads(SOURCE_HIGH.read_text())["best"]
    return np.asarray(q["vector"],float)

class Evaluator(BASE):
    def __init__(self,policy,variant,points,gjm_position=None):
        if ACTIVE not in LAYOUTS or variant!="shunt_output":
            raise ValueError("EXP-063 uses validated 3L shunt_output DTC topology")
        super().__init__(policy,variant,points,None)
        gjm,pcb=LAYOUTS[ACTIVE]
        edges=tuple(tuple(e) for e in gjm+pcb)
        if len(edges)!=3 or len(set(edges))!=3 or len(pcb)>3:
            raise ValueError("Bad fixed capacitor layout")
        self.fixed_edges=edges
        self.cap_edges=edges+self.variable_edges+self.fixed_ic_edges
        self.BC=parent.incidence(self.cap_edges)
        self.Q_C=np.asarray(
            [80.]*len(gjm)+[60. if -1 in e else 40. for e in pcb]
            +[35.,35.,60.,60.],float)
        for i,e in enumerate(edges):
            self.bounds[3+i]=(0.02,100.) if i<len(gjm) else (
                (0.02,1.) if -1 in e else (0.02,0.2))
        self.area=3.+2./3.*len(gjm)
        validate_trial_pcb_pattern_c_branches(policy,[
            dict(parent.norm_edge(e),capacitance_pf=0.1,q=60 if -1 in e else 40)
            for e in pcb])
        self.cache_x,self.cache_il=None,None

# Parent independent_mna reconstructs the same new evaluator with a
# separate explicit 7x7 inductor-branch current matrix.
parent.Evaluator=Evaluator

def seed(ev,source,j):
    x=np.asarray(source,float).copy()
    if x.shape!=(22,):raise ValueError("Invalid saved 3L vector")
    gjm,pcb=LAYOUTS[ACTIVE]
    edges=parent.PCB_EDGES
    originals=[("GJM" if i in (
        () if ev.area==3 else (0,) if ev.area<4 else (0,2)
        ) else "PCB",tuple(e),source[3+i]) for i,e in enumerate(edges)]
    for i,e in enumerate(gjm+pcb):
        kind="GJM" if i<len(gjm) else "PCB"
        match=[v for t,edge,v in originals if edge==tuple(e) and t==kind]
        x[3+i]=match[0] if match else (1.0 if kind=="GJM"
                        else (0.40 if -1 in e else 0.08))
    if j:
        rng=np.random.default_rng(20261020+101*list(LAYOUTS).index(ACTIVE))
        x[:3]*=np.exp(rng.normal(0,0.05,3))
        x[3:6]*=np.exp(rng.normal(0,0.15,3))
        x[6:8]+=rng.normal(0,0.01,2)
        x[8:10]+=rng.normal(0,0.1,2)
        x[10:]+=rng.normal(0,0.13,12)
    return np.clip(x,ev.bounds[:,0],ev.bounds[:,1])

def stage(ev,x,maxiter,target):
    v,s=parent.opt(ev,x,maxiter,target)
    return v,{**s,"converged":s["success"],"maxiter":maxiter}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--layout",choices=tuple(LAYOUTS),required=True)
    p.add_argument("--starts",type=int,default=2)
    p.add_argument("--coarse",type=int,default=7)
    p.add_argument("--fine",type=int,default=17)
    p.add_argument("--dense",type=int,default=1001)
    p.add_argument("--target",type=float,default=30.005)
    p.add_argument("--out",type=Path)
    a=p.parse_args()
    if a.starts!=2 or min(a.coarse,a.fine)<3 or a.dense<101:
        raise ValueError("Require two starts and dense grid")
    global ACTIVE
    ACTIVE=a.layout
    policy=load_constraint("RF-T008",allow_trial=True)
    if policy["trial_ic_fixed_c_by_connection"]["max_composite_branches"]!=2:
        raise AssertionError("Need RF-T008 v3")
    gd,pd=LAYOUTS[ACTIVE]
    area=3.+len(gd)*2./3.
    source=get_base(area)
    full=Evaluator(policy,"shunt_output",a.dense,None)
    coarse=Evaluator(policy,"shunt_output",a.coarse,None)
    fine=Evaluator(policy,"shunt_output",a.fine,None)
    rows=[]
    for j in range(a.starts):
        init=seed(full,source,j)
        run=run_termination_aware_slsqp(coarse,fine,init,a.target,optimize_stage=stage)
        attempts=[]
        for t in run["attempts"]:
            v=np.asarray(t["vector"],float)
            m=full.summary(v)
            ok=bool(m["min_H2_db"]>=30 and m["min_H3_db"]>=30)
            attempts.append({"tier":t["tier"],"vector":v.tolist(),
                "converged":t["converged"],"coarse":t["coarse"],"fine":t["fine"],
                "finite_30db_pass":ok,"eligible":bool(ok and t["converged"]),
                "dense":m})
        rows.append({"start":j,"initial_vector":init.tolist(),"attempts":attempts,
                     "iteration_policy":run["iteration_policy"],"recovery_cause":run["recovery_cause"]})
        print("TRY",ACTIVE,j,[(z["tier"],z["dense"]["worst_IL_db"],
                        z["eligible"]) for z in attempts],flush=True)
    candidates=[z for r in rows for z in r["attempts"] if z["eligible"]]
    best=min(candidates,key=lambda z:z["dense"]["worst_IL_db"]) if candidates else None
    chk=parent.independent_mna(full,np.asarray(best["vector"],float),
                               policy,"shunt_output") if best else None
    if chk and not chk["pass"]: raise AssertionError("7x7 independent MNA failure")
    if best:
        x=np.asarray(best["vector"])
        branches=[dict(parent.norm_edge(e),role="shunt_to_ground" if -1 in e else "bridge")
                  for e in full.variable_edges]
        validate_ic_fixed_c_settings(policy,branches,x[8:10].tolist(),
            dict(zip(parent.CASES,x[10:].reshape((6,2)).tolist())))
    result={"experiment_id":"EXP-063","constraint_id":"RF-T008","revision":3,
            "phase":"Phase 2","area":area,"layout":ACTIVE,
            "L_edges":parent.THREE_L_EDGES,"chip_row":["L0","Ls","L1"],
            "GJM_edges":gd,"PCB_edges":pd,"variable_C_edges":full.variable_edges,
            "fixed_IC_C_parallel_edges":full.fixed_ic_edges,
            "effective_constraint_sha256":constraint_fingerprint(policy),
            "code_execution_sha":subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip(),
            "sampling":{"segments":28,"coarse":a.coarse,"fine":a.fine,"dense":a.dense,
                        "MNA_per_segment":3},"starts":rows,
            "best_converged_30db":best,"independent_MNA":chk,
            "limitations":["Local finite-grid Phase2; not global optimum",
               "Constant-Q and fixed model-origin external S2P; not EM validation",
               "No SRF, Q(f), physical coupling simultaneity, tolerance or Phase3"]}
    out=a.out or ROOT/"results/EXP-063"/(ACTIVE+".json")
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)+"\n")
    print("RESULT",ACTIVE,"IL",best["dense"]["worst_IL_db"] if best else "NO_CONVERGED",
          "MNA",chk["pass"] if chk else "NOT_RUN",flush=True)

if __name__=="__main__":
    main()

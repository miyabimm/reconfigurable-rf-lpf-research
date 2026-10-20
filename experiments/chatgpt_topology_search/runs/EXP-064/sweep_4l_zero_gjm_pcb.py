#!/usr/bin/env python3
"""EXP-064 Phase2 RF-T008 v3 4L/0GJM PCB-C edge reassignment at chip area 4.

Change only three PCB patterned capacitor edges; retain EXP-058 4L T-type
inductor connections and shunt_output two-composite-DTC placement.
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path
import numpy as np
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
sys.path.insert(0,str(ROOT/"experiments/chatgpt_topology_search/runs/EXP-058"))
sys.path.insert(0,str(ROOT/"src"))
import sweep_area4 as parent
import sweep_area3 as optim
from lpf.slsqp_budget import run_termination_aware_slsqp
from lpf.constraint_versions import load_constraint,constraint_fingerprint
from lpf.trial_pcb_pattern_c import validate_trial_pcb_pattern_c_branches
from lpf.trial_ic_fixed_c import validate_ic_fixed_c_settings

EDGES={
 "b01":(0,1),"b12":(1,2),"b03":(0,3),"b02":(0,2),
 "b14":(1,4),"b34":(3,4),"b42":(4,2),
 "g4":(4,-1),"g3":(3,-1),"g1":(1,-1),"g2":(2,-1),
}
LAYOUTS={
 "control":("b01","g4","b12"),
 "g4g3_b01":("g4","g3","b01"),
 "g4g3_b12":("g4","g3","b12"),
 "g4g3_g1":("g4","g3","g1"),
 "g4g3_g2":("g4","g3","g2"),
 "g4g3_b03":("g4","g3","b03"),
 "g4g3_b02":("g4","g3","b02"),
 "g4g3_b34":("g4","g3","b34"),
 "g3_b01_b12":("g3","b01","b12"),
 "g4_b01_b03":("g4","b01","b03"),
 "g3g1_b12":("g3","g1","b12"),
 "g3g2_b01":("g3","g2","b01")
}
SOURCE=ROOT/"data/pareto_snapshots/rf_t008_exp058_area4_20261020.json"
ACTIVE=None
BASE=parent.Evaluator

class Evaluator(BASE):
    def __init__(self,policy,variant,removed,points):
        if ACTIVE not in LAYOUTS or variant!="shunt_output":
            raise ValueError("Validated 4L zero GJM shunt_output case required")
        super().__init__(policy,variant,"cp",points)
        edges=tuple(EDGES[e] for e in LAYOUTS[ACTIVE])
        assert len(edges)==len(set(edges))==3
        self.fixed_edges=edges
        self.cap_edges=edges+self.var_edges+self.var_edges
        self.BC=parent.old4.incidence(self.cap_edges)
        self.Q_C=np.asarray([60. if -1 in e else 40. for e in edges]
            +[35.,35.,60.,60.],float)
        for i,e in enumerate(edges):
            self.bounds[4+i]=(0.02,1.) if -1 in e else (0.02,0.2)
        validate_trial_pcb_pattern_c_branches(policy,[
            dict(parent.norm(e),capacitance_pf=0.1,q=60 if -1 in e else 40)
            for e in edges])
        self.cache_x,self.cache_il=None,None

# Prior independent MNA recomputes all inductor branch currents as 9x9 linear system.
parent.Evaluator=Evaluator

def seed(ev,xold,index):
    x=np.array(xold,float)
    assert x.shape==(24,)
    from_edges=((0,1),(4,-1),(1,2))
    for i,key in enumerate(LAYOUTS[ACTIVE]):
        e=EDGES[key]
        x[4+i]=(xold[4+from_edges.index(e)] if e in from_edges else
                (0.45 if -1 in e else 0.08))
    if index:
        rng=np.random.default_rng(20261020+73*list(LAYOUTS).index(ACTIVE))
        x[:4]*=np.exp(rng.normal(0,0.055,4))
        x[4:7]*=np.exp(rng.normal(0,0.12,3))
        x[7:10]+=rng.normal(0,0.01,3)
        x[10:12]+=rng.normal(0,0.08,2)
        x[12:]+=rng.normal(0,0.10,12)
    return np.clip(x,ev.bounds[:,0],ev.bounds[:,1])

def stage(ev,x,maxiter,target):
    xx,s=optim.opt(ev,x,maxiter,target)
    return xx,{**s,"converged":s["success"],"maxiter":maxiter}

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--layout",choices=tuple(LAYOUTS),required=True)
    parser.add_argument("--starts",type=int,default=2)
    parser.add_argument("--coarse",type=int,default=7)
    parser.add_argument("--fine",type=int,default=17)
    parser.add_argument("--dense",type=int,default=1001)
    parser.add_argument("--target",type=float,default=30.005)
    parser.add_argument("--out",type=Path)
    a=parser.parse_args()
    if a.starts!=2 or min(a.coarse,a.fine)<3 or a.dense<101:
        raise ValueError("Only 2 fixed starts, complete dense RF mesh")
    global ACTIVE
    ACTIVE=a.layout
    policy=load_constraint("RF-T008",allow_trial=True)
    assert policy["trial_ic_fixed_c_by_connection"]["max_composite_branches"]==2
    j=json.loads(SOURCE.read_text())
    xold=np.asarray(j["best_cost_cell"]["vector"],float)
    full=Evaluator(policy,"shunt_output","cp",a.dense)
    coarse=Evaluator(policy,"shunt_output","cp",a.coarse)
    fine=Evaluator(policy,"shunt_output","cp",a.fine)
    if ACTIVE=="control":
        baseline=full.summary(xold)["worst_IL_db"]
        if abs(baseline-j["best_cost_cell"]["metrics"]["worst_IL_db"])>1e-7:
            raise AssertionError("Failure to reproduce saved EXP-058 area4 control")
    results=[]
    for s in range(a.starts):
        ini=seed(full,xold,s)
        r=run_termination_aware_slsqp(coarse,fine,ini,a.target,optimize_stage=stage)
        rows=[]
        for t in r["attempts"]:
            v=np.asarray(t["vector"],float)
            summary=full.summary(v)
            conform=bool(summary["min_H2_db"]>=30 and summary["min_H3_db"]>=30)
            rows.append({"tier":t["tier"],"vector":v.tolist(),"coarse":t["coarse"],
                         "fine":t["fine"],"converged":t["converged"],
                         "finite_30db_pass":conform,"eligible":bool(conform and t["converged"]),
                         "dense":summary})
        results.append({"start":s,"initial_vector":ini.tolist(),"attempts":rows,
                        "iteration_policy":r["iteration_policy"],"recovery_cause":r["recovery_cause"]})
        print("TRY",ACTIVE,s,[(q["tier"],q["dense"]["worst_IL_db"],q["eligible"]) for q in rows],flush=True)
    valid=[q for row in results for q in row["attempts"] if q["eligible"]]
    best=min(valid,key=lambda q:q["dense"]["worst_IL_db"]) if valid else None
    mna=parent.independent_mna(policy,"shunt_output","cp",
                   np.asarray(best["vector"],float)) if best else None
    if mna is not None and not mna["pass"]:
        raise AssertionError("Independent 9x9 coupled L branch current MNA failed")
    if best:
        x=np.asarray(best["vector"])
        branches=[dict(parent.norm(e),role="shunt_to_ground" if -1 in e else "bridge")
                 for e in full.var_edges]
        validate_ic_fixed_c_settings(policy,branches,x[10:12].tolist(),
             dict(zip(parent.CASES,x[12:].reshape(6,2).tolist())))
    record={"experiment_id":"EXP-064","phase":"Phase 2","constraint_id":"RF-T008",
      "revision":3,"chip_area":4.0,"GJM_count":0,"layout":ACTIVE,
      "L_edges":parent.old4.L_EDGES,"chip_row":["L0","L1","L3","L2"],
      "PCB_edges":full.fixed_edges,"variable_C_edges":full.var_edges,
      "IC_fixed_parallel_edges":full.var_edges,
      "effective_constraint_sha256":constraint_fingerprint(policy),
      "code_execution_sha":subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip(),
      "sampling":{"segments":28,"coarse":a.coarse,"fine":a.fine,"dense":a.dense,
                  "independent_MNA_probes":84},
      "starts":results,"best_converged_30db":best,"independent_MNA":mna,
      "limitations":["Finite 28x1001 nominal model, not global optimum",
          "No physical component Q(f)/SRF/EM/physical k/tolerance or Phase3"]}
    out=a.out or ROOT/"results/EXP-064"/(ACTIVE+".json")
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(record,ensure_ascii=False,indent=2,allow_nan=False)+"\n")
    print("RESULT",ACTIVE,
          best["dense"]["worst_IL_db"] if best else "NO_CONVERGED",mna,flush=True)

if __name__=="__main__":
    main()

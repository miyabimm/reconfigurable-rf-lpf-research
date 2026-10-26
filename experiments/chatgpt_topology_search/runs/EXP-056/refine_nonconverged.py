#!/usr/bin/env python3
"""EXP-056: RF-T007 targeted SLSQP iteration-budget and warm-start refinement.

Revisit EXP-055 4L Cv1(0,1) and Cv1(2,4) selected points that passed
finite 28x1001 band and explicit 84-probe 9x9 coupled-L MNA but whose
coarse SLSQP phase reached 160 iterations. Keep topology, area,
component/Q values, fixed two S2Ps, one mandatory Cpar0=0.5pF/Q40 and
H2/H3 >=30dB identical. This is NOT physical-k or margin optimization.
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

import numpy as np

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
sys.path.insert(0,str(ROOT/"experiments/chatgpt_topology_search/runs/EXP-055"))
sys.path.insert(0,str(ROOT/"src"))
import adapt_f003_4l as src
from lpf.constraint_versions import load_constraint,constraint_fingerprint

SELECTED={
    "cv1_output_shunt_tip":"cv1_output_shunt_tip_best.json",
    "cv1_input_parallel_L0":"cv1_input_parallel_L0_best.json",
}
REFERENCE=ROOT/"experiments/chatgpt_topology_search/runs/EXP-055/checkpoints/cv1_input_tip_best.json"

def load_checked_vector(path,name,ev):
    obj=json.loads(path.read_text(encoding="utf-8"))
    assert obj["constraint_id"]=="RF-T007" and obj["experiment_id"]=="EXP-055"
    v=np.asarray(obj["vector"],float)
    assert v.shape==(29,) and np.all(np.isfinite(v))
    assert obj["topology"]["variable_C_edges"][1]==list(src.VARIANTS[name])
    got=ev.summary(v)
    if abs(got["worst_IL_db"]-obj["metrics"]["worst_IL_db"])>1e-6:
        raise AssertionError(f"Saved EXP055 {name} dense IL failed reproduction {got}")
    return v,got

def runs(seed, name, n, rng):
    starts=[seed.copy()]
    lim=src.bounds(name)
    for j in range(1,n):
        x=seed.copy()
        sigma=0.012 if j==1 else 0.05
        x[:4]*=np.exp(rng.normal(0,sigma,4))
        x[4:8]*=np.exp(rng.normal(0,sigma,4))
        x[8:11]+=rng.normal(0,sigma/5,3)
        x[11:]+=rng.normal(0,sigma,18)
        starts.append(np.clip(x,lim[:,0],lim[:,1]))
    return starts

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--starts",type=int,default=3)
    p.add_argument("--maxiter",type=int,default=500)
    p.add_argument("--fine-maxiter",type=int,default=280)
    p.add_argument("--coarse",type=int,default=7)
    p.add_argument("--fine",type=int,default=17)
    p.add_argument("--dense",type=int,default=1001)
    p.add_argument("--mna",type=int,default=3)
    p.add_argument("--target",type=float,default=30.005)
    p.add_argument("--out",type=Path)
    a=p.parse_args()
    if min(a.starts,a.maxiter,a.fine_maxiter,a.coarse,a.fine,a.dense,a.mna)<1 or a.target<30:
        raise ValueError("Invalid experiment configuration")
    policy=load_constraint("RF-T007",allow_trial=True)
    win=json.loads(REFERENCE.read_text(encoding="utf-8"))
    reference=src.Evaluator(policy,a.dense,"cv1_input_tip")
    assert abs(reference.summary(win["vector"])["worst_IL_db"]-0.8173655897607699)<1e-6
    report={"experiment_id":"EXP-056","phase":"Phase 2","constraint_id":"RF-T007",
      "source_exp":"EXP-055","source_actions":39341678211,
      "previous_best_same_area_IL_db":0.8173655897607699,
      "source_2DTC_F003":"EXP-047",
      "target_slsqp_nonconvergence_not_action_timeout":True,
      "iteration_limit_before":{"coarse":160,"fine":80},
      "iteration_limit_now":{"coarse":a.maxiter,"fine":a.fine_maxiter},
      "optimization":"minimax worst external UL/DL IL under mandatory H2/H3>=30dB; no extra harmonic margin objective",
      "constraint_fingerprint":constraint_fingerprint(policy),
      "execution_sha":subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip(),
      "chip_area_units":5+1/3,
      "always_on_shunt_Cpar":{"edge":[3,-1],"C_pF":0.5,"Q":40},
      "settings":list(src.CASES),
      "grid":{"intervals":28,"coarse":a.coarse,"fine":a.fine,"dense":a.dense,"mna":a.mna},
      "variants":{},
      "limitations":["Local finite 28*1001 grid only, independent 84 MNA; no global/continuous proof",
      "No physical-k feasibility, Q(f), SRF, tolerance, measured S2P, extra harmonic margin or Phase3"] }
    rng=np.random.default_rng(20261020+56)
    for name,file in SELECTED.items():
        coarse=src.Evaluator(policy,a.coarse,name)
        fine=src.Evaluator(policy,a.fine,name)
        dense=src.Evaluator(policy,a.dense,name)
        start,start_metrics=load_checked_vector(
          ROOT/"experiments/chatgpt_topology_search/runs/EXP-055/checkpoints"/file,name,dense)
        trials=[]
        for j,x in enumerate(runs(start,name,a.starts,rng)):
            try:
                xc,s0=src.base.exp51.optimize_stage(coarse,x,a.maxiter,a.target)
                xf,s1=src.base.exp51.optimize_stage(fine,xc,a.fine_maxiter,a.target)
                metrics=dense.summary(xf)
                row={"start":j,"vector":xf.tolist(),"coarse":s0,"fine":s1,
                     "converged":bool(s0["converged"] and s1["converged"]),
                     "metrics":metrics}
            except (ValueError,np.linalg.LinAlgError,OverflowError) as e:
                row={"start":j,"failed":str(e),"converged":False}
            trials.append(row)
            print("TRY",name,j,"IL",row.get("metrics",{}).get("worst_IL_db"),
                  "H2",row.get("metrics",{}).get("min_H2_db"),
                  "H3",row.get("metrics",{}).get("min_H3_db"),
                  "converged",row["converged"],
                  "coarse",row.get("coarse",{}).get("message"),
                  "fine",row.get("fine",{}).get("message"),flush=True)
        valid=[t for t in trials if t.get("metrics",{}).get("finite_H2H3_30dB_pass")]
        converged=[t for t in valid if t["converged"]]
        selected=min(valid,key=lambda z:z["metrics"]["worst_IL_db"]) if valid else None
        fully_converged_best=min(converged,key=lambda z:z["metrics"]["worst_IL_db"]) if converged else None
        mna=src.independent_mna(policy,np.asarray(selected["vector"]),name,a.mna) if selected else None
        conv_mna=src.independent_mna(policy,np.asarray(fully_converged_best["vector"]),name,a.mna) if fully_converged_best else None
        if (mna and not mna["pass"]) or (conv_mna and not conv_mna["pass"]):
            raise AssertionError("Independent MNA discrepancy")
        report["variants"][name]={
            "source_EXP055_metrics":start_metrics,
            "source_EXP055_vector":start.tolist(),
            "trials":trials,
            "eligible_count":len(valid),
            "fully_converged_count":len(converged),
            "selected_eligible":selected,
            "selected_eligible_independent_MNA":mna,
            "selected_converged_eligible":fully_converged_best,
            "selected_converged_independent_MNA":conv_mna}
    report["summary"]={"planned_attempts":a.starts*len(SELECTED),
      "attempted":sum(len(z["trials"]) for z in report["variants"].values()),
      "converged":sum(sum(int(t["converged"]) for t in z["trials"]) for z in report["variants"].values()),
      "selected_ranked":sorted([
       {"variant":name,"IL_db":data["selected_eligible"]["metrics"]["worst_IL_db"],
        "selected_converged":data["selected_eligible"]["converged"],
        "converged_best_IL_db":data["selected_converged_eligible"]["metrics"]["worst_IL_db"] if data["selected_converged_eligible"] else None}
       for name,data in report["variants"].items() if data["selected_eligible"]],
        key=lambda x:x["IL_db"])}
    dst=a.out or ROOT/"results/EXP-056/longer_slsqp.json"
    dst.parent.mkdir(parents=True,exist_ok=True)
    dst.write_text(json.dumps(report,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print("FINAL",dst,report["summary"],flush=True)

if __name__=="__main__":
    main()

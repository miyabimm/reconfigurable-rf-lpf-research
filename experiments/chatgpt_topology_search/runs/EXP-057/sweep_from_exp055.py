#!/usr/bin/env python3
"""EXP-057: local four-L electrical-graph sweep from EXP-055 RF-T007 best.

Phase2 numerical topology study ONLY; keep EXP-055 capacitor/DTC graph fixed.
EXP-055 area5+1/3, Cv0 shunt(3,GND), Cv1 bridge(0,3), Cv2 bridge(1,2),
exactly one permanent 0.5pF/Q40 shunt parasitic at Cv0, all source/load S2Ps.
Mutate src.L_EDGES serially only; src.Evaluator and independent 9x9 MNA are
separately assembled circuit equations (no shared admittance solve).
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
from lpf.constraint_versions import constraint_fingerprint,load_constraint
from lpf.slsqp_budget import run_staged_slsqp, STANDARD_SLSQP_BUDGET

SOURCE=ROOT/"experiments/chatgpt_topology_search/runs/EXP-055/checkpoints/cv1_input_tip_best.json"
REF_IL=.8173655897607699
CV1="cv1_input_tip"
# Four branches in order L0,L1,L2,L3. The physical row L0-L1-L3-L2 and
# signed adjacent k index (0,1),(1,3),(3,2) are invariant.
GRAPHS={
 "control_exp055":((0,1),(1,3),(1,4),(1,2)),
 "shunt_tip_from_input":((0,1),(0,3),(1,4),(1,2)),
 "shunt_tip_from_output":((0,1),(2,3),(1,4),(1,2)),
 "ground_pendant_from_output":((0,1),(1,3),(2,4),(1,2)),
 "ground_pendant_from_input":((0,1),(1,3),(0,4),(1,2)),
 "input_series_through_tip":((0,3),(3,1),(1,4),(1,2)),
 "output_series_through_tip":((0,1),(1,3),(1,4),(3,2)),
 "output_series_through_pendant":((0,1),(1,3),(1,4),(4,2)),
 "shunt_pendant_from_tip":((0,1),(0,3),(3,4),(1,2)),
 "input_series_through_pendant":((0,4),(1,3),(1,4),(1,2)),
}

def validate_graph(edges):
    if len(edges)!=4 or len(set(tuple(sorted(e)) for e in edges))!=4:
        raise ValueError("Exactly four distinct L branches required")
    parent=list(range(5))
    def root(i):
        while parent[i]!=i:
            i=parent[i]
        return i
    for a,b in edges:
        if a==b or not 0<=a<5 or not 0<=b<5:
            raise ValueError("No self-loops or negative/floating node indices")
        ra,rb=root(a),root(b)
        if ra==rb:
            raise ValueError("L circuit must be a 5-node spanning tree")
        parent[ra]=rb
    if len({root(i) for i in range(5)})!=1:
        raise ValueError("Disconnected L graph")

def starts(vector,n,rng):
    b=src.bounds(CV1)
    out=[vector.copy()]
    for k in range(1,n):
        x=vector.copy()
        scale=.04 if k==1 else .09
        x[:4]*=np.exp(rng.normal(0,scale,4))
        x[4:8]*=np.exp(rng.normal(0,scale,4))
        x[8:11]+=rng.normal(0,scale/6,3)
        x[11:]+=rng.normal(0,scale,18)
        out.append(np.clip(x,b[:,0],b[:,1]))
    return out

def serializable_attempt(at):
    return {k:v.tolist() if isinstance(v,np.ndarray) else v
            for k,v in at.items()}

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--starts",type=int,default=2)
    ap.add_argument("--coarse",type=int,default=7)
    ap.add_argument("--fine",type=int,default=17)
    ap.add_argument("--dense",type=int,default=1001)
    ap.add_argument("--mna",type=int,default=3)
    ap.add_argument("--target",type=float,default=30.005)
    ap.add_argument("--out",type=Path)
    ap.add_argument("--graphs",nargs="*",choices=list(GRAPHS),default=list(GRAPHS))
    a=ap.parse_args()
    if not a.graphs or min(a.starts,a.coarse,a.fine,a.dense,a.mna)<1 or a.target<30:
        raise ValueError("Invalid run settings")
    policy=load_constraint("RF-T007",allow_trial=True)
    seed_obj=json.loads(SOURCE.read_text(encoding="utf-8"))
    assert seed_obj["constraint_id"]=="RF-T007" and seed_obj["experiment_id"]=="EXP-055"
    assert seed_obj["topology"]["variable_C_edges"]==[[3,-1],[0,3],[1,2]]
    assert seed_obj["topology"]["fixed_C_edges"]==[[0,1],[4,-1],[1,2],[0,3]]
    assert seed_obj["topology"]["permanent_shunt_DTC_parasitic_edge"]==[3,-1]
    seed=np.array(seed_obj["vector"],float)
    assert seed.shape==(29,) and np.all(np.isfinite(seed))
    original_graph=src.L_EDGES
    assert tuple(tuple(q) for q in seed_obj["topology"]["L_edges"])==original_graph
    rng=np.random.default_rng(20261020+57)
    result={"experiment_id":"EXP-057","phase":"Phase 2","constraint_id":"RF-T007",
        "source_EX055":str(SOURCE.relative_to(ROOT)),
        "source_exp055_worst_IL_db":REF_IL,
        "constraint_sha256":constraint_fingerprint(policy),
        "execution_sha":subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip(),
        "source_code":"EXP-057/sweep_from_exp055.py",
        "policy":STANDARD_SLSQP_BUDGET.as_dict(),
        "chip_area_units":5+1/3,
        "inductor_series":"LQP02HV/Q25",
        "physical_chip_row":["L0","L1","L3","L2"],
        "coupling_pairs":src.K_PAIRS,
        "fixed_C_edges":src.capacitor_edges(CV1)[:4],
        "variable_C_edges":src.capacitor_edges(CV1)[4:7],
        "one_fixed_Cpar":{"edge":[3,-1],"C_pF":.5,"Q":40,"persistent_when_DTC_OFF":True},
        "grid":{"regions":28,"coarse":a.coarse,"fine":a.fine,"dense":a.dense,"independent_MNA":a.mna},
        "hard_min_H2_H3_db":30,"internal_guard_db":a.target,
        "variants":{}}
    try:
        src.L_EDGES=original_graph
        original=src.Evaluator(policy,a.dense,CV1).summary(seed)
        if abs(original["worst_IL_db"]-REF_IL)>1e-7 or not original["finite_H2H3_30dB_pass"]:
            raise AssertionError("EXP-055 full original seed did not reproduce")
        result["reproduced_EXP055"]=original
        for name in a.graphs:
            graph=GRAPHS[name]
            validate_graph(graph)
            src.L_EDGES=graph
            coarse=src.Evaluator(policy,a.coarse,CV1)
            fine=src.Evaluator(policy,a.fine,CV1)
            dense=src.Evaluator(policy,a.dense,CV1)
            trials=[]
            for j,x in enumerate(starts(seed,a.starts,rng)):
                try:
                    opt=run_staged_slsqp(coarse,fine,x,a.target,src.base.exp51.optimize_stage)
                    # Preserve every primary and recovery attempt separately.
                    rows=[]
                    for at in opt["attempts"]:
                        cand=serializable_attempt(at)
                        cand["metrics"]=dense.summary(at["vector"])
                        rows.append(cand)
                    trial={"start":j,"attempts":rows,"recovery_invoked":opt["recovery_invoked"]}
                except (ValueError,np.linalg.LinAlgError,OverflowError) as err:
                    trial={"start":j,"failed":str(err),"attempts":[],"recovery_invoked":False}
                trials.append(trial)
                best_of_trial=min((it for it in trial["attempts"] if it["metrics"]["finite_H2H3_30dB_pass"]),
                                 key=lambda it:it["metrics"]["worst_IL_db"],default=None)
                print("TRY",name,j,None if best_of_trial is None else
                    best_of_trial["metrics"]["worst_IL_db"],"CONVERGED",
                    None if best_of_trial is None else best_of_trial["converged"],
                    "RETRIED",trial["recovery_invoked"],flush=True)
            eligible=[it for t in trials for it in t["attempts"]
                      if it["metrics"]["finite_H2H3_30dB_pass"]]
            best=min(eligible,key=lambda z:z["metrics"]["worst_IL_db"]) if eligible else None
            converged=min((x for x in eligible if x["converged"]),
                          key=lambda z:z["metrics"]["worst_IL_db"],default=None)
            mna=src.independent_mna(policy,np.array(best["vector"]),CV1,a.mna) if best else None
            converged_mna=(src.independent_mna(policy,np.array(converged["vector"]),CV1,a.mna)
                           if converged is not None else None)
            if (mna and not mna["pass"]) or (converged_mna and not converged_mna["pass"]):
                raise AssertionError("Independent 9x9 MNA failed "+name)
            result["variants"][name]={
                "L_edges":graph,"trials":trials,
                "best_finite_eligible":best,"best_eligible_independent_MNA":mna,
                "best_converged_finite_eligible":converged,
                "best_converged_independent_MNA":converged_mna}
            print("GRAPH",name,"BEST",None if best is None else best["metrics"]["worst_IL_db"],
                  "MNA",None if mna is None else mna["pass"],flush=True)
    finally:
        src.L_EDGES=original_graph
    ranked=sorted(({"graph":name,"worst_IL_db":z["best_finite_eligible"]["metrics"]["worst_IL_db"],
                   "min_H2_db":z["best_finite_eligible"]["metrics"]["min_H2_db"],
                   "min_H3_db":z["best_finite_eligible"]["metrics"]["min_H3_db"],
                   "converged":z["best_finite_eligible"]["converged"],
                   "independent_MNA_pass":z["best_eligible_independent_MNA"]["pass"]}
                  for name,z in result["variants"].items() if z["best_finite_eligible"]),
                  key=lambda x:x["worst_IL_db"])
    result["summary"]={"graphs":len(GRAPHS),"graphs_executed":len(a.graphs),
      "starts":a.starts*len(a.graphs),
      "optimizer_stages":sum(len(t["attempts"]) for z in result["variants"].values() for t in z["trials"]),
      "recovery_invocations":sum(int(t["recovery_invoked"]) for z in result["variants"].values() for t in z["trials"]),
      "ranked":ranked,"EXP055_reference_worst_IL_db":REF_IL,
      "improvement_over_EXP055_db":REF_IL-ranked[0]["worst_IL_db"] if ranked else None}
    out=a.out or ROOT/"results/EXP-057/exp055_fourl_neighborhood.json"
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(result,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print("FINAL",out,"SUMMARY",result["summary"],flush=True)

if __name__=="__main__":
    main()

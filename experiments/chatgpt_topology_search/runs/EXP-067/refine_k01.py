#!/usr/bin/env python3
"""EXP-067 continuation check: counter local optima with opposite-basin starts.

A *separate* Phase2 continuation within the registered K01 sweep. Pinned
EXP-067 first-stage aggregate artifact (same physical topology/constraints).
Same SLSQP-v2 bounded budgets. Cross-seed both nearest neighboring k best
solutions and deliberately remote negative/positive 4L resonance basins.
"""
import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
import numpy as np

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
sys.path.insert(0,str(HERE))
import k01_sweep as scan
from lpf.slsqp_budget import run_termination_aware_slsqp
from lpf.constraint_versions import load_constraint

REFINE_GRID=(-.095,-.093,-.091,.04,.045,.05,.055,.06,.065,.07)
EXPECTED_PARENT_SHA="63250aa110ed76105f54dd74131b924bc54a5fcabb1f56f818161ace3fb46d05"

def inputs(e,target,source):
    curve=source["curve"]
    pool=[q for q in curve if q["vector"] is not None]
    lo=[q for q in pool if q["k01"]<=target]
    hi=[q for q in pool if q["k01"]>=target]
    lower=max(lo,key=lambda q:q["k01"]) if lo else min(pool,key=lambda q:q["k01"])
    upper=min(hi,key=lambda q:q["k01"]) if hi else max(pool,key=lambda q:q["k01"])
    targets=[("lower_neighbor",lower),("upper_neighbor",upper)]
    for label,k in [("negative_basin",-.09218029453384365),
                    ("positive_basin",.06),("positive_end",.1),
                    ("pre_switch",.04)]:
        targetrow=min(pool,key=lambda q:abs(q["k01"]-k))
        targets.append((label,targetrow))
    selected=[]
    seen=set()
    for name,cand in targets:
        if cand["index"] not in seen:
            seen.add(cand["index"])
            selected.append((name,scan.vcheck(cand["vector"],e,target),
                             cand["k01"]))
    a,b=np.asarray(lower["vector"]),np.asarray(upper["vector"])
    blend=a.copy()
    for i in [0,1,2,3,4,5,6,11,12]:
        blend[i]=np.sqrt(max(a[i],1e-12)*max(b[i],1e-12))
    for idx in [9,10]:
        blend[idx]=.5*(a[idx]+b[idx])
    blend[13:]=.5*(a[13:]+b[13:])
    selected.append(("neighbor_geometric_bridge",scan.vcheck(blend,e,target),None))
    return selected

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--index",type=int,required=True)
    ap.add_argument("--parent",type=Path,required=True)
    ap.add_argument("--out",type=Path,required=True)
    a=ap.parse_args()
    if a.index not in range(len(REFINE_GRID)):raise ValueError("Invalid refinement index")
    data=a.parent.read_bytes()
    if hashlib.sha256(data).hexdigest()!=EXPECTED_PARENT_SHA:
        raise ValueError("First-stage Actions summary hash mismatch")
    parent=json.loads(data)
    if parent["experiment_id"]!="EXP-067" or parent["grid_count"]!=22 or parent["eligible_grid_points"]!=22:
        raise ValueError("Incomplete parent grid")
    target=REFINE_GRID[a.index]
    scan.graph.begin("free","original")
    policy=load_constraint("RF-T008",allow_trial=True)
    if scan.constraint_fingerprint(policy)!=scan.EXPECTED_CONSTRAINT_SHA256:
        raise AssertionError("Constraint drift")
    ev=scan.graph.Evaluator(policy,"input_output",("cf0",),1001)
    coarse=scan.graph.Evaluator(policy,"input_output",("cf0",),7)
    fine=scan.graph.Evaluator(policy,"input_output",("cf0",),17)
    for e in (ev,coarse,fine):e.bounds[8,:]=target
    rows=[];eligible=[]
    for name,x,prior_k in inputs(ev,target,parent):
        result=run_termination_aware_slsqp(coarse,fine,x,30.005,scan.stage_solver)
        attempts=[scan.numeric_candidate(ev,t,name) for t in result["attempts"]]
        eligible.extend([t for t in attempts if t["eligible_converged"]])
        rows.append({"name":name,"from_K01":prior_k,"initial_vector":x.tolist(),
                     "recovery_cause":result["recovery_cause"],
                     "attempts":attempts})
        print("CONT",target,name,"from",prior_k,
              [(z["tier"],z["dense"]["worst_IL_db"],z["eligible_converged"])
               for z in attempts],flush=True)
    best=min(eligible,key=lambda z:z["dense"]["worst_IL_db"]) if eligible else None
    mna=None
    if best:
        vec=np.asarray(best["vector"],float)
        mna=scan.graph.base.parent.independent_mna(policy,"input_output",("cf0",),vec)
        if not mna["pass"]:raise AssertionError("Independent MNA failure")
        if abs(vec[8]-target)>1e-12:raise AssertionError("Frozen k01 violated")
    original=min((v for v in parent["curve"] if v["vector"] is not None),
                 key=lambda q:abs(q["k01"]-target))
    out={
        "experiment_id":"EXP-067","phase":"Phase 2","stage":"continuation_check",
        "constraint_id":"RF-T008","revision":3,
        "k01_target":target,"refinement_index":a.index,
        "source_run_id":39517715488,"source_summary_sha256":EXPECTED_PARENT_SHA,
        "source_nearest_k01":original["k01"],
        "source_nearest_IL_db":original["IL_db"],
        "seed_count":len(rows),"starts":rows,
        "best_converged_30db":best,"independent_MNA":mna,
        "RF_grid":"28x1001, six settings","solver_policy":"slsqp-staged-v2",
        "execution_sha":subprocess.check_output(["git","rev-parse","HEAD"],
                                 cwd=ROOT,text=True).strip(),
        "limitations":["Local best among finite starts only, no global certificate",
                       "Physical signed k, Q(f), SRF, EM and tolerance unverified"]
    }
    a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_text(json.dumps(out,ensure_ascii=False,indent=2,allow_nan=False)+"\n")
    print("RESULT",target,"best",
          best["dense"]["worst_IL_db"] if best else None,"MNA",mna and mna["pass"],flush=True)

if __name__=="__main__":
    main()

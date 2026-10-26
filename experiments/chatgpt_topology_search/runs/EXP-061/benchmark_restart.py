#!/usr/bin/env python3
"""EXP-061 controlled SLSQP budget comparison using actual EXP-060 failed checkpoints.

Include only EXP-060 starts whose coarse stopped status4/8 but fine stage
successfully terminated (status0). Both arms start from the same saved
fine-stage vector; primary=240/120 and larger=500/280. Compare convergence,
finite 30dB, independent 9x9 MNA, objective, iterations, function calls.
These are two NEW optimization attempts, original unsuccessful EXP060 results
are NEVER retroactively relabelled. Research is Phase2, RF-T008 revision3.
"""
import argparse
import json
import sys
import subprocess
from pathlib import Path
import numpy as np

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
sys.path.insert(0,str(ROOT/"experiments/chatgpt_topology_search/runs/EXP-060"))
sys.path.insert(0,str(ROOT/"src"))
import search_coupling_lgraphs as graph
from lpf.phase2_models import exp058_area3 as stages
from lpf.constraint_versions import load_constraint,constraint_fingerprint
from lpf.trial_ic_fixed_c import validate_ic_fixed_c_settings
from lpf.trial_pcb_pattern_c import validate_trial_pcb_pattern_c_branches

SRC = ROOT/"results/EXP-060/collected"

def cases():
    allrows=[]
    for path in sorted(SRC.glob("*.json")):
        x=json.loads(path.read_text())
        if x.get("experiment_id")!="EXP-060" or not isinstance(x.get("attempts"), list):continue
        for a in x["attempts"]:
            raw=a["solver"]
            if not raw["coarse"]["success"] and raw["fine"]["success"]:
                allrows.append((x["graph"],x["K_mode"],a,{"source":path.name,
                    "coarse_status":raw["coarse"]["status"],
                    "fine_status":raw["fine"]["status"]}))
    if len(allrows)!=20:
        raise ValueError(f"Expected exactly 20 coarse-failed/fine-converged starts; got {len(allrows)}")
    return allrows

def optimize(coarse,fine,initial,coarse_max,fine_max):
    c,cst=stages.opt(coarse,initial,coarse_max,30.005)
    f,fst=stages.opt(fine,c,fine_max,30.005)
    return f,{"coarse":cst,"fine":fst,"full_convergence":bool(cst["success"] and fst["success"])}

def verify(policy,x,evaluator):
    m=evaluator.summary(x)
    passed=bool(m["min_H2_db"]>=30 and m["min_H3_db"]>=30)
    return m,passed

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--bucket",type=int,required=True)
    ap.add_argument("--buckets",type=int,default=4)
    ap.add_argument("--out",type=Path,required=True)
    q=ap.parse_args()
    if q.bucket<0 or q.bucket>=q.buckets or q.buckets<1:
        raise ValueError("Bad bucket")
    subset=[s for idx,s in enumerate(cases()) if idx%q.buckets==q.bucket]
    policy=load_constraint("RF-T008",allow_trial=True)
    results=[]
    for graph_name,k_mode,a,metadata in subset:
        graph.begin(k_mode,graph_name)
        dense=graph.Evaluator(policy,"input_output",("cf0",),1001)
        coarse=graph.Evaluator(policy,"input_output",("cf0",),7)
        fine=graph.Evaluator(policy,"input_output",("cf0",),17)
        original=np.asarray(a["vector"],float)
        original_metrics=dense.summary(original)
        diag={
            "graph":graph_name,"k_mode":k_mode,"source_start":int(a["start"]),
            "source":metadata,"original_converged":bool(a["converged"]),
            "original_finite30":bool(a["finite_30db_pass"]),
            "original_coarse_iterations":int(a["solver"]["coarse"]["nit"]),
            "original_fine_iterations":int(a["solver"]["fine"]["nit"]),
            "original_metrics":original_metrics,"arms":{}
        }
        for name,(bc,bf) in {"same_budget":(240,120),"raised_budget":(500,280)}.items():
            vector,status=optimize(coarse,fine,original,bc,bf)
            dense_metrics,eligible=verify(policy,vector,dense)
            mna=None
            if status["full_convergence"] and eligible:
                mna=graph.base.parent.independent_mna(policy,"input_output",("cf0",),vector)
                if not mna["pass"]:
                    raise AssertionError("Independent 9x9 coupled-L MNA disagrees")
                fixed=np.asarray(vector[11:13],float).tolist()
                caps=np.asarray(vector[13:]).reshape(6,2).tolist()
                validate_ic_fixed_c_settings(policy,
                    [dict(graph.base.parent.norm(e),role="bridge") for e in dense.var_edges],
                    fixed,dict(zip(graph.base.CASES,caps)))
            diag["arms"][name]={
                "coarse_budget":bc,"fine_budget":bf,
                "solver":status,"vector":vector.tolist(),"dense":dense_metrics,
                "converged_and_30dB":bool(status["full_convergence"] and eligible),
                "independent_MNA":mna
            }
            print("BENCH",graph_name,k_mode,a["start"],name,
                  status["coarse"]["status"],status["fine"]["status"],
                  "IL",dense_metrics["worst_IL_db"],
                  "PASS",diag["arms"][name]["converged_and_30dB"],flush=True)
        results.append(diag)
    out={
        "experiment_id":"EXP-061","phase":"Phase 2","constraint_id":"RF-T008",
        "trial_revision":3,"source_run_id":39434590336,
        "source_reason":"EXP-060 coarse status4/8 but fine status0",
        "bucket":q.bucket,"buckets":q.buckets,
        "effective_constraint_sha256":constraint_fingerprint(policy),
        "execution_sha":subprocess.check_output(["git","rev-parse","HEAD"],text=True,cwd=ROOT).strip(),
        "cases":results,"starts":len(results),"limitations":[
          "Followup interventions not proof of original coarse solver failure cause.",
          "Only 20 coarse-failed/fine-success candidates, no global-optimality guarantee.",
          "Independent 9x9 MNA checks only fully converged 30dB candidates.",
          "Source EXP060 result flags immutable, no Phase3 or physical SRF/Q(f) verification."
        ]}
    q.out.parent.mkdir(parents=True,exist_ok=True)
    q.out.write_text(json.dumps(out,ensure_ascii=False,indent=2,allow_nan=False)+"\n")
    print("BUCKET_DONE",q.bucket,len(results),
          "same_success",sum(v["arms"]["same_budget"]["converged_and_30dB"] for v in results),
          "raised_success",sum(v["arms"]["raised_budget"]["converged_and_30dB"] for v in results),flush=True)

if __name__=="__main__":
    main()

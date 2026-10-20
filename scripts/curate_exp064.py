#!/usr/bin/env python3
"""Git-curate executed EXP-064 area4 4L zero-GJM search; never promote noncompliant results."""
import argparse,csv,hashlib,io,json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
RUN=ROOT/"experiments/chatgpt_topology_search/runs/EXP-064"
SNAP=ROOT/"data/pareto_snapshots/rf_t008_exp064_area4_20261020.json"
RUN_ID=39450827220
FP="7de08611f8dd15b40fdfb7946e8c93de5796d026641bdca0f12e992962d05fd4"
CASES=("B71","B12","B28","B13+B14","B26","B8")
LOWER_COST_BEST=0.9340275796118456
ORIGINAL_AREA4_BEST=0.9486501590658404

def require(ok,msg):
    if not ok:raise AssertionError(msg)
def dump(path,obj):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(obj,indent=2,ensure_ascii=False,allow_nan=False)+"\n")
    return path
def ref(path):
    return {"path":path.relative_to(ROOT).as_posix(),
            "sha256":hashlib.sha256(path.read_bytes()).hexdigest()}
def checkpoint(d):
    b=d["best_converged_30db"];x=b["vector"]
    L=[tuple(e) for e in d["L_edges"]]
    P=[tuple(e) for e in d["PCB_edges"]]
    V=[tuple(e) for e in d["variable_C_edges"]]
    require(len(x)==24 and len(L)==4 and len(P)==3 and len(V)==2,"bad 4L record")
    cid="EXP064-area4-"+d["layout"]
    parts=[dict(id="L"+str(i),type="LQP02HV",nodes=L[i],
                L_nH=x[i],Q=25,chip_area_units=1) for i in range(4)]
    parts.extend(dict(id="PCB"+str(i),type="PCB_PATTERN_C",
                nodes=e,C_pF=x[4+i],Q=60 if -1 in e else 40,
                chip_area_units=0) for i,e in enumerate(P))
    for i,e in enumerate(V):
        parts.extend([
            dict(id="ICfix"+str(i),type="IC_FIXED_C_Q60",
                 nodes=e,C_pF=x[10+i],Q=60,setting_invariant=True),
            dict(id="Cv"+str(i),type="IC_VARIABLE_C_Q35",
                 nodes=e,Q=35,max_C_pF=3,setting_dependent=True)])
    return {
      "schema_version":1,"experiment_id":"EXP-064",
      "candidate_id":cid,"phase":"Phase 2","constraint_id":"RF-T008","revision":3,
      "chip_area_units":4.0,
      "topology":{"L_edges":L,"PCB_edges":P,
                  "variable_C_edges":V,"IC_fixed_parallel_edges":V},
      "components":parts,"couplings":[
          {"pair":p,"k":x[7+i]} for i,p in enumerate(
          (("L0","L1"),("L1","L3"),("L3","L2")))],
      "chip_row":["L0","L1","L3","L2"],
      "ic_variable_C_pf_by_setting":{
           s:[max(0.0,x[12+2*i]),max(0.0,x[13+2*i])]
           for i,s in enumerate(CASES)},
      "fixed_values":{"L_nH":x[:4],"PCB_C_pf":x[4:7],
                      "k_signed":x[7:10],"IC_fixed_C_pf":x[10:12]},
      "vector":x,"metrics":b["dense"],
      "solver":{"tier":b["tier"],"coarse":b["coarse"],"fine":b["fine"]},
      "independent_MNA":d["independent_MNA"],
      "source":{"run_id":RUN_ID,"layout":d["layout"],
                "execution_sha":d["code_execution_sha"]},
      "limitations":d["limitations"]}
def main():
    p=argparse.ArgumentParser()
    p.add_argument("--input",type=Path,required=True)
    a=p.parse_args()
    raw=[json.loads(x.read_text()) for x in sorted(a.input.glob("*.json"))
         if x.name!="summary.json"]
    require(len(raw)==12 and len({x["layout"] for x in raw})==12,"not exactly 12 unique layouts")
    require(all(x["experiment_id"]=="EXP-064" and x["revision"]==3 and
           x["effective_constraint_sha256"]==FP and len(x["starts"])==2
           for x in raw),"invalid model or starts")
    execs={x["code_execution_sha"] for x in raw}
    require(len(execs)==1,"mixed execution commits")
    sha=next(iter(execs))
    details=[];status=[]
    for x in raw:
        b=x["best_converged_30db"]
        if b is not None:
            require(b["eligible"] and b["converged"]
                    and b["dense"]["min_H2_db"]>=30
                    and b["dense"]["min_H3_db"]>=30
                    and x["independent_MNA"]["pass"]
                    and x["independent_MNA"]["probes"]==84,"invalid selected MNA/30dB")
        details.append({"layout":x["layout"],
              "IL_db":b["dense"]["worst_IL_db"] if b else None,
              "min_H2_db":b["dense"]["min_H2_db"] if b else None,
              "min_H3_db":b["dense"]["min_H3_db"] if b else None,
              "independent_MNA_pass":x["independent_MNA"]["pass"] if b else None,
              "PCB_edges":x["PCB_edges"]})
        for z in x["starts"]:
            require(len(z["attempts"])in (1,2),"invalid continuation")
            status.append({
                "layout":x["layout"],"start":z["start"],
                "converged":any(t["converged"] for t in z["attempts"]),
                "stages":[{"tier":t["tier"],"coarse_status":t["coarse"]["status"],
                           "fine_status":t["fine"]["status"],"eligible":t["eligible"],
                           "IL_db":t["dense"]["worst_IL_db"]} for t in z["attempts"]]})
    require(len(status)==24,"missing starts")
    valid=[x for x in raw if x["best_converged_30db"]]
    require(valid,"no candidate to curate; failed records need separate preservation")
    winner=min(valid,key=lambda x:x["best_converged_30db"]["dense"]["worst_IL_db"])
    win_il=winner["best_converged_30db"]["dense"]["worst_IL_db"]
    improved=win_il<ORIGINAL_AREA4_BEST-1e-7
    pareto=win_il<LOWER_COST_BEST-1e-7
    retain=[winner] if improved else [next(x for x in raw if x["layout"]=="g4g3_b01")]
    checkpoint_entries=[]; overlays=[]
    for x in retain:
        cp=checkpoint(x); name=x["layout"]
        cpath=dump(RUN/"checkpoints"/(name+".json"),cp)
        checkpoint_entries.append({**ref(cpath),"candidate_id":cp["candidate_id"],
                              "selection_reason":"pareto" if pareto else "topology_diversity"})
        vpath=dump(RUN/"validation"/(name+"_mna.json"),{
            "experiment_id":"EXP-064","candidate_id":cp["candidate_id"],
            "source_run_id":RUN_ID,"source_sha":sha,
            "dense":x["best_converged_30db"]["dense"],
            "independent_9x9_MNA":x["independent_MNA"],
            "pass":True,"finite_grid_only":True})
        overlays.append({**ref(vpath),"method":"independent_mna","status":"passed"})
    converged=sum(z["converged"] for z in status)
    summary=dump(RUN/"run_summary.json",{
       "schema_version":1,"experiment_id":"EXP-064","phase":"Phase 2",
       "constraint_id":"RF-T008","revision":3,
       "execution_status":"completed","source_run_id":RUN_ID,
       "code_execution_sha":sha,"constraint_sha256":FP,
       "attempts":{"planned":24,"attempted":24,"converged":converged,
          "nonconverged":24-converged,"failed":0,"not_started":0},
       "selected_candidate_count":len(checkpoint_entries),
       "tested_layouts":details,"attempt_stage_outcomes":status,
       "old_area4_best_IL_db":ORIGINAL_AREA4_BEST,"lower_cost_best_IL_db":LOWER_COST_BEST,
       "best_found_IL_db":win_il,"best_layout":winner["layout"],
       "improved_over_previous_area4":improved,"now_nondominated":pareto,
       "limitations":["12 PCB topologies, two starts each; finite-grid, local results only",
             "Do not infer global design limit from tested topology failure",
             "No physical Q(f)/SRF/EM/k implementation, tolerance or continuous-band proof"]})
    dump(SNAP,{
        "schema_version":1,"experiment_id":"EXP-064","phase":"Phase 2",
        "constraint_id":"RF-T008","trial_revision":3,"source_run_id":RUN_ID,
        "area":4.0,"previous_best_IL_db":ORIGINAL_AREA4_BEST,
        "new_best_IL_db":win_il,"candidate":winner["layout"],
        "under_existing_area3p667_best_IL_db":LOWER_COST_BEST,
        "observed_pareto_area4":pareto,
        "conclusion":"Numerical scoped sweep; unchanged or updated as explicitly labeled",
        "limitations":["Not exhaustive global Pareto or physical fabricability proof"]})
    mpath=RUN/"manifest.json"
    m=json.loads(mpath.read_text())
    m["code"]["execution_sha"]=sha
    m["execution"]={"status":"completed","elapsed_seconds":None,"evaluation_count":None}
    m["validation"]={"numerical":"passed","independent":"passed",
         "implementation":"not_run",
         "analysis_grid":{"intervals":28,"points_per_interval":1001,"settings":6},
         "independent_grid":{"intervals":28,"points_per_interval":3,"total":84,
                 "method":"9x9 coupled inductor branch-current MNA"}}
    m["evidence"]=[{"path":q["path"],"sha256":q["sha256"]}
                   for q in checkpoint_entries+overlays]+[
                   ref(summary),ref(RUN/"sweep_4l_zero_gjm_pcb.py"),ref(RUN/"README.md")]
    m["limitations"]=["Local 4L/0GJM 12 PCB layouts and 24 starts",
            "Nominal constant-Q model; H2/H3 30dB finite-grid, not 35dB proof",
            "No continuous extreme, SRF, physical k, Q(f), EM, tolerances or Phase3"]
    dump(mpath,m)
    spath=RUN/"storage_record.json"
    storage=json.loads(spath.read_text())
    storage.update(stage="complete",checkpoints=checkpoint_entries,
                   validation_overlays=overlays,git_readback="passed",
                   summary=ref(summary))
    storage["supporting_evidence"]=[
       {**ref(RUN/"sweep_4l_zero_gjm_pcb.py"),"role":"source_snapshot",
        "reason":"Executed full RF-T008 model and independent 9x9 MNA code"},
       {**ref(RUN/"README.md"),"role":"method_note",
        "reason":"Pre-run purpose, experiment gate and frozen nominal constraints"}]
    storage["limitations"]=["Selected evidence only; 12 per-layout raw outcomes remain in 30-day Actions artifacts",
        "No global optimality or physical component validation."]
    dump(spath,storage)
    idx=ROOT/"data/experiment_index.csv"
    with idx.open(newline="") as f:
        rr=csv.DictReader(f); fields=rr.fieldnames; rows=list(rr)
    require(sum(r["experiment_id"]=="EXP-064" for r in rows)==1,"index record missing/duplicate")
    for r in rows:
        if r["experiment_id"]=="EXP-064":
            r.update(execution_status="completed",numerical_validation="passed",
                     independent_validation="passed")
    s=io.StringIO(newline="")
    w=csv.DictWriter(s,fieldnames=fields,lineterminator="\n")
    w.writeheader();w.writerows(rows);idx.write_text(s.getvalue())
    print("CURATED_EXP064",win_il,"BEST",winner["layout"],"PARETO",pareto,
          "CONVERGED",converged,flush=True)
if __name__=="__main__":
    main()

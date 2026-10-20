#!/usr/bin/env python3
"""Curate executed EXP-063 Phase2 3L trial into Git with honest non-improvement."""
import argparse
import csv
import hashlib
import io
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
RUN=ROOT/"experiments/chatgpt_topology_search/runs/EXP-063"
SNAP=ROOT/"data/pareto_snapshots/rf_t008_exp063_threeL_20261020.json"
RUNID=39449538072
HASH="7de08611f8dd15b40fdfb7946e8c93de5796d026641bdca0f12e992962d05fd4"
CASES=("B71","B12","B28","B13+B14","B26","B8")
BASE={9:1.0103502552079047,11:0.9340275796118456,13:0.9281187612899361}
CHOICE={9:"a3_ground_n1",11:"a367_ground_n1",13:"a433_ground_n1"}

def need(cond,msg):
    if not cond:raise AssertionError(msg)

def dump(path,j):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(j,indent=2,ensure_ascii=False,allow_nan=False)+"\n")
    return path

def ref(path):
    return {"path":path.relative_to(ROOT).as_posix(),
            "sha256":hashlib.sha256(path.read_bytes()).hexdigest()}

def make_checkpoint(d):
    b=d["best_converged_30db"]
    x=b["vector"]
    area=d["area"]
    k=round(area*3)
    c_id="EXP063-"+{9:"A3",11:"A3P667",13:"A4P333"}[k]+"-ground_n1"
    L=[tuple(e) for e in d["L_edges"]]
    G=[tuple(e) for e in d["GJM_edges"]]
    P=[tuple(e) for e in d["PCB_edges"]]
    V=[tuple(e) for e in d["variable_C_edges"]]
    need(len(x)==22 and len(L)==3 and len(G)+len(P)==3 and len(V)==2,"bad 3L candidate")
    parts=[]
    for i,e in enumerate(L):
        parts.append({"id":("L0","L1","Ls")[i],"type":"LQP02HV",
                      "nodes":e,"L_nH":x[i],"Q":25,"chip_area_units":1})
    for i,e in enumerate(G):
        parts.append({"id":"GJM"+str(i),"type":"GJM01","nodes":e,"C_pF":x[3+i],
                      "Q":80,"chip_area_units":2/3})
    for i,e in enumerate(P):
        parts.append({"id":"PCB"+str(i),"type":"PCB_PATTERN_C","nodes":e,
                      "C_pF":x[3+len(G)+i],"Q":60 if -1 in e else 40,
                      "chip_area_units":0})
    for i,e in enumerate(V):
        parts += [{"id":"ICfix"+str(i),"type":"IC_FIXED_C_Q60","nodes":e,
                   "C_pF":x[8+i],"Q":60,"setting_invariant":True},
                  {"id":"Cv"+str(i),"type":"IC_VARIABLE_C_Q35","nodes":e,
                   "Q":35,"setting_dependent":True,"max_C_pF":3}]
    cv={s:[max(0,x[10+i*2]),max(0,x[11+i*2])] for i,s in enumerate(CASES)}
    cp={
      "schema_version":1,"experiment_id":"EXP-063","candidate_id":c_id,
      "phase":"Phase 2","constraint_id":"RF-T008","revision":3,
      "chip_area_units":area,
      "topology":{"L_edges":L,"GJM_edges":G,"PCB_edges":P,
                  "variable_C_edges":V,"fixed_IC_parallel_edges":V},
      "components":parts,
      "couplings":[{"pair":pair,"k":x[6+i]} for i,pair in enumerate(
          (("L0","Ls"),("Ls","L1")))],
      "chip_row":["L0","Ls","L1"],
      "ic_variable_C_pf_by_setting":cv,
      "fixed_values":{"L_nH":x[:3],"GJM_C_pf":x[3:3+len(G)],
                      "PCB_C_pf":x[3+len(G):6],"k_signed":x[6:8],
                      "IC_fixed_C_pf":x[8:10]},
      "vector":x,"metrics":b["dense"],
      "solver":{"tier":b["tier"],"coarse":b["coarse"],"fine":b["fine"]},
      "independent_MNA":d["independent_MNA"],
      "source":{"run_id":RUNID,"code_sha":d["code_execution_sha"],
                "layout":d["layout"]},
      "selection_note":"Non-improving grounded PCB alternative retained for topology diversity",
      "limitations":d["limitations"]
    }
    return cp

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--input",type=Path,required=True)
    a=p.parse_args()
    d=[json.loads(f.read_text()) for f in sorted(a.input.glob("a*.json"))]
    need(len(d)==12 and len({x["layout"] for x in d})==12,"12 unique layouts required")
    need(all(x["experiment_id"]=="EXP-063" and x["revision"]==3
      and x["effective_constraint_sha256"]==HASH and len(x["starts"])==2 for x in d),
      "model or effort mismatch")
    sha={x["code_execution_sha"] for x in d}
    need(len(sha)==1,"mixed execution SHA")
    exec_sha=next(iter(sha))
    lookup={x["layout"]:x for x in d}
    details=[];statuses=[]
    for x in d:
        b=x["best_converged_30db"]
        need(b is not None and b["eligible"] and b["converged"],
             "missing eligible 3L result")
        need(b["dense"]["min_H2_db"]>=30 and b["dense"]["min_H3_db"]>=30
          and x["independent_MNA"]["pass"],"failed RF/MNA")
        details.append({"layout":x["layout"],"area":x["area"],
            "IL_db":b["dense"]["worst_IL_db"],
            "H2_min_db":b["dense"]["min_H2_db"],"H3_min_db":b["dense"]["min_H3_db"],
            "GJM_edges":x["GJM_edges"],"PCB_edges":x["PCB_edges"],
            "MNA_pass":x["independent_MNA"]["pass"]})
        for start in x["starts"]:
            stages=start["attempts"]
            need(1<=len(stages)<=2,"bad v2 stage count")
            statuses.append({"layout":x["layout"],"start":start["start"],
                "stages":[{"tier":v["tier"],"coarse_status":v["coarse"]["status"],
                           "fine_status":v["fine"]["status"],"converged":v["converged"],
                           "finite_30db_pass":v["finite_30db_pass"],
                           "IL_db":v["dense"]["worst_IL_db"]} for v in stages],
                "converged":any(v["converged"] for v in stages)})
    counts={}
    for cost in BASE:
        values=[v for v in details if round(v["area"]*3)==cost]
        need(len(values)==4,"missing cost variant")
        best=min(values,key=lambda v:v["IL_db"])
        counts[str(cost)]={"IL_db":best["IL_db"],"layout":best["layout"],
                    "old_EXP058_IL_db":BASE[cost],
                    "improvement_db":BASE[cost]-best["IL_db"]}
        need(best["IL_db"]>=BASE[cost]-1e-6,"new 3L improvement needs independent review")
    # Three best altered circuits are selection-for-diversity, not new Pareto points.
    cp_list=[];overlay_list=[]
    for cost,name in CHOICE.items():
        item=lookup[name]
        b=item["best_converged_30db"]
        need(b["converged"] and item["independent_MNA"]["pass"],"invalid retained variant")
        cp=make_checkpoint(item)
        file=RUN/"checkpoints"/(name+".json")
        dump(file,cp)
        cp_list.append({**ref(file),"candidate_id":cp["candidate_id"],
                        "selection_reason":"topology_diversity"})
        f=RUN/"validation"/(name+"_mna.json")
        dump(f,{"experiment_id":"EXP-063","candidate_id":cp["candidate_id"],
            "source_action_run_id":RUNID,"source_execution_sha":exec_sha,
            "dense":b["dense"],"independent_MNA":item["independent_MNA"],
            "pass":True,"grid_is_finite":True})
        overlay_list.append({**ref(f),"method":"independent_mna","status":"passed"})
    nconv=sum(x["converged"] for x in statuses)
    summary=dump(RUN/"run_summary.json",{
       "schema_version":1,"experiment_id":"EXP-063",
       "phase":"Phase 2","constraint_id":"RF-T008","revision":3,
       "run_id":RUNID,"execution_status":"completed","code_execution_sha":exec_sha,
       "effective_constraint_sha256":HASH,
       "attempts":{"planned":24,"attempted":24,"converged":nconv,
                   "nonconverged":24-nconv,"failed":0,"not_started":0},
       "selected_candidate_count":len(cp_list),
       "cost_best":counts,"layout_results":details,"attempt_status":statuses,
       "pareto_update":"no new nondominated points in 3L areas 3, 3p667, 4p333",
       "limitations":["Local 12-layout 24-start search; no global optimality",
         "No improvement in tested alternative PCB-C placements",
         "Nominal constant-Q, 28x1001 finite grid and independent 84-point 7x7 MNA",
         "H2/H3 35dB nominal / IL 0.3dB targets not reached; no Q(f)/SRF/EM/tolerance"]
    })
    dump(SNAP,{"schema_version":1,"experiment_id":"EXP-063","phase":"Phase 2",
       "constraint_id":"RF-T008","revision":3,"run_id":RUNID,
       "baseline_EXP058_costs":BASE,"new_best_by_cost":counts,
       "non_dominated_set_change":False,
       "note":"EXP-063 studied 3L at same RF-T008 v3 but did not update the stored 3L Pareto points; EXP-062 higher-cost snapshot is tracked separately.",
       "limitations":["Finite 12-layout scoped local search, not proof against all 3L topologies"]})
    man_path=RUN/"manifest.json"
    man=json.loads(man_path.read_text())
    man["code"]["execution_sha"]=exec_sha
    man["execution"]={"status":"completed","elapsed_seconds":None,"evaluation_count":None}
    man["validation"]={"numerical":"passed","independent":"passed","implementation":"not_run",
        "analysis_grid":{"intervals":28,"points_per_interval":1001,"settings":6},
        "independent_grid":{"intervals":28,"points_per_interval":3,"total":84,
                            "method":"independent 7x7 branch-current MNA"}}
    man["evidence"]=[{"path":z["path"],"sha256":z["sha256"]} for z in cp_list+overlay_list]+[
        ref(summary),ref(RUN/"sweep_3l_grounded_pcb.py"),ref(RUN/"README.md")]
    man["limitations"]=["All tested 3L costs retained previous EXP-058 best-found; no 3L Pareto update",
       "Three inferior grounded-PCB candidates archived solely for topology diversity",
       "Local finite-grid nominal Phase2 only, no physical realization guarantee"]
    dump(man_path,man)
    record_path=RUN/"storage_record.json"
    storage=json.loads(record_path.read_text())
    storage["stage"]="complete";storage["checkpoints"]=cp_list
    storage["validation_overlays"]=overlay_list
    storage["summary"]=ref(summary)
    storage["supporting_evidence"]=[
      {**ref(RUN/"sweep_3l_grounded_pcb.py"),"role":"source_snapshot",
       "reason":"Executed 3L topology evaluator/SLSQP and independent 7x7 MNA source"},
      {**ref(RUN/"README.md"),"role":"method_note",
       "reason":"Locked experiment scope, initial data provenance and Phase2 limits"}]
    storage["git_readback"]="passed"
    storage["limitations"]=["No new 3L Pareto points. Three diversity circuits preserved; 12 raw layouts remain as time-limited Actions artifacts."]
    dump(record_path,storage)
    idx_path=ROOT/"data/experiment_index.csv"
    with idx_path.open(newline="") as f:
        reader=csv.DictReader(f)
        cols=reader.fieldnames
        rows=list(reader)
    need(sum(r["experiment_id"]=="EXP-063" for r in rows)==1,"EXP-063 index duplicate/missing")
    for row in rows:
        if row["experiment_id"]=="EXP-063":
            row.update(execution_status="completed",numerical_validation="passed",
                       independent_validation="passed")
    s=io.StringIO(newline="")
    w=csv.DictWriter(s,fieldnames=cols,lineterminator="\n")
    w.writeheader();w.writerows(rows)
    idx_path.write_text(s.getvalue())
    print("CURATED EXP063",counts,"converged",nconv,"no new Pareto",flush=True)

if __name__=="__main__":
    main()

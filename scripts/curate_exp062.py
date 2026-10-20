#!/usr/bin/env python3
"""Curate completed EXP-062 Actions JSON into immutable Phase2 Git evidence.

This script never runs optimization and never changes RF constraints.
Source: Actions run 39447892051, 12 layouts, 24 SLSQP initial starts.
"""
import argparse
import csv
import hashlib
import io
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / "experiments/chatgpt_topology_search/runs/EXP-062"
SNAP = ROOT / "data/pareto_snapshots/rf_t008_exp062_high_cost_20261020.json"
SRC_RUN_ID = 39447892051
REQ_SHA = "7de08611f8dd15b40fdfb7946e8c93de5796d026641bdca0f12e992962d05fd4"
CASES = ("B71","B12","B28","B13+B14","B26","B8")
BASELINE = [(3,1.0103502552079047),(3+2/3,0.9340275796118456),
            (4,0.948650159),(4+1/3,0.928118761),
            (4+2/3,0.8371337485828259)]

def require(x,message):
    if not x: raise AssertionError(message)

def sha(data):
    return hashlib.sha256(data).hexdigest()

def dump(path,obj):
    path.parent.mkdir(parents=True,exist_ok=True)
    b=(json.dumps(obj,indent=2,ensure_ascii=False,allow_nan=False)+"\n").encode()
    path.write_bytes(b)
    return path

def ref(path):
    raw=path.read_bytes()
    return {"path":path.relative_to(ROOT).as_posix(),"sha256":sha(raw)}

def checkpoint(obj):
    b=obj["best_converged_30db"]
    x=b["vector"]
    area=obj["chip_area"]
    idx=round((area-4)*1.5)
    ident={2:"A5P333",3:"A6",4:"A6P667"}[idx]
    cid="EXP062-"+ident+"-grounded-best"
    gjm=[tuple(e) for e in obj["GJM_edges"]]
    pcb=[tuple(e) for e in obj["PCB_edges"]]
    var=[tuple(e) for e in obj["variable_C_edges"]]
    L=[tuple(e) for e in obj["L_edges"]]
    assert len(L)==4 and len(gjm)+len(pcb)==4 and len(var)==2 and len(x)==25
    cvars={case:[max(0.0,x[13+2*i]),max(0.0,x[14+2*i])]
           for i,case in enumerate(CASES)}
    parts=[dict(id="L"+str(i),type="LQP02HV",nodes=L[i],L_nH=x[i],Q=25,
                chip_area_units=1) for i in range(4)]
    for i,e in enumerate(gjm):
        parts.append(dict(id="GJM"+str(i),type="GJM01",nodes=e,C_pF=x[4+i],
                          Q=80,chip_area_units=2/3))
    for i,e in enumerate(pcb):
        parts.append(dict(id="PCB"+str(i),type="PCB_PATTERN_C",nodes=e,
                          C_pF=x[4+len(gjm)+i],Q=60 if -1 in e else 40,
                          chip_area_units=0))
    for i,e in enumerate(var):
        parts.append(dict(id="ICfix"+str(i),type="IC_FIXED_C_Q60",
                          nodes=e,C_pF=x[11+i],Q=60,setting_invariant=True))
        parts.append(dict(id="Cv"+str(i),type="IC_VARIABLE_C_Q35",
                          nodes=e,Q=35,setting_dependent=True,
                          C_max_pF=3.0))
    couplings=[{"pair":a,"k":x[8+i]} for i,a in enumerate(
        (("L0","L1"),("L1","L3"),("L3","L2")))]
    return {
        "schema_version":1,"experiment_id":"EXP-062","candidate_id":cid,
        "phase":"Phase 2","constraint_id":"RF-T008","trial_revision":3,
        "chip_area_units":area,
        "topology":{"L_edges":L,"fixed_GJM_edges":gjm,
                    "PCB_C_edges":pcb,"variable_C_edges":var,
                    "IC_fixed_C_parallel_edges":var},
        "components":parts,"couplings":couplings,
        "chip_row":obj["physical_L_row"],
        "ic_variable_C_pf_by_setting":cvars,
        "fixed_values":{"L_nH":x[:4],"GJM_C_pf":x[4:4+len(gjm)],
                        "PCB_C_pf":x[4+len(gjm):8],
                        "k_signed":x[8:11],"IC_fixed_C_pf":x[11:13]},
        "vector":x,"vector_order":"L0..3; 4 fixed caps; k01,k13,k32; two ICfix; six*2 variable",
        "metrics":b["dense"],"solver":{"start_tier":b["tier"],"coarse":b["coarse"],"fine":b["fine"]},
        "independent_MNA":obj["independent_MNA"],
        "source":{"run_id":SRC_RUN_ID,"layout":obj["layout"],"code_sha":obj["code_execution_sha"]},
        "limitations":obj["limitations"]
    }

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--input",type=Path,required=True)
    a=p.parse_args()
    data=[json.loads(f.read_text()) for f in sorted(a.input.glob("a*.json"))]
    require(len(data)==12,"exactly 12 raw layout files required")
    require(len({z["layout"] for z in data})==12,"repeated layout")
    require({round(d["chip_area"]*3) for d in data}=={16,18,20},"cost coverage incomplete")
    require(all(d["experiment_id"]=="EXP-062" and d["revision"]==3
                and d["effective_constraint_sha256"]==REQ_SHA
                and len(d["starts"])==2 for d in data),"invalid input provenance")
    require(len({d["code_execution_sha"] for d in data})==1,"mixed executed commits")
    source_sha=data[0]["code_execution_sha"]
    selections={}
    attempt_rows=[]
    for d in data:
        good=d.get("best_converged_30db")
        if good:
            require(good["converged"] and good["eligible"] and
                    good["dense"]["min_H2_db"]>=30 and good["dense"]["min_H3_db"]>=30,
                    "invalid selected finite RF result")
            require(d["independent_MNA"]["pass"] and
                    d["independent_MNA"]["probes"]==84,
                    "missing selected independent MNA")
            area=round(d["chip_area"]*3)
            if area not in selections or good["dense"]["worst_IL_db"] < (
                    selections[area]["best_converged_30db"]["dense"]["worst_IL_db"]):
                selections[area]=d
        status=[]
        for r in d["starts"]:
            tiers=r["attempts"]
            require(tiers and len(tiers)<=2,"invalid stage history")
            status.append({"initial_start":r["start"],
                           "primary_coarse":tiers[0]["coarse"],
                           "primary_fine":tiers[0]["fine"],
                           "continuation":tiers[1]["tier"] if len(tiers)>1 else None,
                           "all_stages":[dict(tier=q["tier"],converged=q["converged"],
                                status_coarse=q["coarse"]["status"],
                                status_fine=q["fine"]["status"],
                                IL_db=q["dense"]["worst_IL_db"],
                                H2_db=q["dense"]["min_H2_db"],
                                H3_db=q["dense"]["min_H3_db"]) for q in tiers],
                           "ever_converged":any(q["converged"] for q in tiers)})
        attempt_rows.extend(status)
    require(sum(len(d["starts"]) for d in data)==24,"initial attempt count mismatch")
    passed=sum(x["ever_converged"] for x in attempt_rows)
    details=[]
    for d in data:
        b=d.get("best_converged_30db")
        details.append({"layout":d["layout"],"chip_area":d["chip_area"],
                        "GJM_edges":d["GJM_edges"],"PCB_edges":d["PCB_edges"],
                        "IL_db":b["dense"]["worst_IL_db"] if b else None,
                        "min_H2_db":b["dense"]["min_H2_db"] if b else None,
                        "min_H3_db":b["dense"]["min_H3_db"] if b else None,
                        "independent_MNA_pass":d["independent_MNA"]["pass"] if b else None,
                        "starts":d["starts"] and len(d["starts"]),
                        "source_execution_sha":d["code_execution_sha"]})
    bests={str(k):v["best_converged_30db"]["dense"]["worst_IL_db"] for k,v in selections.items()}
    expected={16:0.8335054302993898,18:0.8278411484628513,20:0.8377954490288592}
    for k,il in expected.items():
        require(abs(float(bests[str(k)])-il)<1e-7,"unexpected best; re-review Actions provenance")
    # Keep best two new nondominated designs; high-cost 6⅔ remains dominated.
    winner=[selections[16],selections[18]]
    chek=[]; val=[]
    for d in winner:
        cp=checkpoint(d)
        filename="a"+("5p333" if abs(d["chip_area"]-5-1/3)<1e-5 else "6")+"_best"
        cpath=dump(RUN/"checkpoints"/(filename+".json"),cp)
        overlay={
          "experiment_id":"EXP-062","candidate_id":cp["candidate_id"],
          "source_actions_run_id":SRC_RUN_ID,"source_execution_sha":source_sha,
          "finite_28x1001":cp["metrics"],"independent_9x9_MNA":d["independent_MNA"],
          "pass":bool(d["independent_MNA"]["pass"]),
          "grid_is_not_continuous_guarantee":True}
        vpath=dump(RUN/"validation"/(filename+"_mna.json"),overlay)
        chek.append({**ref(cpath),"candidate_id":cp["candidate_id"],
                     "selection_reason":"pareto"})
        val.append({**ref(vpath),"method":"independent_mna","status":"passed"})
    summary=dump(RUN/"run_summary.json",{
        "schema_version":1,"experiment_id":"EXP-062","phase":"Phase 2",
        "constraint_id":"RF-T008","revision":3,
        "execution_status":"completed_actions_and_selected_Git_validation",
        "action_run_id":SRC_RUN_ID,"code_execution_sha":source_sha,
        "effective_constraint_sha256":REQ_SHA,
        "attempts":{"planned":24,"attempted":24,"converged":passed,
                    "nonconverged":24-passed,"failed":0,"not_started":0},
        "selected_candidate_count":len(chek),"cost_best_IL_db":bests,
        "layout_results":sorted(details,key=lambda a:(a["chip_area"],a["IL_db"] if a["IL_db"] is not None else 1e8)),
        "attempt_termination_diagnostics":attempt_rows,
        "limitations":["12 layouts; two initial starts each; local finite-grid results only.",
                       "H2/H3 ~30.005 dB, not 35 dB nominal target; 0.30dB IL not reached.",
                       "No Q(f), SRF, EM, physical coupling or tolerance validation."]
    })
    allp=[dict(area=a,IL_db=il,origin="EXP-058/059 historical preserved") for a,il in BASELINE]
    allp += [dict(area=d["chip_area"],IL_db=d["best_converged_30db"]["dense"]["worst_IL_db"],
                  origin="EXP-062",layout=d["layout"])
             for d in selections.values()]
    nondom=[p for p in allp if not any(
       q["area"]<=p["area"]+1e-8 and q["IL_db"]<=p["IL_db"]+1e-10
       and (q["area"]<p["area"]-1e-8 or q["IL_db"]<p["IL_db"]-1e-10)
       for q in allp)]
    dump(SNAP,{
       "schema_version":1,"snapshot_id":"RF_T008_EXP062_AREAS5P333_6_6P667_20261020",
       "phase":"Phase 2","constraint_id":"RF-T008","revision":3,
       "run_id":SRC_RUN_ID,"constraint_sha256":REQ_SHA,
       "existing_smaller_costs_unchanged":True,
       "all_observed_cost_best":sorted(allp,key=lambda x:x["area"]),
       "nondominated_among_observed":sorted(nondom,key=lambda x:x["area"]),
       "conclusions":["Cost 5⅓ and 6 recovered as nondominated new observed points",
                      "Cost 6⅔ remains dominated by lower area under this local search",
                      "No global Pareto or physical realization claim"]
    })
    manifest_path=RUN/"manifest.json"
    man=json.loads(manifest_path.read_text())
    require(man["experiment_id"]=="EXP-062","bad starting manifest")
    man["code"]["execution_sha"]=source_sha
    man["execution"]={"status":"completed","elapsed_seconds":None,"evaluation_count":None}
    man["validation"]={"numerical":"passed","independent":"passed","implementation":"not_run",
                       "analysis_grid":{"intervals":28,"points_per_interval":1001,"settings":6},
                       "independent_grid":{"intervals":28,"points_per_interval":3,"total":84,"method":"independent 9x9 coupled inductor MNA"}}
    man["evidence"]=([{"path":x["path"],"sha256":x["sha256"]} for x in chek+val]
                     +[ref(summary),ref(RUN/"search_grounded_transfer_4l.py"),ref(RUN/"README.md")])
    man["limitations"]=["12-layout 24-start local search at three 4L cost cells; finite-grid no global optimum",
      "New observed Pareto points at 5⅓ and 6 only; 6⅔ unchanged/dominated",
      "35dB nominal/IL≤0.30dB goals unmet; no Q(f)/SRF/EM/coupling realization/tolerances/Phase3"]
    dump(manifest_path,man)
    rec_path=RUN/"storage_record.json"
    rec=json.loads(rec_path.read_text())
    rec["stage"]="complete";rec["checkpoints"]=chek;rec["validation_overlays"]=val
    rec["supporting_evidence"]=[
      {**ref(RUN/"search_grounded_transfer_4l.py"),"role":"source_snapshot",
       "reason":"Executed 12-layout numerical solver and MNA source"},
      {**ref(RUN/"README.md"),"role":"method_note","reason":"Pre-run hypothesis and gate record"}]
    rec["summary"]=ref(summary)
    rec["git_readback"]="passed"
    rec["limitations"]=["Only 2 new nondominated complete checkpoints curated. All 12 variants remain in time-limited Actions artifacts.",
      "Physical RF validation is separate and not completed."]
    dump(rec_path,rec)
    index_path=ROOT/"data/experiment_index.csv"
    with index_path.open(newline="") as f:
        rows=list(csv.DictReader(f))
        columns=list(rows[0])
    count=0
    for r in rows:
        if r["experiment_id"]=="EXP-062":
            r.update(execution_status="completed",
                numerical_validation="passed",independent_validation="passed")
            count+=1
    require(count==1,"missing or duplicate EXP-062 index row")
    tmp=io.StringIO(newline="")
    writer=csv.DictWriter(tmp,fieldnames=columns,lineterminator="\n")
    writer.writeheader();writer.writerows(rows)
    index_path.write_text(tmp.getvalue())
    print("CURATED EXP-062", "source",source_sha,"12 LAYOUTS",24,"STARTS",
          "converged",passed,"best",bests,"pareto",
          [(p["area"],p["IL_db"]) for p in nondom],flush=True)

if __name__=="__main__":
    main()

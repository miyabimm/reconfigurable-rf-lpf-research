#!/usr/bin/env python3
"""EXP-065 Phase2 Git curation for a 96-case, 192-start RF-T008 v3 broad sweep.

Require complete numeric provenance; only converge+finite30+independent 9x9
MNA candidates can enter selected checkpoint or updated area 5⅓ Pareto.
SLSQP failure statuses retained, no global optimality inference.
"""
import argparse
import csv
import hashlib
import io
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
RUN=ROOT/"experiments/chatgpt_topology_search/runs/EXP-065"
SNAP=ROOT/"data/pareto_snapshots/rf_t008_exp065_4l2gjm_wide_20261020.json"
RUN_ID=39453297733
FP="7de08611f8dd15b40fdfb7946e8c93de5796d026641bdca0f12e992962d05fd4"
BASELINE=0.8335054302993898
CASES=("B71","B12","B28","B13+B14","B26","B8")

def require(ok,message):
    if not ok:raise AssertionError(message)
def dump(path,x):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(x,ensure_ascii=False,indent=2,allow_nan=False)+"\n")
    return path
def ref(path):
    return {"path":path.relative_to(ROOT).as_posix(),
            "sha256":hashlib.sha256(path.read_bytes()).hexdigest()}

def checkpoint(d):
    b=d["best_converged_30db"]
    x=b["vector"]
    area=d["chip_area"]
    ge=list(map(tuple,d["GJM_edges"]))
    pe=list(map(tuple,d["PCB_edges"]))
    ve=list(map(tuple,d["variable_C_edges"]))
    le=list(map(tuple,d["L_edges"]))
    require(len(x)==25 and len(ge)==len(pe)==len(ve)==2 and len(le)==4,
            "invalid 4L/2GJM topology vector")
    parts=[{"id":"L"+str(i),"type":"LQP02HV","nodes":e,
        "L_nH":x[i],"Q":25,"chip_area_units":1} for i,e in enumerate(le)]
    for i,e in enumerate(ge):
        parts.append({"id":"GJM"+str(i),"type":"GJM01","nodes":e,
            "C_pF":x[4+i],"Q":80,"chip_area_units":2/3})
    for i,e in enumerate(pe):
        parts.append({"id":"PCB"+str(i),"type":"PCB_PATTERN_C","nodes":e,
            "C_pF":x[6+i],"Q":60 if -1 in e else 40,"chip_area_units":0})
    for i,e in enumerate(ve):
        parts.append({"id":"ICfix"+str(i),"type":"IC_FIXED_C_Q60",
                      "nodes":e,"C_pF":x[11+i],"Q":60,"setting_invariant":True})
        parts.append({"id":"Cv"+str(i),"type":"IC_VARIABLE_C_Q35",
                      "nodes":e,"Q":35,"setting_dependent":True,"max_C_pF":3})
    cid="EXP065-"+d["layout"]+"-"+d["dtc"]+"-"+d["graph"]
    return {
      "schema_version":1,"experiment_id":"EXP-065","candidate_id":cid,
      "phase":"Phase 2","constraint_id":"RF-T008","revision":3,
      "chip_area_units":area,
      "topology":{"L_edges":le,"GJM_edges":ge,"PCB_edges":pe,
                  "variable_C_edges":ve,"IC_fixed_parallel_edges":ve},
      "components":parts,
      "couplings":[{"pair":q,"k":x[8+i]} for i,q in enumerate(
          (("L0","L1"),("L1","L3"),("L3","L2")))],
      "chip_row":["L0","L1","L3","L2"],
      "ic_variable_C_pf_by_setting":{
          s:[max(0.0,float(x[13+i*2])),max(0.0,float(x[14+i*2]))]
          for i,s in enumerate(CASES)},
      "fixed_values":{"L_nH":x[:4],"GJM_C_pf":x[4:6],
          "PCB_C_pf":x[6:8],"k_signed":x[8:11],"IC_fixed_C_pf":x[11:13]},
      "vector":x,"vector_order":"4L; 2GJM; 2PCB; k01,k13,k32; 2 ICfixed; 6x2 Cvar",
      "metrics":b["dense"],"solver":{"tier":b["tier"],
                     "coarse":b["coarse"],"fine":b["fine"]},
      "independent_MNA":d["independent_MNA"],
      "source":{"actions_run_id":RUN_ID,"code_sha":d["code_execution_sha"],
                "layout":d["layout"],"dtc":d["dtc"],"graph":d["graph"]},
      "limitations":d["limitations"]
    }

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--input",type=Path,required=True)
    a=p.parse_args()
    raw=[json.loads(x.read_text()) for x in sorted(a.input.glob("*.json"))]
    require(len(raw)==96,"96 completed joint layout artifacts required")
    keys=[(d["layout"],d["dtc"],d["graph"]) for d in raw]
    require(len(set(keys))==96,"duplicate topology keys")
    require({d["layout"] for d in raw}==
      {"best_exp062","two_ground_pcb","gjm_n3","bridge_out","gjm_bridge_in",
       "gjm_n3_bridge","pcb_out_ground","gjm_no_input"},"missing fixed-C layout")
    require({d["dtc"] for d in raw}==
       {"two_bridges","tip_and_output","tip_and_input","dual_tip_shunts"},
       "missing DTC layout")
    require({d["graph"] for d in raw}==
       {"original","tip3_from_input","output_via_tip4"},"missing L graph")
    require(all(d["experiment_id"]=="EXP-065" and
          d["revision"]==3 and d["effective_constraint_sha256"]==FP and
          abs(d["chip_area"]-4-2*(2/3))<1e-7 and
          len(d["starts"])==2 for d in raw),"bad RF constraints or missing start")
    code_shas={d["code_execution_sha"] for d in raw}
    require(len(code_shas)==1,"mixed execution code SHAs")
    execution_sha=next(iter(code_shas))
    details=[]
    term=[]
    ranked=[]
    for d in raw:
        best=d["best_converged_30db"]
        if best:
            require(best["eligible"] is True and best["converged"] is True
                and best["dense"]["min_H2_db"]>=30
                and best["dense"]["min_H3_db"]>=30
                and d["independent_MNA"]["pass"] is True
                and d["independent_MNA"]["probes"]==84,
                "selected candidate not independently RF/MNA eligible")
            ranked.append(d)
        for start in d["starts"]:
            attempts=start["attempts"]
            require(len(attempts)<=2,"v2 stage call count exceeded")
            term.append({"topology":list((d["layout"],d["dtc"],d["graph"])),
               "start":start["start"],"exception":start["exception"],
               "tier_results":[{
                   "tier":t["tier"],"coarse_status":t["coarse"]["status"],
                   "fine_status":t["fine"]["status"],
                   "coarse_nit":t["coarse"]["nit"],"fine_nit":t["fine"]["nit"],
                   "converged":t["converged"],"eligible":t["eligible"],
                   "finite_30db_pass":t["finite_30db_pass"],
                   "IL_db":t["dense"]["worst_IL_db"],
                   "min_H2_db":t["dense"]["min_H2_db"],
                   "min_H3_db":t["dense"]["min_H3_db"],
               } for t in attempts]})
        details.append({
           "layout":d["layout"],"dtc":d["dtc"],"graph":d["graph"],
           "worst_IL_db":best["dense"]["worst_IL_db"] if best else None,
           "min_H2_db":best["dense"]["min_H2_db"] if best else None,
           "min_H3_db":best["dense"]["min_H3_db"] if best else None,
           "MNA_pass":d["independent_MNA"]["pass"] if best else None,
           "eligible_starts":sum(any(x["eligible"] for x in z["attempts"]) for z in d["starts"]),
           "exception_starts":sum(z["exception"] is not None for z in d["starts"])})
    require(len(term)==192,"expected exactly 192 initial starts")
    ranked.sort(key=lambda d:d["best_converged_30db"]["dense"]["worst_IL_db"])
    require(ranked,"missing any verified candidate; treat as explicit aborted experiment")
    # Keep control plus top three distinct electrical+variableC structures.
    wanted=[]
    control=next(d for d in raw if (d["layout"],d["dtc"],d["graph"])==
                 ("best_exp062","two_bridges","original"))
    require(control["best_converged_30db"] is not None,"failed EXP062 reproduce")
    control_il=control["best_converged_30db"]["dense"]["worst_IL_db"]
    require(abs(control_il-BASELINE)<1e-7,"control failed to reproduce EXP062")
    wanted.append(control)
    for d in ranked:
        if d in wanted:continue
        if any((q["graph"],q["dtc"],q["layout"])==
               (d["graph"],d["dtc"],d["layout"]) for q in wanted):continue
        wanted.append(d)
        if len(wanted)>=4:break
    cp_refs=[];validation_refs=[]
    for d in wanted:
        cp=checkpoint(d)
        fname=d["layout"]+"_"+d["dtc"]+"_"+d["graph"]
        c=dump(RUN/"checkpoints"/(fname+".json"),cp)
        cp_refs.append({**ref(c),"candidate_id":cp["candidate_id"],
                        "selection_reason":("pareto" if d is ranked[0]
                            and ranked[0]["best_converged_30db"]["dense"]["worst_IL_db"]<
                            BASELINE-1e-7 else "topology_diversity")})
        v=dump(RUN/"validation"/(fname+"_mna.json"),{
              "experiment_id":"EXP-065","candidate_id":cp["candidate_id"],
              "source_actions_run_id":RUN_ID,"source_execution_sha":execution_sha,
              "grid":{"intervals":28,"dense_points":1001},
              "metrics":cp["metrics"],"independent_9x9_MNA":d["independent_MNA"],
              "pass":True,"finite_grid_not_continuous_proof":True})
        validation_refs.append({**ref(v),"method":"independent_mna","status":"passed"})
    failed=sum(s["exception"] is not None for s in term)
    converged=sum(s["exception"] is None and any(t["converged"] for t in s["tier_results"])
                  for s in term)
    nonconverged=192-failed-converged
    best=ranked[0]
    best_il=best["best_converged_30db"]["dense"]["worst_IL_db"]
    improved=best_il<BASELINE-1e-7
    summary=dump(RUN/"run_summary.json",{
      "schema_version":1,"experiment_id":"EXP-065","phase":"Phase 2",
      "constraint_id":"RF-T008","revision":3,
      "execution_status":"completed","source_actions_run_id":RUN_ID,
      "code_execution_sha":execution_sha,"constraint_sha256":FP,
      "scope":{"fixed_C_layouts":8,"two_DTC_layouts":4,
               "four_L_graphs":3,"joint_topology_cases":96,"initial_starts":192},
      "attempts":{"planned":192,"attempted":192,"converged":converged,
                  "nonconverged":nonconverged,"failed":failed,"not_started":0},
      "selected_candidate_count":len(cp_refs),
      "eligible_layout_count":len(ranked),
      "prior_EXP062_best_IL_db":BASELINE,"best_found_IL_db":best_il,
      "new_global_within_observed_area5p333":improved,
      "best_topology":{"layout":best["layout"],"dtc":best["dtc"],
                       "graph":best["graph"]},
      "all_joint_topology_results":details,
      "all_initial_termination_histories":term,
      "limitations":["96 scoped circuit graphs x2 starts; not full space/global optimum",
          "Zero improvement is meaningful only within tested 96 topologies and local basins",
          "Finite 28x1001 mesh H2/H3 >=30dB, no continuous margin proof",
          "35dB nominal and IL0.3dB targets do not follow from 30dB pass",
          "No Q(f)/SRF/EM/physical simultaneous k/tolerance/Phase3"]})
    dump(SNAP,{
      "schema_version":1,"experiment_id":"EXP-065",
      "phase":"Phase 2","constraint_id":"RF-T008","revision":3,
      "source_actions_run_id":RUN_ID,"area":4+2*(2/3),
      "baseline_EXP062_IL_db":BASELINE,"new_best_IL_db":best_il,
      "best_topology":summary and {"layout":best["layout"],"dtc":best["dtc"],
                                  "graph":best["graph"]},
      "new_pareto_candidate_at_area5p333":improved,
      "note":"Update to merged observed Pareto requires compare lower-cost points and retain historical snapshots; local finite grid.",
      "limitations":["96 selected joint topologies not exhaustive/global proof",
                     "Other costs 3, 3p667, 4p333, 4p667, 6, 6p667 unmodified"]})
    mpath=RUN/"manifest.json"
    m=json.loads(mpath.read_text())
    m["code"]["execution_sha"]=execution_sha
    m["execution"]={"status":"completed","elapsed_seconds":None,"evaluation_count":None}
    m["validation"]={"numerical":"passed","independent":"passed",
        "implementation":"not_run",
        "analysis_grid":{"intervals":28,"points_per_interval":1001,"settings":6},
        "independent_grid":{"intervals":28,"points_per_interval":3,"total":84,
                            "method":"independent 9x9 coupled inductor MNA"}}
    m["evidence"]=[{"path":z["path"],"sha256":z["sha256"]} for z in cp_refs+validation_refs]+[
        ref(summary),ref(RUN/"wide_search_4l2gjm.py"),
        ref(RUN/"source_exp062_area5p333_best.json"),ref(RUN/"README.md")]
    m["limitations"]=["96 joint topology variants x 192 starts; local finite-grid search",
        "Only candidate(s) converged + 30dB + independent 9x9 MNA treated as eligible",
        "Physical validation Q(f)/SRF/EM/tolerances/k and Phase3 not performed"]
    dump(mpath,m)
    spath=RUN/"storage_record.json"
    s=json.loads(spath.read_text())
    s.update(stage="complete",checkpoints=cp_refs,validation_overlays=validation_refs,
             summary=ref(summary),git_readback="passed")
    s["supporting_evidence"]=[
      {**ref(RUN/"wide_search_4l2gjm.py"),"role":"source_snapshot",
       "reason":"Executed multi-axis RF-T008 evaluator, SLSQP, independent MNA source code"},
      {**ref(RUN/"source_exp062_area5p333_best.json"),"role":"source_snapshot",
       "reason":"Pinned complete EXP-062 baseline vector and source SHA used as warm start"},
      {**ref(RUN/"README.md"),"role":"method_note",
       "reason":"Pre-run scope, RF constraints, and unapproved physical work boundaries"}
    ]
    s["limitations"]=["All 96 raw result files in Actions artifacts; curated 4 full representative circuit vectors",
        "192 initial statuses and 96 topology metrics preserved in compact summary.",
        "Not a proof of global Pareto or physical feasibility."]
    dump(spath,s)
    path=ROOT/"data/experiment_index.csv"
    with path.open(newline="") as f:
        rd=csv.DictReader(f);cols=rd.fieldnames;rows=list(rd)
    require(sum(x["experiment_id"]=="EXP-065" for x in rows)==1,"index not unique")
    for x in rows:
        if x["experiment_id"]=="EXP-065":
            x.update(execution_status="completed",
                     numerical_validation="passed",independent_validation="passed")
    out=io.StringIO(newline="")
    w=csv.DictWriter(out,fieldnames=cols,lineterminator="\n")
    w.writeheader();w.writerows(rows)
    path.write_text(out.getvalue())
    print("CURATED_EXP065",RUN_ID,"eligible",len(ranked),
          "best",best_il,"improved",improved,
          "starts",len(term),"converged",converged,"nonconverged",nonconverged,
          "failed",failed,flush=True)

if __name__=="__main__":
    main()

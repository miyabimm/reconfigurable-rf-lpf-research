#!/usr/bin/env python3
"""Independent read-only RF-T008 v3 PR#148-151 evidence review (no optimizer imports).

Audits saved numerical claims, component/Q/area rules, explicit signed k
matrix SPD recomputed independently, six-mode IC fixed/var pairing, original
dense-grid RF summaries, separate MNA solution accuracy/power balance records,
SLSQP termination accounting, EXP-062->065 identity, and observed cost Pareto.

This is independent evidence *inspection* + independently recomputed L SPD,
not a re-run of 28x1001 frequency responses or an independent third solver.
"""
import csv
import json
import math
from pathlib import Path
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
FP="7de08611f8dd15b40fdfb7946e8c93de5796d026641bdca0f12e992962d05fd4"
BANDS={"B71","B12","B28","B13+B14","B26","B8"}
SAMPLES={
 "EXP-062":("a5p333_best","a6_best"),
 "EXP-063":("a3_ground_n1","a367_ground_n1","a433_ground_n1"),
 "EXP-064":("g4g3_b34",),
 "EXP-065":("best_exp062_two_bridges_original",
            "pcb_out_ground_two_bridges_original",
            "bridge_out_two_bridges_original",
            "two_ground_pcb_two_bridges_original")
}
COUNTS={
 "EXP-062":(24,23,1),
 "EXP-063":(24,24,0),
 "EXP-064":(24,24,0),
 "EXP-065":(192,178,14)
}

def read(path):
    return json.loads((ROOT/path).read_text())

def check(condition,msg):
    if not condition:
        raise AssertionError("Independent PR148-151 review: "+msg)

def eq(a,b,tol=1e-9):
    return math.isfinite(a) and math.isfinite(b) and abs(a-b)<=tol

def review_candidate(exp,name):
    base=f"experiments/chatgpt_topology_search/runs/{exp}"
    q=read(f"{base}/checkpoints/{name}.json")
    check(q["experiment_id"]==exp,f"{exp}/{name}: EXP ID")
    check(q["phase"]=="Phase 2" and q["constraint_id"]=="RF-T008",
          f"{exp}/{name}: trial or Phase3")
    p=q["components"]
    ls=[x for x in p if x["type"]=="LQP02HV"]
    gjm=[x for x in p if x["type"]=="GJM01"]
    pcb=[x for x in p if x["type"]=="PCB_PATTERN_C"]
    fix=[x for x in p if x["type"]=="IC_FIXED_C_Q60"]
    var=[x for x in p if x["type"]=="IC_VARIABLE_C_Q35"]
    n=3 if exp=="EXP-063" else 4
    check(len(ls)==n and all(x["Q"]==25 and
          0.4<=x["L_nH"]<=27 for x in ls),f"{exp}/{name}: L/Q/bounds")
    check(all(x["Q"]==80 and 0.02-1e-8<=x["C_pF"]<=100+1e-8 for x in gjm),
          f"{exp}/{name}: GJM/Q/bounds")
    check(len(pcb)<=3 and all(
          x["Q"]==(60 if -1 in x["nodes"] else 40) and
          .02-1e-8<=x["C_pF"]<=(1 if -1 in x["nodes"] else .2)+1e-8
          for x in pcb),f"{exp}/{name}: PCB-C/Q/bounds")
    check(len(fix)==len(var)<=2 and all(x["Q"]==60 and
          (.5 if -1 in x["nodes"] else .2)-1e-8<=x["C_pF"]<=3+1e-8
          for x in fix),f"{exp}/{name}: IC fixed-C/Q/bounds")
    check(all(x["Q"]==35 and any(x["nodes"]==y["nodes"] for y in fix)
          for x in var),f"{exp}/{name}: IC fixed/variable branch pairing")
    check(eq(q["chip_area_units"],n+(2/3)*len(gjm)),
          f"{exp}/{name}: chip-area accounting")
    check(len(q["vector"])==2*n+len(gjm)+len(pcb)+13,
          f"{exp}/{name}: vector dimension")
    vals=q["ic_variable_C_pf_by_setting"]
    check(set(vals)==BANDS and all(len(row)==len(var) and
          all(-1e-8<=x<=3+1e-8 for x in row) for row in vals.values()),
          f"{exp}/{name}: six-mode Cvar placement/bounds")
    check(len(q["couplings"])==n-1 and all(abs(x["k"])<=.1+1e-10
          for x in q["couplings"]),f"{exp}/{name}: physical-row signed k")
    M=np.diag(np.array([x["L_nH"] for x in ls],float))
    names={x["id"]:i for i,x in enumerate(ls)}
    for k in q["couplings"]:
        a,b=(names[x] for x in k["pair"])
        M[a,b]=M[b,a]=k["k"]*math.sqrt(M[a,a]*M[b,b])
    eigen=float(np.linalg.eigvalsh(M)[0])
    check(eigen>0,f"{exp}/{name}: independent 3/4L SPD")
    rf=q["metrics"];mna=q["independent_MNA"]
    saved_eigen=mna.get("L_matrix_min_eigenvalue_nH",
                         mna.get("min_L_matrix_eigenvalue_nH"))
    probes=mna.get("probes",mna.get("probe_points"))
    residual=mna.get("max_power_residual_W",
                     mna.get("max_power_balance_residual_W"))
    check(eq(eigen,saved_eigen,2e-9),f"{exp}/{name}: MNA-L-eigen mismatch")
    check(mna["pass"] is True and probes==84 and
          mna["max_IL_difference_db"]<1e-8 and residual<1e-9,
          f"{exp}/{name}: MNA sampling/accuracy/power balance")
    check(rf["min_H2_db"]>=30 and rf["min_H3_db"]>=30 and
          rf["worst_IL_db"]>=0,f"{exp}/{name}: finite spectrum noncompliant")
    return {"candidate":q["candidate_id"],"area":q["chip_area_units"],
            "IL_db":rf["worst_IL_db"],"min_L_eig_nH":eigen,
            "MNA_probes":probes,"MNA_max_IL_delta_db":mna["max_IL_difference_db"],
            "vector":q["vector"]}

def main():
    with (ROOT/"data/experiment_index.csv").open(newline="") as f:
        rows=list(csv.DictReader(f))
    checkpoints={}
    summaries={}
    for exp,names in SAMPLES.items():
        row=[x for x in rows if x["experiment_id"]==exp]
        check(len(row)==1 and row[0]["execution_status"]=="completed",
              f"{exp}: completed main index must be unique")
        check(row[0]["independent_validation"]=="passed",
              f"{exp}: independent-validation index absent")
        base=f"experiments/chatgpt_topology_search/runs/{exp}"
        manifest=read(f"{base}/manifest.json")
        storage=read(f"{base}/storage_record.json")
        summary=read(f"{base}/run_summary.json")
        summaries[exp]=summary
        check(manifest["phase"]=="Phase 2" and
              manifest["constraints"]["effective_constraint_sha256"]==FP,
              f"{exp}: constraint drift")
        check(manifest["validation"]["independent"]=="passed" and
              manifest["validation"]["numerical"]=="passed",
              f"{exp}: saved validation not passed")
        check(storage["stage"]=="complete" and storage["git_readback"]=="passed",
              f"{exp}: incomplete audited Git evidence")
        planned,conv,non=COUNTS[exp]
        st=summary["attempts"]
        check(st["attempted"]==planned and st["converged"]==conv and
              st["nonconverged"]==non and st["failed"]==0 and
              st["not_started"]==0,
              f"{exp}: termination/attempt totals")
        checkpoints[exp]={name:review_candidate(exp,name) for name in names}
    check(eq(summaries["EXP-064"]["best_found_IL_db"],
             checkpoints["EXP-064"]["g4g3_b34"]["IL_db"],1e-12),
          "EXP-064 new area4 best not checkpointed")
    check(summaries["EXP-064"]["now_nondominated"] is True and
          summaries["EXP-064"]["best_found_IL_db"]<
          summaries["EXP-064"]["lower_cost_best_IL_db"],
          "EXP-064 new cost4 Pareto domination")
    check(eq(summaries["EXP-065"]["best_found_IL_db"],
             checkpoints["EXP-065"]["pcb_out_ground_two_bridges_original"]["IL_db"],1e-12),
          "EXP-065 new best not checkpointed")
    v0=checkpoints["EXP-062"]["a5p333_best"]["vector"]
    v1=checkpoints["EXP-065"]["best_exp062_two_bridges_original"]["vector"]
    check(len(v0)==len(v1) and max(abs(x-y) for x,y in zip(v0,v1))<=1e-12,
          "EXP-062 -> EXP-065 reference seed not reproduced")
    check(eq(checkpoints["EXP-062"]["a5p333_best"]["IL_db"],
             checkpoints["EXP-065"]["best_exp062_two_bridges_original"]["IL_db"],1e-12),
          "EXP-062 -> EXP-065 reference RF not reproduced")
    check(summaries["EXP-065"]["eligible_layout_count"]==93 and
          len(summaries["EXP-065"]["all_joint_topology_results"])==96 and
          len(summaries["EXP-065"]["all_initial_termination_histories"])==192,
          "EXP-065 topology/termination trace incomplete")
    eligible=[x for x in summaries["EXP-065"]["all_joint_topology_results"]
              if x["worst_IL_db"] is not None]
    check(len(eligible)==93 and all(x["MNA_pass"] is True for x in eligible),
          "EXP-065 eligible topology MNA trace")
    # Cross-PR Pareto is audited from the *already-curated* prior snapshot,
    # with EXP-064 cost4 and EXP-065 cost5.333 replaced by final checkpoints.
    previous=read("data/pareto_snapshots/rf_t008_exp062_exp063_exp064_cross_pr_20261020.json")
    pts=[]
    for row in previous["observed_nondominated"]:
        x={"area":row["area_chip_units"],"IL_db":row["worst_IL_db"],"source":row["source"]}
        if eq(x["area"],4.):
            check(eq(x["IL_db"],checkpoints["EXP-064"]["g4g3_b34"]["IL_db"]),
                  "cost4 source mismatch")
        if eq(x["area"],5+1/3):
            x["IL_db"]=checkpoints["EXP-065"]["pcb_out_ground_two_bridges_original"]["IL_db"]
            x["source"]="EXP-065"
        if eq(x["area"],6.):
            check(eq(x["IL_db"],checkpoints["EXP-062"]["a6_best"]["IL_db"]),
                  "cost6 source mismatch")
        pts.append(x)
    pts.sort(key=lambda x:x["area"])
    integrated=read("data/pareto_snapshots/rf_t008_exp062_065_integrated_20261020.json")
    check(integrated["effective_constraint_sha256"]==FP and
          integrated["sampled_starts"]==264 and
          integrated["converged_starts"]==249 and
          integrated["nonconverged_starts"]==15 and
          integrated["failed_starts"]==0 and
          integrated["independent_checkpoint_evidence_reviewed"]==10,
          "integrated cross-PR snapshot provenance/total mismatch")
    saved=integrated["observed_nondominated"]
    check(len(saved)==7, "integrated snapshot must have 7 nondominated points")
    for lhs,rhs in zip(pts,saved):
        check(eq(lhs["area"],rhs["area_chip_units"]) and
              eq(lhs["IL_db"],rhs["worst_IL_db"],1e-10) and
              lhs["source"]==rhs["source"],
              "integrated snapshot diverges from recomputed observed Pareto")
    check(len(integrated["dominated"])==1 and
          eq(integrated["dominated"][0]["best_found_IL_db"],
             previous["dominated_cells"][0]["best_found_IL_db"],1e-10),
          "integrated dominated cell changed")
    check(len(pts)==7 and
          all(pts[i]["IL_db"]>pts[i+1]["IL_db"]+1e-7
              for i in range(len(pts)-1)),
          "area/IL observed nondominated frontier inconsistent")
    check(pts[5]["source"]=="EXP-065" and
          pts[5]["IL_db"]<checkpoints["EXP-062"]["a5p333_best"]["IL_db"]-1e-7,
          "new cost5p333 Pareto improvement missing")
    check(previous["dominated_cells"][0]["best_found_IL_db"]>pts[-1]["IL_db"],
          "cost6p667 domination status changed")
    print("INDEPENDENT_PR148_151_REVIEW_PASS")
    print("CONSTRAINT_FP",FP)
    print("EXP_COUNTS",COUNTS)
    print("TEN_CHECKPOINTS",sum(map(len,checkpoints.values())))
    print("ATTEMPTS",sum(a for a,_,_ in COUNTS.values()),
          "CONVERGED",sum(b for _,b,_ in COUNTS.values()),
          "NOT_CONVERGED",sum(c for _,_,c in COUNTS.values()))
    print("PARETO",json.dumps(pts,ensure_ascii=False,allow_nan=False))
    print("INDEPENDENCE_LIMIT","Saved 84-probe MNA result audited, full MNA calculation not repeated here.")
if __name__=="__main__":main()

#!/usr/bin/env python3
"""Read-only termination audit of EXP-060 immutable GitHub Actions artifacts.
Does not rerun circuits or change RF, optimizer or convergence flags.
"""
import argparse
import collections
import json
from pathlib import Path

def audit(folder):
    cases=sorted(p for p in Path(folder).rglob("*.json") if p.name!="summary.json")
    if len(cases)!=63:
        raise ValueError(f"Expected 63 raw EXP-060 cases, found {len(cases)}")
    result={"source_run_id":39434590336,"source_experiment_id":"EXP-060",
            "provenance":"raw GitHub Actions 63 individual JSON artifacts",
            "cases":len(cases),"starts":0,
            "stage_status":{},"failure_both_stages":{},
            "primary_failure_cause":{},"rescue_invoked":0,
            "by_graph":{},"cases_detail":[]}
    stage_hist={"coarse":collections.Counter(),"fine":collections.Counter(),
                "coarse_rescue":collections.Counter(),"fine_rescue":collections.Counter()}
    pairs=collections.Counter();causes=collections.Counter()
    for f in cases:
        q=json.loads(f.read_text(encoding="utf-8"))
        if q.get("experiment_id")!="EXP-060":
            raise ValueError(f"Wrong experiment: {f}")
        row={"file":f.name,"graph":q["graph"],"k_mode":q["K_mode"],"attempts":[]}
        for a in q["attempts"]:
            result["starts"]+=1
            stat=a["solver"]
            steps=[]
            for stage in ("coarse","fine"):
                t=stat[stage]
                st=int(t["status"])
                stage_hist[stage][st]+=1
                steps.append(st)
                if "rescue" in t:
                    result["rescue_invoked"]+=1
                    stage_hist[stage+"_rescue"][int(t["rescue"]["status"])]+=1
            pairs[tuple(steps)]+=1
            if a["converged"]:cause="both_stages_converged"
            elif 9 in steps or "iteration limit" in (" ".join(stat[x]["message"] for x in ("coarse","fine"))).lower():
                cause="iteration_limit"
            elif 8 in steps:cause="positive_directional_derivative"
            elif 4 in steps:cause="inequality_constraints_incompatible"
            elif 6 in steps:cause="singular_matrix_C"
            elif 5 in steps:cause="singular_matrix_E"
            elif 7 in steps:cause="rank_deficient_equality"
            else:cause="other_nonconvergence"
            causes[cause]+=1
            row["attempts"].append({
                "start":a["start"],"converged":a["converged"],
                "finite_30db_pass":a["finite_30db_pass"],
                "eligible_converged":a["eligible_converged"],
                "cause":cause,
                "coarse":{k:stat["coarse"][k] for k in ("success","status","message","nit","nfev","minimum_sample_slack_db","iteration_limit")},
                "fine":{k:stat["fine"][k] for k in ("success","status","message","nit","nfev","minimum_sample_slack_db","iteration_limit")},
                "worst_IL_db":a["dense"]["worst_IL_db"],
                "min_H2_db":a["dense"]["min_H2_db"],
                "min_H3_db":a["dense"]["min_H3_db"]
            })
        result["cases_detail"].append(row)
    result["stage_status"]={k:dict(v) for k,v in stage_hist.items()}
    result["failure_both_stages"]={"-".join(map(str,k)):v for k,v in pairs.items()}
    result["primary_failure_cause"]=dict(causes)
    def stat_iter(stage,key):
        a=[u["attempts"][i][stage][key] for u in result["cases_detail"] for i in range(len(u["attempts"]))]
        return {"max":max(a),"min":min(a),"median":sorted(a)[len(a)//2],
                "at_or_above_90pct_normal_limit":sum(v>= (216 if stage=="coarse" else 108) for v in a)}
    result["stage_iteration_distribution"]={s:stat_iter(s,"nit") for s in ("coarse","fine")}
    for row in result["cases_detail"]:
        g=row["graph"]
        p=result["by_graph"].setdefault(g,{"attempts":0,"converged":0,
            "eligible":0,"failures":collections.Counter()})
        for a in row["attempts"]:
            p["attempts"]+=1;p["converged"]+=int(a["converged"])
            p["eligible"]+=int(a["eligible_converged"])
            if not a["converged"]:p["failures"][a["cause"]]+=1
    for p in result["by_graph"].values():p["failures"]=dict(p["failures"])
    if result["starts"]!=126:
        raise ValueError("Expected exactly 126 starts")
    return result

if __name__=="__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("--folder",type=Path,required=True)
    ap.add_argument("--out",type=Path,required=True)
    arg=ap.parse_args()
    x=audit(arg.folder)
    arg.out.parent.mkdir(parents=True,exist_ok=True)
    arg.out.write_text(json.dumps(x,ensure_ascii=False,indent=2)+"\n")
    print("TOTAL",x["cases"],x["starts"])
    print("CAUSES",json.dumps(x["primary_failure_cause"],sort_keys=True))
    print("STATUS",json.dumps(x["stage_status"],sort_keys=True))
    print("PAIR",json.dumps(x["failure_both_stages"],sort_keys=True))
    print("ITER",json.dumps(x["stage_iteration_distribution"],sort_keys=True))
    print("RESCUE",x["rescue_invoked"])
    print("GRAPHS",json.dumps(x["by_graph"],sort_keys=True))

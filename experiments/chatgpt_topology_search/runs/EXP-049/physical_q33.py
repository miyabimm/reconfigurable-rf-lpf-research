#!/usr/bin/env python3
"""Phase 2 EXP-049 bounded continuation with public LQW04 nominal range gate.

A supplier's 0.8..33nH LQW04AN_00 *catalog range* is enforced, but this does
not validate per-part 6GHz SRF or Q(f). RF-T006 and original EXP checkpoints
are unmodified. This wrapper reuses original numerical model and solver.
"""
import hashlib, importlib.util, json, os, time
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[4]
folder=ROOT/"experiments/chatgpt_topology_search/runs/EXP-049"
source=folder/"target_1p1.py"
source_sha=hashlib.sha256(source.read_bytes()).hexdigest()
spec=importlib.util.spec_from_file_location("exp049_focused_engine",str(source))
mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
previous_configs=mod.configurations
original_bounds=mod.b.bounds
MIN=0.8;MAX=33.0
OUTPUT=ROOT/"results/EXP-049/physical_q33.json"

def physical_bounds(t):
    bounds=list(original_bounds(t))
    for idx,q in enumerate(t.get("LQ",[25.]*t["nl"])):
        if q==33:
            lo,hi=bounds[idx]
            bounds[idx]=(max(lo,MIN),min(hi,MAX))
    return bounds

def configs():
    original=list(previous_configs())
    high=mod.PREVIOUS["study_results"]
    best4=[s for s in high if s["mandatory_pass_full_grid"]
           and s["chip_L"]==4 and s["Q33_count"]==4]
    best4.sort(key=lambda r:r["full_grid_metrics"]["IL"])
    for s in best4[:3]:
        for ng in (s["chip_GJM"],s["chip_GJM"]+1):
            if ng>10:continue
            for mode in ("ladder_notches","ladder_mixed","ladder_shunt"):
                t=mod.b.spec(4,ng,mode)
                t["LQ"]=[33.]*4
                t["area_units"]=12+ng*2./3.
                for cv in mod.cap_layouts(t)[:5]:
                    for pcb in (
                       t["P"],((1,-1),(2,-1)),
                       ((1,-1),(3,-1)),((1,2),(2,-1))
                    )[:2]:
                        custom=dict(t)
                        custom["V"]=cv
                        custom["P"]=pcb
                        custom["name"]=f"4L_{ng}GJM_{mode}_Cv{cv[0][0]}{cv[1][0]}_PCB{pcb[0][0]}{pcb[1][0]}"
                        original.append((custom,s))
    # Include the 5L earlier trial topologies, but also reroute PCB caps.
    extra=[]
    for t,s in original:
      if t["nl"]!=5 or t["ng"]>8 or t["mode"]!="ladder_notches":continue
      for pcb in (((1,-1),(3,-1)),((2,-1),(4,-1))):
       custom=dict(t)
       custom["P"]=pcb
       custom["name"]=t["name"]+f"_PCB{pcb[0][0]}{pcb[1][0]}"
       extra.append((custom,s))
    original.extend(extra)
    d={}
    for t,s in original:
      key=(t["nl"],t["ng"],t["mode"],t["V"],t["P"],tuple(t.get("LQ",[])))
      if key not in d or s["full_grid_metrics"]["IL"]<d[key][1]["full_grid_metrics"]["IL"]:
       d[key]=(t,s)
    return sorted(d.values(),key=lambda z:(z[0]["area_units"],z[1]["full_grid_metrics"]["IL"]))

def main():
    mod.b.bounds=physical_bounds
    mod.configurations=configs
    mod.OUTPUT=OUTPUT
    mod.START=time.monotonic()
    mod.MAXSEC=float(os.environ.get("EXP049_PHYSICAL_MAX_SECONDS","425"))
    mod.main()
    obj=json.loads(OUTPUT.read_text("utf-8"))
    for point in obj["selected_per_area"]:
      q=point["lq_assumptions"]
      for li,qi in zip(point["vector"][:point["chip_L"]],q):
        if qi==33 and not (MIN-1e-9<=li<=MAX+1e-9):
          raise ValueError(f"Q33 inductance {li}nH outside supplier series range")
    obj["LQW04AN_00_min_nH"]=MIN
    obj["LQW04AN_00_max_nH"]=MAX
    obj["range_reference"]="https://www.murata.com/ja-jp/products/inductor/chip/overview/lineup/rf1"
    obj["numerical_script_sha256"]=source_sha
    obj["part_level_SRF_Qf_test"]="not_run"
    obj["limitations"].append(
       "The 0.8..33nH published series range is not proof of a purchasable exactly tuned part, Q33 at every frequency or SRF beyond 6GHz.")
    OUTPUT.write_text(json.dumps(obj,ensure_ascii=False,indent=2,allow_nan=False)+"\n")
    best=obj["best_full_grid"]
    print("PHYSICAL_Q33_FINAL",json.dumps({"range_nH":[MIN,MAX],"target_met":obj["target_met"],
       "best_area":best["area_cost"] if best else None,
       "best_metrics":best["full_grid_metrics"] if best else None,
       "best_L_nH":best["vector"][:best["chip_L"]] if best else None,
       "independent":obj["independent_validation"]}),flush=True)
if __name__=="__main__":main()

#!/usr/bin/env python3
"""EXP-049 Phase-2 high-Q chip-area step-up (RF-F003 allowed LQW04 Q33).

Continues, without altering, EXP-049's fixed Q25 selected and SLSQP refinement
artifacts. Q33 per-chip area is 3 vs Q25 LQP02HV area 1. No nonformal relaxation.
"""
import hashlib
import importlib.util
import itertools
import json
import os
import time
from pathlib import Path
import numpy as np
from scipy.optimize import minimize
ROOT=Path(__file__).resolve().parents[4]
P=ROOT/"experiments/chatgpt_topology_search/runs/EXP-049"
OUT=ROOT/"results/EXP-049/highq.json"
f=importlib.util.spec_from_file_location("exp049_q_engine",str(P/"optimize.py"))
b=importlib.util.module_from_spec(f);f.loader.exec_module(b)
REF=P/"continuation.json"
SOURCE=json.loads(REF.read_text("utf-8"))
SOURCE_SHA=hashlib.sha256(REF.read_bytes()).hexdigest()
START=time.monotonic()
BUDGET=float(os.environ.get("EXP049_HIGHQ_MAX_SECONDS","370"))
RNG=np.random.default_rng(490062)
calls=0

def q_study_options():
 pool=[r for r in SOURCE["best_per_area"] if r["mandatory_pass_full_grid"]]
 # Include 4L/5L options with a good IL baseline rather than blindly using max area.
 pool=sorted(pool,key=lambda r:r["full_grid_metrics"]["IL"])
 sources=[]
 for x in pool:
  if x["chip_L"] in (4,5) and x["area_cost"] <= 10.00001 and len(sources)<6:
   sources.append(x)
 opts=[]
 for s in sources:
  n=s["chip_L"];ls=np.array(s["vector"][:n])
  order=list(np.argsort(ls)[::-1])
  ixset=set()
  for k in (1,2,3,n):
   if k>n:continue
   candidates=[tuple(sorted(order[:k]))]
   if k==1:candidates+=[(0,),(n-1,)]
   if k==2:candidates+=[tuple(sorted((0,n-1)))]
   for subset in candidates:
    if subset in ixset:continue
    ixset.add(subset)
    top=b.spec(s["chip_L"],s["chip_GJM"],s["topology"].split("_",2)[2])
    top["LQ"]=[33 if j in subset else 25 for j in range(n)]
    top["Q33_indices"]=subset
    top["area_units"]=s["area_cost"]+2*len(subset)
    opts.append((top,s))
 return sorted(opts,key=lambda t:(t[0]["area_units"],t[1]["full_grid_metrics"]["IL"],
                                  len(t[0]["Q33_indices"])))

def shortlist(x,m,t,origin,attempt):
 r=b.represent(x,t,m,origin,attempt)
 r["source_exp049_topology"]=t["name"]
 r["Q33_positions"]=list(t["Q33_indices"])
 r["Q25_count"]=t["nl"]-len(t["Q33_indices"])
 r["Q33_count"]=len(t["Q33_indices"])
 r["lq_assumptions"]=list(t["LQ"])
 r["physical_LQW04_spec_check"]="not_run"
 return r

def main():
 global calls
 cfg=q_study_options()
 coarse=b.grids(8,100)
 records=[];bycost={};selected=None
 print("HIGHQ_CONFIGS",len(cfg),"source_SHA",SOURCE_SHA,
       "remaining_time",BUDGET,flush=True)
 for t,src in cfg:
  if time.monotonic()-START>BUDGET:break
  initial=np.array(src["vector"],float)
  x0=np.array([np.clip(v,lo,hi) for v,(lo,hi) in zip(initial,b.bounds(t))])
  # Compare base Q25 at same topology with extra Q33; actual area changes as recorded.
  best=[None];best_unconstrained=[None];count=[0]
  memo={"x":None,"m":None}
  def metric(x):
   global calls
   if memo["x"] is None or not np.array_equal(memo["x"],x):
    calls+=1;count[0]+=1;mm=b.metrics(x,t,coarse)
    memo["x"]=x.copy();memo["m"]=mm
    if mm is not None:
     if best_unconstrained[0] is None or b.objective(mm)<best_unconstrained[0][0]:
      best_unconstrained[0]=(b.objective(mm),x.copy(),mm)
     if b.valid(mm) and (best[0] is None or mm["IL"]<best[0][2]["IL"]):
      best[0]=(b.objective(mm),x.copy(),mm)
   return memo["m"]
  def fun(x):
   mm=metric(x)
   return mm["IL"] if mm is not None else 1e8
  constr=[
   {"type":"ineq","fun":lambda x: -100 if metric(x) is None else metric(x)["H2"]-30.025},
   {"type":"ineq","fun":lambda x: -100 if metric(x) is None else metric(x)["H3"]-30.025},
   {"type":"ineq","fun":lambda x: -100 if metric(x) is None else metric(x)["W"]-20.15},
  ]
  success=False
  try:
   fit=minimize(fun,x0,method="SLSQP",bounds=b.bounds(t),constraints=constr,
       options={"maxiter":70,"ftol":5e-5})
   success=bool(fit.success)
  except (ValueError,OverflowError,np.linalg.LinAlgError) as e:
   fit=type("Fail",(),{"message":str(e),"success":False})()
  # Penalty Powell can rescue a locally infeasible SLSQP.
  if best[0] is None and (time.monotonic()-START)<BUDGET:
   seed=best_unconstrained[0][1] if best_unconstrained[0] else x0
   def penalty(x):
    mm=metric(x)
    return b.objective(mm)
   minimize(penalty,seed,method="Powell",bounds=b.bounds(t),
      options={"maxfev":800,"xtol":0.005,"ftol":0.0005})
  current=best[0]
  records.append(dict(cost=t["area_units"],nl=t["nl"],ng=t["ng"],
     Q33_positions=t["Q33_indices"],topology=t["name"],calls=count[0],
     solver_converged=success,
     best_screen=current[2] if current else None,
     best_any=best_unconstrained[0][2] if best_unconstrained[0] else None))
  print("QSCAN",round(t["area_units"],6),t["name"],t["Q33_indices"],
        "eval",count[0],"feasible",b.brief(current[2]) if current else "none",flush=True)
  if current is None:continue
  area_key=str(round(t["area_units"],6))
  point=shortlist(current[1],current[2],t,"higher_chip_L_Q33",len(records))
  existing=bycost.get(area_key)
  if existing is None or current[2]["IL"]<existing["grid_metrics"]["IL"]:
   bycost[area_key]=point
  # Always cross-check 1.1 dB on full grid before early stopping.
  if current[2]["IL"]<=1.13:
   fine=b.grids(1001,1)
   mm=b.metrics(current[1],t,fine)
   if b.valid(mm) and mm["IL"]<=1.1:
    selected=point
    print("Q33_TARGET_FINE",b.brief(mm),"area",t["area_units"],flush=True)
    break
 print("HIGHQ_FINAL_FULL_GRID_CHECK",len(bycost),"area levels",flush=True)
 fine=b.grids(1001,1);completed=[]
 best=None
 for key,point in sorted(bycost.items(),key=lambda x:float(x[0])):
  t=b.spec(point["chip_L"],point["chip_GJM"],point["topology"].split("_",2)[2])
  t["LQ"]=point["lq_assumptions"]
  x=np.array(point["vector"])
  mm=b.metrics(x,t,fine)
  point["full_grid_metrics"]=mm
  point["mandatory_pass_full_grid"]=b.valid(mm)
  point["IL_target_1p1_met"]=bool(b.valid(mm) and mm["IL"]<=1.1)
  completed.append(point)
  print("DENSE_HIGHQ",key,point["topology"],point["Q33_positions"],
    b.brief(mm),"PASS",b.valid(mm),flush=True)
  if b.valid(mm) and (best is None or mm["IL"]<best["full_grid_metrics"]["IL"]):
   best=point
 validation=None
 if best:
  t=b.spec(best["chip_L"],best["chip_GJM"],best["topology"].split("_",2)[2])
  t["LQ"]=best["lq_assumptions"]
  validation=b.independent(np.array(best["vector"]),t,b.grids(3,750))
  print("INDEPENDENT_HIGHQ",json.dumps(validation),flush=True)
 output={"experiment_id":"EXP-049","phase":"Phase 2","status":"completed_highQ_bounded_continuation",
         "trial":"RF-T006","formal_base":"RF-F003","target_IL_db":1.1,
         "source_continuation_sha256":SOURCE_SHA,
         "effective_constraints_sha256":b.constraint_fingerprint(b.POLICY),
         "execution_sha":os.environ.get("GITHUB_SHA"),
         "seed":490062,"attempts":len(records),"evaluations":calls,
         "elapsed_seconds":time.monotonic()-START,
         "q33_area_cost_increment_per_replacement":2,
         "assumed_Q_LQP02HV":25,"assumed_Q_LQW04":33,
         "study_results":completed,"best_full_grid":best,
         "target_met":bool(best and best["full_grid_metrics"]["IL"]<=1.1),
         "independent_validation":validation,
         "attempt_records":records,
         "limitations":["Q33 is a formal RF-F003 assumed constant-Q model; not demonstrated part-number Q(f).",
           "LQW04 inductance range/SRF for each chosen nH value not verified.",
           "No continuous frequency extrema, EM, tolerances, physical PCB/IC layout or actual measurement.",
           "Only finite topologies and subsets, no global optimality or infeasibility proof.",
           "Full RF-F003 28x1001 segment and 6x3001 wideband grids rerun for per-area winners."]}
 OUT.parent.mkdir(parents=True,exist_ok=True)
 OUT.write_text(json.dumps(output,indent=2,ensure_ascii=False,allow_nan=False)+"\n",encoding="utf-8")
 print("HIGHQ_FINAL",json.dumps({"target_met":output["target_met"],
  "area":best["area_cost"] if best else None,
  "metrics":best["full_grid_metrics"] if best else None,
  "evaluations":calls,"independent":validation}),flush=True)

if __name__=="__main__":main()

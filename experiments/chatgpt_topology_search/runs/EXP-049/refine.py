#!/usr/bin/env python3
"""EXP-049 continuation: warm-start IL-limited area escalation from verified EXP-049 checkpoints.

Only consumes the immutable stage-1 selected.json; writes a separate concise
continuation.json with its own execution SHA. No rewriting old manifests/data.
"""
import hashlib
import importlib.util
import json
import os
import time
from pathlib import Path
import numpy as np
from scipy.optimize import minimize

ROOT=Path(__file__).resolve().parents[4]
P=ROOT/"experiments/chatgpt_topology_search/runs/EXP-049"
ORIG=P/"selected.json"
OUT=ROOT/"results/EXP-049/continuation.json"
spec=importlib.util.spec_from_file_location("exp049_area",str(P/"optimize.py"))
b=importlib.util.module_from_spec(spec)
spec.loader.exec_module(b)
old=json.loads(ORIG.read_text("utf-8"))
CHECKSUM=hashlib.sha256(ORIG.read_bytes()).hexdigest()
RNG=np.random.default_rng(490061)
START=time.monotonic()
MAX_SECONDS=float(os.environ.get("EXP049_REFINE_MAX_SECONDS","480"))
CANDIDATES=[]
evaluations=0

def topologies():
 c=[]
 # Begin at the previous verified area-8 winner; add one GJM01 at a time.
 for ng in (6,7,8,9):
  c.extend([b.spec(4,ng,mode) for mode in
            ("ladder_notches","ladder_shunt","ladder_mixed")])
 for nl,counts in ((5,(5,6,7,8)),(6,(4,5,6,7)),(7,(5,6))):
  for ng in counts:
   c.extend([b.spec(nl,ng,mode) for mode in
             ("ladder_notches","ladder_shunt","ladder_mixed")])
 return sorted([x for x in c if x["area_units"]<=11.0],
               key=lambda q:(q["area_units"],q["nl"],q["mode"]))

def source_for(t):
 options=[]
 for v in old["best_per_area"]:
  if v["chip_L"]==t["nl"] and v["topology"].endswith(t["mode"]):
   options.append(v)
 options.extend(z for z in CANDIDATES if
                z["chip_L"]==t["nl"] and z["topology"].endswith(t["mode"])
                and b.valid(z["grid_metrics"]))
 return min(options,key=lambda r:r.get("full_grid_metrics",r["grid_metrics"])["IL"]) if options else None

def extend_seed(t, oldone):
 if oldone is None:
  return b.seed(t,"filter")
 n=t["nl"];ng=t["ng"]
 prev_ng=oldone["chip_GJM"];prev_n=oldone["chip_L"]
 if prev_n!=n:
  return b.seed(t,"filter")
 x=np.asarray(oldone["vector"],float)
 L=x[:n];Cg=x[n:n+prev_ng];Cp=x[n+prev_ng:n+prev_ng+2]
 k=x[n+prev_ng+2:n+prev_ng+2+n-1];Cv=x[-12:]
 if ng>=prev_ng:
  add=np.full(ng-prev_ng,0.012)
  Cg=np.r_[Cg,add]
 else:Cg=Cg[:ng]
 new=np.r_[L,Cg,Cp,k,Cv]
 return np.array([np.clip(v,lo,hi) for v,(lo,hi) in zip(new,b.bounds(t))])

def solve(t,x0,label,grid,maxfev):
 global evaluations
 best_feasible=[None];best_any=[None];calls=[0]
 memo={"x":None,"m":None}
 def met(x):
  if memo["x"] is None or not np.array_equal(x,memo["x"]):
   global evaluations
   evaluations+=1;calls[0]+=1
   mm=b.metrics(x,t,grid)
   memo["x"]=x.copy();memo["m"]=mm
   if mm is not None:
    v=b.objective(mm)
    if best_any[0] is None or v<best_any[0][0]:
     best_any[0]=(v,np.array(x).copy(),mm)
    if b.valid(mm) and (best_feasible[0] is None or mm["IL"]<best_feasible[0][2]["IL"]):
     best_feasible[0]=(v,np.array(x).copy(),mm)
  return memo["m"]
 def fun(x):
  m=met(x)
  return 1e7 if m is None else m["IL"]
 constraints=[
  {"type":"ineq","fun":lambda x: -1e4 if met(x) is None else met(x)["H2"]-30.02},
  {"type":"ineq","fun":lambda x: -1e4 if met(x) is None else met(x)["H3"]-30.02},
  {"type":"ineq","fun":lambda x: -1e4 if met(x) is None else met(x)["W"]-20.20},
 ]
 try:
  opt=minimize(fun,x0,method="SLSQP",bounds=b.bounds(t),constraints=constraints,
            options={"maxiter":maxfev,"ftol":8e-5})
 except (ValueError,RuntimeError,OverflowError) as exc:
  opt=type("Result",(),{"success":False,"message":str(exc),"x":x0})()
 # Recover feasible probe anywhere on SLSQP path, not solely the final x.
 m=met(np.asarray(opt.x))
 candidate=best_feasible[0]
 print("SLSQP",t["name"],label,"evals",calls[0],
       "feasible",b.brief(candidate[2]) if candidate else "not_found",
       "final",b.brief(m) if m else "invalid",flush=True)
 return candidate, {"topology":t["name"],"origin":label,"calls":calls[0],
                    "converged":bool(opt.success),"message":str(opt.message),
                    "feasible":candidate[2] if candidate else None,
                    "best_objective":best_any[0][2] if best_any[0] else None}

def main():
 global evaluations
 if old["experiment_id"]!="EXP-049" or old["trial"]!="RF-T006":
  raise RuntimeError("Unexpected EXP-049 input")
 coarse=b.grids(8,100)
 configs=topologies()
 print("EX049_REFINE",len(configs),"configs",len(old["best_per_area"]),
       "input_sha",CHECKSUM,flush=True)
 per_area={}
 records=[]
 # Keep original verified stage-1 area winners; extra area cannot invalidate them.
 for rec in old["best_per_area"]:
  if rec["mandatory_pass_full_grid"]:
   area=str(round(rec["area_cost"],6))
   per_area[area]=dict(rec,provenance="stage1_verified")
 hit=False
 for t in configs:
  if time.monotonic()-START>MAX_SECONDS:break
  area=t["area_units"]
  if (t["ng"]>=8 and t["nl"]<=4):pass
  prev=source_for(t)
  seeds=[]
  if prev is not None:
   seeds.append(("continuation",extend_seed(t,prev)))
   xscaled=extend_seed(t,prev)
   # Global LC scale: lower series L while raising capacitors, seeking lower Q25 loss.
   xscaled[:t["nl"]]*=.75
   xscaled[t["nl"]:t["nl"]+t["ng"]]*=1.25
   seeds.append(("lower_L",np.array([np.clip(v,lo,hi) for v,(lo,hi) in zip(xscaled,b.bounds(t))])))
  else:
   seeds.append(("filter",b.seed(t,"filter")))
  if t["mode"]=="ladder_notches":
   seeds.append(("EXP048",b.seed(t,"EXP048")))
  for kind,seed in seeds:
   if time.monotonic()-START>MAX_SECONDS:break
   result,record=solve(t,seed,kind,coarse,90)
   records.append(record)
   if result is None:continue
   candidate=b.represent(result[1],t,result[2],kind,len(records))
   CANDIDATES.append(candidate)
   current=per_area.get(str(round(area,6)))
   if current is None or candidate["grid_metrics"]["IL"]<current.get("full_grid_metrics",current["grid_metrics"])["IL"]:
    per_area[str(round(area,6))]=candidate
   if candidate["grid_metrics"]["IL"]<=1.15:
    fine=b.grids(1001,1)
    fine_m=b.metrics(result[1],t,fine)
    if b.valid(fine_m) and fine_m["IL"]<=1.1:
     hit=True
     print("TARGET_HIT",t["name"],b.brief(fine_m),flush=True)
     break
  if hit:break
 print("REFINEMENT_GRID_VERIFICATION",len(per_area),"areas",flush=True)
 fine=b.grids(1001,1)
 measured=[]
 for key,one in sorted(per_area.items(),key=lambda item:float(item[0])):
  if time.monotonic()-START>MAX_SECONDS+90:break
  if one.get("provenance")=="stage1_verified":
   measured.append(one);continue
  t=next(z for z in configs if z["name"]==one["topology"])
  mm=b.metrics(np.array(one["vector"]),t,fine)
  one["full_grid_metrics"]=mm
  one["mandatory_pass_full_grid"]=b.valid(mm)
  one["IL_target_1p1_met"]=bool(b.valid(mm) and mm["IL"]<=1.1)
  if not b.valid(mm):
   # Do not replace an independently verified stage-1 winner with a coarse false pass.
   fallback=next((z for z in old["best_per_area"]
                  if abs(z["area_cost"]-one["area_cost"])<1e-8 and z["mandatory_pass_full_grid"]),None)
   if fallback is not None:
    measured.append(dict(fallback,provenance="stage1_verified_fallback"))
   else:measured.append(one)
  else:measured.append(one)
  print("AREA_REFINE",key,one["topology"],b.brief(mm),"valid",b.valid(mm),flush=True)
 feasible=[z for z in measured if z["mandatory_pass_full_grid"]]
 best=min(feasible,key=lambda z:z["full_grid_metrics"]["IL"]) if feasible else None
 independent=None
 if best:
  t=next((q for q in configs if q["name"]==best["topology"]),None)
  if t is None:t=b.spec(best["chip_L"],best["chip_GJM"],best["topology"].split("_",2)[2])
  independent=b.independent(np.array(best["vector"]),t,b.grids(3,750))
  print("INDEPENDENT",json.dumps(independent),flush=True)
 result={"experiment_id":"EXP-049","phase":"Phase 2","status":"completed_bounded_continuation",
         "trial":"RF-T006","base":"RF-F003","target_IL_db":1.1,
         "source_selected_sha256":CHECKSUM,
         "effective_constraints_sha256":b.constraint_fingerprint(b.POLICY),
         "run_code_sha":os.environ.get("GITHUB_SHA"),
         "seed":490061,"attempts":len(records),"evaluations":evaluations,
         "elapsed_seconds":time.monotonic()-START,
         "best_per_area":measured,"best_full_grid":best,
         "target_met":bool(best and best["full_grid_metrics"]["IL"]<=1.1),
         "independent_validation":independent,
         "screen_grid":{"RF_band_points_per_segment":8,"wide_step_MHz":100},
         "verification_grid":{"RF_band_points_per_segment":1001,
                              "wide_step_MHz":1,"wide_points":18006},
         "attempt_records":records,
         "limitations":["Best found only, no global optimality or infeasibility proof",
                        "Only selected ladder/shunt/mixed branches and 4–7 L chip topology families",
                        "Continuing EXP-049 without rewriting its original selected.json/manifest.json",
                        "Independent MNA 114 probes, not every point; constant Q; real SRF not modeled",
                        "Continuous frequency, PCB footprint, tolerance and EM not validated"]}
 OUT.parent.mkdir(parents=True,exist_ok=True)
 OUT.write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)+"\n",encoding="utf-8")
 print("REFINE_FINAL",json.dumps({"found":result["target_met"],"area":best["area_cost"] if best else None,
      "metrics":best["full_grid_metrics"] if best else None,"attempts":len(records),
      "evals":evaluations,"independent":independent}),flush=True)

if __name__=="__main__":main()

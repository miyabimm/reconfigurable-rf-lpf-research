#!/usr/bin/env python3
"""EXP-049 Phase-2 high-Q local topology + tuning continuation.

F003/T006 unchanged. Trial LQW04 Q33 model; genuine manufacturer Q(f), SRF
and part-level inductance compatibility not checked. Separate immutable record.
"""
import hashlib, importlib.util, json, math, os, time, itertools
from pathlib import Path
import numpy as np
from scipy.optimize import minimize

ROOT=Path(__file__).resolve().parents[4]
BASE=ROOT/"experiments/chatgpt_topology_search/runs/EXP-049"
OUTPUT=ROOT/"results/EXP-049/target_1p1.json"
engine_spec=importlib.util.spec_from_file_location("exp049_engine",str(BASE/"optimize.py"))
b=importlib.util.module_from_spec(engine_spec);engine_spec.loader.exec_module(b)
HFILE=BASE/"highq.json"
PREVIOUS=json.loads(HFILE.read_text("utf-8"))
PRESHA=hashlib.sha256(HFILE.read_bytes()).hexdigest()
RNG=np.random.default_rng(490063)
START=time.monotonic()
MAXSEC=float(os.environ.get("EXP049_TARGET_MAX_SECONDS","460"))
EVALS=0
RECORDS=[]
CANDIDATES=[]
TARGET=1.1
QN=33
def cap_layouts(t):
    n=t["nl"]
    base=[(1,-1),(n-1,-1)]
    # Important to explore placement, not only add large number of expensive GJMs.
    moves=[tuple(base),((2,-1),(n-1,-1)),((1,-1),(n-2,-1)),
           ((2,-1),(n-2,-1)),((1,-1),(2,-1)),
           ((n-2,-1),(n-1,-1)),((1,2),(n-1,-1)),
           ((1,-1),(n-2,n-1))]
    return list(dict.fromkeys(moves))
def configurations():
    prior=PREVIOUS["study_results"]
    high=[r for r in prior if r["mandatory_pass_full_grid"]]
    high.sort(key=lambda r:r["full_grid_metrics"]["IL"])
    original=PREVIOUS["best_full_grid"]
    allq=[r for r in high if r["Q33_count"]==r["chip_L"]]
    # Require warm feasible basis; can increase area by adding GJM or moving Cv.
    choices=[]
    for seed in ([original]+allq[:5]):
      n=seed["chip_L"];g=seed["chip_GJM"]
      if n!=5:continue
      for ng in range(max(6,g),min(10,g+2)+1):
        for mode in ("ladder_notches","ladder_shunt","ladder_mixed"):
         t=b.spec(n,ng,mode)
         t["LQ"]=[33.]*n
         t["area_units"]=3*n+(2./3.)*ng
         # Position perturbation: same 2 independent Cv branches.
         for cv in cap_layouts(t) if ng==6 and mode=="ladder_notches" else cap_layouts(t)[:4]:
          layout=dict(t)
          layout["V"]=cv
          layout["name"]=f"{n}L_{ng}GJM_{mode}_Cv{''.join(str(x[0]) for x in cv)}"
          choices.append((layout,seed))
    # Add 6L all-Q33 family as a separate area increment.
    for ng in (5,6,7):
     for mode in ("ladder_notches","ladder_mixed"):
      t=b.spec(6,ng,mode);t["LQ"]=[33.]*6
      t["area_units"]=18+(2./3.)*ng
      choices.append((t,original))
    # Deduplicate equivalent layout while retaining best source seed.
    d={}
    for t,s in choices:
      k=(t["nl"],t["ng"],t["mode"],t["V"],tuple(t["LQ"]))
      if k not in d or s["full_grid_metrics"]["IL"]<d[k][1]["full_grid_metrics"]["IL"]:
       d[k]=(t,s)
    return sorted(d.values(),key=lambda z:(z[0]["area_units"],z[1]["full_grid_metrics"]["IL"]))
def start_vector(t,seed):
  old=np.asarray(seed["vector"],float)
  n=t["nl"];pg=seed["chip_GJM"];ng=t["ng"];pn=seed["chip_L"]
  if n!=pn:
    # Repartition the largest L in the 5L source into two series L, preserving total.
    L=np.r_[old[:pn],max(.4,old[:pn].mean()/2)]
    k=np.r_[old[pn+pg+2:pn+pg+2+pn-1],0.]
  else:
    L=old[:n]
    k=old[n+pg+2:n+pg+2+n-1]
  c=old[pn:pn+pg]
  extra=np.full(max(0,ng-pg),0.03)
  G=np.r_[c[:min(pg,ng)],extra]
  P=old[pn+pg:pn+pg+2]
  Cv=old[-12:]
  vec=np.r_[L,G,P,k,Cv]
  assert len(vec)==len(b.bounds(t)),(len(vec),len(b.bounds(t)))
  return np.array([np.clip(val,lo,hi) for val,(lo,hi) in zip(vec,b.bounds(t))])
def tune(t,source,grid,stage):
  global EVALS
  x0=start_vector(t,source)
  nm=source["full_grid_metrics"]["IL"]
  saved=[None]
  memo={"x":None,"m":None}
  calls=[0]
  def met(x):
   global EVALS
   if memo["x"] is None or not np.array_equal(memo["x"],x):
    EVALS+=1;calls[0]+=1
    m=b.metrics(x,t,grid);memo["x"]=x.copy();memo["m"]=m
    if b.valid(m) and (saved[0] is None or m["IL"]<saved[0][1]["IL"]):
     saved[0]=(np.array(x).copy(),m)
   return memo["m"]
  def fun(x):
   m=met(x)
   return 1e7 if m is None else m["IL"]
  cc=[
    {"type":"ineq","fun":lambda x: -100 if met(x) is None else met(x)["H2"]-30.04},
    {"type":"ineq","fun":lambda x: -100 if met(x) is None else met(x)["H3"]-30.04},
    {"type":"ineq","fun":lambda x: -100 if met(x) is None else met(x)["W"]-20.08},
  ]
  if t["nl"]==5 and t["ng"]==source["chip_GJM"] and t["V"]==tuple(map(tuple,source["Cv_edges"])) and t["mode"]==source["topology"].split("_",2)[2]:
    m=b.metrics(x0,t,grid)
    if b.valid(m):saved[0]=(x0.copy(),m)
  if saved[0] is None:
   # Short Powell recovery for changed Cv/GJM placement before constrained SLSQP.
   def penalty(x):
    m=met(x)
    return b.objective(m)
   minimize(penalty,x0,method="Powell",bounds=b.bounds(t),
             options={"maxfev":360,"xtol":0.004,"ftol":0.001})
  seed=saved[0][0] if saved[0] else x0
  try:
   fit=minimize(fun,seed,method="SLSQP",bounds=b.bounds(t),constraints=cc,
       options={"maxiter":65,"ftol":1e-5})
   converged=bool(fit.success);reason=str(fit.message)
  except (ValueError,RuntimeError,np.linalg.LinAlgError) as exc:
   converged=False;reason=str(exc)
  row={"topology":t["name"],"area":t["area_units"],"source_area":source["area_cost"],
       "stage":stage,"evaluations":calls[0],"solver_converged":converged,
       "solver_reason":reason,"feasible":saved[0][1] if saved[0] else None}
  return saved[0],row
def package(t,result,origin):
 x,m=result
 rec=b.represent(x,t,m,origin,len(RECORDS))
 rec["chip_L_series"]=["LQW04_Q33"]*t["nl"]
 rec["lq_assumptions"]=t["LQ"]
 rec["area_cost"]=t["area_units"]
 rec["Cv_edges"]=t["V"]
 return rec
def main():
 assert PREVIOUS["trial"]=="RF-T006" and PREVIOUS["target_IL_db"]==TARGET
 shortlist={}
 coarse=b.grids(8,100)
 choices=configurations()
 print("T006_TARGET_CONFIGS",len(choices),"SHA",PRESHA,flush=True)
 for ti,(t,source) in enumerate(choices):
  if time.monotonic()-START>MAXSEC:break
  result,row=tune(t,source,coarse,f"search_{ti}")
  RECORDS.append(row)
  print("TUNE",ti,t["name"],"area",round(t["area_units"],4),
        "eval",row["evaluations"],"found",b.brief(result[1]) if result else "none",flush=True)
  if result:
   p=package(t,result,f"EXP049_highq:{source['topology']}")
   k=str(round(t["area_units"],6))
   if k not in shortlist or p["grid_metrics"]["IL"]<shortlist[k]["point"]["grid_metrics"]["IL"]:
    shortlist[k]={"point":p,"config":t}
   # Early acceptance only on exact full-grid validation.
   if result[1]["IL"]<1.14:
    dense=b.grids(1001,1)
    m=b.metrics(result[0],t,dense)
    if b.valid(m) and m["IL"]<=TARGET:
      print("T006_TARGET_FULL_GRID_REACHED",t["name"],m,flush=True)
      break
 full=b.grids(1001,1)
 graded=[]
 best=None
 for key,item in sorted(shortlist.items(),key=lambda z:float(z[0])):
  t=item["config"];p=item["point"]
  m=b.metrics(np.array(p["vector"]),t,full)
  p["full_grid_metrics"]=m
  p["mandatory_pass_full_grid"]=b.valid(m)
  p["target_met"]=bool(b.valid(m) and m["IL"]<=TARGET)
  graded.append(p)
  print("DENSE_TARGET",key,t["name"],b.brief(m),"pass",b.valid(m),flush=True)
  if b.valid(m) and (best is None or m["IL"]<best["full_grid_metrics"]["IL"]):
   best=p
 validation=None
 if best:
  t=next((z["config"] for z in shortlist.values()
          if z["point"]["topology"]==best["topology"]),None)
  if t is not None:
   validation=b.independent(np.array(best["vector"]),t,b.grids(3,750))
   print("MNA_TARGET",validation,flush=True)
 result={
    "experiment_id":"EXP-049","phase":"Phase 2","status":"completed_bounded_highq_topology_continuation",
    "trial":"RF-T006","source_highq_sha256":PRESHA,"target_IL_db":TARGET,
    "effective_constraints_sha256":b.constraint_fingerprint(b.POLICY),
    "execution_sha":os.environ.get("GITHUB_SHA"),"attempted":len(RECORDS),
    "evaluations":EVALS,"elapsed_seconds":time.monotonic()-START,
    "screen_points_per_RF_region":8,"screen_wide_step_MHz":100,
    "full_points_per_RF_region":1001,"full_wide_step_MHz":1,
    "selected_per_area":graded,"best_full_grid":best,"target_met":bool(best and best["target_met"]),
    "independent_validation":validation,"round_summary":RECORDS,
    "limitations":["Local bounded SLSQP/Powell and limited capacitor-placement choices only.",
                   "Constant Q33 across 0–6 GHz is a simplified model; SRF/Q(f) are unverified.",
                   "High-Q LQW04 series chosen abstractly; no part number or exact available inductance verified.",
                   "Continuous extrema and tolerance/EM/physical PCB area unverified.",
                   "Full-grid checks for selected per-area winners; 114-point independent branch-MNA only."]
 }
 OUTPUT.parent.mkdir(parents=True,exist_ok=True)
 OUTPUT.write_text(json.dumps(result,indent=2,ensure_ascii=False,allow_nan=False)+"\n")
 print("T006_TARGET_FINAL",json.dumps({"target_met":result["target_met"],
  "best_area":best["area_cost"] if best else None,
  "best":best["full_grid_metrics"] if best else None,
  "attempted":len(RECORDS),"evaluations":EVALS,
  "independent":validation}),flush=True)
if __name__=="__main__":main()

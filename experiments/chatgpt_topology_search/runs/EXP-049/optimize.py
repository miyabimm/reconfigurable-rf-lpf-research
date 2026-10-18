#!/usr/bin/env python3
"""EXP-049: escalating-area RF-T006 4L/5L/6L local topology search.

Real executed numerical search, not a claim of physical feasibility or a proof
of global Pareto optimality. Authoritative EXP-049 main reservation required.
Only selected per-area evidence is preserved; no intermediate iteration dumps.
"""
import csv
import hashlib
import json
import math
import os
import subprocess
import time
from pathlib import Path
import numpy as np
from scipy.optimize import minimize
from src.lpf.constraint_versions import load_constraint, constraint_fingerprint
from src.lpf.port_parasitics import get_two_port_s, s_to_abcd

ROOT=Path(__file__).resolve().parents[4]
CASE=("B71","B12","B28","B13+B14","B26","B8")
POLICY=load_constraint("RF-T006",allow_trial=True)
SRC=ROOT/"experiments/chatgpt_topology_search/runs/EXP-048/selected.json"
HIST=ROOT/"experiments/chatgpt_topology_search/runs/EXP-047/area5p333_g2_independent_28x1001_20261017.json"
OUT=ROOT/"results/EXP-049/selected.json"
OLD=json.loads(SRC.read_text("utf-8"))
FORMAL=json.loads(HIST.read_text("utf-8"))
BASE=np.array(OLD["selected"]["vector_23"],float)
BANDS=list(csv.DictReader((ROOT/"data/bands.csv").open(encoding="utf-8",newline="")))
SEED=49006
RNG=np.random.default_rng(SEED)
started=time.monotonic()
eval_count=0
STOP_AFTER_SUCCESS=True
TOL=1e-12

def spec(nl,ng,mode):
 """GJM paths and PCB paths; sorted chip area increases in steps of 2/3."""
 if mode.startswith("T"):
  assert nl==4
  L=((0,1),(1,3),(1,4),(1,2));port=(0,2);nn=5
  cg=[(1,-1),(4,-1)]
  extra=[(0,1),(1,2),(1,3),(1,4)]
  if mode=="T_bridge":
   cg+=extra[:ng-2]
  elif mode=="T_mixed":
   cg += [(3,-1)] + extra[:ng-3]
  else:raise ValueError(mode)
  cv=((3,-1),(2,-1));pcb=((2,-1),(3,-1))
 else:
  L=tuple((i,i+1) for i in range(nl));port=(0,nl);nn=nl+1
  cv=((1,-1),(nl-1,-1))
  # PCB pattern C have physical 0.02..0.20pF and do not carry primary matching.
  pcb=((2,-1),(nl-2,-1)) if nl>=5 else ((2,-1),(3,-1))
  if mode=="ladder_notches":
   cg=[(i,i+1) for i in range(nl)]
   cg=(cg+[(i,-1) for i in range(1,nl)]+[(0,-1),(nl,-1)])[:ng]
  elif mode=="ladder_shunt":
   cg=[(i,-1) for i in range(1,nl)]+[(0,-1),(nl,-1)]
   cg=(cg+[(i,i+1) for i in range(nl)])[:ng]
  elif mode=="ladder_mixed":
   cg=[]
   for i in range(nl):
    cg.append((i,-1) if i%2 else (i,i+1))
   cg=(cg+[(i,-1) for i in range(1,nl)]+[(i,i+1) for i in range(nl)])[:ng]
  else:raise ValueError(mode)
 return dict(nl=nl,ng=ng,mode=mode,nn=nn,ports=port,L=tuple(L),
   G=tuple(cg),P=tuple(pcb),V=tuple(cv),name=f"{nl}L_{ng}GJM_{mode}",
   area_units=nl+2*ng/3, count_pcb=len(pcb))

def configs():
 c=[]
 for ng in (3,4,5,6):
  for mode in ("T_bridge","T_mixed","ladder_notches","ladder_shunt","ladder_mixed"):
   c.append(spec(4,ng,mode))
 for nl,ng in ((5,3),(5,4),(5,5),(6,3),(6,4)):
  for mode in ("ladder_notches","ladder_shunt","ladder_mixed"):
   c.append(spec(nl,ng,mode))
 return sorted(c,key=lambda t:(t["area_units"],t["nl"],t["ng"],t["mode"]))

def bounds(t):
 # User RF-T006: LQP02HV 0.4..27nH Q25; GJM <=100pF Q80,
 # PCB C 0.02..0.2pF Q40; independent Cv <=3pF Q35.
 n,k=t["nl"],t["ng"]
 return [(0.4,27)]*n+[(0.005,8.)]*k+[(0.02,0.2)]*2+[(-0.1,0.1)]*(n-1)+[(0.,3.)]*12

def seed(t,seed_type):
 n,k=t["nl"],t["ng"]
 src=np.array(FORMAL["vector"],float)
 if seed_type=="EXP048":
  l=np.r_[BASE[:4],*[[] for _ in range(0)]]; ks=BASE[8:11]
  if n>4:
   # Partition the shortest L to preserve initial current path scale.
   l=np.r_[l, np.full(n-4,5.)]
   ks=np.r_[ks,np.zeros(n-4)]
  gjm=np.r_[BASE[4:6],np.full(k-2,0.60)]
  pcb=BASE[6:8]
  cv=BASE[11:]
 elif seed_type=="EXP047":
  l=np.r_[src[:4],np.full(n-4,5.)]
  ks=np.r_[src[8:11],np.zeros(n-4)]
  gjm=np.r_[src[4:6],np.full(k-2,1.10)]
  pcb=src[6:8]
  cv=src[11:].reshape(6,3)[:,[0,2]].reshape(-1)
 elif seed_type=="filter":
  # Small-L/loss-optimized ladder origin; targeted 3-6GHz LC rejection.
  l=np.full(n,6.5)
  ks=np.zeros(n-1)
  gjm=np.resize(np.array([1.6,1.15,0.9,0.65,0.48,0.33]),k)
  pcb=np.array([0.1,0.12])
  cv=np.array([0.55,1.25,0.45,1.0,0.55,.85,.5,.72,.4,.53,.15,.3])
 else:raise ValueError(seed_type)
 return np.clip(np.r_[l,gjm,pcb,ks,cv], *np.array(bounds(t)).T) if False else np.array(
     [min(hi,max(lo,v)) for v,(lo,hi) in zip(np.r_[l,gjm,pcb,ks,cv],bounds(t))])

def grids(nb=4,sw=150):
 f=[];cases=[];kind=[]
 for ic,case in enumerate(CASE):
  for b in BANDS:
   if b["case"]!=case:continue
   for ff in np.linspace(float(b["low_mhz"]),float(b["high_mhz"]),nb):
    f.append(ff);cases.append(ic);kind.append(b["region"])
  for ff in np.arange(3000,6000.01,sw):
   f.append(ff);cases.append(ic);kind.append("extra")
 f=np.asarray(f,float);cases=np.asarray(cases,int);kind=np.array(kind)
 P={}
 for label in ("input_parasitic","output_parasitic"):
  P[label]=np.array([s_to_abcd(get_two_port_s(POLICY,label,float(ff)*1e6))
                     for ff in f])
 return dict(f=f,case=cases,kind=kind,inp=P["input_parasitic"],out=P["output_parasitic"])

def params(x,t):
 n,k=t["nl"],t["ng"]
 return (x[:n],x[n:n+k],x[n+k:n+k+2],
         x[n+k+2:n+k+2+n-1],x[n+k+2+n-1:].reshape(6,2))

def transfer(x,t,g):
 n=t["nl"];nn=t["nn"];l,gjm,pcb,k,cv=params(x,t)
 om=2e6*np.pi*g["f"];npoints=len(om)
 # Chip L offdiagonal M=j*k*sqrt(L_i L_(i+1)), Q25 assumed constant.
 H=np.diag(l/25+1j*l).astype(complex)
 for i,coupling in enumerate(k):
  mut=1j*coupling*np.sqrt(l[i]*l[i+1])
  H[i,i+1]+=mut;H[i+1,i]+=mut
 try:inv=np.linalg.inv(H)
 except np.linalg.LinAlgError:return None
 inc=np.zeros((nn,n))
 for j,(u,v) in enumerate(t["L"]):
  inc[u,j]+=1;inc[v,j]-=1
 Y=np.broadcast_to((inc@inv@inc.T)[None,:,:]/(om[:,None,None]*1e-9),
                   (npoints,nn,nn)).copy()
 edges=t["G"]+t["P"]+t["V"]
 vals=np.column_stack((np.broadcast_to(gjm,(npoints,len(gjm))),
                       np.broadcast_to(pcb,(npoints,2)),cv[g["case"]]))
 qualities=np.r_[np.full(len(gjm),80.),[40.,40.],[35.,35.]]
 for j,(u,v) in enumerate(edges):
  q=qualities[j]
  s=om*vals[:,j]*1e-12/(1+1/q**2)
  y=s/q+1j*s
  Y[:,u,u]+=y
  if v>=0:
   Y[:,v,v]+=y;Y[:,u,v]-=y;Y[:,v,u]-=y
 input_node,output_node=t["ports"]
 p=[input_node,output_node];ids=[a for a in range(nn) if a not in p]
 try:
  block=Y[:,ids,:][:,:,ids]
  link=Y[:,ids,:][:,:,p]
  W=np.linalg.solve(block,link)
  YY=Y[:,p,:][:,:,p]-Y[:,p,:][:,:,ids]@W
  a,b,c,d=YY[:,0,0],YY[:,0,1],YY[:,1,0],YY[:,1,1]
  if np.any(np.abs(c)<1e-30):return None
  det=a*d-b*c
  Lmat=np.stack((np.stack((-d/c,-1/c),axis=-1),
                 np.stack((-det/c,-a/c),axis=-1)),axis=-2)
  chain=g["inp"]@Lmat@g["out"]
  den=chain[:,0,0]*(60-40j)+chain[:,0,1]+50*(chain[:,1,0]*(60-40j)+chain[:,1,1])
  gain=12000/np.abs(den)**2
  if not np.all(np.isfinite(gain)) or np.any(gain<=0):return None
  return -10*np.log10(gain)
 except (np.linalg.LinAlgError,FloatingPointError,OverflowError,ValueError):return None

def metrics(x,t,g):
 attenuation=transfer(x,t,g)
 if attenuation is None:return None
 kinds=g["kind"]
 return {"IL":float(max(attenuation[np.isin(kinds,("UL","DL"))])),
         "H2":float(min(attenuation[kinds=="H2"])),
         "H3":float(min(attenuation[kinds=="H3"])),
         "W":float(min(attenuation[kinds=="extra"])),
         "wide_worst_freq_MHz":float(g["f"][np.where(kinds=="extra")[0][np.argmin(attenuation[kinds=="extra"])]]),
         "wide_worst_setting":CASE[g["case"][np.where(kinds=="extra")[0][np.argmin(attenuation[kinds=="extra"])]]]}
def valid(m):
 return m is not None and m["H2"]>=30 and m["H3"]>=30 and m["W"]>=20
def objective(m):
 if m is None:return 1e8
 # Hard constraints 30/30/20 target padded by 0.10 for grid refinement.
 return (m["IL"]+12*max(0,30.10-m["H2"])**2
         +12*max(0,30.10-m["H3"])**2
         +7*max(0,20.25-m["W"])**2)

def independent(x,t,points):
 """Independent explicit nodal plus one current unknown per coupled inductor."""
 n=t["nl"];nn=t["nn"];l,gjm,pcb,k,cv=params(x,t)
 grid=points
 baseline=transfer(x,t,grid)
 errors=[];balances=[]
 for j,(ff,ic) in enumerate(zip(grid["f"],grid["case"])):
  om=2e6*np.pi*ff
  Z=np.diag(l/25+1j*l).astype(complex)
  for m,mut in enumerate(k):
   z=1j*mut*np.sqrt(l[m]*l[m+1]);Z[m,m+1]+=z;Z[m+1,m]+=z
  inc=np.zeros((nn,n))
  for h,(u,v) in enumerate(t["L"]):inc[u,h]+=1;inc[v,h]-=1
  tc=grid["inp"][j];to=grid["out"][j];load=60-40j
  Din=tc[0,1]+50*tc[1,1]
  Ys=(tc[0,0]+50*tc[1,0])/Din;Is=1/Din
  Dout=to[0,0]*load+to[0,1]
  Yl=(to[1,0]*load+to[1,1])/Dout
  A=np.zeros((nn+n,nn+n),complex);A[:nn,nn:]=inc;A[nn:,:nn]=inc.T
  A[nn:,nn:]=-om*1e-9*Z
  cb=np.r_[gjm,pcb,cv[ic]]
  Q=np.r_[np.full(len(gjm),80.),40.,40.,35.,35.]
  ss=om*cb*1e-12/(1+1/Q**2);YY=ss/Q+1j*ss
  for (u,v),y in zip(t["G"]+t["P"]+t["V"],YY):
   A[u,u]+=y
   if v>=0:A[v,v]+=y;A[u,v]-=y;A[v,u]-=y
  pi,po=t["ports"]
  A[pi,pi]+=Ys;A[po,po]+=Yl
  rhs=np.zeros(nn+n,complex);rhs[pi]=Is
  r=np.linalg.solve(A,rhs);vv=r[:nn];ii=r[nn:]
  pout=60*abs(vv[po]/Dout)**2
  loss=-10*np.log10(pout/.005)
  errors.append(abs(loss-baseline[j]))
  iint=Is-Ys*vv[pi]
  vext=tc[0,0]*vv[pi]+tc[0,1]*iint
  iext=tc[1,0]*vv[pi]+tc[1,1]*iint
  reflected=abs(1-100*iext)**2/200
  inloss=(vext*np.conj(iext)).real-(vv[pi]*np.conj(iint)).real
  outloss=(vv[po]*np.conj(Yl*vv[po])).real-pout
  Lloss=sum(om*1e-9*l[z]/25*abs(ii[z])**2 for z in range(n))
  Closs=0
  for (u,v),y in zip(t["G"]+t["P"]+t["V"],YY):
   voltage=vv[u] if v<0 else vv[u]-vv[v]
   Closs+=y.real*abs(voltage)**2
  balances.append(abs(.005-(pout+reflected+inloss+outloss+Lloss+Closs)))
 return dict(points=len(grid["f"]),method=f"independent {nn+n}x{nn+n} explicit branch-current MNA",
             max_abs_db_disagreement=max(errors),max_power_balance_W=max(balances),
             passed=bool(max(errors)<1e-8 and max(balances)<1e-10))

def represent(x,t,met,source,round_id):
 return dict(area_cost=t["area_units"],chip_L=t["nl"],chip_GJM=t["ng"],
             pcb_C=t["count_pcb"],variable_C=2,topology=t["name"],
             l_edges=t["L"],GJM_edges=t["G"],PCB_edges=t["P"],Cv_edges=t["V"],
             port_nodes=t["ports"],l_q=25,fixed_GJM_q=80,pcb_C_q=40,cv_q=35,
             parameter_order="L_nH, GJM_C_pF, PCB_C_pF, adjacent_k, Cv0/Cv1 per B71 B12 B28 B13+B14 B26 B8",
             vector=np.asarray(x).tolist(),grid_metrics=met,
             selected_from=source,round_id=round_id,
             mandatory_pass_on_screen_grid=valid(met))
def brief(m):
 return f"IL {m['IL']:.4f}, H2 {m['H2']:.3f}, H3 {m['H3']:.3f}, W {m['W']:.3f}" if m else "invalid"

def main():
 global eval_count
 source_sha=hashlib.sha256(SRC.read_bytes()).hexdigest()
 # An immutable main reservation must exist before any numerical run.
 reservation=subprocess.check_output(
   ["git","show","origin/main:data/experiment_number_registry.csv"],
    cwd=ROOT,text=True)
 assert any(row.startswith("EXP-049,reserved,MasayaTakagi,") and ",RF-T006," in row for row in reservation.splitlines())
 assert POLICY["active_constraint_id"]=="RF-T006"
 assert POLICY["components"]["IC_VARIABLE_C"]["max_branches_principle"]==2
 print("EXP-049 reservation PASS source_sha",source_sha,
       "constraint_sha",constraint_fingerprint(POLICY),flush=True)
 coarse=grids(4,150)
 allcfg=configs()
 records=[];winners={};candidate_count=0;best_overall=None;stop_area=None
 levels=sorted(set(c["area_units"] for c in allcfg))
 print("area_levels",levels,"topologies",len(allcfg),flush=True)
 max_duration=float(os.getenv("EXP049_MAX_SECONDS","600"))
 for cost in levels:
  if time.monotonic()-started>max_duration:break
  options=[x for x in allcfg if x["area_units"]==cost]
  print("AREA",round(cost,6),"templates",len(options),flush=True)
  per_cost=None;winner=None
  for top in options:
   if time.monotonic()-started>max_duration:break
   inputs=["EXP048","EXP047","filter"] if top["mode"] in ("T_bridge","ladder_notches") else ["filter","EXP048"]
   for origin in inputs:
    if time.monotonic()-started>max_duration:break
    x0=seed(top,origin)
    trace=[0];local_best=[None];local_feasible=[None]
    def f(x):
     global eval_count
     eval_count+=1;trace[0]+=1
     m=metrics(x,top,coarse)
     if m is None:return 1e8
     score=objective(m)
     if local_best[0] is None or score<local_best[0][0]:
      local_best[0]=(score,np.array(x).copy(),m)
     if valid(m) and (local_feasible[0] is None or m["IL"]<local_feasible[0][2]["IL"]):
      local_feasible[0]=(score,np.array(x).copy(),m)
     return score
    # Separately bound every coordinate; never exceed RF-F003 component limits.
    opt=minimize(f,x0,method="Powell",bounds=bounds(top),
             options={"maxfev":1650,"xtol":0.004,"ftol":0.0006})
    candidate_count+=1
    trial=local_feasible[0]
    result={"area_cost":cost,"topology":top["name"],"origin":origin,
            "evaluations":trace[0],"solver_success":bool(opt.success),
            "reason":str(opt.message),
            "best_screen":local_best[0][2] if local_best[0] else None,
            "feasible_screen":trial[2] if trial else None}
    records.append(result)
    if trial is not None:
     record=represent(trial[1],top,trial[2],origin,candidate_count)
     if per_cost is None or trial[2]["IL"]<per_cost["grid_metrics"]["IL"]:
      per_cost=record
    print("try",top["name"],origin,"evals",trace[0],
          "best",brief(local_best[0][2]) if local_best[0] else "none",
          "feasible",brief(trial[2]) if trial else "none",flush=True)
  if per_cost is not None:
   winners[str(round(cost,6))]=per_cost
   if best_overall is None or per_cost["grid_metrics"]["IL"]<best_overall["grid_metrics"]["IL"]:
    best_overall=per_cost
   print("AREA_BEST",round(cost,6),brief(per_cost["grid_metrics"]),flush=True)
   # Do not stop at coarse 1.1; verify densely before accepting.
   if per_cost["grid_metrics"]["IL"]<=1.1:
    fine=grids(1001,1)
    topo=next(z for z in allcfg if z["name"]==per_cost["topology"])
    mm=metrics(np.array(per_cost["vector"]),topo,fine)
    print("TARGET_FINE",brief(mm),flush=True)
    if valid(mm) and mm["IL"]<=1.1:
     stop_area=cost
     break
  else:
   print("AREA_BEST",round(cost,6),"NO_FEASIBLE_COARSE",flush=True)
 # Evaluate every area winner at full explicit 28028+18006 point grid.
 fine=grids(1001,1)
 result_list=[]
 best_verified=None
 for key,one in sorted(winners.items(),key=lambda kv:float(kv[0])):
  top=next(z for z in allcfg if z["name"]==one["topology"])
  x=np.array(one["vector"])
  mm=metrics(x,top,fine)
  one["full_grid_metrics"]=mm
  one["mandatory_pass_full_grid"]=valid(mm)
  one["IL_target_1p1_met"]=bool(valid(mm) and mm["IL"]<=1.1)
  result_list.append(one)
  print("DENSE",key,one["topology"],brief(mm),"PASS",valid(mm),flush=True)
  if valid(mm) and (best_verified is None or mm["IL"]<best_verified["full_grid_metrics"]["IL"]):
   best_verified=one
 # Independent MNA on selected full-grid feasible candidate.
 validation=None
 if best_verified:
  top=next(z for z in allcfg if z["name"]==best_verified["topology"])
  # Preserve 28 segments at endpoints/midpoints + six*five wideband probes.
  probes=grids(3,750)
  x=np.array(best_verified["vector"])
  validation=independent(x,top,probes)
  print("INDEPENDENT",json.dumps(validation),flush=True)
 # Baseline EXP-048 conserved as immutable input, never mistaken for a new fit.
 summary={"experiment_id":"EXP-049","status":"completed_local_exploration",
          "phase":"Phase 2","trial":"RF-T006","base_formal":"RF-F003",
          "target_IL_db":1.1,"mandatory_H2_db":30,"mandatory_H3_db":30,
          "mandatory_3to6GHz_db":20,"effective_constraints_sha256":constraint_fingerprint(POLICY),
          "origin_EXP048_selected_sha256":source_sha,
          "seed":SEED,"source_execution_sha":os.environ.get("GITHUB_SHA"),
          "explored_area_levels":levels,"searched_topology_templates":len(allcfg),
          "completed_starts":candidate_count,"evaluations":eval_count,
          "elapsed_seconds":time.monotonic()-started,
          "best_per_area":result_list,
          "best_full_grid":best_verified,
          "independent_MNA":validation,
          "target_met":bool(best_verified and best_verified["full_grid_metrics"]["IL"]<=1.1),
          "stopped_early_after_target_area":stop_area,
          "round_summary":records,
          "verification":{"legacy_28_intervals_samples_per_segment":1001,
             "legacy_evaluations":28028,"extra_3001_per_setting":3001,
             "extra_evaluations":18006,"independent_probe_count":len(probes["f"]) if validation else 0},
          "limitations":["Bounded local optimization; no global infeasibility or optimality proof.",
                         "Only a finite set of 4L/5L/6L capacitive topologies searched.",
                         "Constant-Q lumped inductors: practical 3-6GHz SRF and Q(f) unverified.",
                         "Continuous-frequency extrema, EM, tolerance, yield, packaging and physical footprints not validated.",
                         "Coarse screening differs from complete finite grids; full-grid scores are separately reported."]}
 OUT.parent.mkdir(parents=True,exist_ok=True)
 OUT.write_text(json.dumps(summary,indent=2,ensure_ascii=False,allow_nan=False)+"\n",encoding="utf-8")
 print("EXP049_FINAL",json.dumps({"target_met":summary["target_met"],
       "completed_starts":candidate_count,"evaluations":eval_count,
       "best":best_verified["full_grid_metrics"] if best_verified else None,
       "area":best_verified["area_cost"] if best_verified else None,
       "independent":validation}),flush=True)
if __name__=="__main__":main()

#!/usr/bin/env python3
"""EXP-048: bounded Phase-2 RF-T006 experiment; no automatic formal promotion.

EXP-047 area-5 1/3 4L/2GJM/2PCB/2Cv source is read byte-for-byte.
Optimization changes component values and tests several same-count capacitor
rewirings. Fixed external S2Ps and six-setting source/load transducer power
are evaluated identically to RF-F003. Output: one curated JSON, no iter dumps.
"""
import csv
import hashlib
import json
import math
import os
import time
from pathlib import Path
import numpy as np
from scipy.optimize import minimize
from src.lpf.constraint_versions import load_constraint, constraint_fingerprint
from src.lpf.port_parasitics import get_two_port_s, s_to_abcd

ROOT=Path(__file__).resolve().parents[4]
SOURCE=ROOT/"experiments/chatgpt_topology_search/runs/EXP-047/area5p333_g2_independent_28x1001_20261017.json"
OUT=ROOT/"results/EXP-048/selected.json"
SETTINGS=("B71","B12","B28","B13+B14","B26","B8")
EDGES_L=((0,1),(1,3),(1,4),(1,2))
TOPOLOGIES={
 "original": (((0,1),(4,-1),(1,2),(0,3)),((3,-1),(1,2))),
 "drop_input_bridge": (((1,-1),(4,-1),(1,2),(0,3)),((3,-1),(1,2))),
 "drop_fixed_bridges": (((1,-1),(4,-1),(2,-1),(3,-1)),((3,-1),(1,2))),
 "all_shunt": (((1,-1),(4,-1),(2,-1),(3,-1)),((3,-1),(2,-1))),
 "output_shunt": (((0,1),(4,-1),(2,-1),(3,-1)),((3,-1),(2,-1))),
 "input_shunt": (((1,-1),(4,-1),(1,2),(3,-1)),((3,-1),(2,-1))),
}
Q=np.array([80,80,40,40,35,35],float)
INC=np.zeros((5,4),float)
for j,(u,v) in enumerate(EDGES_L):
 INC[u,j]+=1;INC[v,j]-=1
BANDS=list(csv.DictReader((ROOT/"data/bands.csv").open(newline="",encoding="utf-8")))
POLICY=load_constraint("RF-T006",allow_trial=True)
SOURCE_PAYLOAD=json.loads(SOURCE.read_text("utf-8"))
V=np.array(SOURCE_PAYLOAD["vector"],float)
X0=np.r_[V[:11],V[11:].reshape(6,3)[:,[0,2]].reshape(-1)]
assert len(X0)==23 and SOURCE_PAYLOAD["condition"]=="RF-F003"
SOURCE_SHA=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
SEED=48006
RNG=np.random.default_rng(SEED)
BND=[(.4,27)]*4+[(0.02,5),(0.02,5),(.02,.2),(.02,.2)]+[(-.1,.1)]*3+[(0,3)]*12
calls=0
started=time.monotonic()

def grid(nband=4,wide_step=100):
 fs=[]; settings=[]; roles=[]
 for ci,s in enumerate(SETTINGS):
  for item in BANDS:
   if item["case"]!=s: continue
   role=item["region"]
   f0=float(item["low_mhz"]);f1=float(item["high_mhz"])
   for f in np.linspace(f0,f1,nband):
    fs.append(f);settings.append(ci);roles.append(role)
  for f in np.arange(3000,6001,wide_step):
   fs.append(float(f));settings.append(ci);roles.append("wide")
 fs=np.array(fs,float);settings=np.array(settings,int);roles=np.array(roles)
 return dict(f=fs,case=settings,role=roles,pre=external(fs,"input_parasitic"),
             post=external(fs,"output_parasitic"))
def external(freq,role):
 # Strictly cache S2Ps through RF-F003's verified loader; use original RI linear interpolation.
 return np.array([s_to_abcd(get_two_port_s(POLICY,role,float(f)*1e6)) for f in freq])
def eval_vector(x,topo,g):
 cf,var=TOPOLOGIES[topo]
 l=x[:4];k=x[8:11]
 H=np.diag(l/25+1j*l).astype(complex)
 for (a,b),z in zip(((0,1),(1,3),(3,2)),k):
  H[a,b]+=1j*z*np.sqrt(l[a]*l[b]);H[b,a]+=1j*z*np.sqrt(l[a]*l[b])
 try:
  inv=np.linalg.inv(H)
 except np.linalg.LinAlgError: return None
 # Impedance in ohms = omega*1e-9*(L/Q+jL). Conductance in siemens.
 F=g["f"];omega=2e6*np.pi*F
 Y=(INC@inv@INC.T)[None,:,:]/(omega[:,None,None]*1e-9)
 Y=np.array(np.broadcast_to(Y,(len(F),5,5)),copy=True)
 cap=np.column_stack([np.broadcast_to(x[4:8],(len(F),4)),
                      x[11:].reshape(6,2)[g["case"]]])
 for j,(u,v) in enumerate(cf+var):
  q=Q[j];s=omega*cap[:,j]*1e-12/(1+1/(q*q))
  y=(s/q+1j*s)
  Y[:,u,u]+=y
  if v>=0:
   Y[:,v,v]+=y;Y[:,u,v]-=y;Y[:,v,u]-=y
 ids=[1,3,4];p=[0,2]
 try:
  W=np.linalg.solve(Y[:,ids][:,:,ids],Y[:,ids][:,:,p])
  YY=Y[:,p][:,:,p]-Y[:,p][:,:,ids]@W
  a,b,c,d=YY[:,0,0],YY[:,0,1],YY[:,1,0],YY[:,1,1]
  if np.any(np.abs(c)<1e-25):return None
  det=a*d-b*c
  L=np.stack((np.stack((-d/c,-1/c),axis=-1),
              np.stack((-det/c,-a/c),axis=-1)),axis=-2)
  chain=g["pre"]@L@g["post"]
  zl=60-40j;den=chain[:,0,0]*zl+chain[:,0,1]+50*(chain[:,1,0]*zl+chain[:,1,1])
  gain=12000/np.abs(den)**2
  if not np.all(np.isfinite(gain)) or np.any(gain<=0):return None
  attenuation=-10*np.log10(gain)
  return attenuation
 except (np.linalg.LinAlgError,FloatingPointError,ValueError):return None
def metrics(x,topo,g):
 v=eval_vector(x,topo,g)
 if v is None:return None
 role=g["role"]
 out={"worst_il_db":float(max(v[np.isin(role,["UL","DL"])])),
      "min_h2_db":float(min(v[role=="H2"])),
      "min_h3_db":float(min(v[role=="H3"])),
      "min_3to6_db":float(min(v[role=="wide"]))}
 for r in ("UL","DL","H2","H3","wide"):
  q=v[role==r];out["samples_"+r]=int(q.size)
 stop=np.where(role=="wide")[0]
 idx=stop[np.argmin(v[stop])]
 out["worst_3to6_MHz"]=float(g["f"][idx])
 out["worst_3to6_setting"]=SETTINGS[g["case"][idx]]
 return out
def score(m):
 if m is None:return 1e7
 # Feasibility first; IL secondary. Objective does not redefine nominal requirements.
 return (0.15*m["worst_il_db"]
  +2.0*max(0,30.10-m["min_h2_db"])**2
  +2.0*max(0,30.10-m["min_h3_db"])**2
  +1.0*max(0,20.20-m["min_3to6_db"])**2)
def fmt(m):
 return (f"IL={m['worst_il_db']:.4f} H2={m['min_h2_db']:.3f} "
         f"H3={m['min_h3_db']:.3f} 3-6={m['min_3to6_db']:.3f}")
def candidate_status(m):
 return (m is not None and m["min_h2_db"]>=30 and m["min_h3_db"]>=30
         and m["min_3to6_db"]>=20)
def independently_verify(x,topo):
 """Explicit 9x9 nodal + L branch-current MNA; separate from Schur nodal Y."""
 cf,var=TOPOLOGIES[topo]
 cases=[];frequency=[]
 for b in BANDS:
  a,z=float(b["low_mhz"]),float(b["high_mhz"])
  for ff in (a,(a+z)/2,z):
   cases.append(SETTINGS.index(b["case"]));frequency.append(ff)
 for case in range(6):
  for ff in (3000.,3066.,4000.,5000.,6000.):
   cases.append(case);frequency.append(ff)
 freq=np.asarray(frequency);case=np.asarray(cases)
 g={"f":freq,"case":case,"role":np.full(len(freq),"wide"),
    "pre":external(freq,"input_parasitic"),
    "post":external(freq,"output_parasitic")}
 reference=eval_vector(x,topo,g)
 errors=[];residuals=[];losses=[]
 for j,(fc,setting) in enumerate(zip(freq,case)):
  omega=2e6*np.pi*fc; L=x[:4]
  ZLmat=np.diag(L/25+1j*L).astype(complex)
  for (a,b),k in zip(((0,1),(1,3),(3,2)),x[8:11]):
   mutual=1j*k*np.sqrt(L[a]*L[b]);ZLmat[a,b]+=mutual;ZLmat[b,a]+=mutual
  tin,tout=g["pre"][j],g["post"][j];load=60-40j
  Din=tin[0,1]+50*tin[1,1]
  Yin=(tin[0,0]+50*tin[1,0])/Din
  Is=1/Din
  Dout=tout[0,0]*load+tout[0,1]
  Yout=(tout[1,0]*load+tout[1,1])/Dout
  capacitors=np.r_[x[4:8],x[11:].reshape(6,2)[setting]]
  si=omega*capacitors*1e-12/(1+1/Q**2)
  Yc=si/Q+1j*si
  A9=np.zeros((9,9),complex)
  for (u,v),y in zip(cf+var,Yc):
   A9[u,u]+=y
   if v>=0:
    A9[v,v]+=y;A9[u,v]-=y;A9[v,u]-=y
  A9[0,0]+=Yin;A9[2,2]+=Yout
  A9[:5,5:]=INC;A9[5:,:5]=INC.T
  A9[5:,5:]=-omega*1e-9*ZLmat
  rhs=np.zeros(9,complex);rhs[0]=Is
  solution=np.linalg.solve(A9,rhs)
  voltage=solution[:5];current=solution[5:]
  pout=load.real*abs(voltage[2]/Dout)**2
  attenuation=-10*np.log10(pout/.005)
  errors.append(abs(attenuation-reference[j]))
  in_current=Is-Yin*voltage[0]
  vext=tin[0,0]*voltage[0]+tin[0,1]*in_current
  iext=tin[1,0]*voltage[0]+tin[1,1]*in_current
  reflected=abs(1-100*iext)**2/200
  inloss=(vext*np.conj(iext)).real-(voltage[0]*np.conj(in_current)).real
  outloss=(voltage[2]*np.conj(Yout*voltage[2])).real-pout
  Lloss=sum(omega*1e-9*L[h]/25*abs(current[h])**2 for h in range(4))
  Closs=0
  for (u,v),y in zip(cf+var,Yc):
   z=voltage[u] if v<0 else voltage[u]-voltage[v]
   Closs+=y.real*abs(z)**2
  terms=(pout,reflected,inloss,outloss,Lloss,Closs)
  losses.append(min(terms))
  residuals.append(abs(.005-sum(terms)))
 result={"independent_method":"explicit 5-node plus 4-L-branch 9x9 MNA",
         "points":len(freq),"legacy_28_region_endpoint_midpoint":84,
         "additional_3to6_probes":30,
         "max_abs_attenuation_disagreement_db":max(errors),
         "max_power_balance_residual_W":max(residuals),
         "min_constituent_power_W":min(losses),
         "passed":bool(max(errors)<1e-8 and max(residuals)<1e-10
                       and min(losses)>=-1e-12)}
 return result

def main():
 global calls
 print("EXP-048 reservation verified on main before execution; Phase 2 RF-T006",flush=True)
 print("sha_policy",constraint_fingerprint(POLICY),"sha_source",SOURCE_SHA,flush=True)
 coarse=grid(4,100)
 base=metrics(X0,"original",coarse)
 print("baseline coarse",fmt(base),"score",score(base),flush=True)
 assert abs(base["worst_il_db"]-SOURCE_PAYLOAD["grid"]["verified"]["worst"])<0.10
 best={"score":score(base),"x":X0.copy(),"topology":"original","metrics":base,
       "stage":"original_unoptimized"}
 records=[]
 def opt(topo,x,limit,tag):
  nonlocal best
  localcount=[0]
  def fun(y):
   nonlocal best
   global calls
   calls+=1;localcount[0]+=1
   m=metrics(y,topo,coarse)
   z=score(m)
   if z<best["score"]:
    best={"score":float(z),"x":np.array(y).copy(),"topology":topo,
          "metrics":m,"stage":tag}
   if localcount[0]%250==0:
    print("progress",topo,tag,localcount[0],"current",round(z,3),
          "global",round(best["score"],3),fmt(best["metrics"]),flush=True)
   return z
  r=minimize(fun,x,
             method="Powell",bounds=BND,options={"maxfev":limit,
                   "xtol":0.003,"ftol":0.0003})
  m=metrics(r.x,topo,coarse)
  records.append({"topology":topo,"stage":tag,"evaluations":localcount[0],
                  "solver_success":bool(r.success),"solver_message":str(r.message),
                  "score":score(m),"metrics":m})
  print("round",topo,tag,localcount[0],fmt(m),
        "feasible",candidate_status(m),flush=True)
  return r.x,m
 # Same topology first, with bounded retuning of all shared L/C/k and per-band Cv.
 x,m=opt("original",X0.copy(),1200,"value_retune_original")
 # Permit only same chip component counts, but reroute the four fixed and two variable Cs.
 for topo in list(TOPOLOGIES)[1:]:
  if time.monotonic()-started>750:break
  x0=X0.copy()
  xx,mm=opt(topo,x0,1100,"topology_screen")
  if score(mm)<score(m):
   x,m=xx,mm
 # Local refinement of best coarse solution in same topology, plus one stochastic restart.
 for j in range(2):
  if time.monotonic()-started>900:break
  x=best["x"].copy();topo=best["topology"]
  if j:x=np.array([np.clip(a+RNG.normal(0,0.04*(hi-lo)),lo,hi)
                    for a,(lo,hi) in zip(x,BND)])
  opt(topo,x,2000,f"refinement_{j}")
 # Feasible-point local IL reduction, retaining explicit H2/H3 and wideband margins.
 if candidate_status(best["metrics"]):
  topo=best["topology"]
  incumbent={"x":best["x"].copy(),"m":best["metrics"]}
  for j in range(2):
   if time.monotonic()-started>700:break
   origin=incumbent["x"].copy()
   if j:
    origin=np.array([np.clip(a+RNG.normal(0,0.012*(hi-lo)),lo,hi)
                     for a,(lo,hi) in zip(origin,BND)])
   trace=[0]
   def penalized(y):
    global calls
    calls+=1;trace[0]+=1
    m=metrics(y,topo,coarse)
    if m is None:return 1e7
    if (m["min_h2_db"]>=30.05 and m["min_h3_db"]>=30.05
        and m["min_3to6_db"]>=20.20
        and m["worst_il_db"]<incumbent["m"]["worst_il_db"]):
     incumbent["x"]=np.array(y).copy();incumbent["m"]=m
    return (m["worst_il_db"]
            +20*max(0,30.05-m["min_h2_db"])**2
            +20*max(0,30.05-m["min_h3_db"])**2
            +8*max(0,20.2-m["min_3to6_db"])**2)
   res=minimize(penalized,origin,method="Powell",bounds=BND,
       options={"maxfev":2800,"xtol":0.002,"ftol":0.0002})
   records.append({"topology":topo,"stage":f"feasible_IL_refinement_{j}",
                   "evaluations":trace[0],"solver_success":bool(res.success),
                   "solver_message":str(res.message),
                   "best_feasible_IL_so_far":incumbent["m"]["worst_il_db"]})
   print("IL refinement",j,"best",fmt(incumbent["m"]),flush=True)
  if incumbent["m"]["worst_il_db"]<best["metrics"]["worst_il_db"]:
   best={"score":score(incumbent["m"]),"x":incumbent["x"].copy(),
         "topology":topo,"metrics":incumbent["m"],
         "stage":"feasible_IL_refinement"}
 # Exact full grids: RF-F003 28 intervals * 1001 and T006 3001 * 6.
 fine=grid(1001,1)
 frozen=metrics(best["x"],best["topology"],fine)
 original=metrics(X0,"original",fine)
 print("fine_baseline",fmt(original),"fine_selected",fmt(frozen),flush=True)
 print("full_18006_pass",candidate_status(frozen),flush=True)
 independent=independently_verify(best["x"],best["topology"])
 print("independent_validation",json.dumps(independent),flush=True)
 OUT.parent.mkdir(parents=True,exist_ok=True)
 payload={"experiment_id":"EXP-048","phase":"Phase 2","constraint_id":"RF-T006",
          "base_constraint_id":"RF-F003","source_experiment_id":"EXP-047",
          "source_sha256":SOURCE_SHA,
          "effective_constraint_sha256":constraint_fingerprint(POLICY),
          "seed":SEED,"method":"Bounded Powell with original 4L 2GJM 2PCB 2Cv seed and same-count capacitor topology rewiring; local non-global",
          "component_counts":{"LQP02HV_Q25":4,"GJM01_Q80":2,"PCB_PATTERN_C_Q40":2,"IC_VARIABLE_C_Q35":2},
          "initial_vector_23":X0.tolist(),
          "baseline_fine":original,"selected":{"topology":best["topology"],
          "fixed_capacitor_edges":TOPOLOGIES[best["topology"]][0],
          "variable_capacitor_edges":TOPOLOGIES[best["topology"]][1],
          "parameter_order":"L0..L3_nH,Cf0..Cf3_pF,k01,k13,k32,Cv0/Cv2_pF for B71 B12 B28 B13B14 B26 B8",
          "vector_23":best["x"].tolist(),"coarse":best["metrics"],"fine":frozen,
          "finite_grid_mandatory_pass":candidate_status(frozen),
          "solver_status":"partial_local_search_no_global_convergence_proof"},
          "coarse_rounds":records,"objective_calls":calls,
          "elapsed_seconds":time.monotonic()-started,
          "fine_grid":{"original_28_segments_pts":1001,"wide_frequency_step_MHz":1,
                       "wide_points_per_setting":3001,"wide_total":18006},
          "independent_validation":independent,
          "limitations":["No continuous extrema/Q(f)/SRF/EM/tolerance/physical validation",
                         "Coarse optimization and local heuristic do not prove infeasibility",
                         "Independent MNA verified only 114 specified probes not all grid points"]}
 OUT.write_text(json.dumps(payload,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
 print("EXP048_RESULT_JSON",json.dumps({"best_topology":best["topology"],
      "original_fine":original,"selected_fine":frozen,
      "score":best["score"],"attempted_evaluations":calls,
      "full_pass":candidate_status(frozen),
      "selected_vector_23":best["x"].tolist(),"validation":independent}),flush=True)
 print("RESULT_PATH",OUT,flush=True)
if __name__=="__main__":main()

#!/usr/bin/env python3
"""EXP-068 Phase2 RF-T008 rev3 independent sensitivity and zero mutual coupling.

Exact same fixed 4L1GJM2-ground-PCB topology as verified EXP059/067.
2x21 fixed-k sweeps and all 2^3 coupling-zero masks. All nonfixed k remain
freely optimized. 12 diverse historical/inter-basin/quasi-random seed families
for each run; 8 extra global Sobol starts when all k are zero.

No unregistered physical test or Phase3 work. Converged SLSQP-v2 AND dense
28x1001 six-setting H2/H3 >=30 AND independent 9x9 MNA for promotion.
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
from scipy.stats import qmc

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
sys.path.insert(0,str(ROOT/"experiments/chatgpt_topology_search/runs/EXP-067"))
sys.path.insert(0,str(ROOT/"src"))
import k01_sweep as scan
from lpf.constraint_versions import load_constraint,constraint_fingerprint
from lpf.slsqp_budget import run_termination_aware_slsqp,STANDARD_SLSQP_BUDGET
from lpf.trial_ic_fixed_c import validate_ic_fixed_c_settings
from lpf.trial_pcb_pattern_c import validate_trial_pcb_pattern_c_branches

EXPERIMENT="EXP-068"
SRC=ROOT/"experiments/chatgpt_topology_search/runs/EXP-067/checkpoints"
GRID=[round(-.1+.01*i,4) for i in range(21)]
MASKS=[
  ("all_free",{}),
  ("zero_k01",{0:0.}),
  ("zero_k13",{1:0.}),
  ("zero_k32",{2:0.}),
  ("zero_k01_k13",{0:0.,1:0.}),
  ("zero_k01_k32",{0:0.,2:0.}),
  ("zero_k13_k32",{1:0.,2:0.}),
  ("all_zero",{0:0.,1:0.,2:0.}),
]
CASES=(
  [("k13",k,{1:k}) for k in GRID]+
  [("k32",k,{2:k}) for k in GRID]+
  [(name,None,bounds) for name,bounds in MASKS]
)
SEED_NAMES=[
 "exp059_neg_all","exp060_outer_minus_limit",
 "exp067_k01_zero","exp067_k01_plus005","exp067_k01_plus010",
 "exp058_old_positive_mapped","opposite_basin_hybrid","signed_k_inversion",
 "sobol_global_0","sobol_global_1","sobol_global_2","sobol_global_3"
]
EXTRA_SOBOL_ALL_ZERO=8
SOURCE_FILES={
"exp067_k01_zero":SRC/"kzero.json",
"exp067_k01_plus005":SRC/"kplus0p05_crossbasin.json",
"exp067_k01_plus010":SRC/"best_kplus0p01.json", # name explicitly means +0.01
"exp067_k01_plus0100":SRC/"kplus0p10.json",
}
# positive profile source is +0.10, not +0.01. Rename for transparency:
SEED_NAMES[4]="exp067_k01_plus0100"

def load_seeds():
    n,m,p=scan.source_vectors()
    at0=np.asarray(json.loads(SOURCE_FILES["exp067_k01_zero"].read_text())["vector"],float)
    at005=np.asarray(json.loads(SOURCE_FILES["exp067_k01_plus005"].read_text())["vector"],float)
    at010=np.asarray(json.loads(SOURCE_FILES["exp067_k01_plus0100"].read_text())["vector"],float)
    out=[n,m,at0,at005,at010,p]
    if any(q.shape!=(25,) for q in out):raise AssertionError("Seed dimensions")
    return out

def enforce(v,e,forced):
    x=np.clip(np.asarray(v,float).copy(),e.bounds[:,0],e.bounds[:,1])
    x[7]=0.
    for index,k in forced.items():x[8+index]=k
    if x.shape!=(25,) or any(abs(x[8+i]-k)>1e-14 for i,k in forced.items()):
        raise AssertionError("Wrong K fixation")
    return x

def sobol_seed(u,reference):
    x=reference.copy()
    # Broad 23D Sobol intentionally does not start in EXP059's local basin.
    x[:4]=np.exp(np.log(.55)+u[:4]*(np.log(24.)-np.log(.55)))
    x[4]=np.exp(np.log(.3)+u[4]*(np.log(16.)-np.log(.3)))
    x[5:7]=np.exp(np.log(.02)+u[5:7]*(np.log(1.)-np.log(.02)))
    x[9:11]=-.1+.2*u[7:9]
    x[11:13]=.2+2.8*u[9:11]
    x[13:]=3*u[11:23]
    x[8]=-.1+.2*u[0]
    return x

def starts_for(ev,forced,index):
    a,b,c,d,e,f=load_seeds()
    mix=c.copy()
    for j in [0,1,2,3,4,5,6,11,12]:
        mix[j]=np.sqrt(max(c[j],1e-12)*max(d[j],1e-12))
    mix[8:11]=[.03,-.06,.05]
    mix[13:]=.5*(c[13:]+d[13:])
    inverse=f.copy()
    inverse[8:11]=-f[8:11]
    starts=[a,b,c,d,e,f,mix,inverse]
    gen=qmc.Sobol(d=23,scramble=True,seed=20261021+10007*index)
    draws=gen.random_base2(m=4 if index==49 else 2)
    n=(4+EXTRA_SOBOL_ALL_ZERO) if index==49 else 4
    starts.extend([sobol_seed(u,a) for u in draws[:n]])
    names=SEED_NAMES+([f"sobol_extra_{i}" for i in range(EXTRA_SOBOL_ALL_ZERO)] if index==49 else [])
    if len(starts)!=len(names):raise AssertionError("Seed count")
    return [(name,enforce(x,ev,forced)) for name,x in zip(names,starts)]

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--index",type=int,required=True)
    ap.add_argument("--out",type=Path,required=True)
    ap.add_argument("--seed-limit",type=int,default=0)
    ap.add_argument("--coarse",type=int,default=7)
    ap.add_argument("--fine",type=int,default=17)
    ap.add_argument("--dense",type=int,default=1001)
    a=ap.parse_args()
    if a.index not in range(len(CASES)) or a.dense<101 or min(a.coarse,a.fine)<2:
        raise ValueError("Bad arguments")
    category,kvalue,forced=CASES[a.index]
    scan.graph.begin("free","original")
    policy=load_constraint("RF-T008",allow_trial=True)
    if constraint_fingerprint(policy)!=scan.EXPECTED_CONSTRAINT_SHA256:
        raise ValueError("RF-T008 constraint fingerprint drift")
    dense=scan.graph.Evaluator(policy,"input_output",("cf0",),a.dense)
    coarse=scan.graph.Evaluator(policy,"input_output",("cf0",),a.coarse)
    fine=scan.graph.Evaluator(policy,"input_output",("cf0",),a.fine)
    for ev in (dense,coarse,fine):
        if tuple(ev.pcb_names)!=("g4","g3","off"):
            raise AssertionError("Wrong PCB topology")
        for pair,value in forced.items():ev.bounds[8+pair,:]=value
    seeds=starts_for(dense,forced,a.index)
    if a.seed_limit>0:seeds=seeds[:a.seed_limit]
    out=[];eligible=[]
    for name,v0 in seeds:
        status=run_termination_aware_slsqp(
            coarse,fine,v0,30.005,scan.stage_solver,
            budget=STANDARD_SLSQP_BUDGET)
        attempts=[scan.numeric_candidate(dense,x,name) for x in status["attempts"]]
        for row in attempts:
            if row["eligible_converged"]:eligible.append(row)
        out.append({"seed_family":name,"initial_vector":v0.tolist(),
                    "recovery_cause":status["recovery_cause"],
                    "attempts":attempts})
        print("TRY",a.index,category,kvalue,name,
              [(x["tier"],x["coarse"]["status"],x["fine"]["status"],
                round(x["dense"]["worst_IL_db"],8),x["eligible_converged"])
               for x in attempts],flush=True)
    best=min(eligible,key=lambda x:x["dense"]["worst_IL_db"]) if eligible else None
    mna=None
    if best is not None:
        v=np.asarray(best["vector"],float)
        if any(abs(v[8+i]-k)>1e-12 for i,k in forced.items()):
            raise AssertionError("SLSQP altered zero/fixed signed k")
        mna=scan.graph.base.parent.independent_mna(
            policy,"input_output",("cf0",),v)
        if not mna["pass"]:raise AssertionError("Independent 9x9 MNA failure")
        validate_ic_fixed_c_settings(policy,
            [dict(scan.pcb.parent.norm(edge),role="bridge")
             for edge in dense.var_edges],
            list(map(float,v[11:13])),
            dict(zip(scan.pcb.CASES,v[13:].reshape((6,2)).tolist())))
        validate_trial_pcb_pattern_c_branches(policy,
            [dict(scan.pcb.parent.norm(edge),capacitance_pf=float(v[5+i]),q=60)
             for i,edge in enumerate(((4,-1),(3,-1)))])
    result={
      "experiment_id":EXPERIMENT,"phase":"Phase 2",
      "constraint_id":"RF-T008","revision":3,
      "index":a.index,"category":category,
      "fixed_value":kvalue,"fixed_pairs":forced,
      "L_edges":scan.graph.L_GRAPHS["original"],
      "physical_row":["L0","L1","L3","L2"],
      "GJM_edge":[0,1],"PCB_edges":[[4,-1],[3,-1]],
      "IC_composite_edges":dense.var_edges,
      "reference_best_EXP059_IL_db":.8371337485828259,
      "nominal_chip_area":4+2/3,
      "RF_effective_constraint_sha256":constraint_fingerprint(policy),
      "method":{"slsqp":"slsqp-staged-v2","coarse_maxiter":240,
                "fine_maxiter":120,"rescue_caps":[500,280],
                "initial_seed_count":len(seeds),"seed_names":[n for n,_ in seeds],
                "frequency_segments":28,"dense_points_per_segment":a.dense,
                "independent_MNA_probes":84},
      "execution_sha":subprocess.check_output(
          ["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip(),
      "starts":out,"converged_and_30db_count":
          sum(any(z["eligible_converged"] for z in row["attempts"]) for row in out),
      "best_converged_30db":best,"independent_MNA":mna,
      "limitations":["No 30dB-compliant result is not a proof of infeasibility.",
        "Finite K grid and finite initial solutions, no global guarantee.",
        "35dB nominal and loss 0.3dB goals evaluated separately.",
        "Nominal constant Q only, no real Q(f)/SRF/EM, signed-k fabrication or Phase3"]
    }
    a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)+"\n")
    print("RESULT",a.index,category,kvalue,"BEST",
          best["dense"]["worst_IL_db"] if best else None,
          "ELIGIBLE",result["converged_and_30db_count"],
          "SEEDS",len(out),"MNA",mna and mna["pass"],flush=True)

if __name__=="__main__":
    main()

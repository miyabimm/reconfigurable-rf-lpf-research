#!/usr/bin/env python3
"""EXP-067: RF-T008 v3 Phase2 K01 fixed-grid multi-basin optimization.

Important: 8 *independent* starts per K01, not just EXP-059 local warm starts.
Seed families EXP058 positive basin, EXP059 negative basin, EXP060 negative-limit,
deliberate coupling-sign inversion, physically informed mixture, and 3 global
scrambled Sobol 23-dimensional starts. Deterministic seed sequence, documented
per-point objective and full original terminal status. Phase2 SLSQP v2.
"""
import argparse
import json
import math
import subprocess
import sys
from pathlib import Path

import numpy as np
from scipy.stats import qmc

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
sys.path.insert(0,str(ROOT/"experiments/chatgpt_topology_search/runs/EXP-060"))
sys.path.insert(0,str(ROOT/"experiments/chatgpt_topology_search/runs/EXP-059"))
sys.path.insert(0,str(ROOT/"experiments/chatgpt_topology_search/runs/EXP-058"))
sys.path.insert(0,str(ROOT/"src"))
import search_coupling_lgraphs as graph
import search_pcb_edges as pcb
import sweep_area3 as optim
from lpf.constraint_versions import load_constraint,constraint_fingerprint
from lpf.slsqp_budget import run_termination_aware_slsqp, STANDARD_SLSQP_BUDGET, TERMINATION_AWARE_POLICY_ID
from lpf.trial_ic_fixed_c import validate_ic_fixed_c_settings
from lpf.trial_pcb_pattern_c import validate_trial_pcb_pattern_c_branches

EXPERIMENT="EXP-067"
NEG=ROOT/"experiments/chatgpt_topology_search/runs/EXP-059/checkpoints/best_n4g_n3g_2pcb.json"
NEG_LIM=ROOT/"experiments/chatgpt_topology_search/runs/EXP-060/checkpoints/outer_input_kminus100.json"
POS=ROOT/"data/pareto_snapshots/rf_t008_exp058_area4p667_20261020.json"
K01_GRID=tuple(round(-.1+.01*i,4) for i in range(21))+(-.09218029453384365,)
SEED_NAMES=(
    "exp059_negative_baseline",
    "exp060_negative_limit",
    "exp058_positive_baseline_rewired_C",
    "positive_negative_hybrid",
    "coupling_sign_inversion",
    "wide_physically_informed",
    "sobol_global_1",
    "sobol_global_2",
    "sobol_global_3",
)
# Source-rooted classes 6; independent global Sobol classes 3.
EXPECTED_CONSTRAINT_SHA256="7de08611f8dd15b40fdfb7946e8c93de5796d026641bdca0f12e992962d05fd4"

def independent_looks(v,idx):
    """Map EXP058 positive historical 3-PCB vector to 2 ground-C connections.

    Do NOT claim this mapping is feasible or evaluated before running the
    optimizer. The new N3-GND starts from physically allowed 0.45 pF/Q60.
    """
    x=v.copy()
    x[5]=min(float(x[5]),1.0)
    x[6]=0.45
    x[7]=0.
    return x

def vcheck(v,e,k):
    x=np.asarray(v,float).copy()
    if x.shape!=(25,):raise ValueError("Expected 25-dim 4L vector")
    x[8]=k
    x[7]=0.  # Disabled PCB branch, not physically installed.
    x=np.clip(x,e.bounds[:,0],e.bounds[:,1])
    if abs(x[8]-k)>1e-13 or x[7]!=0:
        raise AssertionError("Fixed K01/dummy topology violated")
    return x

def source_vectors():
    x_neg=np.array(json.loads(NEG.read_text())["vector"],float)
    x_nlim=np.array(json.loads(NEG_LIM.read_text())["vector"],float)
    x_pos=independent_looks(np.array(json.loads(POS.read_text())["best"]["vector"],float),0)
    if x_neg.shape!=(25,) or x_pos.shape!=(25,) or x_nlim.shape!=(25,):
        raise AssertionError("Historical source shape mismatch")
    return x_neg,x_nlim,x_pos

def make_initials(e,k,idx):
    x_neg,x_nlim,x_pos=source_vectors()
    rng=np.random.default_rng(20261021+10007*idx)
    # Midpoint of *two independent historical basins*, not a local
    # perturbation of EXP059 alone. L/C positive values blend geometrically.
    hybrid=x_neg.copy()
    for j in [0,1,2,3,4,5,6,11,12]:
        hybrid[j]=math.sqrt(max(x_neg[j],1e-12)*max(x_pos[j],1e-12))
    hybrid[9:11]=[0.1,-0.09]
    hybrid[13:]=np.clip(0.5*(x_neg[13:]+x_pos[13:]),0,3)
    inverse=x_pos.copy()
    inverse[9:11]=[-0.08,-0.08]
    # Deliberately cover less explored central-k regimes. Large perturbations
    # of the positive source, rather than small jitter of the best negative.
    wide=x_pos.copy()
    wide[:4]*=np.exp(rng.normal(0,0.5,4))
    wide[4:7]*=np.exp(rng.normal(0,0.45,3))
    wide[9:11]=[-0.1,0.1]
    wide[11:13]=[1.1,0.85]
    wide[13:]=np.clip(0.65*x_pos[13:]+0.35*rng.uniform(0,3,12),0,3)
    seeds=[x_neg,x_nlim,x_pos,hybrid,inverse,wide]

    # Global Sobol, scrambled and shuffled via nonreference 23-D design.
    # Sampling is deliberately *not* concentrated near EXP059; the same
    # Sobol pattern is deterministic but differs between K01 grid points.
    sobol=qmc.Sobol(d=23,scramble=True,seed=20261021+7919*idx)
    draws=sobol.random_base2(m=2)[:3]
    for u in draws:
        a=x_neg.copy()
        a[:4]=np.exp(np.log(.55)+u[:4]*(np.log(24.)-np.log(.55)))
        a[4]=np.exp(np.log(.3)+u[4]*(np.log(16.)-np.log(.3)))
        a[5:7]=np.exp(np.log(.02)+u[5:7]*(np.log(1.)-np.log(.02)))
        a[9:11]=-.1+.2*u[7:9]
        a[11:13]=.2+2.8*u[9:11]
        # 12 setting-dependent capacitors cover whole available range;
        # no forced proximity to original 6-mode schedule.
        a[13:]=3*u[11:23]
        seeds.append(a)
    assert len(seeds)==len(SEED_NAMES)==9
    return [(name,vcheck(a,e,k)) for name,a in zip(SEED_NAMES,seeds)]

def stage_solver(ev,x,maxiter,target):
    return optim.opt(ev,x,maxiter,target)

def numeric_candidate(ev,att,name):
    v=np.asarray(att["vector"],float)
    metrics=ev.summary(v)
    pass30=bool(metrics["min_H2_db"]>=30 and metrics["min_H3_db"]>=30)
    return {
        "tier":att["tier"],"warm_start_source":att["warm_start_source"],
        "coarse_budget":att["coarse_maxiter"],
        "fine_budget":att["fine_maxiter"],
        "coarse":att["coarse"],"fine":att["fine"],
        "converged":bool(att["converged"]),
        "finite_H2H3_30db_pass":pass30,
        "eligible_converged":bool(att["converged"] and pass30),
        "dense":metrics,"vector":v.tolist(),
        "initial_seed_family":name,
    }

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--index",type=int,required=True)
    ap.add_argument("--out",type=Path,required=True)
    ap.add_argument("--coarse",type=int,default=7)
    ap.add_argument("--fine",type=int,default=17)
    ap.add_argument("--dense",type=int,default=1001)
    ap.add_argument("--target",type=float,default=30.005)
    ap.add_argument("--limit-seeds",type=int,default=9,
                    help="9 standard; smaller count only for smoke testing, not final evidence")
    args=ap.parse_args()
    if args.index not in range(len(K01_GRID)):raise ValueError("Index out of sweep")
    if args.limit_seeds<1 or args.limit_seeds>len(SEED_NAMES):raise ValueError("Bad limit-seeds")
    if min(args.coarse,args.fine,args.dense)<1 or args.dense<101 or args.target<30:
        raise ValueError("Bad sampling")
    k=K01_GRID[args.index]
    graph.begin("free","original")
    policy=load_constraint("RF-T008",allow_trial=True)
    if constraint_fingerprint(policy)!=EXPECTED_CONSTRAINT_SHA256:
        raise AssertionError("RF-T008 v3 constraint fingerprint drift")
    if policy["trial_ic_fixed_c_by_connection"]["max_composite_branches"]!=2:
        raise AssertionError("Invalid composite IC C count")
    dense=graph.Evaluator(policy,"input_output",("cf0",),args.dense)
    coarse=graph.Evaluator(policy,"input_output",("cf0",),args.coarse)
    fine=graph.Evaluator(policy,"input_output",("cf0",),args.fine)
    for ev in [dense,coarse,fine]:
        ev.bounds[8,:]=k
        if tuple(ev.pcb_names)!=("g4","g3","off"):
            raise AssertionError("PCB connectivity mismatch")
    if args.index==21:
        old=source_vectors()[0]
        saved=dense.summary(vcheck(old,dense,k))
        if abs(saved["worst_IL_db"]-.8371337485828259)>1e-8:
            raise AssertionError("Exact previously verified baseline not reproduced")
    seeds=make_initials(dense,k,args.index)[:args.limit_seeds]
    rows=[]
    eligible=[]
    for family,start in seeds:
        r=run_termination_aware_slsqp(coarse,fine,start,args.target,
                                      stage_solver,budget=STANDARD_SLSQP_BUDGET)
        attempts=[numeric_candidate(dense,att,family) for att in r["attempts"]]
        for a in attempts:
            # Convergence is a *stage* status, not based on RF grid alone.
            if a["eligible_converged"]:eligible.append(a)
        rows.append({"seed_family":family,"initial_vector":start.tolist(),
                     "recovery_cause":r["recovery_cause"],"attempts":attempts})
        print("TRY",args.index,k,family,
              [(a["tier"],a["coarse"]["status"],a["fine"]["status"],
                round(a["dense"]["worst_IL_db"],9),a["eligible_converged"])
               for a in attempts],flush=True)
    best=min(eligible,key=lambda a:a["dense"]["worst_IL_db"]) if eligible else None
    mna=None
    if best:
        x=np.asarray(best["vector"],float)
        mna=graph.base.parent.independent_mna(policy,"input_output",("cf0",),x)
        if not mna["pass"]:raise AssertionError("Independent coupled L 9x9 MNA failed")
        if abs(x[8]-k)>1e-12:raise AssertionError("Fixed K01 changed")
        pcb.validate_trial_pcb_pattern_c_branches(policy,[
            dict(pcb.parent.norm(e),capacitance_pf=float(x[5+i]),q=60)
            for i,e in enumerate(((4,-1),(3,-1)))])
        validate_ic_fixed_c_settings(policy,
            [dict(pcb.parent.norm(e),role="bridge") for e in dense.var_edges],
            list(map(float,x[11:13])),dict(zip(pcb.CASES,x[13:].reshape(6,2).tolist())))
    result={
        "experiment_id":EXPERIMENT,"phase":"Phase 2","constraint_id":"RF-T008",
        "trial_revision":3,"fixed_k01":k,"index":args.index,
        "k_grid":list(K01_GRID),"nominal_chip_area":4+2/3,
        "L_edges":graph.L_GRAPHS["original"],
        "physical_row":["L0","L1","L3","L2"],
        "k_adjacent_pairs":graph.base.parent.old4.K_PAIRS,
        "fixed_GJM_edge":(0,1),"PCB_edges":((4,-1),(3,-1)),
        "variable_C_edges":dense.var_edges,
        "IC_fixed_parallel_edges":dense.var_edges,
        "PCB_grounded_Q":60,"IC_fixed_Q":60,"IC_variable_Q":35,"L_Q":25,
        "source_refs":{
            "negative":"experiments/chatgpt_topology_search/runs/EXP-059/checkpoints/best_n4g_n3g_2pcb.json",
            "negative_limit":"experiments/chatgpt_topology_search/runs/EXP-060/checkpoints/outer_input_kminus100.json",
            "positive":"data/pareto_snapshots/rf_t008_exp058_area4p667_20261020.json",
        },
        "method":{"independent_families":list(SEED_NAMES),
            "Sobol_global_dimensions":23,
            "Sobol_global_uses_historical_nominal_values":False,
            "SLSQP_policy":TERMINATION_AWARE_POLICY_ID,
            "normal_stage_maxiter":[240,120],
            "conditional_iteration_rescue_maxiter":[500,280],
            "stage_restarts_max_per_seed":1,
            "dense_samples_per_interval":args.dense,
            "frequency_intervals":28,
            "independent_MNA_probes_per_interval":3},
        "effective_constraint_sha256":constraint_fingerprint(policy),
        "execution_git_sha":subprocess.check_output(
            ["git","rev-parse","HEAD"],text=True,cwd=ROOT).strip(),
        "attempted_seed_count":len(seeds),
        "converged_seed_count":sum(any(a["converged"] for a in row["attempts"]) for row in rows),
        "eligible_seed_count":sum(any(a["eligible_converged"] for a in row["attempts"]) for row in rows),
        "attempts":rows,"best_converged_30db":best,
        "independent_MNA":mna,
        "limitations":["Local SLSQP from diverse starts still does not establish global optimum.",
          "No continuous-band extrema guarantee beyond fixed 28x1001 finite samples.",
          "30dB minimum guard ~0.005dB, not required 35dB design margin or IL<=0.30dB.",
          "SRF/Q(f), true magnetic polarity geometry, EM and tolerances unverified; no Phase3."]
    }
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)+"\n")
    print("RESULT",args.index,"K01",k,
          "best_IL",best["dense"]["worst_IL_db"] if best else None,
          "eligible",result["eligible_seed_count"],"of",len(seeds),
          "MNA",mna["pass"] if mna else None,flush=True)

if __name__=="__main__":
    main()

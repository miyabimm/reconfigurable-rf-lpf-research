#!/usr/bin/env python3
"""EXP-060, RF-T008 rev3 Phase2, 4L/1GJM/2PCB-C, coupling saturation & L connection graphs.

Warm-start only from the independently MNA-verified EXP-059 lowest-IL design.
Sweep physically neighboring mutual inductances |k|<=0.1 with both signs;
also rewire branch edges while keeping chip row L0-L1-L3-L2, two Q60 grounded
PCB capacitors N4-GND/N3-GND, GJM (IN,N1), and two composite DTC branches.
Do not confuse fixed signed k=0.1 with a guarantee of physical realization.
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path
import numpy as np

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
sys.path.insert(0,str(ROOT/"experiments/chatgpt_topology_search/runs/EXP-059"))
sys.path.insert(0,str(ROOT/"experiments/chatgpt_topology_search/runs/EXP-058"))
sys.path.insert(0,str(ROOT/"src"))
import search_pcb_edges as base
import sweep_area3 as optimizer
from lpf.constraint_versions import load_constraint, constraint_fingerprint
from lpf.trial_ic_fixed_c import validate_ic_fixed_c_settings
from lpf.trial_pcb_pattern_c import validate_trial_pcb_pattern_c_branches

CHECKPOINT=ROOT/"experiments/chatgpt_topology_search/runs/EXP-059/checkpoints/best_n4g_n3g_2pcb.json"
# 5 nodes: IN=0, central=1, OUT=2, end resonator tips=3 and 4.
L_GRAPHS={
    "original":((0,1),(1,3),(1,4),(1,2)),
    "n3_from_in":((0,1),(0,3),(1,4),(1,2)),
    "n3_from_out":((0,1),(2,3),(1,4),(1,2)),
    "n4_from_in":((0,1),(1,3),(0,4),(1,2)),
    "n4_from_out":((0,1),(1,3),(2,4),(1,2)),
    "series_via_n4":((0,1),(1,3),(1,4),(4,2)),
    "series_via_n3":((0,1),(1,3),(1,4),(3,2)),
    "input_via_n3":((0,3),(1,3),(1,4),(1,2)),
    "input_via_n4":((0,4),(1,3),(1,4),(1,2)),
    "resonators_series_via_n4":((0,1),(4,3),(1,4),(1,2)),
    "resonators_series_via_n3":((0,1),(1,3),(3,4),(1,2)),
    "n3_from_in_n4_out":((0,1),(0,3),(2,4),(1,2)),
    "n3_from_out_n4_in":((0,1),(2,3),(0,4),(1,2)),
    "n3_from_in_output_via_n4":((0,1),(0,3),(1,4),(4,2)),
    "n3_from_out_output_via_n4":((0,1),(2,3),(1,4),(4,2)),
    "resonators_chain_in":((0,1),(4,3),(0,4),(1,2)),
    "resonators_chain_out":((0,1),(4,3),(2,4),(1,2)),
}
# A bound (low,high) may hold a signed k exactly, or restrict its magnitude.
K_MODES={
    "free":{},
    "k01_minus100":{0:(-0.1,-0.1)},
    "k01_plus100":{0:(0.1,0.1)},
    "k13_plus100":{1:(0.1,0.1)},
    "k13_minus100":{1:(-0.1,-0.1)},
    "k32_minus100":{2:(-0.1,-0.1)},
    "k32_plus100":{2:(0.1,0.1)},
    "outer_minus100":{0:(-0.1,-0.1),2:(-0.1,-0.1)},
    "all_baseline_sign_max":{0:(-0.1,-0.1),1:(0.1,0.1),2:(-0.1,-0.1)},
    "all_minus100":{0:(-0.1,-0.1),1:(-0.1,-0.1),2:(-0.1,-0.1)},
    "all_plus100":{0:(0.1,0.1),1:(0.1,0.1),2:(0.1,0.1)},
    "all_inverse_sign_max":{0:(0.1,0.1),1:(-0.1,-0.1),2:(0.1,0.1)},
    "k13_plus080to100":{1:(0.08,0.1)},
    "k13_minus080to100":{1:(-0.1,-0.08)},
    "outer_minus095to100":{0:(-0.1,-0.095),2:(-0.1,-0.095)},
}

def check_tree(edges):
    if len(edges)!=4 or len({tuple(sorted(e)) for e in edges})!=4:
        raise ValueError("4-L graph requires distinct 4 edges")
    seen={0}
    for _ in range(5):
        for a,b in edges:
            if a in seen:seen.add(b)
            if b in seen:seen.add(a)
    if seen!={0,1,2,3,4}:raise ValueError("4-L electrical graph not a spanning tree")
    # Connected + 4 distinct edges on 5 vertices means a tree.
    if any(a==b or min(a,b)<0 or max(a,b)>4 for a,b in edges):
        raise ValueError("Bad L edge")

class Evaluator(base.Evaluator):
    def __init__(self,policy,variant,gjm_names,points):
        super().__init__(policy,variant,gjm_names,points)
        for i,b in K_MODES[ACTIVE_MODE].items():
            self.bounds[8+i,:]=b

ACTIVE_MODE="free"
base.parent.Evaluator=Evaluator

def begin(mode,graph):
    global ACTIVE_MODE
    if mode not in K_MODES or graph not in L_GRAPHS:
        raise ValueError("unknown mode or graph")
    check_tree(L_GRAPHS[graph])
    ACTIVE_MODE=mode
    base.ACTIVE_LAYOUT="n4g_n3g_2pcb"
    base.parent.old4.L_EDGES=L_GRAPHS[graph]
    base.parent.Evaluator=Evaluator

def init(e,original,start,graph,mode):
    v=original.copy()
    if start==1:
        rng=np.random.default_rng(20261020+47*list(L_GRAPHS).index(graph)
                                  +1009*list(K_MODES).index(mode))
        v[:4]*=np.exp(rng.normal(0,0.09,4))
        v[4:7]*=np.exp(rng.normal(0,0.12,3))
        v[8:11]+=rng.normal(0,0.025,3)
        v[11:13]+=rng.normal(0,0.08,2)
        v[13:]+=rng.normal(0,0.15,12)
    elif start==2:
        # Deliberate k-sign-flip initial path, distinguish sign basins.
        v[8:11]*=-1.
    for i,bounds in K_MODES[mode].items():
        if bounds[0]==bounds[1]:v[8+i]=bounds[0]
        elif v[8+i]<bounds[0] or v[8+i]>bounds[1]:
            v[8+i]=(bounds[0]+bounds[1])/2
    return np.clip(v,e.bounds[:,0],e.bounds[:,1])

def is_converged(status):
    coarse=status["coarse"].get("rescue",status["coarse"])
    fine=status["fine"].get("rescue",status["fine"])
    return bool(coarse["success"] and fine["success"])

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--mode",required=True,choices=tuple(K_MODES))
    ap.add_argument("--graph",required=True,choices=tuple(L_GRAPHS))
    ap.add_argument("--starts",type=int,default=2)
    ap.add_argument("--coarse",type=int,default=7)
    ap.add_argument("--fine",type=int,default=17)
    ap.add_argument("--dense",type=int,default=1001)
    ap.add_argument("--target",type=float,default=30.005)
    ap.add_argument("--out",type=Path)
    a=ap.parse_args()
    if min(a.starts,a.coarse,a.fine,a.dense)<1 or a.dense<101 or a.target<30:
        raise ValueError("Invalid sweep budget")
    begin(a.mode,a.graph)
    policy=load_constraint("RF-T008",allow_trial=True)
    assert policy["trial_ic_fixed_c_by_connection"]["max_composite_branches"]==2
    original=json.loads(CHECKPOINT.read_text())
    seed=np.asarray(original["vector"],float)
    assert len(seed)==25 and abs(original["numerical"]["worst_IL_db"]-0.8371337485828259)<1e-10
    ev=Evaluator(policy,"input_output",("cf0",),a.dense)
    coarse=Evaluator(policy,"input_output",("cf0",),a.coarse)
    fine=Evaluator(policy,"input_output",("cf0",),a.fine)
    if a.graph=="original" and a.mode=="free":
        baseline=ev.summary(seed)
        if abs(baseline["worst_IL_db"]-original["numerical"]["worst_IL_db"])>2e-9:
            raise AssertionError("EXP-059 baseline transfer not reproduced")
    attempts=[]
    for start in range(a.starts):
        x0=init(ev,seed,start,a.graph,a.mode)
        x,status=optimizer.staged(coarse,fine,x0,a.target)
        summary=ev.summary(x)
        finite30=bool(summary["min_H2_db"]>=30 and summary["min_H3_db"]>=30)
        completed=is_converged(status)
        attempts.append({
            "start":start,"solver":status,"converged":completed,
            "finite_30db_pass":finite30,"eligible_converged":bool(completed and finite30),
            "vector":x.tolist(),"dense":summary})
        print("TRY",a.graph,a.mode,start,"IL",summary["worst_IL_db"],
              "H2",summary["min_H2_db"],"H3",summary["min_H3_db"],
              "converged",completed,"eligible",completed and finite30,flush=True)
    good=[v for v in attempts if v["eligible_converged"]]
    best=min(good,key=lambda v:v["dense"]["worst_IL_db"]) if good else None
    # For failed trials, retain full vector but never promote a nonconverged result.
    numerical=None
    if best is not None:
        numerical=base.parent.independent_mna(policy,"input_output",("cf0",),
                                               np.asarray(best["vector"]))
        if not numerical["pass"]:
            raise AssertionError("Independent coupled 9x9 MNA failed")
        x=best["vector"]
        edges=[dict(base.parent.norm(ed),role="bridge")
               for ed in ev.var_edges]
        validate_ic_fixed_c_settings(policy,edges,[float(v) for v in x[11:13]],
                          dict(zip(base.CASES,np.asarray(x[13:]).reshape((6,2)).tolist())))
        pcb=[dict(base.parent.norm(ed),capacitance_pf=float(x[5+i]),q=60)
             for i,ed in enumerate(((4,-1),(3,-1)))]
        validate_trial_pcb_pattern_c_branches(policy,pcb)
    output={
        "experiment_id":"EXP-060","phase":"Phase 2","constraint_id":"RF-T008",
        "revision":3,"parent_experiment":"EXP-059","baseline_IL_db":0.8371337485828259,
        "chip_area_units":4+2/3,"graph":a.graph,"L_edges":L_GRAPHS[a.graph],
        "K_mode":a.mode,"fixed_K_bound_overrides":K_MODES[a.mode],
        "K_coupling_pairs":base.parent.old4.K_PAIRS,
        "physical_inductor_row":["L0","L1","L3","L2"],
        "GJM_edge":(0,1),"fixed_PCB_edges":((4,-1),(3,-1)),
        "variable_C_edges":ev.var_edges,"IC_fixed_C_edges":ev.var_edges,
        "inductor_Q":25,"capacitor_Q":ev.Q_C.tolist(),
        "source_checkpoint":str(CHECKPOINT.relative_to(ROOT)),
        "effective_constraint_sha256":constraint_fingerprint(policy),
        "code_execution_sha":subprocess.check_output(["git","rev-parse","HEAD"],
                                                     cwd=ROOT,text=True).strip(),
        "grid":{"intervals":28,"coarse":a.coarse,"fine":a.fine,
                "dense":a.dense,"independent_MNA_points_per_interval":3},
        "attempts":attempts,"best_converged_30db":best,
        "independent_MNA":numerical,
        "limitations":["Finite-grid local SLSQP, no global optimization or continuum guarantee.",
                       "Tight/boundary k restrictions are diagnostic, not design rule.",
                       "No RF-T007 parasitic; IC fixed Q60/variable Q35 separately stamped.",
                       "No real Q(f), SRF, mutual-coupling physical realizability, EM, tolerance or Phase3."]
    }
    filepath=a.out or ROOT/"results/EXP-060"/f"{a.graph}_{a.mode}.json"
    filepath.parent.mkdir(parents=True,exist_ok=True)
    filepath.write_text(json.dumps(output,ensure_ascii=False,indent=2,allow_nan=False)+"\n")
    print("RESULT",a.graph,a.mode,
          best["dense"] if best else "NO_CONVERGED_30DB",
          "MNA",numerical,flush=True)

if __name__=="__main__":
    main()

#!/usr/bin/env python3
"""EXP-062 Phase 2 RF-T008 v3: controlled transfer of EXP-059 PCB shunt insight
to 4L 2/3/4 GJM cost cells. Nominal finite-grid local search only.
"""
import argparse
import json
import sys
import subprocess
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path.insert(0, str(ROOT / "src"))
from lpf.phase2_models import exp058_area4l_gjm as parent
from lpf.phase2_models import exp058_area3 as optimizer
from lpf.slsqp_budget import run_termination_aware_slsqp
from lpf.constraint_versions import load_constraint, constraint_fingerprint
from lpf.trial_pcb_pattern_c import validate_trial_pcb_pattern_c_branches
from lpf.trial_ic_fixed_c import validate_ic_fixed_c_settings

# Four fixed-capacitor positions in every cost cell; no uncounted chip parts.
# Each (edge, type) is explicit. GJM Q80, PCB GND Q60 / non-GND Q40.
# Cross-cost controls retain the original EXP-058 capacitor placement.
LAYOUTS = {
    "a533_control": ([(0,1),(4,-1)], [(1,2),(0,3)]),
    "a533_ground2": ([(0,1),(1,2)], [(4,-1),(3,-1)]),
    "a533_ground_alt": ([(0,1),(0,3)], [(4,-1),(3,-1)]),
    "a533_ground_one": ([(0,1),(4,-1)], [(3,-1),(1,2)]),
    "a6_control": ([(0,1),(4,-1),(1,2)], [(0,3)]),
    "a6_grounded": ([(0,1),(4,-1),(1,2)], [(3,-1)]),
    "a6_ground_swap": ([(0,1),(1,2),(0,3)], [(4,-1)]),
    "a6_ground_swap2": ([(0,1),(4,-1),(0,3)], [(3,-1)]),
    "a667_control": ([(0,1),(4,-1),(1,2),(0,3)], []),
    "a667_ground3": ([(0,1),(4,-1),(1,2),(3,-1)], []),
    "a667_ground_alt": ([(0,1),(4,-1),(0,3),(3,-1)], []),
    "a667_ground_swap": ([(0,1),(1,2),(0,3),(3,-1)], []),
}
# Ground in circuit solver = -1; ground in trial validator = 0.
SOURCE = ROOT / "experiments/chatgpt_topology_search/runs/EXP-059/checkpoints/best_n4g_n3g_2pcb.json"
HIGH = ROOT / "data/pareto_snapshots/rf_t008_exp058_area5p333_to_6p667_20261020.json"
ACTIVE = None
BASE = parent.Evaluator

def cost(layout):
    return 4. + len(LAYOUTS[layout][0])*(2./3.)

class Evaluator(BASE):
    def __init__(self, policy, variant, unused, points):
        if variant != "input_output" or ACTIVE not in LAYOUTS:
            raise ValueError("Only fixed EXP-059 two-bridge DTC controls authorized")
        # Parent computes the fixed S2P and six-band coverage; override cap graph.
        super().__init__(policy, variant, ("cf0",), points)
        gjm, pcb = LAYOUTS[ACTIVE]
        edges = tuple(tuple(e) for e in gjm+pcb)
        if len(edges)!=4 or len(set(edges))!=4 or len(pcb)>3:
            raise AssertionError("Bad 4-slot topology")
        self.fixed_edges = edges
        self.cap_edges = edges+self.var_edges+self.var_edges
        self.BC = parent.old4.incidence(self.cap_edges)
        self.Q_C = np.array([80.]*len(gjm)
            + [60. if -1 in e else 40. for e in pcb]
            + [35.,35.,60.,60.],float)
        for j,e in enumerate(edges):
            self.bounds[4+j] = (0.02,100.) if j<len(gjm) else (
                (0.02,1.) if -1 in e else (0.02,0.2))
        validate_trial_pcb_pattern_c_branches(policy,[
            dict(parent.norm(e),capacitance_pf=0.1,
                 q=60 if -1 in e else 40) for e in pcb])
        self.gjm_names = tuple("GJM"+str(i) for i in range(len(gjm)))
        self.cache_x,self.cache_il=None,None

# Parent independent_mna uses Evaluator as a dynamic global; this replacement
# only changes model placement, not independent 9x9 branch-current equations.
parent.Evaluator = Evaluator

def seed(ev, source, source_edges, source_types, randomized, idx):
    x=np.asarray(source,float).copy()
    assert x.shape==(25,)
    old=list(zip(source_edges,source_types,source[4:8]))
    gjm,pcb=LAYOUTS[ACTIVE]
    for i,e in enumerate(gjm+pcb):
        kind="GJM" if i<len(gjm) else "PCB"
        identical=[v for oe,ot,v in old if tuple(oe)==tuple(e) and ot==kind]
        # Keep a physical shunt value of order 0.4 pF when adding new PCB.
        x[4+i]=identical[0] if identical else (1.0 if kind=="GJM" else
                                  (0.45 if -1 in e else 0.08))
    if randomized:
        rng=np.random.default_rng(20261020+997*idx+37*list(LAYOUTS).index(ACTIVE))
        x[:4]*=np.exp(rng.normal(0,0.045,4))
        x[4:8]*=np.exp(rng.normal(0,0.1,4))
        x[8:11]+=rng.normal(0,0.009,3)
        x[11:13]+=rng.normal(0,0.07,2)
        x[13:]+=rng.normal(0,0.08,12)
    return np.clip(x,ev.bounds[:,0],ev.bounds[:,1])

def stage(ev, x, maxiter, target):
    x1,stat=optimizer.opt(ev,np.asarray(x,float),maxiter,target)
    return x1, {**stat,"converged":stat["success"],"maxiter":maxiter}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--layout",required=True,choices=list(LAYOUTS))
    p.add_argument("--starts",type=int,default=2)
    p.add_argument("--coarse",type=int,default=7)
    p.add_argument("--fine",type=int,default=17)
    p.add_argument("--dense",type=int,default=1001)
    p.add_argument("--target",type=float,default=30.005)
    p.add_argument("--out",type=Path)
    args=p.parse_args()
    if args.starts!=2 or min(args.coarse,args.fine)<3 or args.dense<101:
        raise ValueError("Require two reproducible warm starts and dense validation")
    global ACTIVE
    ACTIVE=args.layout
    policy=load_constraint("RF-T008",allow_trial=True)
    if policy["trial_ic_fixed_c_by_connection"]["max_composite_branches"]!=2:
        raise AssertionError("RF-T008 v3 is required")
    best=json.loads(SOURCE.read_text())
    high=json.loads(HIGH.read_text())
    vec0=np.asarray(best["vector"],float)
    area=cost(ACTIVE)
    chosen=min(high["selected_candidates"],key=lambda q:abs(q["area"]-area))
    if abs(chosen["area"]-area)>1e-6: raise AssertionError("Missing cost seed")
    vhigh=np.asarray(chosen["vector"],float)
    high_edges=parent.ALL_FIXED
    high_gjm=set(parent.GJM_POS[j] for j in chosen["GJM_positions"])
    types_high=["GJM" if i in high_gjm else "PCB" for i in range(4)]
    ev=Evaluator(policy,"input_output",("cf0",),args.dense)
    ec=Evaluator(policy,"input_output",("cf0",),args.coarse)
    ef=Evaluator(policy,"input_output",("cf0",),args.fine)
    srcs=[
        seed(ev,vec0,[(0,1),(4,-1),(3,-1),(0,3)],["GJM","PCB","PCB","PCB"],False,0),
        seed(ev,vhigh,high_edges,types_high,True,1),
    ]
    results=[]
    for j,x0 in enumerate(srcs):
        run=run_termination_aware_slsqp(ec,ef,x0,args.target,optimize_stage=stage)
        tierrows=[]
        for att in run["attempts"]:
            vec=np.asarray(att["vector"],float)
            metrics=ev.summary(vec)
            pass30=metrics["min_H2_db"]>=30 and metrics["min_H3_db"]>=30
            tierrows.append({
                "tier":att["tier"],"vector":vec.tolist(),
                "coarse":att["coarse"],"fine":att["fine"],
                "converged":att["converged"],"finite_30db_pass":bool(pass30),
                "eligible":bool(att["converged"] and pass30),
                "dense":metrics,"warm_start_source":att["warm_start_source"],
            })
        results.append({"start":j,"input_vector":x0.tolist(),"attempts":tierrows,
                        "iteration_policy":run["iteration_policy"],"recovery_cause":run["recovery_cause"]})
        print("TRY",ACTIVE,j,[(q["tier"],q["dense"]["worst_IL_db"],q["converged"],q["finite_30db_pass"]) for q in tierrows],flush=True)
    good=[q for run in results for q in run["attempts"] if q["eligible"]]
    selected=min(good,key=lambda q:q["dense"]["worst_IL_db"]) if good else None
    check=parent.independent_mna(policy,"input_output",("cf0",),np.asarray(selected["vector"],float)) if selected else None
    if selected and not check["pass"]:raise AssertionError("Independent coupled L MNA failed")
    if selected:
        x=np.asarray(selected["vector"])
        vars=[dict(parent.norm(e),role="bridge") for e in ev.var_edges]
        validate_ic_fixed_c_settings(policy,vars,x[11:13].tolist(),
             dict(zip(parent.CASES,x[13:].reshape(6,2).tolist())))
    payload={
        "experiment_id":"EXP-062","constraint_id":"RF-T008","revision":3,
        "phase":"Phase 2","chip_area":area,
        "layout":ACTIVE,"GJM_edges":LAYOUTS[ACTIVE][0],"PCB_edges":LAYOUTS[ACTIVE][1],
        "variable_C_edges":ev.var_edges,"L_edges":parent.old4.L_EDGES,
        "physical_L_row":["L0","L1","L3","L2"],
        "effective_constraint_sha256":constraint_fingerprint(policy),
        "code_execution_sha":subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip(),
        "sampling":{"segments":28,"coarse":args.coarse,"fine":args.fine,
                    "dense":args.dense,"independent_MNA":84},
        "source_best":"EXP-059","same_cost_seed":"EXP-058",
        "starts":results,"best_converged_30db":selected,
        "independent_MNA":check,
        "limitations":["Nominal constant-Q model and fixed external S2P",
                       "Local multistart only; no proof of global optimum",
                       "28x1001 grid and 84 independent MNA probes only",
                       "No Q(f)/SRF, physical k, EM, tolerance or Phase3"]
    }
    out=args.out or ROOT/"results/EXP-062"/(ACTIVE+".json")
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(payload,ensure_ascii=False,indent=2,allow_nan=False)+"\n")
    print("RESULT",ACTIVE, "IL",selected["dense"]["worst_IL_db"] if selected else "NO_CONVERGED",
          "MNA",check["pass"] if check else "NOT_RUN",flush=True)

if __name__=="__main__":
    main()

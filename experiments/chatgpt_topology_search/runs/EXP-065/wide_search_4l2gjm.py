#!/usr/bin/env python3
"""EXP-065 RF-T008 v3 Phase2 wide 4L/2GJM topology factorial search.

Axes: 8 mixed Q80 GJM/Q60-Q40 PCB-C layouts, four composite two-DTC
connection graphs, three 4L spanning-tree electrical graphs. Fixed chip
area 4 + 2*(2/3)=5 1/3. Separate Q60 IC fixed-C and Q35 variable-C stamps.
Nonconverged 30dB candidates are NEVER promoted to Pareto.
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path
import numpy as np

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
sys.path[:0]=[str(ROOT/"src"),
             str(ROOT/"src")]
from lpf.phase2_models import exp058_area4l_gjm as parent
from lpf.phase2_models import exp058_area3 as optimizer
from lpf.constraint_versions import load_constraint,constraint_fingerprint
from lpf.slsqp_budget import run_termination_aware_slsqp
from lpf.trial_ic_fixed_c import validate_ic_fixed_c_settings
from lpf.trial_pcb_pattern_c import validate_trial_pcb_pattern_c_branches

BASE=parent.Evaluator
REFERENCE=HERE/"source_exp062_area5p333_best.json"
OLD=ROOT/"data/pareto_snapshots/rf_t008_exp058_area5p333_to_6p667_20261020.json"
REFERENCE_IL=0.8335054302993898
COST=4+2*(2/3)

# Ordered [two GJM, two PCB], all edges distinct. Ground=-1.
LAYOUTS={
 "best_exp062":([(0,1),(4,-1)],[(3,-1),(1,2)]),
 "two_ground_pcb":([(0,1),(1,2)],[(4,-1),(3,-1)]),
 "gjm_n3":([(0,1),(3,-1)],[(4,-1),(1,2)]),
 "bridge_out":([(0,1),(4,-1)],[(3,-1),(0,3)]),
 "gjm_bridge_in":([(0,1),(0,3)],[(4,-1),(3,-1)]),
 "gjm_n3_bridge":([(0,1),(3,-1)],[(4,-1),(0,3)]),
 "pcb_out_ground":([(0,1),(4,-1)],[(3,-1),(2,-1)]),
 "gjm_no_input":([(4,-1),(1,2)],[(0,1),(3,-1)])
}
DTC={
 "two_bridges":((0,3),(1,2)),
 "tip_and_output":((3,-1),(1,2)),
 "tip_and_input":((3,-1),(0,3)),
 "dual_tip_shunts":((3,-1),(4,-1))
}
L_GRAPHS={
 "original":((0,1),(1,3),(1,4),(1,2)),
 "tip3_from_input":((0,1),(0,3),(1,4),(1,2)),
 "output_via_tip4":((0,1),(1,3),(1,4),(4,2))
}
ACTIVE=None

def validate_graph(edges):
    assert len(edges)==len({tuple(sorted(e)) for e in edges})==4
    seen={0}
    for _ in range(5):
        for i,j in edges:
            if i in seen:seen.add(j)
            if j in seen:seen.add(i)
    assert seen==set(range(5)), "4L graph is not a spanning tree"

class Evaluator(BASE):
    def __init__(self,policy,variant,unused,points):
        layout,dtc,graph=ACTIVE
        if variant!="input_output":
            raise ValueError("Internal parent 'input_output' slot must be used")
        super().__init__(policy,"input_output",("cf0",),points)
        gjm,pcb=LAYOUTS[layout]
        caps=tuple(tuple(e) for e in gjm+pcb)
        v_edges=tuple(DTC[dtc])
        if len(caps)!=4 or len(set(caps))!=4 or len(v_edges)!=2 or len(set(v_edges))!=2:
            raise ValueError("Invalid capacitor topology")
        self.fixed_edges=caps
        self.var_edges=v_edges
        self.cap_edges=caps+v_edges+v_edges
        self.BC=parent.old4.incidence(self.cap_edges)
        self.Q_C=np.array([80.,80.]
            +[60. if -1 in e else 40. for e in pcb]
            +[35.,35.,60.,60.],float)
        for i,e in enumerate(caps):
            self.bounds[4+i]=(0.02,100.) if i<2 else ((0.02,1.) if -1 in e else (0.02,0.2))
        for i,e in enumerate(v_edges):
            self.bounds[11+i]=(0.5,3.) if -1 in e else (0.2,3.)
        validate_trial_pcb_pattern_c_branches(policy,[
            dict(parent.norm(e),capacitance_pf=0.1,q=60 if -1 in e else 40)
            for e in pcb])
        self.cache_x,self.cache_il=None,None

# Crucially, optimizer uses 5-node Schur reduction whereas independent_mna
# constructs its own 9x9 branch-current linear equations in parent.
parent.Evaluator=Evaluator

def get_reference():
    data=json.loads(REFERENCE.read_text())
    if data["experiment_id"]!="EXP-062" or abs(data["metrics"]["worst_IL_db"]-REFERENCE_IL)>1e-9:
        raise AssertionError("EXP-062 independently MNA verified baseline not pinned")
    x=np.asarray(data["vector"],float)
    assert x.shape==(25,)
    return x

def get_old():
    data=json.loads(OLD.read_text())
    row=next(v for v in data["selected_candidates"] if abs(v["area"]-COST)<1e-7)
    return np.asarray(row["vector"],float)

def warm_seed(ev,start,layout,dtc,graph):
    vec=get_reference() if start==0 else get_old()
    original_fixed=([(0,1),(4,-1),(3,-1),(1,2)] if start==0 else
                    [(0,1),(4,-1),(1,2),(0,3)])
    original_types=(["GJM","GJM","PCB","PCB"] if start==0 else
        ["GJM" if n in {"cf0","cf1"} else "PCB" for n in
         ("cf0","cf1","cf2","cp")])
    old=dict(((t,tuple(e)),float(v))
            for t,e,v in zip(original_types,original_fixed,vec[4:8]))
    gjm,pcb=LAYOUTS[layout]
    x=vec.copy()
    for i,e in enumerate(gjm+pcb):
        t="GJM" if i<2 else "PCB"
        x[4+i]=old.get((t,tuple(e)),1.5 if t=="GJM" else (.45 if -1 in e else .08))
    old_edges=((0,3),(1,2)) if start==0 else (
        parent.DTC["input_output"] if dtc=="two_bridges" else parent.DTC["shunt_output"])
    orig_fixes=vec[11:13].copy()
    old_cv=vec[13:].reshape(6,2).copy()
    for i,e in enumerate(DTC[dtc]):
        idx=next((j for j,z in enumerate(old_edges) if z==e),None)
        x[11+i]=float(orig_fixes[idx]) if idx is not None else (.55 if -1 in e else .25)
        for setting in range(6):
            x[13+2*setting+i]=float(old_cv[setting,idx]) if idx is not None else (
                0.5 if setting<4 else 0.20)
    if start:
        rng=np.random.default_rng(20261020+17*list(LAYOUTS).index(layout)
             +211*list(DTC).index(dtc)+419*list(L_GRAPHS).index(graph))
        x[:4]*=np.exp(rng.normal(0,.09,4))
        x[4:8]*=np.exp(rng.normal(0,.16,4))
        x[8:11]+=rng.normal(0,.025,3)
        x[11:13]+=rng.normal(0,.1,2)
        x[13:]+=rng.normal(0,.16,12)
    return np.clip(x,ev.bounds[:,0],ev.bounds[:,1])

def stage(ev,x,n,target):
    v,s=optimizer.opt(ev,np.asarray(x,float),n,target)
    return v,{**s,"converged":s["success"],"maxiter":n}

def main():
    a=argparse.ArgumentParser()
    a.add_argument("--layout",required=True,choices=tuple(LAYOUTS))
    a.add_argument("--dtc",required=True,choices=tuple(DTC))
    a.add_argument("--graph",required=True,choices=tuple(L_GRAPHS))
    a.add_argument("--starts",type=int,default=2)
    a.add_argument("--coarse",type=int,default=7)
    a.add_argument("--fine",type=int,default=17)
    a.add_argument("--dense",type=int,default=1001)
    a.add_argument("--target",type=float,default=30.005)
    a.add_argument("--out",type=Path)
    args=a.parse_args()
    if args.starts!=2 or args.dense<101 or min(args.coarse,args.fine)<3 or args.target<30:
        raise ValueError("Invalid EXP-065 execution budget")
    global ACTIVE
    ACTIVE=(args.layout,args.dtc,args.graph)
    validate_graph(L_GRAPHS[args.graph])
    parent.old4.L_EDGES=L_GRAPHS[args.graph]
    policy=load_constraint("RF-T008",allow_trial=True)
    if policy["trial_ic_fixed_c_by_connection"]["max_composite_branches"]!=2:
        raise AssertionError("EXP-065 must use RF-T008 revision 3")
    ev=Evaluator(policy,"input_output",("cf0",),args.dense)
    ec=Evaluator(policy,"input_output",("cf0",),args.coarse)
    ef=Evaluator(policy,"input_output",("cf0",),args.fine)
    if ACTIVE==("best_exp062","two_bridges","original"):
        assert abs(ev.summary(get_reference())["worst_IL_db"]-REFERENCE_IL)<2e-8
    attempts=[]
    for start in range(args.starts):
        row={"start":start}
        try:
            initial=warm_seed(ev,start,*ACTIVE)
            row["initial_vector"]=initial.tolist()
            run=run_termination_aware_slsqp(ec,ef,initial,args.target,stage)
            tiers=[]
            for att in run["attempts"]:
                x=np.asarray(att["vector"],float)
                m=ev.summary(x)
                eligible=bool(att["converged"] and
                              m["min_H2_db"]>=30 and m["min_H3_db"]>=30)
                tiers.append({
                   "tier":att["tier"],"vector":x.tolist(),
                   "coarse":att["coarse"],"fine":att["fine"],
                   "converged":bool(att["converged"]),
                   "finite_30db_pass":bool(m["min_H2_db"]>=30 and m["min_H3_db"]>=30),
                   "eligible":eligible,"dense":m})
            row.update(attempts=tiers,iteration_policy=run["iteration_policy"],
                       recovery_cause=run["recovery_cause"],exception=None)
            print("TRY",*ACTIVE,start,[(z["tier"],z["dense"]["worst_IL_db"],z["eligible"]) for z in tiers],flush=True)
        except (ValueError,ArithmeticError,np.linalg.LinAlgError) as exc:
            row.update(attempts=[],exception={"type":type(exc).__name__,"message":str(exc)})
            print("FAIL",*ACTIVE,start,type(exc).__name__,str(exc),flush=True)
        attempts.append(row)
    compliant=[a for r in attempts for a in r["attempts"] if a["eligible"]]
    best=min(compliant,key=lambda r:r["dense"]["worst_IL_db"]) if compliant else None
    chk=parent.independent_mna(policy,"input_output",("cf0",),
          np.asarray(best["vector"],float)) if best else None
    if chk is not None and not chk["pass"]:
        raise AssertionError("EXP-065 independent 9x9 MNA failure")
    if best:
        x=np.asarray(best["vector"],float)
        validate_ic_fixed_c_settings(policy,[
           dict(parent.norm(e),role="shunt_to_ground" if -1 in e else "bridge")
           for e in ev.var_edges],x[11:13].tolist(),
           dict(zip(parent.CASES,x[13:].reshape(6,2).tolist())))
    report={
       "experiment_id":"EXP-065","phase":"Phase 2","constraint_id":"RF-T008",
       "revision":3,"chip_area":COST,"GJM_count":2,"PCB_count":2,
       "layout":args.layout,"dtc":args.dtc,"graph":args.graph,
       "GJM_edges":LAYOUTS[args.layout][0],"PCB_edges":LAYOUTS[args.layout][1],
       "variable_C_edges":ev.var_edges,"IC_fixed_C_parallel_edges":ev.var_edges,
       "L_edges":L_GRAPHS[args.graph],"physical_row":["L0","L1","L3","L2"],
       "capacitor_Q":ev.Q_C.tolist(),"signed_k_bounds":[-.1,.1],
       "baseline_EXP062_IL_db":REFERENCE_IL,
       "effective_constraint_sha256":constraint_fingerprint(policy),
       "code_execution_sha":subprocess.check_output(["git","rev-parse","HEAD"],
                              cwd=ROOT,text=True).strip(),
       "sampling":{"segments":28,"coarse":args.coarse,"fine":args.fine,
                   "dense":args.dense,"independent_MNA_probes":84},
       "starts":attempts,"best_converged_30db":best,"independent_MNA":chk,
       "limitations":["Local multistart search across 96 predefined joint topologies, not exhaustive",
          "30dB 28x1001 finite sample not continuous-extrema proof",
          "Q(f), SRF, real physical signed coupling k, EM, tolerances, Phase3 not verified"]
    }
    out=args.out or ROOT/"results/EXP-065"/("_".join(ACTIVE)+".json")
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(report,indent=2,ensure_ascii=False,allow_nan=False)+"\n")
    print("RESULT",*ACTIVE,"IL",best["dense"]["worst_IL_db"] if best else "NO_ELIGIBLE",
          "MNA",chk["pass"] if chk is not None else "SKIP",flush=True)

if __name__=="__main__":
    main()

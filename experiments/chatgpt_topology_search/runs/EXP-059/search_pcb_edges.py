#!/usr/bin/env python3
"""EXP-059 RF-T008 v3 Phase2 4L/1GJM PCB-C connection sweep at chip area 4+2/3.

Based on independently verified EXP-058 best two-composite-DTC network.
The fixed L graph, GJM Cf0(0,1), Q25 inductors and signed neighbor k bounds
are preserved. 0..3 physical PCB capacitors may be relocated; Q60 for GND,
Q40 for non-ground. Two DTC Q35 have their own fixed parallel Q60 capacitors.
Original fixed external S2P, six LTE settings and 30dB mandatory rejection.
"""
import argparse
import json
import math
import sys
import subprocess
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path.insert(0, str(ROOT / "experiments/chatgpt_topology_search/runs/EXP-058"))
sys.path.insert(0, str(ROOT / "src"))
import sweep_area4l_gjm as parent
import sweep_area3 as optimizer
from lpf.constraint_versions import load_constraint, constraint_fingerprint
from lpf.trial_pcb_pattern_c import validate_trial_pcb_pattern_c_branches
from lpf.trial_ic_fixed_c import validate_ic_fixed_c_settings

SNAPSHOT = ROOT/"data/pareto_snapshots/rf_t008_exp058_area4p667_20261020.json"
SOURCE_EDGES = ((0,1),(4,-1),(1,2),(0,3))
EDGES = {
    "g4": (4,-1), "g3": (3,-1), "g1": (1,-1), "g2": (2,-1),
    "b12": (1,2), "b03": (0,3), "b42": (4,2), "b32": (3,2),
    "b04": (0,4), "b34": (3,4), "b02": (0,2),
    "off": None,
}
# Exactly 1 GJM stays on IN(0)-N1. Values here identify PCB slots only.
# Positional permutations with identical sets are not counted twice.
LAYOUTS = {
    "control": ("g4","b12","b03"),
    "n3g_for_b12": ("g4","g3","b03"),
    "n3g_for_b03": ("g4","b12","g3"),
    "n4out_for_b12": ("g4","b42","b03"),
    "n4out_for_b03": ("g4","b12","b42"),
    "n3g_and_n4out": ("g4","g3","b42"),
    "n3g_no_n4g": ("g3","b12","b03"),
    "n4out_no_n4g": ("b42","b12","b03"),
    "n3g_n4out_no_n4g": ("g3","b42","b03"),
    "n3g_n4out_keep_b12": ("g3","b12","b42"),
    "n3out_for_b12": ("g4","b32","b03"),
    "n3out_for_b03": ("g4","b12","b32"),
    "n4in_for_b12": ("g4","b04","b03"),
    "n3n4_for_b12": ("g4","b34","b03"),
    "n1g_for_b12": ("g4","g1","b03"),
    "outg_for_b12": ("g4","g2","b03"),
    "inout_for_b12": ("g4","b02","b03"),
    "n4out_n3out": ("g4","b42","b32"),
    "n4in_n3g": ("g4","b04","g3"),
    "n3g_n4out_2pcb": ("g3","b42","off"),
    "n4g_n3g_2pcb": ("g4","g3","off"),
    "n4g_n4out_2pcb": ("g4","b42","off"),
    "n4g_only_1pcb": ("g4","off","off"),
}
CASES = parent.CASES
BASE_CLASS = parent.Evaluator
ACTIVE_LAYOUT = None

def validate_layout(layout):
    assert layout in LAYOUTS
    names = LAYOUTS[layout]
    assert len(names) == 3 and all(x in EDGES for x in names)
    active = [EDGES[x] for x in names if EDGES[x] is not None]
    assert len(active) == len(set(active)) <= 3
    return names

class Evaluator(BASE_CLASS):
    def __init__(self, policy, variant, gjm_names, points):
        if tuple(gjm_names) != ("cf0",):
            raise ValueError("The one GJM is fixed at Cf0(0,1)")
        super().__init__(policy, variant, gjm_names, points)
        if ACTIVE_LAYOUT is None:
            raise ValueError("Missing PCB layout")
        self.pcb_names = validate_layout(ACTIVE_LAYOUT)
        # A disabled slot is an explicit zero-admittance dummy, NOT a PCB
        # component. Its incidence is arbitrary, its C bounds are (0,0).
        pcb_edges = [EDGES[n] if EDGES[n] is not None else (0,1)
                     for n in self.pcb_names]
        self.fixed_edges = ((0,1),) + tuple(pcb_edges)
        self.cap_edges = self.fixed_edges + self.var_edges + self.var_edges
        self.BC = parent.old4.incidence(self.cap_edges)
        qs = [80.]
        for j,name in enumerate(self.pcb_names):
            e = EDGES[name]
            if e is None:
                self.bounds[5+j,:] = (0.,0.)
                qs.append(40.)
            else:
                self.bounds[5+j,:] = ((0.02,1.0) if -1 in e else (0.02,0.2))
                qs.append(60. if -1 in e else 40.)
        self.Q_C = np.array(qs+[35.,35.,60.,60.],float)
        pcb = [dict(parent.norm(EDGES[name]), capacitance_pf=0.1,
                    q=(60 if -1 in EDGES[name] else 40))
               for name in self.pcb_names if name != "off"]
        validate_trial_pcb_pattern_c_branches(policy, pcb)
        self.cache_x,self.cache_il = None,None

# Base independent_MNA reconstructs this Evaluator from scratch and
# explicitly stamps each 4-L branch-current equation (9x9), with the updated
# PCB incidences/Q. This ensures a numerically independent solve from
# Schur-reduced 2-port optimizer.
parent.Evaluator = Evaluator

def seed(ev, v, start, seed_number):
    x = np.asarray(v,float).copy()
    for j,name in enumerate(ev.pcb_names):
        e = EDGES[name]
        if e is None:
            x[5+j] = 0.
        elif e in SOURCE_EDGES[1:]:
            x[5+j] = v[4 + SOURCE_EDGES.index(e)]
        else:
            x[5+j] = 0.55 if -1 in e else 0.10
    # For a new shunt DTC, the old first bridge DTC setting is only an
    # approximate initial guess; the fixed shunt IC capacitor starts at 0.5pF.
    if ev.variant == "shunt_output":
        x[11] = 0.5
    if start > 0:
        rng = np.random.default_rng(seed_number)
        x[:4] *= np.exp(rng.normal(0,0.055,4))
        x[4:8] *= np.exp(rng.normal(0,0.18,4))
        x[8:11] += rng.normal(0,0.012,3)
        x[11:13] += rng.normal(0,0.12,2)
        x[13:] += rng.normal(0,0.12,12)
    return np.clip(x,ev.bounds[:,0],ev.bounds[:,1])

def converged(s):
    a=s["coarse"].get("rescue",s["coarse"])
    b=s["fine"].get("rescue",s["fine"])
    return bool(a["success"] and b["success"])

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--layout",required=True,choices=tuple(LAYOUTS))
    ap.add_argument("--variant",required=True,choices=("input_output","shunt_output"))
    ap.add_argument("--starts",type=int,default=2)
    ap.add_argument("--coarse",type=int,default=7)
    ap.add_argument("--fine",type=int,default=17)
    ap.add_argument("--dense",type=int,default=1001)
    ap.add_argument("--target",type=float,default=30.005)
    ap.add_argument("--out",type=Path)
    a=ap.parse_args()
    if min(a.starts,a.coarse,a.fine,a.dense) < 1 or a.target < 30 or a.dense < 101:
        raise ValueError("Invalid EXP-059 run limits")
    global ACTIVE_LAYOUT
    ACTIVE_LAYOUT=a.layout
    policy=load_constraint("RF-T008",allow_trial=True)
    assert policy["trial_ic_fixed_c_by_connection"]["max_composite_branches"] == 2
    snap=json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    prior=np.array(snap["best"]["vector"],float)
    assert prior.shape==(25,) and abs(snap["best"]["metrics"]["worst_IL_db"]-0.8543674592970051)<1e-10
    full=Evaluator(policy,a.variant,("cf0",),a.dense)
    coarse=Evaluator(policy,a.variant,("cf0",),a.coarse)
    fine=Evaluator(policy,a.variant,("cf0",),a.fine)
    if a.layout=="control" and a.variant=="input_output":
        check=full.summary(prior)
        if abs(check["worst_IL_db"]-snap["best"]["metrics"]["worst_IL_db"])>1e-7:
            raise AssertionError("Frozen EXP-058 best must reproduce exact transfer function")
    rows=[]
    for j in range(a.starts):
        x0=seed(full,prior,j,20261020+1001*list(LAYOUTS).index(a.layout)
                +41*j+(0 if a.variant=="input_output" else 911))
        v,status=optimizer.staged(coarse,fine,x0,a.target)
        m=full.summary(v)
        eligible=bool(m["min_H2_db"]>=30 and m["min_H3_db"]>=30)
        good=bool(eligible and converged(status))
        rows.append({"start":j,"solver":status,"converged":converged(status),
                     "finite_30db_pass":eligible,"eligible_converged":good,
                     "vector":v.tolist(),"dense":m})
        print("TRY",a.layout,a.variant,j,"IL",m["worst_IL_db"],
              "H2",m["min_H2_db"],"H3",m["min_H3_db"],
              "converged",converged(status),"finite30",eligible,flush=True)
    pool=[v for v in rows if v["eligible_converged"]]
    selected=min(pool,key=lambda v:v["dense"]["worst_IL_db"]) if pool else None
    # Also save the best unconverged/failed 30dB candidate, but do not upgrade
    # it to an eligible Pareto solution.
    best30=min((v for v in rows if v["finite_30db_pass"]),
               key=lambda v:v["dense"]["worst_IL_db"],default=None)
    independent=parent.independent_mna(policy,a.variant,("cf0",),
                       np.asarray(selected["vector"],float)) if selected else None
    if independent is not None and not independent["pass"]:
        raise AssertionError("Independent coupled-L 9x9 MNA failed")
    if selected:
        vars=[dict(parent.norm(e),role="shunt_to_ground" if -1 in e else "bridge")
              for e in full.var_edges]
        x=selected["vector"]
        validate_ic_fixed_c_settings(policy,vars,[float(q) for q in x[11:13]],
              dict(zip(CASES,np.asarray(x[13:]).reshape((6,2)).tolist())))
    result={
        "experiment_id":"EXP-059","phase":"Phase 2","constraint_id":"RF-T008",
        "revision":3,"source_EXP058":str(SNAPSHOT.relative_to(ROOT)),
        "source_area":4.666666666666667,"chip_area_units":4+2/3,
        "layout":a.layout,"pcb_slot_names":list(full.pcb_names),
        "pcb_installed_count":sum(n!="off" for n in full.pcb_names),
        "fixed_C_edges":full.fixed_edges,"variable_C_edges":full.var_edges,
        "fixed_IC_edges":full.var_edges,"Q_C":full.Q_C.tolist(),
        "inductor_edges":parent.old4.L_EDGES,"physical_row":["L0","L1","L3","L2"],
        "k_pairs":parent.old4.K_PAIRS,"LQP02HV_Q":25,
        "effective_constraint_sha256":constraint_fingerprint(policy),
        "code_execution_sha":subprocess.check_output(["git","rev-parse","HEAD"],
                            cwd=ROOT,text=True).strip(),
        "grid":{"intervals":28,"coarse":a.coarse,"fine":a.fine,"dense":a.dense,
                "independent_MNA_points_per_interval":3},
        "runs":rows,"best_converged_30db":selected,"best_any_30db":best30,
        "independent_MNA":independent,
        "limitations":["SLSQP local multistart, not global optimum",
                       "Only 28x1001 finite grid for RF pass, no continuous-extrema proof",
                       "No electromagnetic, SRF, Q(f), physical mutual-k simultaneity or tolerance validation",
                       "Unconverged and 30dB failing candidates are not classified as compliant Pareto"]
    }
    out=a.out or ROOT/"results/EXP-059"/(a.layout+"_"+a.variant+".json")
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)+"\n",encoding="utf-8")
    print("RESULT",a.layout,a.variant,
          selected["dense"] if selected else "NO_CONVERGED_30DB",
          "MNA",independent,flush=True)

if __name__=="__main__":
    main()

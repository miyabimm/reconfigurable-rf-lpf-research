#!/usr/bin/env python3
"""EXP-050 RF-T007: first RF-T005 Pareto adaptation, EXP-043 3L / area 3.

Historical original vector remains immutable. RF-T007 adds C=0.5pF Q40 to
every ground-shunt DTC. This topology has only Cv0=(node3,GND); Cv1 and Cv2
bridge the two series inductors and DO NOT receive shunt parasitics.

For this particular graph ONLY, the added fixed Q40 C is parallel to PCB Cp,
which is also Q40, so combining admittances into Cp_eff=Cp+0.5pF yields an
algebraically exact *accelerated optimizer* without changing physical Cp bounds.
Independent branch-current MNA stamps Cp and 0.5pF as DISTINCT lossy branches.
The same shortcut is NOT generally applicable to other T005 Pareto topologies.
"""
import argparse
import json
import math
import subprocess
import sys
from pathlib import Path

import numpy as np
from scipy.optimize import minimize

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
OLD = ROOT / "experiments/chatgpt_topology_search/runs/EXP-043"
sys.path.insert(0, str(OLD))
sys.path.insert(0, str(ROOT / "src"))
import search_3l as historical
from lpf.constraint_versions import load_constraint, constraint_fingerprint
from lpf.trial_shunt_dtc import shunt_dtc_parasitic_branches

CASES = historical.CASES
CONFIG = "zero_gjm_double"
SNAPSHOT = OLD / "checkpoints/zero_gjm_double.json"
PARASITIC_PF = 0.5

class Evaluator(historical.Evaluator):
    """One exact Q40 parallel-admittance fast path for the area-3 topology."""

    def il(self, x):
        z = np.asarray(x, float).copy()
        if len(z) != 26:
            raise ValueError("EXP-043 3L vector must have 26 components")
        z[5] += PARASITIC_PF   # ONLY an electrical calculation, not a PCB-C change
        return super().il(z)

def get_summary(ev, x):
    m = ev.summary(x)
    return {**m,
            "harmonics_30_pass": bool(m["min_H2_db"] >= 30 and m["min_H3_db"] >= 30),
            "chip_area_units": float(ev.area),
            "C_pcb_real_pf": float(x[5]),
            "C_shunt_fixed_parasitic_pf": PARASITIC_PF,
            "C_shunt_effective_Q40_pf": float(x[5] + PARASITIC_PF)}

def independent_mna(ev, x, samples=3):
    """Direct 7x7 branch-current MNA, no reduced-Y/ABCD LPF shortcut.

    Both the PCB Cp and parasitic C0 are distinct dissipative branches.
    Frozen input/output S2P cascades are reduced only to external port Norton
    source/output admittance; independent MNA solves the internal network.
    """
    x = np.asarray(x, float)
    probe = Evaluator(load_constraint("RF-T007", allow_trial=True), CONFIG, samples)
    reduced = probe.il(x)
    max_il_err = 0.
    max_balance = 0.
    min_loss = float("inf")
    eig_min = float("inf")
    q_arr = np.array([40., 40., 40., 35., 35., 35., 40.])
    C_edges = historical.CF_EDGES + historical.CONFIGS[CONFIG][1] + ((3, -1),)
    B = historical.incidence(C_edges)
    L = np.asarray(x[:3], float)
    M = np.diag(L.copy())
    for (i,j), k in zip(((0,2),(2,1)), x[6:8]):
        M[i,j] = M[j,i] = k * math.sqrt(L[i]*L[j])
    eig_min = float(np.linalg.eigvalsh(M)[0])
    if eig_min <= 0:
        raise ValueError("Non-positive inductance matrix")
    H = np.diag(L/25.) + 1j*M
    BL = historical.BL
    for idx, (mhz, setting) in enumerate(zip(probe.f, probe.setting)):
        omega = mhz * 2e6 * math.pi
        values = np.r_[x[3:6], x[8 + 3*setting: 11 + 3*setting], PARASITIC_PF]
        cap_y = omega*1e-12*values/(1/q_arr - 1j)
        tin, tout = probe.pre[idx], probe.post[idx]
        zsrc = 50.
        zload = 60.-40j
        din = tin[0,1] + zsrc*tin[1,1]
        ysrc = (tin[0,0] + zsrc*tin[1,0]) / din
        source = 1./din
        dout = tout[0,0]*zload + tout[0,1]
        yload = (tout[1,0]*zload + tout[1,1]) / dout
        A = np.zeros((7,7), dtype=complex)
        A[:4,:4] = B @ np.diag(cap_y) @ B.T
        A[0,0] += ysrc
        A[2,2] += yload
        A[:4,4:] = BL
        A[4:,:4] = BL.T
        A[4:,4:] = -omega*1e-9*H
        rhs = np.zeros(7,complex)
        rhs[0] = source
        v_i = np.linalg.solve(A,rhs)
        volt,ind = v_i[:4],v_i[4:]
        p_load = zload.real * abs(volt[2]/dout)**2
        il = -10*np.log10(max(200*p_load,1e-300))
        max_il_err = max(max_il_err, abs(il - reduced[idx]))
        current_in = source - ysrc*volt[0]
        vext = tin[0,0]*volt[0] + tin[0,1]*current_in
        iext = tin[1,0]*volt[0] + tin[1,1]*current_in
        p_reflect = abs(1.0 - 100.0*iext)**2/200.0
        p_input = np.real(vext*np.conj(iext) - volt[0]*np.conj(current_in))
        p_output = np.real(volt[2]*np.conj(yload*volt[2])) - p_load
        p_l = np.real(np.vdot(ind, omega*1e-9*H @ ind))
        c_loss_each = cap_y.real * np.abs(B.T@volt)**2
        p_c = float(c_loss_each.sum())
        balance = 1/200.0 - (p_reflect + p_input + p_output + p_l + p_c + p_load)
        max_balance = max(max_balance, abs(balance))
        min_loss = min(min_loss, p_reflect, p_input, p_output, p_l, p_c, p_load,
                       *[float(v) for v in c_loss_each])
    return {
        "model": "7x7 explicit branch-current MNA; Cp and DTC shunt parasitic distinct",
        "total_probe_points": int(len(probe.f)),
        "max_IL_error_db": float(max_il_err),
        "max_power_balance_residual_W": float(max_balance),
        "minimum_component_dissipation_W": float(min_loss),
        "min_coupled_L_eigenvalue_nH": eig_min,
        "pass": bool(max_il_err < 1e-8 and max_balance < 1e-9 and
                     min_loss > -1e-10 and eig_min > 0),
    }

def opt_stage(ev, start, maxiter, target):
    initial = np.r_[start, ev.summary(start)["worst_IL_db"]]
    bounds = [tuple(v) for v in ev.bounds] + [(0., 100.)]
    def residual(z):
        vals = ev.il(z[:-1])
        return np.where(ev.role == 0, z[-1]-vals, vals-target)
    sol = minimize(lambda z: float(z[-1]), initial, method="SLSQP",
                   bounds=bounds, constraints={"type":"ineq","fun":residual},
                   options={"maxiter":maxiter,"ftol":3e-9})
    x = np.clip(sol.x[:-1], ev.bounds[:,0],ev.bounds[:,1])
    return x, {
        "success": bool(sol.success),
        "message": str(sol.message),
        "iterations": int(sol.nit),
        "function_evaluations": int(sol.nfev),
        "coarse_min_slack_db": float(np.min(residual(sol.x))),
    }

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--starts", type=int, default=2)
    p.add_argument("--maxiter", type=int, default=100)
    p.add_argument("--coarse", type=int, default=9)
    p.add_argument("--refine", type=int, default=21)
    p.add_argument("--dense", type=int, default=1001)
    p.add_argument("--mna-points", type=int, default=3)
    p.add_argument("--target", type=float, default=30.02)
    p.add_argument("--out", type=Path)
    a = p.parse_args()
    if a.starts < 1 or a.maxiter < 1 or a.dense < 101 or a.target < 30:
        raise ValueError("Invalid EXP-050 experiment budget")
    policy = load_constraint("RF-T007", allow_trial=True)
    old_policy = load_constraint("RF-T005", allow_trial=True)
    spec = policy["trial_shunt_dtc_parasitic"]
    if spec["fixed_capacitance_pf"] != 0.5 or spec["q"] != 40:
        raise ValueError("Unexpected RF-T007 parasitic")
    # API ground=0; EXP-043 source ground=-1 and signal node 0..3.
    # Shift each signal-node label by +1 before applying the policy helper.
    branch_labels = [
        {"a": 4, "b": 0, "role": "shunt_to_ground"}, # Cv0: source node3-GND
        {"a": 1, "b": 2, "role": "bridge"},         # Cv1: source node0-node1
        {"a": 2, "b": 3, "role": "bridge"},         # Cv2: source node1-node2
    ]
    fixed = shunt_dtc_parasitic_branches(policy,branch_labels)
    if len(fixed) != 1 or fixed[0]["node"] != 4:
        raise ValueError("Area3 must get exactly one shunt parasitic")
    old_vec = np.asarray(json.loads(SNAPSHOT.read_text())["vector"], float)
    if len(old_vec) != 26:
        raise ValueError("Invalid preserved source vector")
    old_ev = historical.Evaluator(old_policy, CONFIG, a.dense)
    old_result = old_ev.summary(old_vec)
    if abs(old_result["worst_IL_db"] - 0.9442683633443218) > 1e-5:
        raise AssertionError("Original RF-T005 frozen checkpoint reproduction failed")
    ev = Evaluator(policy, CONFIG, a.dense)
    baseline = get_summary(ev, old_vec)
    compensated = old_vec.copy()
    compensated[8::3] = np.maximum(0., compensated[8::3] - 0.5)
    comp_eval = get_summary(ev, compensated)
    starts = [old_vec, compensated]
    if a.starts > 2:
        rng = np.random.default_rng(20261019)
        for j in range(a.starts-2):
            z = compensated.copy()
            z[:3] *= np.exp(rng.normal(0,.06,3))
            z[6:8] += rng.normal(0,.01,2)
            z[8:] += rng.normal(0,.08,18)
            starts.append(np.clip(z,ev.bounds[:,0],ev.bounds[:,1]))
    coarse = Evaluator(policy, CONFIG, a.coarse)
    fine = Evaluator(policy, CONFIG, a.refine)
    results = []
    valid_pool = [
        {"start":"unchanged", "vector":old_vec.tolist(), "dense":baseline,
         "stage":"frozen_unoptimized"},
        {"start":"compensated_Cv0", "vector":compensated.tolist(), "dense":comp_eval,
         "stage":"heuristic_unoptimized"},
    ]
    for j, initial in enumerate(starts[:a.starts]):
        try:
            c, cs = opt_stage(coarse,initial,a.maxiter,a.target)
            f, fs = opt_stage(fine,c,max(60,a.maxiter//2),a.target)
            dense = get_summary(ev,f)
            row = {"start":j,"coarse":cs,"refined":fs,"dense":dense,
                   "vector":f.tolist(),"stage":"SLSQP_locally_optimized"}
        except (ValueError, np.linalg.LinAlgError) as exc:
            row = {"start":j, "stage":"failed", "error":str(exc)}
        results.append(row)
        if "dense" in row:
            valid_pool.append(row)
        print("RUN",j,row.get("dense"),flush=True)
    admissible = [r for r in valid_pool if r["dense"]["harmonics_30_pass"]]
    best = min(admissible,key=lambda r:r["dense"]["worst_IL_db"]) if admissible else None
    if best:
        independent = independent_mna(ev,np.asarray(best["vector"],float),a.mna_points)
        if not independent["pass"]:
            raise AssertionError("Independent 7x7 MNA failed")
        disposition = "numerically_30dB_compliant_on_finite_grid"
    else:
        independent = None
        disposition = "no_verified_30dB_candidate_in_implemented_local_search"
    report = {
        "experiment_id":"EXP-050",
        "constraint_id":"RF-T007",
        "original_constraint":"RF-T005",
        "phase":2,
        "step":"1_of_6_area3",
        "topology":"EXP-043 zero_gjm_double 3 LQP02HV / 0 GJM / 3 PCB-C / 3 Cv",
        "chip_area":3,
        "fixed_shunt_parasitics":[{"variable_branch":"Cv0", "node":3,
             "ground":-1, "fixed_pf":0.5,"q":40}],
        "other_variable_branches_not_parasitic":["Cv1","Cv2"],
        "effective_policy_sha256":constraint_fingerprint(policy),
        "code_commit":subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT).decode().strip(),
        "historical_source_file":str(SNAPSHOT.relative_to(ROOT)),
        "source_original_exact_vector":old_vec.tolist(),
        "evaluation":{"segments":28,"dense_points_per_segment":a.dense,
                      "mna_probe_points_per_segment":a.mna_points},
        "historical_t005_saved_metrics":old_result,
        "rf_t007_unchanged_vector":baseline,
        "rf_t007_compensated_Cv0_vector":comp_eval,
        "local_optimization":results,
        "selected":best,
        "independent_MNA":independent,
        "disposition":disposition,
        "limitations":["Phase2 constant-Q lumped model",
                       "Finite-grid only; no global optimum guarantee",
                       "No tolerance, SRF, EM or physical DTC implementation verification",
                       "Other five Pareto topology adaptations NOT performed by this run"],
    }
    out = a.out or ROOT/"results/EXP-050/area3_rft007.json"
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("RESULT",out, "DISPOSITION",disposition, "BEST",
          best["dense"] if best else None,flush=True)

if __name__ == "__main__":
    main()

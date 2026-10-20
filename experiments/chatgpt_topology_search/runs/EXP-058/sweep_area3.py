#!/usr/bin/env python3
"""EXP-058 Phase 2 RF-T008 v3, chip area 3: three 3L T-type DTC pairs.

Model: frozen external S2P / 50 Ohm source / 60-j40 Ohm load.
Each of exactly two installed DTC branches has distinct parallel:
  fixed Q60 C (same across settings) and variable Q35 C (per setting).
No old RF-T007 0.5pF/Q40 parasitic. Every PCB C uses connection-aware Q.
Phase2 nominal continuous C. No Phase3 switch modelling.
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
sys.path.insert(0, str(ROOT / "experiments/chatgpt_topology_search/runs/EXP-043"))
sys.path.insert(0, str(ROOT / "src"))
import search_3l as old
from lpf.constraint_versions import load_constraint, constraint_fingerprint
from lpf.trial_pcb_pattern_c import validate_trial_pcb_pattern_c_branches
from lpf.trial_ic_fixed_c import validate_ic_fixed_c_settings

ORIGINAL = ROOT / "experiments/chatgpt_topology_search/runs/EXP-043/checkpoints/zero_gjm_double.json"
VARIANTS = {
    "shunt_input": (0, 1),
    "shunt_output": (0, 2),
    "dual_series": (1, 2),
}
ALL_VAR_EDGES = ((3, -1), (0, 1), (1, 2))
PCB_EDGES = old.CF_EDGES


def norm_edge(edge):
    # This trial validator uses ground=0; old 3L circuit uses -1.
    return {"a": edge[0] + 1, "b": edge[1] + 1}


class Evaluator(old.Evaluator):
    def __init__(self, policy, variant, points):
        self.variant = variant
        self.ids = VARIANTS[variant]
        self.variable_edges = tuple(ALL_VAR_EDGES[j] for j in self.ids)
        self.fixed_ic_edges = self.variable_edges
        super().__init__(policy, "zero_gjm_double", points)
        self.cap_edges = PCB_EDGES + self.variable_edges + self.fixed_ic_edges
        self.BC = old.incidence(self.cap_edges)
        self.Q_C = np.array((40., 40., 60., 35., 35., 60., 60.), float)
        # Vector: L3, PCB C3, chip neighboring k2, IC fixed C2, six x IC variable C2.
        self.bounds = np.array(
            [(0.4, 27.)] * 3
            + [(0.02, 0.2), (0.02, 0.2), (0.02, 1.0)]
            + [(-0.1, 0.1)] * 2
            + [(0.5, 3.) if -1 in edge else (0.2, 3.)
               for edge in self.variable_edges]
            + [(0., 3.)] * 12, float)
        self.area = 3.
        pcb = [dict(norm_edge(edge), capacitance_pf=0.1,
                    q=60 if -1 in edge else 40)
               for edge in PCB_EDGES]
        validate_trial_pcb_pattern_c_branches(policy, pcb)
        self.policy = policy

    def il(self, x):
        x = np.asarray(x, float)
        if x.shape != (22,):
            raise ValueError("RF-T008 3L area3 vector must contain 22 values")
        if self.cache_x is not None and np.array_equal(self.cache_x, x):
            return self.cache_il
        n = len(self.f)
        K, M, H = self.matrices(x)
        if np.linalg.eigvalsh(M)[0] <= 0:
            raise ValueError("Non-positive coupled-inductor matrix")
        Y = np.broadcast_to(K, (n, 4, 4)).copy() / (self.omega[:, None, None] * 1e-9)
        cv = x[10:].reshape((6, 2))[self.setting]
        caps = np.column_stack((
            np.broadcast_to(x[3:6], (n, 3)),
            cv,
            np.broadcast_to(x[8:10], (n, 2)),
        ))
        yc = self.omega[:, None] * 1e-12 * caps / (1/self.Q_C[None, :] - 1j)
        Y += np.einsum("nb,ib,jb->nij", yc, self.BC, self.BC, optimize=True)
        ports, interior = [0, 2], [1, 3]
        P = Y[:, ports, :][:, :, ports]
        U = Y[:, ports, :][:, :, interior]
        V = Y[:, interior, :][:, :, ports]
        E = Y[:, interior, :][:, :, interior]
        red = P - U @ np.linalg.solve(E, V)
        a, b, c, d = red[:,0,0], red[:,0,1], red[:,1,0], red[:,1,1]
        if np.any(np.abs(c) < 1e-20):
            raise ValueError("Singular port admittance")
        t = np.empty((n,2,2), complex)
        t[:,0,0] = -d/c
        t[:,0,1] = -1/c
        t[:,1,0] = -(a*d-b*c)/c
        t[:,1,1] = -a/c
        complete = self.pre @ t @ self.post
        zl, zs = 60. - 40j, 50.
        den = (complete[:,0,0]*zl + complete[:,0,1]
               + zs*(complete[:,1,0]*zl + complete[:,1,1]))
        gain = 4*zs*zl.real / np.abs(den)**2
        result = -10*np.log10(np.maximum(gain, 1e-300))
        self.cache_x, self.cache_il = x.copy(), result
        return result


def seed(ev, old_vec, jitter):
    x = np.zeros(22)
    x[:8] = old_vec[:8]
    x[8:10] = [0.5 if -1 in e else 0.2 for e in ev.variable_edges]
    for s in range(6):
        for j, source_id in enumerate(ev.ids):
            old_v = old_vec[8+3*s+source_id]
            x[10+2*s+j] = max(0, old_v - x[8+j])
    if jitter:
        rng = np.random.default_rng(20261020 + sum(ev.ids))
        x[:3] *= np.exp(rng.normal(0, 0.07, 3))
        x[3:6] *= np.exp(rng.normal(0, 0.14, 3))
        x[6:8] += rng.normal(0, 0.01, 2)
        x[8:10] += rng.normal(0, 0.2, 2)
        x[10:] += rng.normal(0, 0.15, 12)
    return np.clip(x, ev.bounds[:,0], ev.bounds[:,1])


def opt(ev, start, niter, target):
    v0 = np.r_[start, ev.summary(start)["worst_IL_db"]]
    b = [tuple(v) for v in ev.bounds] + [(0., 100.)]
    def slacks(v):
        y = ev.il(v[:-1])
        return np.where(ev.role == 0, v[-1] - y, y - target)
    sol = minimize(lambda v: float(v[-1]), v0, method="SLSQP",
                   bounds=b, constraints={"type":"ineq","fun":slacks},
                   options={"maxiter":niter, "ftol":3e-9})
    return np.clip(sol.x[:-1], ev.bounds[:,0], ev.bounds[:,1]), {
        "success": bool(sol.success),
        "status": int(sol.status),
        "message": str(sol.message),
        "nit": int(sol.nit),
        "nfev": int(sol.nfev),
        "minimum_sample_slack_db": float(np.min(slacks(sol.x))),
        "iteration_limit": bool(sol.status == 9 or "iteration limit reached" in str(sol.message).lower()),
    }


def staged(ev0, ev1, x, target):
    a, s0 = opt(ev0, x, 240, target)
    if s0["iteration_limit"]:
        a, retry = opt(ev0, a, 500, target)
        s0["rescue"] = retry
        b, s1 = opt(ev1, a, 280, target)
    else:
        b, s1 = opt(ev1, a, 120, target)
        if s1["iteration_limit"]:
            b, retry = opt(ev1, b, 280, target)
            s1["rescue"] = retry
    return b, {"coarse": s0, "fine": s1}


def independent_mna(ev, vector, policy, variant):
    probe = Evaluator(policy, variant, 3)
    reference = probe.il(vector)
    n = len(probe.f)
    edges = probe.cap_edges
    B = old.incidence(edges)
    BL = old.BL
    L = np.asarray(vector[:3], float)
    M = np.diag(L.copy())
    for (i,j), k in zip(((0,2),(2,1)), vector[6:8]):
        M[i,j] = M[j,i] = k*math.sqrt(L[i]*L[j])
    H = np.diag(L/25) + 1j*M
    eig = float(np.linalg.eigvalsh(M)[0])
    maxerr, maxres, minloss = 0., 0., float("inf")
    for idx,(mhz,setting) in enumerate(zip(probe.f,probe.setting)):
        w = 2e6*math.pi*mhz
        caps = np.r_[vector[3:6], vector[10+2*setting:12+2*setting], vector[8:10]]
        yc = w*1e-12*caps/(1/probe.Q_C-1j)
        inp, outp = probe.pre[idx], probe.post[idx]
        zs, zl = 50., 60.-40j
        din = inp[0,1] + zs*inp[1,1]
        ysrc = (inp[0,0]+zs*inp[1,0])/din
        source = 1/din
        dout = outp[0,0]*zl + outp[0,1]
        yload = (outp[1,0]*zl+outp[1,1])/dout
        A = np.zeros((7,7), complex)
        A[:4,:4] = B @ np.diag(yc) @ B.T
        A[0,0] += ysrc
        A[2,2] += yload
        A[:4,4:] = BL
        A[4:,:4] = BL.T
        A[4:,4:] = -w*1e-9*H
        rhs = np.zeros(7,complex)
        rhs[0] = source
        solution = np.linalg.solve(A,rhs)
        v, i = solution[:4], solution[4:]
        p_load = zl.real*abs(v[2]/dout)**2
        il = -10*np.log10(max(200*p_load,1e-300))
        maxerr=max(maxerr,abs(il-reference[idx]))
        current_in=source-ysrc*v[0]
        vext=inp[0,0]*v[0]+inp[0,1]*current_in
        iext=inp[1,0]*v[0]+inp[1,1]*current_in
        reflected=abs(1.-100.*iext)**2/200.
        pin=np.real(vext*np.conj(iext)-v[0]*np.conj(current_in))
        pout=np.real(v[2]*np.conj(yload*v[2]))-p_load
        pl=np.real(np.vdot(i,w*1e-9*H@i))
        closs=yc.real*abs(B.T@v)**2
        pc=float(sum(closs))
        residual=1/200.-(reflected+pin+pout+pl+pc+p_load)
        maxres=max(maxres,abs(residual))
        minloss=min(minloss,reflected,pin,pout,pl,pc,p_load,*closs)
    return {"probe_points": n, "max_IL_difference_db": maxerr,
            "max_power_balance_residual_W": maxres,
            "min_component_dissipation_W": float(minloss),
            "min_L_matrix_eigenvalue_nH": eig,
            "pass": bool(eig>0 and maxerr<1e-8 and maxres<1e-9 and minloss>-1e-10)}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--variant",choices=tuple(VARIANTS),required=True)
    parser.add_argument("--starts",type=int,default=2)
    parser.add_argument("--coarse",type=int,default=7)
    parser.add_argument("--fine",type=int,default=17)
    parser.add_argument("--dense",type=int,default=1001)
    parser.add_argument("--target",type=float,default=30.005)
    parser.add_argument("--out",type=Path)
    arg=parser.parse_args()
    if min(arg.starts,arg.coarse,arg.fine,arg.dense) < 1 or arg.target < 30 or arg.dense < 101:
        raise ValueError("Invalid search budget")
    policy=load_constraint("RF-T008",allow_trial=True)
    assert policy["trial_ic_fixed_c_by_connection"]["max_composite_branches"]==2
    assert policy["components"]["IC_VARIABLE_C"]["max_branches_principle"]==2
    orig=np.asarray(json.loads(ORIGINAL.read_text())["vector"],float)
    if len(orig)!=26:
        raise ValueError("Historical 3L seed corrupt")
    dense=Evaluator(policy,arg.variant,arg.dense)
    coarse=Evaluator(policy,arg.variant,arg.coarse)
    fine=Evaluator(policy,arg.variant,arg.fine)
    rows=[]
    for j in range(arg.starts):
        initial=seed(dense,orig,j)
        z, status=staged(coarse,fine,initial,arg.target)
        metrics=dense.summary(z)
        eligible=bool(metrics["min_H2_db"]>=30 and metrics["min_H3_db"]>=30)
        row={"start":j,"solver":status,"vector":z.tolist(),"dense":metrics,
             "finite_30db_pass":eligible}
        rows.append(row)
        print("START",arg.variant,j,"IL",metrics["worst_IL_db"],
              "H2",metrics["min_H2_db"],"H3",metrics["min_H3_db"],flush=True)
    valid=[r for r in rows if r["finite_30db_pass"]]
    best=min(valid,key=lambda v:v["dense"]["worst_IL_db"]) if valid else None
    independent=independent_mna(dense,np.asarray(best["vector"]),policy,arg.variant) if best else None
    if independent is not None and not independent["pass"]:
        raise AssertionError("Independent 7x7 MNA / power check failed")
    if best is not None:
        br=[{"a":norm_edge(edge)["a"],"b":norm_edge(edge)["b"],
             "role":"shunt_to_ground" if -1 in edge else "bridge"}
            for edge in dense.variable_edges]
        fixed=[float(v) for v in np.asarray(best["vector"])[8:10]]
        var=np.asarray(best["vector"])[10:].reshape((6,2))
        validate_ic_fixed_c_settings(policy,br,fixed,dict(zip(old.CASES,var.tolist())))
    record={
        "experiment_id":"EXP-058","phase":"Phase 2","constraint_id":"RF-T008",
        "revision":3,"area_chip_units":3.0,"variant":arg.variant,
        "fixed_C_edges":PCB_EDGES,"variable_C_edges":dense.variable_edges,
        "composite_IC_fixed_C_edges":dense.fixed_ic_edges,
        "component_Qs":dense.Q_C.tolist(),"physical_chip_row":["L0","Ls","L1"],
        "reference_source":str(ORIGINAL.relative_to(ROOT)),
        "model":"two distinct Q60/Q35 capacitor admittances per DTC; PCB ground Q60, other Q40; no T007 parasitic",
        "effective_constraint_sha256":constraint_fingerprint(policy),
        "code_sha":subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip(),
        "sampling":{"intervals":28,"coarse":arg.coarse,"fine":arg.fine,"dense":arg.dense,"independent_per_interval":3},
        "starts":rows,"best_finite_30db":best,"independent_MNA":independent,
        "conclusions":"Finite-grid best-found only; 35dB and 0.3dB targets independently checked",
        "limitations":["Local SLSQP only; no infeasibility/global-optimum proof",
                       "No continuous-frequency extrema guarantee",
                       "No SRF/Q(f), real PCB area, EM, manufacture tolerances or Phase3"],
    }
    output=arg.out or ROOT/"results/EXP-058"/(arg.variant+".json")
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(record,ensure_ascii=False,indent=2,allow_nan=False)+"\n")
    print("RESULT",output,"candidate",best["dense"] if best else "NONE",flush=True)


if __name__=="__main__":
    main()

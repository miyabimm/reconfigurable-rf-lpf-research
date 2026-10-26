"""RF-T008 v3 3L composite-DTC evaluator extracted from EXP-058."""
import math
import numpy as np
from lpf.trial_pcb_pattern_c import validate_trial_pcb_pattern_c_branches
from scipy.optimize import minimize
from ._grid import ROOT, CASES, ThreeLGrid, THREE_L_FIXED_EDGES, THREE_L_BL, incidence

ORIGINAL = ROOT / "experiments/chatgpt_topology_search/runs/EXP-043/checkpoints/zero_gjm_double.json"
VARIANTS = {
    "shunt_input": (0, 1),
    "shunt_output": (0, 2),
    "dual_series": (1, 2),
}
ALL_VAR_EDGES = ((3, -1), (0, 1), (1, 2))
PCB_EDGES = THREE_L_FIXED_EDGES


def norm_edge(edge):
    # This trial validator uses ground=0; old 3L circuit uses -1.
    return {"a": edge[0] + 1, "b": edge[1] + 1}


class Evaluator(ThreeLGrid):
    def __init__(self, policy, variant, points, gjm_position=None):
        self.variant = variant
        self.gjm_position = gjm_position
        self.gjm_positions = (() if gjm_position is None else ((gjm_position,) if isinstance(gjm_position,int) else tuple(gjm_position)))
        self.ids = VARIANTS[variant]
        self.variable_edges = tuple(ALL_VAR_EDGES[j] for j in self.ids)
        self.fixed_ic_edges = self.variable_edges
        super().__init__(policy, points)
        self.cap_edges = PCB_EDGES + self.variable_edges + self.fixed_ic_edges
        self.BC = incidence(self.cap_edges)
        self.Q_C = np.array([80. if j in self.gjm_positions else (60. if -1 in edge else 40.) for j,edge in enumerate(PCB_EDGES)] + [35.,35.,60.,60.], float)
        # Vector: L3, PCB C3, chip neighboring k2, IC fixed C2, six x IC variable C2.
        self.bounds = np.array(
            [(0.4, 27.)] * 3
            + [(0.02, 100.) if j in self.gjm_positions else ((0.02, 1.) if -1 in edge else (0.02, 0.2)) for j,edge in enumerate(PCB_EDGES)]
            + [(-0.1, 0.1)] * 2
            + [(0.5, 3.) if -1 in edge else (0.2, 3.)
               for edge in self.variable_edges]
            + [(0., 3.)] * 12, float)
        self.area = 3. + (2./3.) * len(self.gjm_positions)
        pcb = [dict(norm_edge(edge), capacitance_pf=0.1,
                    q=60 if -1 in edge else 40)
               for j,edge in enumerate(PCB_EDGES) if j not in self.gjm_positions]
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
    probe = Evaluator(policy, variant, 3, ev.gjm_position)
    reference = probe.il(vector)
    n = len(probe.f)
    edges = probe.cap_edges
    B = incidence(edges)
    BL = THREE_L_BL
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



"""RF-T007 coupled 4L forward evaluator extracted from EXP-055.

Legacy solver results remain as originally recorded; independent 9x9 MNA
checks are kept separate from the forward model.
"""
import math
import numpy as np
from scipy.optimize import minimize
from ._grid import ROOT, CASES as SHARED_CASES, incidence as incidence_edges, SampledExternalEvaluator

# Branch L0,L1,L2,L3; single physical row L0-L1-L3-L2.
L_EDGES = ((0,1),(1,3),(1,4),(1,2))
K_PAIRS = ((0,1),(1,3),(3,2))
# Optional third DTC is ALWAYS between two non-ground signal nodes.
VARIANTS = {
    "two_dtc": None,
    "cv1_input_output": (0,2),
    "cv1_input_parallel_L0": (0,1),
    "cv1_input_tip": (0,3),
    "cv1_tip_output": (3,2),
    "cv1_output_shunt_tip": (2,4),
}
# Cf0 GJM, Cf1 GJM, Cf2 PCB, Cp PCB, Cv0/Cv1/Cv2 Q35, Cpar Q40.
Q_C = np.array([80.,80.,40.,40.,35.,35.,35.,40.])
CASES = SHARED_CASES

def incidence(edges):
    return incidence_edges(edges, nodes=5)

def capacitor_edges(name):
    if name not in VARIANTS:
        raise KeyError(name)
    cv1 = VARIANTS[name] if VARIANTS[name] is not None else (0,2)
    return ((0,1),(4,-1),(1,2),(0,3),
            (3,-1),cv1,(1,2),(3,-1))

def bounds(name):
    x = np.array([(0.4,27.)]*4 + [(0.02,100.),(0.02,100.),
            (0.02,0.2),(0.02,0.2)] + [(-0.1,0.1)]*3
            + [(0.,3.)]*18, float)
    if name == "two_dtc":
        for i in range(6):
            x[12+3*i] = (0.,0.)  # source-vector Cv1 slots are placeholders.
    assert x.shape == (29,2)
    return x

def inductance(x):
    L = np.asarray(x[:4],float)
    M = np.diag(L.copy())
    for (a,b),k in zip(K_PAIRS,x[8:11]):
        M[a,b] = M[b,a] = k*math.sqrt(L[a]*L[b])
    eig = float(np.linalg.eigvalsh(M)[0])
    if eig <= 0:
        raise ValueError("Non-positive inductance matrix")
    H = np.diag(L/25.) + 1j*M
    BL = incidence(L_EDGES)
    return BL@np.linalg.solve(H,BL.T), M, H, BL

class Evaluator(SampledExternalEvaluator):
    def __init__(self,policy,points,name,with_parasitic=True):
        super().__init__(policy,points)
        self.name = name
        self.with_parasitic = bool(with_parasitic)
        self.L_edges = L_EDGES
        self.BC = incidence(capacitor_edges(name))
        self.bounds = bounds(name)
        self.cache_x = self.cache_il = None

    def il(self,x):
        x = np.asarray(x,float)
        if x.shape != (29,):
            raise ValueError("Expected EXP-047 full 29 element parameter vector")
        if self.cache_x is not None and np.array_equal(self.cache_x,x):
            return self.cache_il
        K,_,_,_ = inductance(x)
        n = len(self.f)
        Y = np.broadcast_to(K,(n,5,5)).copy()/(self.omega[:,None,None]*1e-9)
        cv = x[11:].reshape(6,3)[self.setting]
        caps = np.column_stack((np.broadcast_to(x[4:8],(n,4)),
                                 cv,np.full(n,0.5 if self.with_parasitic else 0.0)))
        y = self.omega[:,None]*1e-12*caps/(1/Q_C[None,:]-1j)
        Y += np.einsum("nb,ib,jb->nij",y,self.BC,self.BC,optimize=True)
        outer=[0,2]; mid=[1,3,4]
        A=Y[:,outer,:][:,:,outer]
        B=Y[:,outer,:][:,:,mid]
        C=Y[:,mid,:][:,:,outer]
        D=Y[:,mid,:][:,:,mid]
        R=A-B@np.linalg.solve(D,C)
        a,b,c,d=R[:,0,0],R[:,0,1],R[:,1,0],R[:,1,1]
        if np.any(abs(c)<1e-21):
            raise ValueError("Singular two port")
        T=np.empty((n,2,2),complex)
        T[:,0,0]=-d/c; T[:,0,1]=-1/c
        T[:,1,0]=-(a*d-b*c)/c; T[:,1,1]=-a/c
        chain=self.pre@T@self.post
        zl=60-40j
        den=chain[:,0,0]*zl+chain[:,0,1]+50*(chain[:,1,0]*zl+chain[:,1,1])
        value=-10*np.log10(np.maximum(200*zl.real/abs(den)**2,1e-300))
        self.cache_x=x.copy(); self.cache_il=value
        return value

    def summary(self,x):
        v=self.il(x); idx=[]
        for role in (0,1,2):
            w=np.flatnonzero(self.role==role)
            idx.append(int(w[np.argmax(v[w]) if role==0 else np.argmin(v[w])]))
        mineig=float(np.linalg.eigvalsh(inductance(np.asarray(x,float))[1])[0])
        return {"worst_IL_db":float(v[idx[0]]),
                "min_H2_db":float(v[idx[1]]),"min_H3_db":float(v[idx[2]]),
                "locations":[{"setting":CASES[self.setting[i]],
                              "MHz":float(self.f[i]),"segment":int(self.segment[i])}
                             for i in idx],
                "min_M_eigenvalue_nH":mineig,
                "finite_H2H3_30dB_pass":bool(v[idx[1]]>=30 and v[idx[2]]>=30)}

def independent_mna(policy,x,name,points):
    """Independent explicit 5-node / 4-coupled-L-current 9x9 MNA."""
    ev=Evaluator(policy,points,name,True)
    fast=ev.il(x)
    _,M,H,BL=inductance(x)
    BC=ev.BC
    max_delta=max_residual=0.
    minimum_passive=float("inf")
    for j,(f,case) in enumerate(zip(ev.f,ev.setting)):
        w=2e6*np.pi*f
        values=np.r_[x[4:8],x[11+3*case:14+3*case],0.5]
        yc=w*1e-12*values/(1/Q_C-1j)
        pre,post=ev.pre[j],ev.post[j]
        zl=60-40j
        din=pre[0,1]+50*pre[1,1]
        Ys=(pre[0,0]+50*pre[1,0])/din
        source=1/din
        dout=post[0,0]*zl+post[0,1]
        Yload=(post[1,0]*zl+post[1,1])/dout
        A=np.zeros((9,9),complex)
        A[:5,:5]=BC@np.diag(yc)@BC.T
        A[0,0]+=Ys; A[2,2]+=Yload
        A[:5,5:]=BL; A[5:,:5]=BL.T
        A[5:,5:]=-w*1e-9*H
        rhs=np.zeros(9,complex); rhs[0]=source
        ans=np.linalg.solve(A,rhs)
        v,curr=ans[:5],ans[5:]
        Pload=zl.real*abs(v[2]/dout)**2
        il=-10*np.log10(max(200*Pload,1e-300))
        max_delta=max(max_delta,abs(il-fast[j]))
        iin=source-Ys*v[0]
        vext=pre[0,0]*v[0]+pre[0,1]*iin
        iext=pre[1,0]*v[0]+pre[1,1]*iin
        refl=abs(1-100*iext)**2/200
        ppre=float(np.real(vext*np.conj(iext)-v[0]*np.conj(iin)))
        ppost=float(np.real(v[2]*np.conj(Yload*v[2]))-Pload)
        pl=float(np.sum(w*1e-9*x[:4]/25*abs(curr)**2))
        pc_each=yc.real*abs(BC.T@v)**2
        pc=float(np.sum(pc_each))
        max_residual=max(max_residual,abs(.005-(refl+ppre+ppost+pl+pc+Pload)))
        minimum_passive=min(minimum_passive,refl,ppre,ppost,pl,pc,Pload,
                            *[float(q) for q in pc_each])
    return {"method":"independent 9x9 KCL/KVL coupled-L MNA",
            "probes":int(len(ev.f)),
            "max_IL_difference_db":float(max_delta),
            "max_power_balance_W":float(max_residual),
            "minimum_passive_W":float(minimum_passive),
            "min_L_eigenvalue_nH":float(np.linalg.eigvalsh(M)[0]),
            "pass":bool(max_delta<1e-8 and max_residual<1e-9
                        and minimum_passive>-1e-10 and np.linalg.eigvalsh(M)[0]>0)}

def make_starts(seed,name,n,rng):
    starts=[seed.copy()]
    compensated=seed.copy()
    for s in range(6):
        compensated[11+3*s]=max(0.,seed[11+3*s]-.5)
        if name!="two_dtc":
            compensated[12+3*s]=0.10
    if n>=2:
        starts.append(compensated)
    for j in range(2,n):
        x=compensated.copy()
        x[:4]*=np.exp(rng.normal(0,.08 if j==2 else .16,4))
        x[4:8]*=np.exp(rng.normal(0,.10 if j==2 else .20,4))
        x[8:11]+=rng.normal(0,.012 if j==2 else .023,3)
        x[11:]+=rng.normal(0,.10 if j==2 else .20,18)
        starts.append(np.clip(x,bounds(name)[:,0],bounds(name)[:,1]))
    return starts

def optimize_stage(ev,start,maxiter,target):
    z=np.asarray(start,float)
    vmax=ev.summary(z)["worst_IL_db"]
    initial=np.r_[z,vmax]
    limits=[tuple(v) for v in ev.bounds]+[(0.,100.)]
    def slack(w):
        values=ev.il(w[:-1])
        return np.where(ev.role==0,w[-1]-values,values-target)
    sol=minimize(lambda w:float(w[-1]),initial,method="SLSQP",
      bounds=limits,constraints={"type":"ineq","fun":slack},
      options={"maxiter":maxiter,"ftol":2e-9})
    vec=np.clip(sol.x[:-1],ev.bounds[:,0],ev.bounds[:,1])
    return vec,{"converged":bool(sol.success),"message":str(sol.message),
      "iterations":int(sol.nit),"function_evaluations":int(sol.nfev),
      "coarse_min_slack_dB":float(np.min(slack(sol.x)))}

"""RF-T008 v3 4L no-GJM composite-DTC evaluator extracted from EXP-058."""
import math
import numpy as np
from lpf.trial_pcb_pattern_c import validate_trial_pcb_pattern_c_branches
from ._grid import ROOT
from . import exp055 as old4
from . import exp058_area3 as optim

CASES=old4.CASES
SOURCE=ROOT/"experiments/chatgpt_topology_search/runs/EXP-047/area5p333_g2_independent_28x1001_20261017.json"
ALL_FIXED=((0,1),(4,-1),(1,2),(0,3))
DTC={
    "shunt_output":((3,-1),(1,2)),
    "shunt_input":((3,-1),(0,3)),
    "input_output":((0,3),(1,2)),
}
REMOVE={"cf0":0,"cf1":1,"cf2":2,"cp":3}


def norm(e):
    return {"a":e[0]+1,"b":e[1]+1}


def inductance(v, *, l_edges=old4.L_EDGES):
    L=np.asarray(v[:4],float)
    M=np.diag(L.copy())
    for (a,b),k in zip(old4.K_PAIRS,v[7:10]):
        M[a,b]=M[b,a]=k*math.sqrt(L[a]*L[b])
    eig=float(np.linalg.eigvalsh(M)[0])
    if eig<=0:raise ValueError("Inductor matrix not SPD")
    H=np.diag(L/25.)+1j*M
    BL=old4.InductorTree(5,l_edges).incidence()
    return BL@np.linalg.solve(H,BL.T),M,H,BL


class Evaluator(old4.Evaluator):
    def __init__(self,policy,variant,removed,points,*,l_edges=old4.L_EDGES):
        super().__init__(policy,points,"two_dtc",False,l_edges=l_edges)
        self.variant,self.removed=variant,removed
        self.fixed_edges=tuple(e for i,e in enumerate(ALL_FIXED) if i!=REMOVE[removed])
        self.var_edges=DTC[variant]
        self.cap_edges=self.fixed_edges+self.var_edges+self.var_edges
        self.BC=old4.incidence(self.cap_edges)
        self.Q_C=np.array([60 if -1 in e else 40 for e in self.fixed_edges]+[35,35,60,60],float)
        self.bounds=np.array(
            [(0.4,27.)]*4
            + [(0.02,1.) if -1 in e else (0.02,0.2) for e in self.fixed_edges]
            + [(-0.1,0.1)]*3
            + [(0.5,3.) if -1 in e else (0.2,3.) for e in self.var_edges]
            + [(0.,3.)]*12,float)
        self.cache_x=self.cache_il=None
        pcbs=[dict(norm(e),capacitance_pf=0.1,q=(60 if -1 in e else 40))
              for e in self.fixed_edges]
        validate_trial_pcb_pattern_c_branches(policy,pcbs)

    def il(self,x):
        x=np.asarray(x,float)
        if x.shape!=(24,):raise ValueError("Four-L area4 vector must be 24 elements")
        if self.cache_x is not None and np.array_equal(self.cache_x,x):return self.cache_il
        K,_,_,_=inductance(x,l_edges=self.inductor_tree)
        n=len(self.f)
        Y=np.broadcast_to(K,(n,5,5)).copy()/(self.omega[:,None,None]*1e-9)
        cv=x[12:].reshape(6,2)[self.setting]
        caps=np.column_stack((np.broadcast_to(x[4:7],(n,3)),cv,
                              np.broadcast_to(x[10:12],(n,2))))
        adm=self.omega[:,None]*1e-12*caps/(1/self.Q_C[None,:]-1j)
        Y+=np.einsum("nb,ib,jb->nij",adm,self.BC,self.BC,optimize=True)
        port=[0,2];interior=[1,3,4]
        P=Y[:,port,:][:,:,port]
        U=Y[:,port,:][:,:,interior]
        V=Y[:,interior,:][:,:,port]
        E=Y[:,interior,:][:,:,interior]
        R=P-U@np.linalg.solve(E,V)
        a,b,c,d=R[:,0,0],R[:,0,1],R[:,1,0],R[:,1,1]
        if np.any(abs(c)<1e-21):raise ValueError("Singular transfer matrix")
        T=np.empty((n,2,2),complex)
        T[:,0,0]=-d/c;T[:,0,1]=-1/c
        T[:,1,0]=-(a*d-b*c)/c;T[:,1,1]=-a/c
        chain=self.pre@T@self.post
        zl=60-40j
        den=chain[:,0,0]*zl+chain[:,0,1]+50*(chain[:,1,0]*zl+chain[:,1,1])
        val=-10*np.log10(np.maximum(200*zl.real/abs(den)**2,1e-300))
        self.cache_x,self.cache_il=x.copy(),val
        return val

    def summary(self,x):
        y=self.il(x);ext=[]
        for role in (0,1,2):
            indices=np.flatnonzero(self.role==role)
            ext.append(int(indices[np.argmax(y[indices]) if role==0 else np.argmin(y[indices])]))
        return {"worst_IL_db":float(y[ext[0]]),"min_H2_db":float(y[ext[1]]),
            "min_H3_db":float(y[ext[2]]),
            "locations":[{"setting":CASES[self.setting[i]],"mhz":float(self.f[i]),
                          "segment":int(self.segment[i])} for i in ext],
            "L_eig_min_nH":float(np.linalg.eigvalsh(inductance(x,l_edges=self.inductor_tree)[1])[0])}


def seed(ev,oldseed,randomized=False):
    x=np.zeros(24)
    x[:4]=oldseed[:4]
    x[4:7]=[oldseed[4+i] for i in range(4) if i!=REMOVE[ev.removed]]
    x[7:10]=oldseed[8:11]
    x[10:12]=[0.5 if -1 in e else 0.2 for e in ev.var_edges]
    for s in range(6):
        for j,e in enumerate(ev.var_edges):
            if e==(3,-1):v=oldseed[11+3*s]
            elif e==(1,2):v=oldseed[13+3*s]
            else:v=0.55*oldseed[13+3*s]
            x[12+2*s+j]=max(0,v-x[10+j])
    if randomized:
        rg=np.random.default_rng(20261020+24+len(ev.variant)+REMOVE[ev.removed])
        x[:4]*=np.exp(rg.normal(0,0.07,4))
        x[4:7]*=np.exp(rg.normal(0,0.2,3))
        x[7:10]+=rg.normal(0,0.01,3)
        x[10:12]+=rg.normal(0,0.12,2)
        x[12:]+=rg.normal(0,0.12,12)
    return np.clip(x,ev.bounds[:,0],ev.bounds[:,1])


def independent_mna(policy,variant,removed,x,*,l_edges=old4.L_EDGES):
    ev=Evaluator(policy,variant,removed,3,l_edges=l_edges)
    expected=ev.il(x)
    _,M,H,BL=inductance(x,l_edges=ev.inductor_tree)
    B=ev.BC
    err=res=0.
    minpassive=float("inf")
    for j,(mhz,setting) in enumerate(zip(ev.f,ev.setting)):
        w=2e6*math.pi*mhz
        cap=np.r_[x[4:7],x[12+2*setting:14+2*setting],x[10:12]]
        adm=w*1e-12*cap/(1/ev.Q_C-1j)
        pre,post=ev.pre[j],ev.post[j]
        zl=60-40j
        din=pre[0,1]+50*pre[1,1]
        Ysrc=(pre[0,0]+50*pre[1,0])/din
        source=1/din
        dout=post[0,0]*zl+post[0,1]
        Yload=(post[1,0]*zl+post[1,1])/dout
        A=np.zeros((9,9),complex)
        A[:5,:5]=B@np.diag(adm)@B.T
        A[0,0]+=Ysrc;A[2,2]+=Yload
        A[:5,5:]=BL;A[5:,:5]=BL.T
        A[5:,5:]=-w*1e-9*H
        right=np.zeros(9,complex);right[0]=source
        ans=np.linalg.solve(A,right)
        v,i=ans[:5],ans[5:]
        Pload=zl.real*abs(v[2]/dout)**2
        il=-10*np.log10(max(200*Pload,1e-300))
        err=max(err,abs(il-expected[j]))
        iin=source-Ysrc*v[0]
        vext=pre[0,0]*v[0]+pre[0,1]*iin
        iext=pre[1,0]*v[0]+pre[1,1]*iin
        reflected=abs(1-100*iext)**2/200
        ppre=float(np.real(vext*np.conj(iext)-v[0]*np.conj(iin)))
        ppost=float(np.real(v[2]*np.conj(Yload*v[2]))-Pload)
        pl=float(np.real(np.vdot(i,w*1e-9*H@i)))
        pc_each=adm.real*abs(B.T@v)**2
        pc=float(pc_each.sum())
        res=max(res,abs(.005-(reflected+ppre+ppost+pl+pc+Pload)))
        minpassive=min(minpassive,reflected,ppre,ppost,pl,pc,Pload,*pc_each)
    eig=float(np.linalg.eigvalsh(M)[0])
    return {"probes":len(ev.f),"max_IL_difference_db":float(err),
        "max_power_residual_W":float(res),"min_component_dissipation_W":float(minpassive),
        "L_matrix_min_eigenvalue_nH":eig,
        "pass":bool(err<1e-8 and res<1e-9 and minpassive>-1e-10 and eig>0)}



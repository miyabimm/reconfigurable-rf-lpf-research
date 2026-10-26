"""RF-T005 C-H30p0002 forward evaluator extracted from EXP-042.

Original EXP-042 run code remains unchanged; this is a stable import API.
"""
import csv
import json
from pathlib import Path
import numpy as np
from lpf.port_parasitics import get_two_port_s, s_to_abcd
from ._grid import ROOT
HERE = ROOT / "experiments/chatgpt_topology_search/runs/EXP-042"

CASES = ("B71", "B12", "B28", "B13+B14", "B26", "B8")
L_EDGES = ((0,1), (1,3), (1,4), (1,2))  # L0,L1,L2,L3; nodes 1..5 mapped 0..4
C_EDGES = ((0,1), (4,-1), (1,2), (0,3),
           (3,-1), (4,-1), (1,2))  # Cf0,Cf1,Cf2,Cp,Cv0,Cv1,Cv2
L_ORDER = (0,1,3,2)  # L0-L1-L3-L2
Q_C = np.asarray((80.,80.,80.,40.,35.,35.,35.))
BOUNDS = tuple([(0.4,27.)]*4 + [(0.0001,100.)]*3 +
               [(0.02,0.2)] + [(-0.1,0.1)]*3 + [(0.,3.)]*18)

def incidence(edges):
    b = np.zeros((5,len(edges)))
    for i,(a,c) in enumerate(edges):
        b[a,i] = 1.
        if c >= 0: b[c,i] = -1.
    return b

BL, BC = incidence(L_EDGES), incidence(C_EDGES)

def matrices(x):
    L = np.asarray(x[:4],float)
    M = np.diag(L.copy())
    for i,k in enumerate(x[8:11]):
        a,b = L_ORDER[i:i+2]
        M[a,b]=M[b,a]=k*np.sqrt(L[a]*L[b])
    eig = float(np.linalg.eigvalsh(M)[0])
    if eig <= 0: raise ValueError("Non-passive coupled inductance matrix")
    H = np.diag(L/25.) + 1j*M
    return BL @ np.linalg.solve(H,BL.T),eig

def rows():
    with (ROOT/"data/bands.csv").open(newline="",encoding="utf-8") as f:
        data=list(csv.DictReader(f))
    assert len(data)==28
    return data

class Evaluator:
    def __init__(self,policy,n):
        records=rows()
        freq=[]; settings=[]; role=[]; segment=[]
        for seg,r in enumerate(records):
            f=np.linspace(float(r["low_mhz"]),float(r["high_mhz"]),n)
            freq.extend(f)
            settings.extend([CASES.index(r["case"])]*n)
            role.extend([0 if r["type"]=="pass" else
                         1 if r["region"]=="H2" else 2]*n)
            segment.extend([seg]*n)
        self.f=np.asarray(freq)
        self.omega=self.f*2e6*np.pi
        self.setting=np.asarray(settings,dtype=int)
        self.role=np.asarray(role,dtype=int)
        self.segment=np.asarray(segment,dtype=int)
        self.pre=np.asarray([s_to_abcd(get_two_port_s(
            policy,"input_parasitic",float(f*1e6),root=ROOT)) for f in self.f])
        self.post=np.asarray([s_to_abcd(get_two_port_s(
            policy,"output_parasitic",float(f*1e6),root=ROOT)) for f in self.f])
        self.prev=None; self.prev_il=None

    def il(self,x):
        x=np.asarray(x,float)
        if self.prev is not None and np.array_equal(self.prev,x):
            return self.prev_il
        K,_=matrices(x)
        Y=np.broadcast_to(K,(len(self.f),5,5)).copy()
        Y/=(self.omega[:,None,None]*1e-9)
        cv=x[11:].reshape((6,3))[self.setting]
        cap=np.column_stack((np.broadcast_to(x[4:8],(len(self.f),4)),cv))
        yc=(self.omega[:,None]*1e-12*cap/(1/Q_C[None,:]-1j))
        Y+=np.einsum("nb,ib,jb->nij",yc,BC,BC,optimize=True)
        ports=[0,2]; interior=[1,3,4]
        P=Y[:,ports,:][:,:,ports]
        U=Y[:,ports,:][:,:,interior]
        V=Y[:,interior,:][:,:,ports]
        E=Y[:,interior,:][:,:,interior]
        red=P-U @ np.linalg.solve(E,V)
        a,b,c,d=red[:,0,0],red[:,0,1],red[:,1,0],red[:,1,1]
        if np.any(np.abs(c)<1e-17): raise ValueError("Undefined ABCD")
        lpf=np.empty((len(self.f),2,2),complex)
        lpf[:,0,0]=-d/c
        lpf[:,0,1]=-1/c
        lpf[:,1,0]=-(a*d-b*c)/c
        lpf[:,1,1]=-a/c
        t=self.pre @ lpf @ self.post
        zl=60.-40j; zs=50.
        den=t[:,0,0]*zl+t[:,0,1]+zs*(t[:,1,0]*zl+t[:,1,1])
        out=-10*np.log10(np.maximum(4*zs*zl.real/np.abs(den)**2,1e-300))
        self.prev,self.prev_il=x.copy(),out
        return out

    def summary(self,x):
        vals=self.il(x)
        indices=[]
        for role in range(3):
            ii=np.flatnonzero(self.role==role)
            indices.append(int(ii[np.argmax(vals[ii]) if role==0 else np.argmin(vals[ii])]))
        names=("worst_il_db","min_h2_db","min_h3_db")
        return {**{n:float(vals[i]) for n,i in zip(names,indices)},
                "critical":[{"case":CASES[self.setting[i]],
                             "frequency_mhz":float(self.f[i]),
                             "segment":int(self.segment[i])} for i in indices],
                "M_min_eig_nH":matrices(x)[1]}

def policy_and_seed():
    reg=json.loads((ROOT/"data/constraints/registry.json").read_text())
    assert reg["active_formal_id"]=="RF-F003"
    assert reg["trial"]["RF-T005"]["base_constraint_id"]=="RF-F003"
    p=json.loads((ROOT/"data/constraints/formal/RF-F003.json").read_text())
    assert p["components"]["IC_VARIABLE_C"]["q"]==35
    assert p["components"]["IC_VARIABLE_C"]["max_total_variable_pf_per_branch"]==3
    assert p["coupling_limits"]["chip_chip_strong_adjacent_abs_k_max"]==.1
    assert p["external_port_parasitics"]["status"]=="mandatory_fixed_precomputed_touchstone_S2P"
    doc=json.loads((HERE/"preliminary_js_5pt.json").read_text())
    assert doc["experiment"]=="EXP-042" and doc["constraint_id"]=="RF-T005"
    v=doc["vector"]
    seed=np.r_[v["L_nH"],v["fixed_C_pF"],v["k_adjacent"],
               np.asarray(v["variable_C_by_setting_pF"]).ravel()]
    assert seed.size==29
    return p,seed

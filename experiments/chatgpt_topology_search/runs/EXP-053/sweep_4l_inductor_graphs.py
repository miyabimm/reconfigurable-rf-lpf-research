#!/usr/bin/env python3
"""EXP-053: true 4L electrical-graph exploration under RF-T007, Phase 2.

Vary ONLY four-inductor terminal connections, not capacitor/DTC connections,
chip area, DTC count, GJM/PCB count, RF-T007 or physical coupling numeric cap.
Owner specifically excluded improving H2/H3 beyond mandatory 30 dB and
studying physical mutual-k realization.  Numerical |k|<=0.10 and inductance
matrix SPD remain required algebraic validity conditions.

Fixed-C network from EXP-052 best:
 Cf0 GJM/Q80 between (0,1), Cf1 PCB/Q40 between (0,2),
 Cp GJM/Q80 between (4,-1); Cv0 Q35 (4,-1), Cv1 Q35 (0,1),
 Cv2 Q35 (1,2); one separate fixed 0.5pF/Q40 (4,-1).
Input S2P, output S2P, source/load and six-band settings are unchanged.

Each graph has five active vertices 0,1,2,3,4, with four LQP02HV/Q25
edges and row physical coupling neighbors (L0,LsA),(LsA,LsB),(LsB,L1).
"""
import argparse
import json
import math
import subprocess
import sys
from pathlib import Path

import numpy as np

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
EXP51=ROOT/"experiments/chatgpt_topology_search/runs/EXP-051"
SOURCE=HERE/"reference_exp052_cf1_bridge.json"
sys.path.insert(0,str(EXP51))
sys.path.insert(0,str(ROOT/"src"))
import optimize_one_shunt_4l as exp51
from lpf.constraint_versions import constraint_fingerprint,load_constraint
from lpf.trial_shunt_dtc import shunt_dtc_parasitic_branches

# All are spanning trees with no unused/floating inductor node. No two graphs
# share the same four undirected L connections.
GRAPHS={
  "reference": ((0,1),(1,2),(1,3),(3,4)),
  "shunt_from_input": ((0,1),(1,2),(0,3),(3,4)),
  "shunt_from_output": ((0,1),(1,2),(2,3),(3,4)),
  "split_input_shunt_center": ((0,3),(1,2),(3,1),(1,4)),
  "split_output_shunt_center": ((0,1),(3,2),(1,3),(1,4)),
  "split_input_shunt_output": ((0,3),(1,2),(3,1),(2,4)),
  "split_output_shunt_output": ((0,1),(3,2),(1,3),(2,4)),
  "shunt_mid_tap_after_output": ((0,1),(3,2),(1,3),(3,4)),
  "line_to_shunt_via_output": ((0,1),(1,3),(3,4),(4,2)),
  "line_through_shunt_node": ((0,3),(3,1),(1,4),(4,2)),
  "reordered_chain_output": ((0,1),(1,4),(4,3),(3,2)),
  "output_branch_input_tap": ((0,3),(3,2),(3,1),(1,4)),
}
# Cf0, Cf1, Cp, Cv0, Cv1, Cv2, fixed shunt parasitic.
C_EDGES=((0,1),(0,2),(4,-1),(4,-1),(0,1),(1,2),(4,-1))
C_Q=np.array([80.,40.,80.,35.,35.,35.,40.],float)
BC=exp51.incidence(C_EDGES)
COUPLINGS=((0,2),(2,3),(3,1))
BOUNDS=exp51.bounds(False)
CASES=exp51.CASES
HARD_MIN_DB=30.0

def validate_graph(graph):
    """Undirected connected loop-free five-node graph, all L branches active."""
    if len(graph)!=4:raise ValueError("Four inductors required")
    parent=list(range(5))
    def root(a):
        while a!=parent[a]:
            a=parent[a]
        return a
    for a,b in graph:
        if a==b or not(0<=a<5 and 0<=b<5):raise ValueError("Bad L edge")
        ra,rb=root(a),root(b)
        if ra==rb:raise ValueError("Loop or duplicate L edge")
        parent[ra]=rb
    if len(set(root(x) for x in range(5)))!=1:
        raise ValueError("Disconnected L graph")

def inductance(x,L_edges):
    L=np.asarray(x[:4],float)
    M=np.diag(L.copy())
    for (a,b),k in zip(COUPLINGS,x[8:11]):
        M[a,b]=M[b,a]=k*math.sqrt(L[a]*L[b])
    eigen=float(np.linalg.eigvalsh(M)[0])
    if eigen<=0:raise ValueError("L inductance matrix not positive definite")
    H=np.diag(L/25.)+1j*M
    bl=exp51.incidence(L_edges)
    return bl@np.linalg.solve(H,bl.T),M,H,bl

class Evaluator(exp51.Evaluator):
    def __init__(self,policy,points,name):
        if name not in GRAPHS:raise KeyError(name)
        super().__init__(policy,points,False)
        self.name=name
        self.L_edges=GRAPHS[name]
        self.BL=exp51.incidence(self.L_edges)
        self.cache_x=None
        self.cache_il=None

    def il(self,x):
        x=np.asarray(x,float)
        if x.shape!=(29,):raise ValueError("Expected EXP-052 29-element source vector")
        if self.cache_x is not None and np.array_equal(self.cache_x,x):
            return self.cache_il
        K,_,_,_=inductance(x,self.L_edges)
        n=len(self.f)
        Y=np.broadcast_to(K,(n,5,5)).copy()/(self.omega[:,None,None]*1e-9)
        cv=x[11:].reshape(6,3)[self.setting]
        caps=np.column_stack((np.broadcast_to(x[4:7],(n,3)),cv,
                              np.full(n,.5)))
        y=self.omega[:,None]*1e-12*caps/(1/C_Q[None,:]-1j)
        Y+=np.einsum("nb,ib,jb->nij",y,BC,BC,optimize=True)
        ports=[0,2];interior=[1,3,4]
        A=Y[:,ports,:][:,:,ports]
        B=Y[:,ports,:][:,:,interior]
        C=Y[:,interior,:][:,:,ports]
        D=Y[:,interior,:][:,:,interior]
        reduced=A-B@np.linalg.solve(D,C)
        a,b,c,d=reduced[:,0,0],reduced[:,0,1],reduced[:,1,0],reduced[:,1,1]
        if np.any(np.abs(c)<1e-21):raise ValueError("Degenerate 2-port")
        T=np.empty((n,2,2),complex)
        T[:,0,0]=-d/c
        T[:,0,1]=-1/c
        T[:,1,0]=-(a*d-b*c)/c
        T[:,1,1]=-a/c
        combined=self.pre@T@self.post
        zl=60-40j
        den=combined[:,0,0]*zl+combined[:,0,1]+50*(
              combined[:,1,0]*zl+combined[:,1,1])
        il=-10*np.log10(np.maximum(200*zl.real/abs(den)**2,1e-300))
        self.cache_x=x.copy()
        self.cache_il=il
        return il

    def summary(self,x):
        values=self.il(x)
        idx=[]
        for r in (0,1,2):
            relevant=np.flatnonzero(self.role==r)
            i=int(relevant[np.argmax(values[relevant]) if r==0
                            else np.argmin(values[relevant])])
            idx.append(i)
        eigen=float(np.linalg.eigvalsh(inductance(np.asarray(x,float),self.L_edges)[1])[0])
        return {"worst_IL_db":float(values[idx[0]]),
                "min_H2_db":float(values[idx[1]]),
                "min_H3_db":float(values[idx[2]]),
                "locations":[{"setting":CASES[self.setting[i]],
                              "MHz":float(self.f[i]),"segment":int(self.segment[i])} for i in idx],
                "L_matrix_min_eig_nH":eigen}

def full_metrics(evaluator,x):
    m=evaluator.summary(x)
    return {**m,"hard_H2H3_30dB_pass":
               bool(m["min_H2_db"]>=HARD_MIN_DB and m["min_H3_db"]>=HARD_MIN_DB),
            "chip_area":5+1/3,"grounded_DTC_fixed_Cpar_count":1}

def independent_MNA(policy,x,graph,points):
    """Separate 9×9 KCL+KVL solver, not network Y->ABCD elimination."""
    ev=Evaluator(policy,points,graph)
    primary=ev.il(x)
    _,M,H,BL=inductance(np.asarray(x,float),ev.L_edges)
    eigen=float(np.linalg.eigvalsh(M)[0])
    largest_IL_error=largest_balance=0.
    min_passive=float("inf")
    for j,(MHz,setting) in enumerate(zip(ev.f,ev.setting)):
        w=2e6*np.pi*MHz
        cc=np.r_[x[4:7],x[11+3*setting:14+3*setting],.5]
        Yc=w*1e-12*cc/(1/C_Q-1j)
        pre,post=ev.pre[j],ev.post[j]
        zl=60-40j
        in_denom=pre[0,1]+50*pre[1,1]
        Ys=(pre[0,0]+50*pre[1,0])/in_denom
        Is=1/in_denom
        out_denom=post[0,0]*zl+post[0,1]
        Yl=(post[1,0]*zl+post[1,1])/out_denom
        A=np.zeros((9,9),complex)
        A[:5,:5]=BC@np.diag(Yc)@BC.T
        A[0,0]+=Ys
        A[2,2]+=Yl
        A[:5,5:]=BL
        A[5:,:5]=BL.T
        A[5:,5:]=-w*1e-9*H
        rhs=np.zeros(9,complex);rhs[0]=Is
        ans=np.linalg.solve(A,rhs)
        v,i=ans[:5],ans[5:]
        Pload=zl.real*abs(v[2]/out_denom)**2
        IL=-10*np.log10(max(200*Pload,1e-300))
        largest_IL_error=max(largest_IL_error,abs(IL-primary[j]))
        iin=Is-Ys*v[0]
        vext=pre[0,0]*v[0]+pre[0,1]*iin
        iext=pre[1,0]*v[0]+pre[1,1]*iin
        reflected=abs(1-100*iext)**2/200
        pin=float(np.real(vext*np.conj(iext)-v[0]*np.conj(iin)))
        pout=float(np.real(v[2]*np.conj(Yl*v[2]))-Pload)
        pind=float(np.sum(w*1e-9*np.asarray(x[:4])/25*abs(i)**2))
        caps_loss=Yc.real*abs(BC.T@v)**2
        pcap=float(caps_loss.sum())
        balance=0.005-(reflected+pin+pout+pind+pcap+Pload)
        largest_balance=max(largest_balance,abs(balance))
        min_passive=min(min_passive,reflected,pin,pout,pind,pcap,Pload,
                        *[float(q) for q in caps_loss])
    return {"method":"independent 9x9 coupled-L branch-current MNA",
            "points":int(len(ev.f)),
            "max_IL_delta_db":float(largest_IL_error),
            "max_power_residual_W":float(largest_balance),
            "min_component_power_W":float(min_passive),
            "min_L_eigenvalue_nH":eigen,
            "pass":bool(largest_IL_error<1e-8 and largest_balance<1e-9
                        and min_passive>-1e-10 and eigen>0)}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--starts",type=int,default=2)
    p.add_argument("--maxiter",type=int,default=160)
    p.add_argument("--coarse",type=int,default=7)
    p.add_argument("--fine",type=int,default=17)
    p.add_argument("--dense",type=int,default=1001)
    p.add_argument("--mna",type=int,default=3)
    p.add_argument("--target",type=float,default=30.005)
    p.add_argument("--graphs",nargs="*",choices=list(GRAPHS),default=list(GRAPHS))
    p.add_argument("--out",type=Path)
    a=p.parse_args()
    if min(a.starts,a.maxiter,a.coarse,a.fine,a.dense,a.mna)<1 or a.target<30:
        raise ValueError("Bad experiment parameters")
    if not a.graphs or len(set(a.graphs))!=len(a.graphs):raise ValueError("Invalid selected graphs")
    unique=set()
    for name,edges in GRAPHS.items():
        validate_graph(edges)
        normalized=frozenset(tuple(sorted(edge)) for edge in edges)
        if normalized in unique:raise AssertionError("Duplicate electrical graph "+name)
        unique.add(normalized)
    policy=load_constraint("RF-T007",allow_trial=True)
    fixed=shunt_dtc_parasitic_branches(policy,[
       {"a":5,"b":0,"role":"shunt_to_ground"},
       {"a":1,"b":2,"role":"bridge"},
       {"a":2,"b":3,"role":"bridge"}])
    if len(fixed)!=1 or fixed[0]["node"]!=5:
        raise AssertionError("RF-T007 fixed parasitic requires one 0.5pF Q40 shunt")
    old=json.loads(SOURCE.read_text(encoding="utf-8"))
    if old["constraint_id"]!="RF-T007" or old["candidate_id"]!="EXP052-T007-4L-CF1-INPUT-OUTPUT-001":
        raise AssertionError("Wrong source snapshot")
    seed=np.asarray(old["vector"],float)
    if seed.shape!=(29,) or abs(seed[7])>1e-12:
        raise AssertionError("Source vector needs absent trap and 29 values")
    sourceIL=float(old["numerical"]["worst_IL_db"])
    ref=Evaluator(policy,a.dense,"reference")
    r=full_metrics(ref,seed)
    if abs(r["worst_IL_db"]-sourceIL)>1e-6:
        raise AssertionError("Failed to reproduce EXP-052 saved reference")
    original_e=exp51.Evaluator(policy,a.dense,False)
    # EXP-051 has a different PCB Cf1 location; should NOT match exactly
    # and is NOT the correct comparator for this experiment.
    source_error=float(abs(r["worst_IL_db"]-sourceIL))
    report={"experiment_id":"EXP-053","constraint_id":"RF-T007",
      "phase":"Phase 2","study":"4L inductor electrical-graph changes",
      "source_EXP052_checkpoint":str(SOURCE.relative_to(ROOT)),
      "source_EXP052_candidate_id":old["candidate_id"],
      "source_EXP052_original_IL_db":sourceIL,
      "reference_reproduction_error_db":source_error,
      "fixed_C_graph":C_EDGES[:3],
      "variable_C_graph":C_EDGES[3:6],
      "permanent_Cpar_edge":C_EDGES[6],
      "C_Q":C_Q.tolist(),"chip_area_units":5+1/3,
      "fixed_num_L":4,"source_load":"50ohm / 60-j40ohm with fixed S2P",
      "internal_H2H3_guard_db":a.target,
      "hard_H2H3_min_db":30.0,
      "no_extra_margin_objective":True,"no_physical_k_realizability_study":True,
      "constraint_fingerprint":constraint_fingerprint(policy),
      "execution_sha":subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip(),
      "settings":list(CASES),"models":{},
      "grid":{"segments":28,"coarse":a.coarse,"fine":a.fine,"dense":a.dense,"mna":a.mna},
      "limitations":["Local multi-start numerical observations, not a global topology optimum",
         "28x1001-point finite pass only and independent 28x3 9x9 MNA",
         "Physical coupling feasibility and extra H2/H3 margin optimization excluded by user",
         "No Q(f), SRF, PCB EM, component tolerance or Phase3 verification"]}
    rng=np.random.default_rng(20261019+53)
    ranked=[]
    for name in a.graphs:
        coarse=Evaluator(policy,a.coarse,name)
        fine=Evaluator(policy,a.fine,name)
        dense=ref if name=="reference" else Evaluator(policy,a.dense,name)
        trials=[]
        starts=[seed.copy()]
        for j in range(a.starts-1):
            z=seed.copy()
            z[:4]*=np.exp(rng.normal(0,.09 if j==0 else .18,4))
            z[4:7]*=np.exp(rng.normal(0,.11 if j==0 else .21,3))
            z[8:11]+=rng.normal(0,.012 if j==0 else .025,3)
            z[11:]+=rng.normal(0,.13 if j==0 else .22,18)
            starts.append(np.clip(z,BOUNDS[:,0],BOUNDS[:,1]))
        for j,start in enumerate(starts):
            try:
                xc,c1=exp51.optimize_stage(coarse,start,a.maxiter,a.target)
                xf,c2=exp51.optimize_stage(fine,xc,max(80,a.maxiter//2),a.target)
                row={"start":j,"coarse":c1,"fine":c2,
                     "converged":bool(c1["converged"] and c2["converged"]),
                     "vector":xf.tolist(),"metrics":full_metrics(dense,xf)}
            except (ValueError,np.linalg.LinAlgError,OverflowError) as ex:
                row={"start":j,"failed":str(ex),"converged":False}
            trials.append(row)
            print("TRY",name,j,row.get("metrics",{}).get("worst_IL_db"),
                  row.get("metrics",{}).get("min_H2_db"),
                  row.get("metrics",{}).get("min_H3_db"),
                  "CONVERGED",row["converged"],flush=True)
        feasible=[x for x in trials if x.get("metrics",{}).get("hard_H2H3_30dB_pass")]
        best=min(feasible,key=lambda q:q["metrics"]["worst_IL_db"]) if feasible else None
        verified=independent_MNA(policy,np.asarray(best["vector"]),name,a.mna) if best else None
        if verified and not verified["pass"]:
            raise AssertionError("Independent 9x9 failed for graph "+name)
        report["models"][name]={"L_edges":GRAPHS[name],"trials":trials,
           "best_strict_H2H3_30dB":best,"independent_MNA":verified,
           "status":"finite_30dB_PASS" if best else "no_feasible_local_result"}
        if best:
            ranked.append({"graph":name,"worst_IL_db":best["metrics"]["worst_IL_db"],
                           "min_H2_db":best["metrics"]["min_H2_db"],
                           "min_H3_db":best["metrics"]["min_H3_db"],
                           "solver_converged":best["converged"]})
        print("GRAPH",name,"BEST",None if best is None else best["metrics"]["worst_IL_db"],
              "MNA",None if verified is None else verified["pass"],flush=True)
    ranked.sort(key=lambda q:q["worst_IL_db"])
    report["summary"]={"graph_count":len(a.graphs),"starts":len(a.graphs)*a.starts,
       "feasible_graphs":len(ranked),"ranked":ranked,
       "reference_IL_db":sourceIL}
    dest=a.out or ROOT/"results/EXP-053/inductor_graph_sweep.json"
    dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("FINAL",str(dest),"RANKED",ranked,flush=True)

if __name__=="__main__":
    main()

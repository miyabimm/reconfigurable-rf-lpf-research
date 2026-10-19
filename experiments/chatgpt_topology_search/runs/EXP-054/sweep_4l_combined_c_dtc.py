#!/usr/bin/env python3
"""EXP-054: RF-T007 4L simultaneous fixed-C and non-ground DTC edge redesign.

Hold EXP-053 best 4L graph and all installed component counts fixed.
Rewire Cf0 GJM/Q80, Cf1 PCB/Q40, Cp GJM/Q80 and Cv1,Cv2/Q35 in
pre-registered pairs/triples. Cv0 stays (4,GND), including distinct
fixed 0.5pF/Q40 Cpar independent of switch state. No extra margin
objective, no physical mutual coupling feasibility study. Phase 2 only.
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path
import numpy as np

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
SOURCE=ROOT/"experiments/chatgpt_topology_search/runs/EXP-053/checkpoints/split_input_shunt_center_best.json"
sys.path.insert(0,str(ROOT/"experiments/chatgpt_topology_search/runs/EXP-053"))
sys.path.insert(0,str(ROOT/"src"))
import sweep_4l_inductor_graphs as base
from lpf.constraint_versions import load_constraint,constraint_fingerprint
from lpf.trial_shunt_dtc import shunt_dtc_parasitic_branches

L_GRAPH=base.GRAPHS["split_input_shunt_center"]
# Array order: Cf0, Cf1, Cp, Cv0, Cv1, Cv2; last parasite follows Cv0.
# Designed multi-edge combinations, not independent one-dimensional C sweeps.
CONFIGS={
 "reference": ((0,1),(0,2),(4,-1),(4,-1),(0,1),(1,2)),
 "cf0_input_mid__cv1_mid_center": ((0,3),(0,2),(4,-1),(4,-1),(3,1),(1,2)),
 "cf0_mid_center__cv1_input_mid": ((3,1),(0,2),(4,-1),(4,-1),(0,3),(1,2)),
 "cf0_input_mid__cv2_mid_output": ((0,3),(0,2),(4,-1),(4,-1),(0,1),(3,2)),
 "cf0_mid_center__cv2_mid_output": ((3,1),(0,2),(4,-1),(4,-1),(0,1),(3,2)),
 "cf0_input_tip__cv1_mid_center": ((0,4),(0,2),(4,-1),(4,-1),(3,1),(1,2)),
 "cf0_center_tip__cv2_mid_output": ((1,4),(0,2),(4,-1),(4,-1),(0,1),(3,2)),
 "cf1_mid_output__cv1_input_mid": ((0,1),(3,2),(4,-1),(4,-1),(0,3),(1,2)),
 "cf1_mid_output__cv2_input_output": ((0,1),(3,2),(4,-1),(4,-1),(0,1),(0,2)),
 "cf1_input_mid__cv2_mid_output": ((0,1),(0,3),(4,-1),(4,-1),(0,1),(3,2)),
 "cf1_center_output__cv1_input_mid": ((0,1),(1,2),(4,-1),(4,-1),(0,3),(1,2)),
 "cf1_input_tip__cv2_mid_output": ((0,1),(0,4),(4,-1),(4,-1),(0,1),(3,2)),
 "cp_mid_ground__cv1_input_mid": ((0,1),(0,2),(3,-1),(4,-1),(0,3),(1,2)),
 "cp_center_ground__cv2_mid_output": ((0,1),(0,2),(1,-1),(4,-1),(0,1),(3,2)),
 "cp_mid_ground__cv2_center_tip": ((0,1),(0,2),(3,-1),(4,-1),(0,1),(1,4)),
 "cf0_input_mid__cv1_mid_center__cv2_mid_output": ((0,3),(0,2),(4,-1),(4,-1),(3,1),(3,2)),
 "cf1_mid_output__cv1_input_mid__cv2_center_tip": ((0,1),(3,2),(4,-1),(4,-1),(0,3),(1,4)),
 "cf0_mid_center__cf1_mid_output__cv2_center_tip": ((3,1),(3,2),(4,-1),(4,-1),(0,1),(1,4)),
 "cf0_input_mid__cf1_center_output__cv1_mid_center": ((0,3),(1,2),(4,-1),(4,-1),(3,1),(1,2)),
 "cf0_mid_center__cp_mid_ground__cv2_mid_output": ((3,1),(0,2),(3,-1),(4,-1),(0,1),(3,2))
}
CAP_Q=np.array([80.,40.,80.,35.,35.,35.,40.],float)
BOUNDS=base.BOUNDS
SETTINGS=base.CASES
def canonical(ends):
    return tuple(sorted(ends))
def check_configs():
    assert len(CONFIGS)==20
    fingerprints=set()
    for name,edges in CONFIGS.items():
        assert len(edges)==6
        # Fixed installed CF0 and Cf1 non-GND, Cp always grounded;
        # one Q35 grounded DTC, two non-ground DTCs, its parasitic follows.
        assert edges[3]==(4,-1)
        assert edges[4][1]!=-1 and edges[5][1]!=-1
        for a,b in edges:
            assert 0<=a<5 and (-1<=b<5) and a!=b
        key=tuple(canonical(e) for e in edges)
        assert key not in fingerprints,name
        fingerprints.add(key)

class Evaluator(base.Evaluator):
    def __init__(self,policy,points,variant):
        if variant not in CONFIGS:
            raise KeyError(variant)
        super().__init__(policy,points,"split_input_shunt_center")
        self.variant=variant
        self.c_edges=CONFIGS[variant]+(CONFIGS[variant][3],)
        self.BC=base.exp51.incidence(self.c_edges)
        self.cache_x=self.cache_il=None
    def il(self,x):
        x=np.asarray(x,float)
        if x.shape!=(29,):raise ValueError("Expected 29 parameter vector")
        if self.cache_x is not None and np.array_equal(x,self.cache_x):
            return self.cache_il
        K,_,_,_=base.inductance(x,self.L_edges)
        n=len(self.f)
        Y=np.broadcast_to(K,(n,5,5)).copy()/(self.omega[:,None,None]*1e-9)
        cv=x[11:].reshape(6,3)[self.setting]
        caps=np.column_stack((np.broadcast_to(x[4:7],(n,3)),cv,
                              np.full(n,0.5)))
        yc=self.omega[:,None]*1e-12*caps/(1/CAP_Q[None,:]-1j)
        Y+=np.einsum("nb,ib,jb->nij",yc,self.BC,self.BC,optimize=True)
        ports=[0,2];mid=[1,3,4]
        A=Y[:,ports,:][:,:,ports]
        B=Y[:,ports,:][:,:,mid]
        C=Y[:,mid,:][:,:,ports]
        D=Y[:,mid,:][:,:,mid]
        z=A-B@np.linalg.solve(D,C)
        a,b,c,d=z[:,0,0],z[:,0,1],z[:,1,0],z[:,1,1]
        if np.any(abs(c)<1e-21):raise ValueError("Undefined 2-port")
        T=np.empty((n,2,2),complex)
        T[:,0,0]=-d/c;T[:,0,1]=-1/c
        T[:,1,0]=-(a*d-b*c)/c;T[:,1,1]=-a/c
        chain=self.pre@T@self.post
        zl=60-40j
        den=chain[:,0,0]*zl+chain[:,0,1]+50*(chain[:,1,0]*zl+chain[:,1,1])
        il=-10*np.log10(np.maximum(200*zl.real/(abs(den)**2),1e-300))
        self.cache_x=x.copy();self.cache_il=il
        return il

def independent_MNA(policy,x,variant,points):
    """Independent explicit KCL + branch-current L/KVL 9x9, power balance."""
    ev=Evaluator(policy,points,variant)
    numeric=ev.il(x)
    _,M,H,BL=base.inductance(np.asarray(x,float),L_GRAPH)
    eigen=float(np.linalg.eigvalsh(M)[0])
    bc=ev.BC
    delta=power_diff=0.0
    min_passive=float("inf")
    for j,(MHz,state) in enumerate(zip(ev.f,ev.setting)):
        w=2e6*np.pi*MHz
        values=np.r_[x[4:7],x[11+state*3:14+state*3],0.5]
        yc=w*1e-12*values/(1/CAP_Q-1j)
        before,after=ev.pre[j],ev.post[j]
        zl=60-40j
        din=before[0,1]+50*before[1,1]
        Ys=(before[0,0]+50*before[1,0])/din
        source=1/din
        dout=after[0,0]*zl+after[0,1]
        Yload=(after[1,0]*zl+after[1,1])/dout
        A=np.zeros((9,9),complex)
        A[:5,:5]=bc@np.diag(yc)@bc.T
        A[0,0]+=Ys;A[2,2]+=Yload
        A[:5,5:]=BL;A[5:,:5]=BL.T
        A[5:,5:]=-w*1e-9*H
        rhs=np.zeros(9,complex);rhs[0]=source
        sol=np.linalg.solve(A,rhs)
        v,ilcurr=sol[:5],sol[5:]
        Pout=zl.real*abs(v[2]/dout)**2
        loss=-10*np.log10(max(200*Pout,1e-300))
        delta=max(delta,abs(loss-numeric[j]))
        iin=source-Ys*v[0]
        extv=before[0,0]*v[0]+before[0,1]*iin
        exti=before[1,0]*v[0]+before[1,1]*iin
        p_refl=abs(1-100*exti)**2/200
        p_pre=float(np.real(extv*np.conj(exti)-v[0]*np.conj(iin)))
        p_post=float(np.real(v[2]*np.conj(Yload*v[2]))-Pout)
        p_ind=float(np.sum(w*1e-9*np.asarray(x[:4])/25*abs(ilcurr)**2))
        p_caps=yc.real*abs(bc.T@v)**2
        p_cap=float(p_caps.sum())
        power_diff=max(power_diff,abs(.005-(p_refl+p_pre+p_post+p_ind+p_cap+Pout)))
        min_passive=min(min_passive,p_refl,p_pre,p_post,p_ind,p_cap,Pout,*map(float,p_caps))
    return {"method":"independent 9x9 coupled-L branch-current MNA",
      "probes":int(len(ev.f)),"max_IL_difference_db":float(delta),
      "max_power_balance_residual_W":float(power_diff),
      "min_dissipative_term_W":float(min_passive),
      "min_L_matrix_eigenvalue_nH":eigen,
      "PASS":bool(delta<1e-8 and power_diff<1e-9 and
                  min_passive>-1e-10 and eigen>0)}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--starts",type=int,default=2)
    p.add_argument("--maxiter",type=int,default=160)
    p.add_argument("--coarse",type=int,default=7)
    p.add_argument("--fine",type=int,default=17)
    p.add_argument("--dense",type=int,default=1001)
    p.add_argument("--mna",type=int,default=3)
    p.add_argument("--target",type=float,default=30.005)
    p.add_argument("--variants",nargs="*",choices=list(CONFIGS),default=list(CONFIGS))
    p.add_argument("--out",type=Path)
    a=p.parse_args()
    if min(a.starts,a.maxiter,a.coarse,a.fine,a.dense,a.mna)<1 or a.target<30:
        raise ValueError("Invalid experiment parameters")
    if not a.variants or len(set(a.variants))!=len(a.variants):
        raise ValueError("Duplicate or empty selection")
    check_configs()
    policy=load_constraint("RF-T007",allow_trial=True)
    parasites=shunt_dtc_parasitic_branches(policy,[
        {"a":5,"b":0,"role":"shunt_to_ground"},
        {"a":1,"b":2,"role":"bridge"},
        {"a":2,"b":3,"role":"bridge"}])
    assert len(parasites)==1 and parasites[0]["node"]==5
    src=json.loads(SOURCE.read_text(encoding="utf-8"))
    assert src["constraint_id"]=="RF-T007"
    assert src["candidate_id"]=="EXP053-T007-4L-SPLIT-INPUT-SHUNT-CENTER-001"
    seed=np.asarray(src["vector"],float)
    if seed.shape!=(29,):raise AssertionError("Source full parameter vector missing")
    reference=Evaluator(policy,a.dense,"reference")
    prior=base.Evaluator(policy,a.dense,"split_input_shunt_center")
    pointwise_diff=float(np.max(abs(reference.il(seed)-prior.il(seed))))
    original=reference.summary(seed)
    if pointwise_diff>1e-8 or abs(original["worst_IL_db"]-.8757946642355757)>1e-6:
        raise AssertionError("Full EXP-053 reference not reproduced")
    report={"experiment_id":"EXP-054","phase":"Phase 2","constraint_id":"RF-T007",
        "source_checkpoint":str(SOURCE.relative_to(ROOT)),
        "source_worst_IL_db":original["worst_IL_db"],
        "source_pointwise_model_discrepancy_db":pointwise_diff,
        "study":"simultaneous fixed GJM/PCB and non-ground Q35 DTC branches",
        "L_edges":L_GRAPH,"fixed_DTC_ground_parasitic":{"edge":[4,-1],"C_pF":.5,"Q":40},
        "chip_area":5+1/3,"chip_L_count":4,"GJM_count":2,"PCB_C_count":1,
        "DTC_count":3,"grounded_DTC_count":1,"fixed_Q":[80,40,80],
        "DTC_Q":35,"L_Q":25,"target_H2H3_guard_db":a.target,
        "minimum_mandatory_H2H3_db":30,
        "objective":"minimize worst UL/DL IL, H2 and H3 hard limits only",
        "effective_constraint_fingerprint":constraint_fingerprint(policy),
        "execution_sha":subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip(),
        "grid":{"bands":28,"coarse":a.coarse,"fine":a.fine,"dense":a.dense,"MNA":a.mna},
        "variants":{},
        "limitations":["Local finite-grid Phase2 only, not global/continuous extrema proof",
         "H2/H3 extra margin not optimized","Physical magnetic coupling feasibility not evaluated",
         "No Q(f), SRF, PCB EM, component variability or Phase3"]}
    rng=np.random.default_rng(20261019+54)
    ranked=[]
    for name in a.variants:
        coarse=Evaluator(policy,a.coarse,name)
        fine=Evaluator(policy,a.fine,name)
        dense=reference if name=="reference" else Evaluator(policy,a.dense,name)
        starts=[seed.copy()]
        for j in range(a.starts-1):
            x=seed.copy()
            x[:4]*=np.exp(rng.normal(0,.09 if j==0 else .18,4))
            x[4:7]*=np.exp(rng.normal(0,.11 if j==0 else .22,3))
            x[8:11]+=rng.normal(0,.012 if j==0 else .025,3)
            x[11:]+=rng.normal(0,.12 if j==0 else .23,18)
            starts.append(np.clip(x,BOUNDS[:,0],BOUNDS[:,1]))
        trials=[]
        for j,start in enumerate(starts):
            try:
                x0,c0=base.exp51.optimize_stage(coarse,start,a.maxiter,a.target)
                xf,cf=base.exp51.optimize_stage(fine,x0,max(80,a.maxiter//2),a.target)
                metrics=base.full_metrics(dense,xf)
                z={"start":j,"coarse":c0,"fine":cf,"converged":bool(c0["converged"] and cf["converged"]),
                    "vector":xf.tolist(),"metrics":metrics}
            except (np.linalg.LinAlgError,ValueError,OverflowError) as err:
                z={"start":j,"failed":str(err),"converged":False}
            trials.append(z)
            print("TRY",name,j,z.get("metrics",{}).get("worst_IL_db"),
              z.get("metrics",{}).get("min_H2_db"),z.get("metrics",{}).get("min_H3_db"),
              "CONVERGED",z["converged"],flush=True)
        candidates=[z for z in trials if z.get("metrics",{}).get("hard_H2H3_30dB_pass")]
        selected=min(candidates,key=lambda z:z["metrics"]["worst_IL_db"]) if candidates else None
        check=independent_MNA(policy,np.asarray(selected["vector"]),name,a.mna) if selected else None
        if check and not check["PASS"]:raise AssertionError("Independent MNA invalid: "+name)
        report["variants"][name]={"C_edges":CONFIGS[name],"trials":trials,
          "selected_H2H3_strict_30dB":selected,"independent_MNA":check,
          "status":"PASS_30db_finite" if selected else "no_verified_eligible_point"}
        if selected:
            ranked.append({"variant":name,"worst_IL_db":selected["metrics"]["worst_IL_db"],
             "min_H2_db":selected["metrics"]["min_H2_db"],
             "min_H3_db":selected["metrics"]["min_H3_db"],
             "selected_converged":selected["converged"]})
        print("GRAPH",name,"BEST",None if selected is None else selected["metrics"]["worst_IL_db"],
              "MNA",None if check is None else check["PASS"],flush=True)
    ranked.sort(key=lambda z:z["worst_IL_db"])
    report["summary"]={"variant_count":len(a.variants),"starts":a.starts*len(a.variants),
      "eligible_variants":len(ranked),"ranked":ranked,"reference_IL_db":original["worst_IL_db"]}
    path=a.out or ROOT/"results/EXP-054/combined_C_DTC_graphs.json"
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(report,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print("FINAL",str(path),"RANKED",ranked,flush=True)

if __name__=="__main__":
    main()

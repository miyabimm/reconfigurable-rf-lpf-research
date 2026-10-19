#!/usr/bin/env python3
"""EXP-052 secondary 4L topology sweep: reposition fixed GJM/PCB capacitors.

All candidates share RF-T007 one grounded Cv0(4,GND) plus distinct 0.5pF/Q40
fixed parasitic at (4,GND); Cv1(0,1), Cv2(1,2) remain non-ground.
Four chip LQP02HV and physical coupling bounds, chip area5+1/3,
two GJM/Q80 and one PCB-C/Q40 unchanged. Only fixed capacitor edges vary.
Objective solely worst IL, mandatory H2/H3>=30dB; no extra margin/k realism.
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path
import numpy as np

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
sys.path.insert(0,str(HERE))
import sweep_4l_connections as edge

CONFIGS={
  "reference": ((0,1),(1,2),(4,-1)),
  "cf0_input_output": ((0,2),(1,2),(4,-1)),
  "cf0_input_tip": ((0,4),(1,2),(4,-1)),
  "cf0_shunt_bottom": ((3,4),(1,2),(4,-1)),
  "cf0_output_tip": ((2,4),(1,2),(4,-1)),
  "cf1_input_output": ((0,1),(0,2),(4,-1)),
  "cf1_shunt_bottom": ((0,1),(3,4),(4,-1)),
  "cp_shunt_mid": ((0,1),(1,2),(3,-1)),
  "cp_junction_ground": ((0,1),(1,2),(1,-1)),
  "cp_output_ground": ((0,1),(1,2),(2,-1)),
}

class Evaluator(edge.Evaluator):
    def __init__(self,policy,points,variant):
        if variant not in CONFIGS:raise KeyError(variant)
        super().__init__(policy,points,"reference")
        self.variant=variant
        self.fixed_edges=CONFIGS[variant]
        self.cap_edges=self.fixed_edges+self.cv_edges+(self.cv_edges[0],)
        self.cap_inc=edge.exp51.incidence(self.cap_edges)
        self.cache_x=None
        self.cache_il=None

def independent_MNA(policy,x,variant,points):
    """Independently assembled 9x9 branch-current KCL/KVL on moved-C graph."""
    ev=Evaluator(policy,points,variant)
    ref=ev.il(x)
    _,M,H=edge.exp51.circuit_matrix(x)
    eigen=float(np.linalg.eigvalsh(M)[0])
    bc=ev.cap_inc
    maximum_error=maximum_balance=0.
    min_loss=float("inf")
    for j,(mhz,setting) in enumerate(zip(ev.f,ev.setting)):
        w=2e6*np.pi*mhz
        values=np.r_[x[4:7],x[11+3*setting:14+3*setting],0.5]
        Yc=w*1e-12*values/(1/edge.Q-1j)
        ti,to=ev.pre[j],ev.post[j]
        zl=60-40j
        din=ti[0,1]+50*ti[1,1]
        ys=(ti[0,0]+50*ti[1,0])/din
        source=1/din
        dout=to[0,0]*zl+to[0,1]
        yl=(to[1,0]*zl+to[1,1])/dout
        A=np.zeros((9,9),complex)
        A[:5,:5]=bc@np.diag(Yc)@bc.T
        A[0,0]+=ys;A[2,2]+=yl
        A[:5,5:]=edge.exp51.BL
        A[5:,:5]=edge.exp51.BL.T
        A[5:,5:]=-w*1e-9*H
        rhs=np.zeros(9,complex);rhs[0]=source
        vfull=np.linalg.solve(A,rhs)
        v,i=vfull[:5],vfull[5:]
        power_load=zl.real*abs(v[2]/dout)**2
        il=-10*np.log10(max(power_load*200,1e-300))
        maximum_error=max(maximum_error,abs(il-ref[j]))
        iin=source-ys*v[0]
        extv=ti[0,0]*v[0]+ti[0,1]*iin
        exti=ti[1,0]*v[0]+ti[1,1]*iin
        pref=abs(1-100*exti)**2/200
        pin=float(np.real(extv*np.conj(exti)-v[0]*np.conj(iin)))
        pout=float(np.real(v[2]*np.conj(yl*v[2]))-power_load)
        pL=float(np.sum(w*1e-9*x[:4]/25*abs(i)**2))
        pc_each=Yc.real*abs(bc.T@v)**2
        pc=float(pc_each.sum())
        maximum_balance=max(maximum_balance,abs(.005-(pref+pin+pout+pL+pc+power_load)))
        min_loss=min(min_loss,pref,pin,pout,pL,pc,power_load,*[float(z) for z in pc_each])
    return {"method":"independent coupled 4L explicit 9x9 MNA for altered fixed-C edges",
      "probes":int(len(ev.f)),"max_IL_delta_dB":float(maximum_error),
      "max_power_balance_error_W":float(maximum_balance),
      "min_passive_dissipation_W":float(min_loss),
      "min_L_eigenvalue_nH":eigen,
      "pass":bool(maximum_error<1e-8 and maximum_balance<1e-9 and min_loss>-1e-10 and eigen>0)}

def main():
    pa=argparse.ArgumentParser()
    pa.add_argument("--starts",type=int,default=2)
    pa.add_argument("--maxiter",type=int,default=160)
    pa.add_argument("--coarse",type=int,default=7)
    pa.add_argument("--fine",type=int,default=17)
    pa.add_argument("--dense",type=int,default=1001)
    pa.add_argument("--mna",type=int,default=3)
    pa.add_argument("--target",type=float,default=30.005)
    pa.add_argument("--variants",nargs="*",default=list(CONFIGS),choices=list(CONFIGS))
    pa.add_argument("--out",type=Path)
    a=pa.parse_args()
    if min(a.starts,a.maxiter,a.coarse,a.fine,a.dense,a.mna)<1 or a.target<30 or not a.variants:
        raise ValueError("Invalid search arguments")
    if len(set(a.variants))!=len(a.variants):raise ValueError("Duplicate variants")
    p=edge.load_constraint("RF-T007",allow_trial=True)
    original=np.asarray(json.loads(edge.CP.read_text())["vector"],float)
    source=edge.exp51.Evaluator(p,a.dense,False)
    reference=Evaluator(p,a.dense,"reference")
    mismatch=float(np.max(np.abs(source.il(original)-reference.il(original))))
    if mismatch>1e-8:
        raise AssertionError("EXP-051 exact source not reproduced by fixed-edge sweeper")
    rng=np.random.default_rng(20261019+520)
    out={
      "experiment_id":"EXP-052","phase":"Phase 2","constraint_id":"RF-T007",
      "study":"fixed_C_edge_position_topology_sweep",
      "reference_EXP051_worst_IL_db":edge.BASE_WORST_IL,
      "reference_reproduction_max_IL_error_db":mismatch,
      "area":5+1/3,"physical_C_categories":["GJM Q80","PCB-pattern Q40","GJM Q80"],
      "variable_DTC_edges":edge.VARIANTS["reference"],
      "one_fixed_shunt_Cpar":{"nodes":[4,-1],"C_pF":0.5,"Q":40,"even_if_Cv0_OFF":True},
      "frozen_externals":"fixed input output S2Ps 50ohm source, 60-j40ohm load",
      "internal_H2H3_guard_dB":a.target,
      "models":{},"sha_execution":subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip(),
      "limitations":["No extra H2/H3 margin optimization; minimum 30dB strict only",
         "No physical mutual coupling feasibility/EM/SRF/Q(f)/variance study",
         "Local finite-grid optimization only, not global Pareto proof"]}
    for variant in a.variants:
        ec=Evaluator(p,a.coarse,variant)
        ef=Evaluator(p,a.fine,variant)
        ed=reference if variant=="reference" else Evaluator(p,a.dense,variant)
        starts=[original.copy()]
        for j in range(a.starts-1):
            z=original.copy()
            z[:4]*=np.exp(rng.normal(0,.10 if j==0 else .2,4))
            z[4:7]*=np.exp(rng.normal(0,.12 if j==0 else .3,3))
            z[8:11]+=rng.normal(0,.014 if j==0 else .025,3)
            z[11:]+=rng.normal(0,.10 if j==0 else .20,18)
            starts.append(np.clip(z,edge.BOUNDS[:,0],edge.BOUNDS[:,1]))
        trials=[]
        for j,start in enumerate(starts):
            try:
                v1,c1=edge.optimize_stage(ec,start,a.maxiter,a.target)
                v2,c2=edge.optimize_stage(ef,v1,max(80,a.maxiter//2),a.target)
                row={"start":j,"coarse":c1,"fine":c2,
                     "converged":bool(c1["converged"] and c2["converged"]),
                     "vector":v2.tolist(),"dense":edge.description(ed,v2)}
            except (np.linalg.LinAlgError,ValueError,OverflowError) as err:
                row={"start":j,"failed":str(err),"converged":False}
            trials.append(row)
            print("TRY",variant,j,row.get("dense",{}).get("worst_IL_db"),
                  row.get("dense",{}).get("min_H2_db"),
                  row.get("dense",{}).get("min_H3_db"),
                  "CONVERGED",row.get("converged"),flush=True)
        passed=[t for t in trials if t.get("dense",{}).get("strict_30dB_H2H3")]
        selected=min(passed,key=lambda z:z["dense"]["worst_IL_db"]) if passed else None
        verify=independent_MNA(p,np.asarray(selected["vector"]),variant,a.mna) if selected else None
        if verify and not verify["pass"]:
            raise AssertionError("Independent 9x9 MNA disagreeing with fixed-edge "+variant)
        out["models"][variant]={"fixed_edges":CONFIGS[variant],
          "baseline_source_same_vector":edge.description(ed,original),
          "runs":trials,"selected_strict_30dB":selected,"independent_MNA":verify,
          "status":"strict_dense_pass" if selected else "no_strict_candidate_found"}
        print("VARIANT",variant,"BEST",selected["dense"]["worst_IL_db"] if selected else None,
              "MNA",verify["pass"] if verify else None,flush=True)
    winners=[{"variant":name,"worst_IL_db":s["selected_strict_30dB"]["dense"]["worst_IL_db"],
      "min_H2_db":s["selected_strict_30dB"]["dense"]["min_H2_db"],
      "min_H3_db":s["selected_strict_30dB"]["dense"]["min_H3_db"],
      "converged":s["selected_strict_30dB"]["converged"]}
      for name,s in out["models"].items() if s["selected_strict_30dB"]]
    out["summary"]={"attempted_starts":a.starts*len(a.variants),"variants":len(a.variants),
       "feasible_variants":len(winners),"ranked_by_worst_IL":sorted(winners,key=lambda x:x["worst_IL_db"])}
    dest=a.out or ROOT/"results/EXP-052/fixed_C_edge_sweep.json"
    dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_text(json.dumps(out,indent=2,ensure_ascii=False)+"\n")
    print("FINAL",str(dest),"RANKING",out["summary"]["ranked_by_worst_IL"],flush=True)

if __name__=="__main__":
    main()

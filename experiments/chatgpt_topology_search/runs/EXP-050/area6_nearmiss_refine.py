#!/usr/bin/env python3
"""EXP-050 Phase2 RF-T007 final area6 refinement of a near-miss from run 39267630715.

Source start3 gave IL=1.238321dB, minimum H2=29.989127dB, H3=30.012057dB,
so MUST NOT be classified as RF-T007 compliant. Retune near the near-miss,
seeking H2/H3>=30.02 target (30 mandatory), and verify 28x1001/84 MNA
with exactly two distinct 0.5pF/Q40 shunt parasitic branches. This is an
additional local attempt within pre-reserved EXP-050, not Phase3.
"""
import argparse
import json
import subprocess
from pathlib import Path
import numpy as np
import area6_rft007 as source
from lpf.constraint_versions import load_constraint

NEAR_MISS = np.array([
  2.385227578741905,2.8844655333628975,26.999999999997588,7.167209507770014,
  5.142570940626166,0.06863528599533787,0.5570070843712657,0.02,
  -0.00029718269245625727,-0.02626388567209946,-0.023663252100387572,
  1.6352040771900405,0.0,1.5396978592667079,
  2.6033654588347126,2.9999999999913216,0.21377873665968392,
  2.463697127142165,2.997783836756545,0.31975748329022335,
  2.28005474836087,2.9999729260411216,0.1952840063758457,
  0.9336624605545518,7.53941863871748e-09,0.7020299983013125,
  1.875566514289647,2.999999999960257,0.0],float)

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--starts",type=int,default=3)
    p.add_argument("--maxiter",type=int,default=350)
    p.add_argument("--coarse",type=int,default=9)
    p.add_argument("--fine",type=int,default=31)
    p.add_argument("--dense",type=int,default=1001)
    p.add_argument("--mna",type=int,default=3)
    p.add_argument("--target",type=float,default=30.02)
    p.add_argument("--out",type=Path)
    args=p.parse_args()
    policy=load_constraint("RF-T007",allow_trial=True)
    coarse=source.Evaluator(policy,args.coarse,0.5)
    fine=source.Evaluator(policy,args.fine,0.5)
    dense=source.Evaluator(policy,args.dense,0.5)
    near=source.metrics(dense,NEAR_MISS)
    if not (near["worst_il_db"]<1.25 and 29.98<near["min_h2_db"]<30
            and near["min_h3_db"]>30):
        raise AssertionError("Frozen 2026-10-19 near-miss source not reproduced")
    starts=[NEAR_MISS]
    rng=np.random.default_rng(20261019+6)
    for i in range(args.starts-1):
        z=NEAR_MISS.copy()
        z[:4]*=np.exp(rng.normal(0,0.015,4))
        z[4:8]*=np.exp(rng.normal(0,0.015,4))
        z[8:11]+=rng.normal(0,0.003,3)
        z[11:]+=rng.normal(0,0.04 if i==0 else 0.10,18)
        starts.append(np.clip(z,source.PHYSICAL_BOUNDS[:,0],source.PHYSICAL_BOUNDS[:,1]))
    attempts=[]
    candidates=[]
    for i,z in enumerate(starts):
        try:
            xc,cs=source.optimize_stage(coarse,z,args.target,args.maxiter)
            xf,fs=source.optimize_stage(fine,xc,args.target,max(120,args.maxiter//2))
            record={"start":i,"coarse":cs,"fine":fs,"vector":xf.tolist(),
                    "dense":source.metrics(dense,xf)}
            candidates.append(record)
        except (ValueError,np.linalg.LinAlgError) as err:
            record={"start":i,"error":str(err)}
        attempts.append(record)
        print("REFINE",i,record.get("dense"),"converged",
              record.get("coarse",{}).get("success"),record.get("fine",{}).get("success"),flush=True)
    passed=[r for r in candidates if r["dense"]["H2H3_30_pass"]]
    best=min(passed,key=lambda r:r["dense"]["worst_il_db"]) if passed else None
    closest=min(candidates,key=lambda r:(max(0,30-r["dense"]["min_h2_db"],
                                        30-r["dense"]["min_h3_db"]),r["dense"]["worst_il_db"])) if candidates else None
    verify=source.independent(policy,np.asarray(best["vector"]),args.mna) if best else None
    if verify and not verify["pass"]:
        raise AssertionError("Independent 9x9 MNA failed for refined best")
    report={
      "experiment_id":"EXP-050","constraint_id":"RF-T007",
      "phase":"Phase 2","step":"6_of_6_area6_nearmiss_refinement",
      "original_source_run_id":39267630715,
      "original_source_status":"near_miss_NOT_30dB_compliant",
      "original_source_near_miss_dense":near,
      "original_near_miss_vector":NEAR_MISS.tolist(),
      "retuned_search":{"starts":args.starts,"maxiter":args.maxiter,
        "coarse":args.coarse,"fine":args.fine,"dense":args.dense,
        "target":args.target},
      "attempts":attempts,"best_strict_pass":best,
      "closest_even_if_fail":closest,
      "independent_9x9_MNA":verify,
      "status":"strict_pass_found" if best else "no_30dB_pass_found",
      "code_commit":subprocess.check_output(["git","rev-parse","HEAD"],cwd=source.ROOT,text=True).strip(),
      "limitations":["Local re-optimization seeded at saved failed candidate; no global bound",
        "Only numerical 28x1001 full band and independent 28x3 MNA",
        "No physical/EM/Q(f)/SRF/tolerance qualification"]}
    out=args.out or source.ROOT/"results/EXP-050/area6_nearmiss_refine.json"
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n")
    print("FINAL",out,"BEST",best["dense"] if best else None,
          "MNA",verify,"STATUS",report["status"],flush=True)

if __name__=="__main__":
    main()

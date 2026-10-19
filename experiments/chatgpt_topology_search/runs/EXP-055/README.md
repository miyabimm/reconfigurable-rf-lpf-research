# EXP-055 — RF-T007 adaptation from RF-F003 EXP-047 four-inductor seed

Phase 2 only; EXP-055 was reserved on GitHub main by commit 28f047e277ebdcd70fde9a4b345fd33b028dbb26. Formal RF-F003 and legacy trials remain unchanged; Phase 3 is not authorized.

## Source checkpoint

EXP-047 saved RF-F003 area 5+1/3: 4×LQP02HV/Q25, 2×GJM01/Q80, 2×PCB_PATTERN_C/Q40, and 2×IC DTC/Q35, with worst UL/DL IL **0.843652331564dB under F003 only**, not RF-T007. Exact frozen vector: experiments/chatgpt_topology_search/runs/EXP-047/area5p333_g2_independent_28x1001_20261017.json. Keep original input and output S2P files.

L graph (L0,L1,L2,L3) = (0,1),(1,3),(1,4),(1,2), physical row L0–L1–L3–L2. Signed k only between physical neighbors, |k|≤0.10, full matrix SPD. Fixed Cf0 GJM (0,1), Cf1 GJM (4,GND), Cf2 PCB (1,2), Cp PCB (0,3). Original Cv0 (3,GND), Cv2 (1,2), third Cv1 physically absent.

## RF-T007 trial matrix

Every variant maintains **one** grounded DTC Cv0 (3,GND), its own **separate permanent** 0.5pF/Q40 Cpar (3,GND), even with Cv0=OFF. Cv2 remains (1,2). The optional third Cv1 is always non-ground with no separate Cpar; all variable components are 0–3pF/Q35. Fixed values and k common to all six settings.

| Variant | Third Cv1 |
|---|---|
| two_dtc | absent, strict original structure |
| cv1_input_output | (0,2) input–output bridge |
| cv1_input_parallel_L0 | (0,1) input L bypass |
| cv1_input_tip | (0,3) input–tip bridge |
| cv1_tip_output | (3,2) tip–output bridge |
| cv1_output_shunt_tip | (2,4) output–fixed-shunt tip bridge |

Research question: could the F003 one-grounded-DTC 4L network adapt to T007 better than earlier T005 two-grounded-DTC 4L variants? This is a hypothesis, not a numerical finding.

## Preregistered execution and gates

1. First reproduce frozen EXP-047 F003 source **without** T007 Cpar using original source S2P; require full 28×1001 worst-IL agreement better than 1e-6dB.
2. Add distinct fixed 0.5pF/Q40 to the grounded Cv0 branch and record unchanged source vector response under T007 separately.
3. Locally optimize common L/fixed C/adjacent k and all six DTC states with deterministic 3-start SLSQP, 7→17 samples/each of 28 segments, then dense 1001 points/segment. Enforce H2/H3≥30dB, internal guard 30.005dB; no extra margin objective. Do not add RF-T006 3–6GHz mandatory stopband.
4. Independently assemble explicit 9×9 branch-current MNA for accepted candidate (84 samples), check external two-port loss, passive power balance and SPD; retain convergence/failed trials.
5. Fair RF-T007 benchmark: EXP-053 area5+1/3, worst IL **0.875794664236dB**. Do not compare old F003 best IL as T007 accomplishment.

**Execution state of this document: preregistered with code and tests, not numerically executed in this record.** Actual GitHub Actions outcome and original artifacts must be checked before any claimed best-found update. No Q(f), SRF, manufacturing tolerance, EM, physical k realizability, continuous-band extrema, measured S2P or Phase 3.

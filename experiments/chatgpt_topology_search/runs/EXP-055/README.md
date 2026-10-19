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


## Executed results — 2026-10-20 JST, RF-T007 (Phase 2)

Original [GitHub Actions run 39341678211](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/actions/runs/39341678211) **SUCCESS on second run attempt**. Initial attempt stopped before numerical work due to an incorrectly formatted fractional-second timestamp in the newly created experiment reservation row. Main ledger timestamp syntax alone was corrected by commit 22af59f1a2a596c82b07dc53c33f806e4947a068, after which preflight, F003 reproduction tests, all numerical optimizations and independent MNA passed. Actual executed code SHA e0b824c1b3160b7280026f481fafcf7c5ed27b95. Raw Actions artifact ID 12230025234, ZIP SHA256 995b86ad76a1530bb36820d89b51e5e9fefd8559b64c39c681934b3905058564; unpacked f003_fourL_adapt.json SHA256 2d0fa0d7c1cbc8c3349f620a3fa2f20e40fd9dea8d90ff0616e9b4d4fcaf7f64.

Historical F003 source reproduced to numerical precision **without** RF-T007 Cpar: IL 0.843652331564dB. The same frozen F003 settings **with** mandatory T007 0.5pF/Q40 Cpar (unoptimized) give worst IL1.160642294dB, H2 min13.738068dB, H3 min18.481795dB: **RF-T007 FAIL**. These two checkpoints must not be labelled optimized T007 solutions.

The six topology variants below were separately reoptimized with full external frozen S2Ps and mandatory one always-on grounded Cv0 parasitic. 18 seeded SLSQP attempts; 13 converged, 5 nonconverged, 0 execution failures. All six variants yielded independently checked eligible H2/H3≥30dB finite-grid candidates. Each selected point passed dense 28 segments ×1001 point checks and independent 84-probe explicit 9×9 coupled-inductor branch-current MNA with passive power conservation.

| Cv1 connection | Area | Worst IL dB | Min H2 dB | Min H3 dB | Selected SLSQP | Independent MNA |
|---|---:|---:|---:|---:|---|---|
| **(0,3) input-tip** | **5⅓** | **0.817365590** | 30.005000 | 30.004810 | converged | PASS |
| (2,4) output-shunt tip | 5⅓ | 0.849084050 | 30.005000 | 30.004492 | **nonconverged** | PASS |
| (0,1) input-L parallel | 5⅓ | 0.857268574 | 30.004999 | 30.004983 | **nonconverged** | PASS |
| (0,2) input-output | 5⅓ | 0.874569989 | 30.005000 | 30.003955 | converged | PASS |
| (3,2) tip-output | 5⅓ | 0.879327057 | 30.005000 | 30.003972 | converged | PASS |
| absent (strict 2 DTC) | 5⅓ | 0.881136148 | 30.005000 | 30.004650 | converged | PASS |

**New observed 4L best for RF-T007**: the F003-derived 4L with third non-ground Cv1(0,3) has worst IL **0.8173655897607699dB**, improving same-area EXP-053 RF-T007 best **0.8757946642355757dB by 0.0584290744748058dB**. This local selected SLSQP start fully converged; H2/H3 mandatory 30dB PASS. Nominal 35dB and IL≤0.30dB FAIL. This is not the historical F003 0.84365dB number.

### Best circuit

LQP02HV/Q25 branches: L0(0,1)=2.164216108nH, L1(1,3)=8.361777873nH, L2(1,4)=19.385899347nH, L3(1,2)=7.360379851nH. Physical row L0–L1–L3–L2, adjacent signed k(L0,L1)=+0.100000, k(L1,L3)=+0.051862759, k(L3,L2)=−0.100000, matrix eigenvalue minimum +2.135002378nH. Fixed Cf0 GJM01/Q80 (0,1)=3.235812228pF, Cf1 GJM01/Q80 (4,GND)=0.397669903pF, Cf2 PCB/Q40 (1,2)=0.200000pF, Cp PCB/Q40 (0,3)=0.020000pF. Variable Cv0 (3,GND), **Cv1 (0,3)**, Cv2 (1,2) all 0–3pF/Q35. A DISTINCT fixed Cpar (3,GND)=0.5pF/Q40 accompanies Cv0 in all six states, including OFF; no extra Cpar on Cv1 or Cv2. Two GJM/2PCB/4L, chip area 5⅓.

| Band | Cv0 pF | Cv1 pF | Cv2 pF |
|---|---:|---:|---:|
| B71 | 0.296473249 | 0.592155918 | 1.203404572 |
| B12 | 0.215939098 | 0.528425218 | 1.174008633 |
| B28 | 0.017205977 | 0.603998129 | 1.009162534 |
| B13+B14 | 0 | 0.370830116 | 0.539057105 |
| B26 | 0.055771702 | 0.205520057 | 0.343304000 |
| B8 | 0 | 0 | 0.118738144 |

Worst IL: B8/960MHz. Minimum H2: B71/1326MHz. Minimum H3: B28/2160.705MHz. Independent MNA for new best: maximum IL discrepancy **4.54747e−13dB**, maximum power residual **7.80626e−18W**, nonnegative passive losses.

Complete full-precision vectors and all six setting DTC triples retained for [winner](checkpoints/cv1_input_tip_best.json), [output-shunt-tip nonconverged](checkpoints/cv1_output_shunt_tip_best.json), [input-L parallel nonconverged](checkpoints/cv1_input_parallel_L0_best.json), and [2-DTC control](checkpoints/two_dtc_best.json). Matching independent MNA overlays are under [validation](validation/). [Run summary](run_summary.json) retains all 6 candidate results, convergence counts, provenance and raw artifact SHA. All 18 raw trial vectors remain in the original Actions artifact (30-day retention); only selected vectors are Git-curated.

**Caveats**: Finite-grid constant-Q local best, not global optimum or continuous-extrema guarantee. New best runs on upper |k|=0.10 bounds (twice) and on PCB-C .02/.20pF limits, with minimum harmonic attenuation margin only ~0.00481dB. This experiment does not investigate H2/H3 extra attenuation margin or physical simultaneous k realizability. No real Q(f), SRF, EM, tolerance, source S2P measurement or Phase 3 analysis. RF-F003 remains formal and unchanged; **Phase 2 continues; Phase 3 not authorized**.

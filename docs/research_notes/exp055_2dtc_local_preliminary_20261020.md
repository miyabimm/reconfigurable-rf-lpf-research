# Preliminary EXP-055 2-DTC deletion sweep (2026-10-20 JST)

**Status: UNREGISTERED local Phase 2 exploratory computation.** This note is NOT a centrally reserved EXP-NNN run, is NOT a GitHub Actions completion, and does NOT change RF-F003 or RF-T007. It requires a future reservation and run on official frozen S2P assets before official promotion.

## Method and RF conditions

Reference: [EXP-055 winner](../../experiments/chatgpt_topology_search/runs/EXP-055/checkpoints/cv1_input_tip_best.json) (RF-T007, 3 DTC, worst IL 0.8173655897607699 dB, area 5+1/3).

The physical chip row L0–L1–L3–L2 and four electrical L edges (0,1),(1,3),(1,4),(1,2) are fixed in connectivity. Retain all four LQP02HV/Q25, two GJM01/Q80, two PCB_PATTERN_C/Q40, adjacency-only |k|<=0.1, six modes, source 50 ohm/load 60-j40 ohm, full external input/output S2P, mandatory min H2/H3 30 dB. Reoptimize four L values, four fixed C values, three adjacent signed k, and all six setting-specific DTC values after dropping one of Cv0(3,GND), Cv1(0,3), Cv2(1,2). DTC Q35, 0–3 pF. For deleted grounded Cv0, RF-T007's separate always-on 0.5pF/Q40 Cpar is also physically absent; if Cv0 remains, Cpar remains independently, including Cv0=OFF.

Local scipy SLSQP epigraph minimax: 7→17 samples across each of 28 intervals, standard 240/120 stage maxiter; use 500/280 only on explicit iteration-limit stopping. Every retained winner checked on all 28 intervals ×1001 grid points and explicit coupled-L branch-current 9x9 MNA on 84 probes with passive power conservation and SPD. Multistart search 29 trials total; this finite subset is not globally exhaustive.

The canonical source circuit RLC components defined by RF-F003 metadata were analytically used to regenerate external 1MHz S2P samples and the required complex RI linear interpolation. Canonical GitHub 800 MHz external S entries agreed within 4.8e-15; frozen EXP-055 three-DTC and two-DTC dense-worst-IL baselines both reproduced to <2e-14 dB. Original canonical `.s2p` files were not locally mounted, so do **not** conflate this with official in-repository asset verification.

## Observed best-found results (same topology and RF-T007)

| Retained variable branches | Worst IL (dB) | Min H2 (dB) | Min H3 (dB) | 84-probe MNA |
|---|---:|---:|---:|---|
| Cv0 + Cv2 (old two-DTC control) | 0.881136147775 | 30.005000 | 30.004650 | PASS |
| Cv0 + Cv1 | 1.100053825487 | 30.005000 | 30.005000 | PASS |
| **Cv1 + Cv2** | **0.849727263547** | **30.005000** | **30.005000** | **PASS** |

The best keeps only two non-ground DTCs: Cv1(0,3) and Cv2(1,2), deleting ground Cv0 and its dedicated 0.5pF parasitic. This **improves over EXP-055 prior 2-DTC control by 0.031408884237 dB** but remains **0.032361673786 dB worse than the original 3-DTC winner**. No claim of an absolute lower bound or IL<=0.30 dB.

## New best circuit

All four L are HV/Q25, fixed L edges L0(0,1),L1(1,3),L2(1,4),L3(1,2); physical row L0-L1-L3-L2.

- L0-L3 nH: 1.810095363217, 8.291857617483, 6.316996198078, 7.802771363933
- GJM01 Cf0(0,1)=4.464316470471pF/Q80, Cf1(4,GND)=1.099005614321pF/Q80
- PCB-C Cf2(1,2)=0.200000000000pF/Q40; Cp(0,3)=0.020000000000pF/Q40
- Signed k(L0,L1)=+0.100000000000, k(L1,L3)=+0.100000000000, k(L3,L2)=+0.039275990486
- Cv1(0,3), Cv2(1,2), both 0–3pF/Q35; no grounded DTC and no attached 0.5pF parasitic
- Chip area=5+1/3, min coupled-L eigenvalue=1.786634111372 nH (SPD)
- Independent 84-probe MNA max discrepancy=3.27e-13dB, passive power-balance residual=1.56e-17W; PASS.

| Mode | Cv1 pF | Cv2 pF | Worst pass IL dB | Minimum H2 dB | Minimum H3 dB |
|---|---:|---:|---:|---:|---:|
| B71 | 1.194061352 | 1.315156115 | 0.780727430 | 30.005000 | 30.005000 |
| B12 | 1.098628990 | 1.156634699 | 0.802959730 | 30.031271 | 35.443358 |
| B28 | 0.979774873 | 1.045639582 | 0.849727264 | 30.005000 | 30.005000 |
| B13+B14 | 0.669837695 | 0.637952481 | 0.793262670 | 30.008886 | 30.087547 |
| B26 | 0.516301859 | 0.434594624 | 0.839320038 | 30.108050 | 30.202124 |
| B8 | 0.000000000 | 0.210244068 | 0.849727264 | 30.005000 | 30.005000 |

Full-precision 29-value vector is in the adjacent `exp055_2dtc_candidate_20261020.json`.

## Remaining gates / risks

- **H2/H3 margin ≈0.005 dB only**, 35dB nominal target FAIL, 0.30dB IL target FAIL; no tolerance study.
- Two k values saturate +0.10 bounds; simultaneous realizability in the required 1D chip row not shown.
- Both PCB-C values are at allowed bounds. No SRF/Q(f), EM, process tolerance, physical layout, measured source S2P or Phase 3 study.
- Local multistart SLSQP finite-grid solution, continuous extrema not proven, topology space is not exhaustive. Independent MNA confirms numeric passive equations; not a separate source-S2P measurement.
- Official promotion requires an **EXP number reserved on main before a new official rerun**, official canonical precomputed S2P files, raw runs/checksums, convergence and dense+MNA evidence curated per project policy.

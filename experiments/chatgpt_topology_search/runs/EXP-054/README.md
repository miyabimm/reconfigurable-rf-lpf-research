# EXP-054 — RF-T007 Phase 2 combined fixed-C / non-ground DTC edge topology search

The owner requested continuation of **4L topology exploration only**. Physical chip coupling realization and additional H2/H3 attenuation margin growth are **not** research objectives. Continue enforcing the mandatory RF-T007 H2/H3≥30dB. Formal RF-F003 and Phase3 status remain unchanged.

**Reservation on main:** EXP-054, `rft007-fourl-combined-cap-bridge-20261019`, confirmed before code and numerical run.

## Frozen source / invariant resources

Source: [EXP-053 best split-input-shunt-center checkpoint](../EXP-053/checkpoints/split_input_shunt_center_best.json), worst IL **0.8757946642355757dB** (28×1001, RF-T007), area **5⅓**. L row L0–LsA–LsB–L1, L edges **[(0,3),(1,2),(3,1),(1,4)]**, LQP02HV ×4/Q25/0.4–27nH, numeric adjacent |k|≤0.1 with full M SPD. GJM01/Q80 ×2 (Cf0,Cp), PCB_PATTERN_C/Q40 ×1 (Cf1), IC_VARIABLE_C/Q35 ×3 (Cv0,Cv1,Cv2), one grounded DTC Cv0(4,GND). Its independently separate **fixed** Cpar=0.5pF/Q40 (4,GND) persists in all six states even at Cv0=OFF. No PCB budget/cost increment for Cpar.

S2P unchanged at input and output, source50Ω/load60−j40Ω. Six setting-specific Cv0/Cv1/Cv2 values each 0–3pF, independent. Existing EXP-053 source exact IL must be reproduced on all 28×1001 sampling points before a new exploration can run.

## New multi-branch electrical connection sweep (20 variants)

Rather than repeating isolated connection moves, change **at least two** installed C/DTC branches at a time in 19 novel variants; keep all component counts and Q unchanged. Candidate family includes:

- Move GJM Cf0 to input–intermediate (0,3) or intermediate–junction (3,1), simultaneously move the non-ground Cv1 between (3,1) and (0,3); also combine Cf0 moving with Cv2 (3,2).
- Move PCB-C Cf1 from full input–output (0,2) to intermediate–output (3,2), input–intermediate (0,3), junction–output (1,2), or input–tip (0,4), simultaneously rewire Cv1 or Cv2.
- Relocate GJM Cp grounding to node3 or node1 while leaving grounded *DTC plus Q40 Cpar* at node4, and rewire a non-ground Cv1 or Cv2.
- Three-edge combinations of GJM Cf0, PCB Cf1, and/or both non-ground Cv1/Cv2, all with one grounded variable-C only.

Full list and exact terminal pairs are in [sweep_4l_combined_c_dtc.py](sweep_4l_combined_c_dtc.py), `CONFIGS`. `reference` uses EXP-053 fixed-C Cf0(0,1), Cf1(0,2), Cp(4,GND), Cv0(4,GND), Cv1(0,1), Cv2(1,2).

No added fixed C or variable C branch is allowed; GJM and PCB limits retained. The previously studied EXP-051/052 and EXP-053 candidates remain unchanged historical records.

## Numerical matrix (preregistered, not executed yet)

- 20 4L C/DTC connection variants, **two** deterministic SLSQP starts each (40 planned), coarse 7 and fine 17 samples per each of 28 bands; selected strictly compliant numerical candidates checked on **28×1001** points.
- Minimax objective six-setting worst UL/DL IL, strict H2/H3≥30dB. An internal **30.005 dB numerical precision guard** matches EXP-053; it is *not* a study of improving margin.
- Explicitly assemble and independently solve a **9×9 coupled-inductor branch-current MNA** at 84 points for each accepted topology, verify IL agreement, nonnegative dissipated power and 5mW available-source power balance.
- Record local optimizer convergence or nonconvergence for each start; a compliant but nonconverged solution must not be marked converged. Curate complete 29-parameter vectors (L/C/k plus 6×3 DTC settings) and independent-MNA results into Git only after execution.

**Status:** pre-run source/preflight only; no EXP-054 numerical results yet. Constant-Q, finite grid, no universal optimality or EM/SRF/Q(f)/tolerance analysis, no Phase3.

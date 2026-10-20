# EXP-057 — EXP-055 best RF-T007 four-L topology neighborhood search

**Registered before numerical execution on main**: EXP-057, RF-T007 Phase 2, reserved at 2026-10-20T04:44:00Z. The objective is to improve EXP-055 independently verified **four-L area5⅓ IL0.8173655897607699dB**, not to reclassify RF-F003 historical results. No Phase3 activity.

### Frozen baseline
Full EXP-055 verified 29-dimensional source vector: [EXP-055 best](../EXP-055/checkpoints/cv1_input_tip_best.json). Preserve six settings and fixed external input/output S2Ps, 50Ω source/60−j40Ω load, four LQP02HV Q25, two GJM01 Q80 and two PCB-C Q40, fixed capacitor edges Cf0(0,1), Cf1(4,GND), Cf2(1,2), Cp(0,3); 3 DTC Q35 edges Cv0(3,GND), Cv1(0,3), Cv2(1,2), one **separate always-on 0.5pF/Q40** parallel Cv0 GND branch, two non-ground DTCs with NO new shunt parasitics, four physically arranged chips L0-L1-L3-L2, signed nearest-neighbor |k|≤0.10, mandatory UL H2/H3≥30dB and no new RF-T006 stopband. Chip area 5⅓, six modes B71/B12/B28/B13+B14/B26/B8.

### New EXP-057 hypothesis
Search 9 novel nearby **4-L connected spanning-tree electrical graphs**, plus the original EXP-055 graph. Only the four L branch node pairs change; signed three mutually-coupled inductor matrix is SPD, k and fixed/variable capacitors are reoptimized within exactly the same bounds as EXP-055. Novel variants distinguish whether shunt tip node3, grounded Cf1 pendant node4, and/or series path are attached at input, center, or output. Graph descriptions and full edges live in `sweep_from_exp055.py`. This controlled search is not globally exhaustive.

### Numerical plan
Two deterministic SLSQP starts per graph (**20 planned**), first original EXP-055 full vector, second bounded numerical jitter from original. Standard [slsqp-staged-v1](../../../..//../../docs/slsqp_iteration_policy.md): primary coarse 240 / fine 120 iterations, and only on explicit SLSQP iteration-limit retry once at coarse500 / fine280 (fine-only retry when appropriate). Save every status, SLSQP termination, warm start, per-graph dense 28 intervals×1001 points six-mode IL/H2/H3; optional 84-probe independent nine-dimensional coupled-L branch-current MNA plus passive power balance for selected compliant candidates. The reference topology is re-solved as a controlled baseline. Use an internal 30.005dB nominal guard but the actual RF pass boundary is 30dB.

**Status: completed**. The following executed-result section supersedes the original pre-run plan.

**Scope limits:** nominal constant Q, finite grid and local minimax only, no global optimality/continuous-band proof; no extra H2/H3 margin optimization, physical k simultaneous realizability, device SRF/Q(f), EM, manufacturing tolerance or measured S2P. Formal RF-F003 unchanged; Phase 2 remains active.

## Completed EXP-057 result — 2026-10-20 JST, Phase 2

Original [Actions numerical run 39371574312](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/actions/runs/39371574312) **SUCCESS**, executed code SHA 5c1e7a59afd1edcb9ee581a14a4872f340b510a1. Original ZIP artifact ID12241866186 ZIP SHA256 791abf3fa2f44fdca9ca738439269088e46b1a28e90ba672f50dad6acba232bd; original 113538-byte exp055_fourl_neighborhood.json inner SHA256 6662d8a89dfca7d8c462825535ea63113c10bb6a15a831ef412752e0636f6c17. Preflight and source EXP055/10-tree graph tests PASS.

**Actual numerical scope:** 10 four-L electrical tree graphs (9 new + 1 EXP055 control) x 2 deterministic starts = **20 attempted**. Standard staged SLSQP primary 240 coarse / 120 fine; recovery 500/280 on explicit iteration-limit only. **19/20 fully converged**, one nonconverged with SLSQP message **Positive directional derivative for linesearch** (not iteration-limit); **0 run exceptions**, **0 recovery invocations**. All 10 selected H2/H3>=30dB candidates pass the full six-setting 28x1001 mesh and **independent explicit 84-point coupled-L 9x9 MNA + power conservation PASS**.

| L graph | Worst IL dB | min H2 dB | min H3 dB | Selected solver | MNA |
|---|---:|---:|---:|---|---|
| **EXP055 source (control)** | **0.817365589674** | 30.005000 | 30.004810 | converged | PASS |
| tip3 shunt from input | 0.914280717727 | 30.005000 | 30.005000 | converged | PASS |
| pendant4 from input | 0.915934801091 | 30.005000 | 30.005000 | converged | PASS |
| output via pendant4 | 0.925319375398 | 30.005000 | 30.004961 | converged | PASS |
| input via tip3 | 0.926434326803 | 30.005000 | 30.005000 | converged | PASS |
| pendant4 from output | 0.936401789724 | 30.005000 | 30.005000 | converged | PASS |
| output via tip3 | 0.973324701616 | 30.005000 | 30.005000 | converged | PASS |
| tip3 shunt from output | 1.000158350754 | 30.004942 | 30.005000 | converged | PASS |
| input via pendant4 | 1.498953741682 | 30.005000 | 30.005000 | converged | PASS |
| pendant4 from tip3 | 7.438404641288 | 30.003478 | 30.005000 | converged | PASS |

**No meaningful IL record improvement.** Old EXP055 best 0.8173655897607699dB, newly refined exact same topology 0.8173655896742016dB: numerical difference only **8.6568e−11dB**, not a meaningful gain. Nine new L electrical trees all worse in the finite 2-start locally optimized sample. No global topology limit proved.

Git-curated complete 29-value circuit vectors, fixed C and mutual k, plus all six DTC settings and separate independent MNA records: [EXP055 control rerun](checkpoints/control_exp055_best.json) / [MNA](validation/control_exp055_independent_mna.json), [best novel tip3 input](checkpoints/shunt_tip_from_input_best.json) / [MNA](validation/shunt_tip_from_input_independent_mna.json), [second novel pendant4 input](checkpoints/ground_pendant_from_input_best.json) / [MNA](validation/ground_pendant_from_input_independent_mna.json). [Full 10-graph summary](run_summary.json) records solver outcomes and source artifact hashes; original full 20-trial JSON remains in Actions artifact with 30-day retention.

**Not executed next-study idea:** preserve EXP055 best 4L connectivity while exploring fixed-C/non-ground-DTC edge co-placement. No excess H2/H3 attenuation-margin target and no physical mutual-k realizability study here. No continuous extrema, SRF/Q(f), EM, manufacturing tolerances, measured S2P, global minimum guarantee or Phase3. Formal RF-F003 remains unchanged, Phase2 continues.

# EXP-057 — EXP-055 best RF-T007 four-L topology neighborhood search

**Registered before numerical execution on main**: EXP-057, RF-T007 Phase 2, reserved at 2026-10-20T04:44:00Z. The objective is to improve EXP-055 independently verified **four-L area5⅓ IL0.8173655897607699dB**, not to reclassify RF-F003 historical results. No Phase3 activity.

### Frozen baseline
Full EXP-055 verified 29-dimensional source vector: [EXP-055 best](../EXP-055/checkpoints/cv1_input_tip_best.json). Preserve six settings and fixed external input/output S2Ps, 50Ω source/60−j40Ω load, four LQP02HV Q25, two GJM01 Q80 and two PCB-C Q40, fixed capacitor edges Cf0(0,1), Cf1(4,GND), Cf2(1,2), Cp(0,3); 3 DTC Q35 edges Cv0(3,GND), Cv1(0,3), Cv2(1,2), one **separate always-on 0.5pF/Q40** parallel Cv0 GND branch, two non-ground DTCs with NO new shunt parasitics, four physically arranged chips L0-L1-L3-L2, signed nearest-neighbor |k|≤0.10, mandatory UL H2/H3≥30dB and no new RF-T006 stopband. Chip area 5⅓, six modes B71/B12/B28/B13+B14/B26/B8.

### New EXP-057 hypothesis
Search 9 novel nearby **4-L connected spanning-tree electrical graphs**, plus the original EXP-055 graph. Only the four L branch node pairs change; signed three mutually-coupled inductor matrix is SPD, k and fixed/variable capacitors are reoptimized within exactly the same bounds as EXP-055. Novel variants distinguish whether shunt tip node3, grounded Cf1 pendant node4, and/or series path are attached at input, center, or output. Graph descriptions and full edges live in `sweep_from_exp055.py`. This controlled search is not globally exhaustive.

### Numerical plan
Two deterministic SLSQP starts per graph (**20 planned**), first original EXP-055 full vector, second bounded numerical jitter from original. Standard [slsqp-staged-v1](../../../..//../../docs/slsqp_iteration_policy.md): primary coarse 240 / fine 120 iterations, and only on explicit SLSQP iteration-limit retry once at coarse500 / fine280 (fine-only retry when appropriate). Save every status, SLSQP termination, warm start, per-graph dense 28 intervals×1001 points six-mode IL/H2/H3; optional 84-probe independent nine-dimensional coupled-L branch-current MNA plus passive power balance for selected compliant candidates. The reference topology is re-solved as a controlled baseline. Use an internal 30.005dB nominal guard but the actual RF pass boundary is 30dB.

**Initial status: planned, NOT numerically executed.** After execution preserve original full output artifact SHA, selected complete 29-element vectors for all six DTC triplets, independent MNA overlays, graph outcomes and full convergence/failure accounting in Git. If no better candidate is found, report that outcome explicitly.

**Scope limits:** nominal constant Q, finite grid and local minimax only, no global optimality/continuous-band proof; no extra H2/H3 margin optimization, physical k simultaneous realizability, device SRF/Q(f), EM, manufacturing tolerance or measured S2P. Formal RF-F003 unchanged; Phase 2 remains active.

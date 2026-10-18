# EXP-009 — 3-variable-C placement and fixed-GJM rewiring (Phase 2; 2026-10-12)

## Key numerical finding

**Best observed cost-6 IL checkpoint:** [EXP009-02](EXP009-02.json) achieves six-setting worst UL/DL IL **0.307229935 dB** with minimum UL H2 **30.011757 dB** and H3 **30.012000 dB**. [EXP009-01](EXP009-01.json) is retained as a separate ~0.05dB rejection-headroom comparator (IL 0.307775390 dB), using **four LQP02 Q25 inductors, three GJM01 Q80 fixed capacitors, and three IC tunable Q80 capacitors**. All variable capacitors remain 0–4 pF. The Q values are constant-frequency lumped assumptions. The `0.30 dB` IL target is **not yet achieved**.

**Important engineering limit:** the L1 inductance converges to the **27 nH search upper bound**. Availability/SRF and Q(f) of such a small inductor at 617–2745 MHz are **not validated**. The two largest adjacent chip couplings are close to 0.4 and have not been EM validated. The harmonic attenuation margin is 0.012–0.05 dB, depending on the checkpoint. Consequently EXP009-01 is a **numerical Phase 2 checkpoint**, not an approved manufacturable circuit.

| Candidate | L1 upper bound | Worst IL | H2 minimum | H3 minimum | Cost | Status |
|---|---:|---:|---:|---:|---:|---|
| Earlier [C6-02](../EXP-008/C6-02.json) | 27 nH search range | 0.339093 dB | 30.030001 dB | 30.029976 dB | 6 | Separate preserved baseline |
| **[EXP009-02](EXP009-02.json)** | **27 nH** | **0.307230 dB** | **30.011757 dB** | **30.012000 dB** | **6** | Lowest observed nominal IL, negligible attenuation margin |
| **[EXP009-01](EXP009-01.json)** | **27 nH** | **0.307775 dB** | **30.049481 dB** | **30.049998 dB** | **6** | Slightly more margin, same SRF concern |
| [EXP009-L15](EXP009-L15.json) | 15 nH | 0.314621 dB | 30.044973 dB | 30.044995 dB | 6 | L-range sensitivity only, not physically verified |
| [EXP009-L12](EXP009-L12.json) | 12 nH | 0.323169 dB | 30.044939 dB | 30.044997 dB | 6 | L-range sensitivity only, not physically verified |

**Exactly one fixed-C edge is changed relative to EXP-008 C6-02**: Cf3 (Q80 GJM01, common to all six settings) moves from in parallel with L0 (input node 1 to node 2) to in parallel with L1 (output node 3 to node 4). The remaining inductor graph, grounding capacitors, variable-C graph, and physical coil order are unchanged, but **all component values, neighbor k, and all six 3-C vectors are reoptimized**. This is neither a simple 1-parameter perturbation nor evidence of an exact causal decomposition.

### Topology and constraints

- Source 50 Ω; load 60−j40 Ω, constant across frequency.
- L0: nodes 1–2; L1: 3–4; L2: 2–5; L3: 2–3.
- Fixed Cf1: 1–3; Cf2: 5–GND; Cf3: **3–4**.
- Variable Cv0: 4–GND; Cv1: 5–GND; Cv2: 2–3 (non-ground, parallel to L3).
- Chip physical row L1–L2–L3–L0. Only adjacent k are nonzero; each |k|≤0.4; full inductance matrix is positive definite.
- Chip area 4×1+3×2/3=**6.0**. The IC resources and actual board space have not been included in this footprint metric.
- Six distinct settings B71/B12/B28/B13+B14 shared/B26/B8; same fixed network, only three C values change by setting.
- Both UL harmonic bands (H2 and H3) use the complete frequency intervals from `data/bands.csv`; IL is worst across all UL/DL settings.

### Finite local searches actually executed

- **14** local variable-C placement/control trials (13 unique edge/2-vs-3-variable combinations, with one duplicate edge label) started from C6-02. Their best 201-grid locally feasible trial was the original L3 placement at IL 0.339410 dB; **these are not limits on alternative variable placements**.
- **25** one-at-a-time fixed-GJM rewires, one start each. The Cf3→parallel-L1 trial produced IL 0.310810 dB (H2≈30.0394 dB), with SLSQP hitting its 130-iteration limit.
- **12** additional multistarts of the *original C6-02 topology* provided no improved 30 dB locally feasible result. They are not an exhaustive multistart for the new Cf3-parallel-L1 topology.
- **4** initial continuation/bound-sensitivity optimizations from the Cf3-parallel-L1 result: a 31- and 91-point minimax continuation yielded IL 0.307775 dB; 15 nH and 12 nH L1 caps yielded the two additional sensitivity candidates above. All runs are local, nonconverged, and were not run with global-optimality certification.
- At least **58** local optimizer executions across these categories, including the three near-boundary continuations after the initial 55. The initial full iteration-level trace of these chat-time prototype runs was not retained in GitHub. A further 31/91/181-point experimental near-boundary continuation of EXP009-01 identified EXP009-02 (lowest IL at 30.0118 dB margin); its complete optimizer history is also not imported. All saved results are independently MNA checked. Saved finished numerical vectors, declared graph choices, and the independent validator are retained.

### Independent checks

All four constant-Q25 candidates and the separate Q19 stress candidate were verified at **7,001 frequency points per individual listed subband interval** and with a separate **9×9 MNA** solving the four inductor branch currents independently, at **54 representative frequencies per candidate**. For EXP009-01, maximum MNA power budget residual was about **8×10⁻18 W**, and minimum dimensionless k-matrix eigenvalue about **0.43414**. Reproducible from committed records:

```bash
python -m pip install -r requirements.txt
python experiments/chatgpt_topology_search/runs/EXP-009/verify.py
python experiments/chatgpt_topology_search/runs/EXP-009/sweep.py --reference-only
python -m unittest discover -s tests -p 'test_exp009_checkpoints.py' -v
```

The independent circuit formulation checks **numerical implementation, passivity and power conservation within the same lumped-component/Q assumptions**, but not actual part self-resonance, measured Q(f), IC routing parasitics, EM coupling, manufacturing tolerance, or a mathematical guarantee over continuous frequency.

### L1 Q and self-resonance sensitivity (additional evidence, not a revised physical model)

A cross-check against publicly listed LQP02 27 nH parts found 27 nH devices in the requested 01005/0402 package, e.g. LQP02HV27NH02L. Distributor specifications list nominal self-resonance **3.2 GHz** and minimum Q **16** for that variant; LQP02HQ27NHZ2E lists SRF **2.9 GHz** and minimum Q **12**. The Murata [LQP02HQ series Q table](https://pim.murata.com/asset/pim4/inductor/RD_LQP02HQ_02E_PDF_INDUCTOR?lastModifiedDatetime=20250708075445) reports representative **Q≈19 at 2.4 GHz** for 27 nH, rather than a universal constant Q=25. The SRF and Q numbers vary with the exact part number, frequency, and test conditions. Sources: [Mouser LQP02HQ 27nH](https://eu.mouser.com/ProductDetail/Murata-Electronics/LQP02HQ27NHZ2E), [Mouser LQP02HV 27nH](https://www.mouser.com/en/c/passive-components/inductors-chokes-coils/power-inductors-smd/?inductance=27+nH), [Murata RF series overview](https://www.murata.com/ja-jp/products/inductor/chip/overview/lineup/rf1).

As a **sensitivity study**, keep all EXP009-01 fixed and tunable values unchanged and reduce only L1 Q (other L Q=25, C Q=80). The 1,501-point-per-subband numerical results were:

| Hypothetical inductance Q vector [L0,L1,L2,L3] | Worst IL | Min H2 | Min H3 | Meets 30 dB? |
|---|---:|---:|---:|---|
| [25,25,25,25] | 0.307775 dB | 30.0495 dB | 30.0500 dB | Yes |
| [25,22,25,25] | 0.309523 dB | **28.792 dB** | 30.038 dB | **No** |
| [25,19,25,25] | 0.311820 dB | **27.451 dB** | 30.023 dB | **No** |
| [25,16,25,25] | 0.314972 dB | **26.002 dB** | 30.001 dB | **No** |
| [20,20,20,20] | 0.366208 dB | 28.750 dB | 29.231 dB | No |

Reproduce these fixed-value stress calculations with [q_sensitivity.py](q_sensitivity.py). The loss change affects the bandwidth/depth of the rejection notch, not just the passband IL. After **separate three-start, per-setting variable-C retuning with fixed L/C/k unchanged**, the minimum H2 was still 29.668 dB (L1 Q22), 29.212 dB (Q19), and 28.750 dB (Q16). The recorded six-band retuning trial vectors and outcomes are in [q_retune_results.json](q_retune_results.json), and can be rerun with [q_retune.py](q_retune.py) (same seeded 3-start SLSQP procedure). These **limited local trials** do not prove that better tuning or a reoptimized fixed topology could not meet 30 dB. This study also does **not** incorporate the actual near-SRF non-ideal frequency response, which requires real component S-parameters/EM.

**Additional whole-network Q continuation:** unlike merely changing Cv0/Cv1/Cv2, a short 31-point local SLSQP continuation that **jointly reoptimized all L/C/k and 6×3 C values** while changing L1 constant Q through 24→22→20→19 found finite-grid 30dB-feasible solutions at every step. The Q19 result, separately saved as [EXP009-Q19](EXP009-Q19.json), had **worst IL 0.317108 dB, min H2 30.021990 dB, min H3 30.019475 dB**. Its independent 7001-point/subband and 54-point 9×9 MNA checks passed, but SLSQP did not converge. This **does not undo** the physical-model concern: even this stress case still models an artificial frequency-constant Q19 for L1 and Q25 for other coils, with no actual self-resonance. It demonstrates that failure of per-band-C-only retuning is not proof that Q19 cannot be accommodated by reoptimizing the fixed circuit. [Joint-Q optimizer](q_joint.py) and [local-search parameter history](q_joint_results.json) are saved for further review. The numerical comparison is **not** a new owner-approved formal Q policy.

**Engineering consequence:** at present, EXP009-01/02 are mathematically valid only for the project constant-Q reference model. They are **not yet stable physical candidates**. A Q(f), SRF and tolerance-constrained search must precede promotion to an implementation shortlist.

### Further reproducible large-scale exploration

[Sweep engine](sweep.py) defines **38 unique constrained graph/control families** (baseline, alternate Cv2 edges, 2-control subsets, and 25 single-GJM rewires). It accepts deterministic seeds, shard count/index, starting points, optimizer iterations, per-subband grids, and a checkpoint path. It rejects resumes with changed code/design-spec/band/optimization fingerprint; it records both failed starts and uncompleted jobs. This general runnable engine was prepared and **smoke-tested locally**, but a complete large GitHub Actions sweep **has not been launched**. Its future multistart results may differ from the numerical local prototypes above.

[Manual GitHub Actions workflow](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/blob/c6c23bab59aeeea70555b016bdec7806f72d239c/.github/workflows/lpf-exp009.yml) prepares preflight verification, eight sharded optimization jobs with artifacts/resume, and an [aggregate report](aggregate.py) that does not misreport unfinished searches as complete. This workflow is an implementation plan; it has not yet executed. It may need to be merged into the default branch before the manual dispatch is available in the GitHub Actions UI.

### Policy status and next technical priorities

- The user's EXP-008/EXP-009 permission is applied **only as an explicit experimental override**: 3 tunable Cs including one non-ground, and H2/H3≥30 dB. The canonical standard remains **2 grounded variable Cs**, nominal target H2/H3≥35 dB, cost hard cap 6, Phase 3 paused.
- Do **not** replace LPF-007/008 or C6-02 historical benchmarks. The stronger legacy 35 dB constraint is different and must not be mixed into a like-for-like comparison.
- Priority: **SRF/Q(f) realism** of 12–27 nH in the relevant LQP02 package; quantify IL penalty under physically justified L1 restrictions and measured Q. Improve 0.307775 further using multiple coupling orders and multi-edge changes, and test yield margin beyond nominal +0.05 dB.
- Phase **2** continues. **Phase 3 is not authorized**; no code-value discretization, switch topology, or switched capacitor parasitic design is claimed.


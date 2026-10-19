# EXP-050 — Sequential RF-T005 Pareto adaptation to RF-T007 (Phase 2)

**Experiment reservation:** EXP-050 was committed to `main:data/experiment_number_registry.csv` on 2026-10-19 (request `rft007-t005-pareto-sequential-20261019`). This is one shared trial/goal covering the six saved non-dominated T005 topology checkpoints in increasing chip-area order; each topology is a separate serialized step and retained checkpoint. RF-T005 baseline results are preserved unchanged.

**Constraints:** Explicit trial RF-T007 (formal RF-F003 base; up to three 0..3pF/Q35 DTC branches). Every DTC whose ends include GND gets a separate **fixed 0.5pF/Q40** shunt-to-GND even when DTC is programmed to 0pF. Bridge/series DTC gets none. No other PCB-C count or nominal Q/area rules change. There is **no** RF-T006 3..6GHz additional stopband in RF-T007.

## Sequence (saved RF-T005 chip area ascending)

| Step | Source | Area | L | Original T005 IL dB | T007 adaption status |
|---|---|---:|---:|---:|---|
| 1 | EXP-043 `checkpoints/zero_gjm_double.json` | 3 | 3 | 0.944268363 | **Executed: 0.938309198dB / H2≥30.020 / H3≥30.019969, independent MNA PASS** |
| 2 | EXP-045 `checkpoints/t3l_extra_pcb_out_0p2_prelim.json` | 3⅔ | 3 | 0.895180009 | **Executed: 0.909728967dB, H2/H3≥30.02dB, independent MNA PASS** |
| 3 | EXP-043 `checkpoints/gjm_cf0_cp.json` | 4⅓ | 3 | 0.879244690 | **Executed: 0.891827011dB, H2/H3≥30.02dB; MNA PASS** |
| 4 | EXP-042 `checkpoints/pcb_both.json` | 4⅔ | 4 | 0.819564515 | **Executed: 1.744672799dB, H2/H3 ≥30dB; MNA PASS; SLSQP nonconverged / dominated** |
| 5 | EXP-042 `checkpoints/pcb_cf1.json` | 5⅓ | 4 | 0.811306586 | **Executed: 1.054411931dB; H2/H3≥30.02dB, converged, MNA PASS, dominated** |
| 6 | EXP-042 `selected_checkpoints_rft005.json` (EXP042-30m005) | 6 | 4 | 0.805148668 | **Executed: 1.233552323dB, H2/H3≥30.02, MNA PASS; locally converged but Pareto dominated** |

Reference: `data/pareto_snapshots/rf_t005_rf_f003_20261017.json`. A numerical comparison of T005 and T007 is not a same-constraint improvement claim.

## First step: 3L, chip area 3

Electrical EXP-043 nodes IN=0, junction=1, OUT=2, shunt tip=3, GND=-1. L0(0,1), L1(1,2), Ls(1,3); fixed PCB Cf0(0,1), Cf1(1,2), Cp(3,GND); DTC Cv0(3,GND), Cv1(0,1), Cv2(1,2). Only Cv0 gets one extra fixed 0.5pF/Q40 at node3-GND. The original Cp also has Q40, so **only this exact topology** allows algebraically adding the two Q40 admittances inside the reduced-Y optimizer (`Cp_eff = Cp + 0.5pF`). This does **not** relax the PCB-C 0.2pF physical ceiling: physical Cp remains in 0.02..0.20pF. For verification, `area3_rft007.py` uses an independently assembled explicit 7×7 coupled-inductor branch-current MNA with **two distinct fixed branches** (Cp, parasitic) and independent loss accounting.

1. Verify the frozen original T005 26-value vector against recorded IL.
2. Recalculate the unchanged physical vector with T007 parasitic.
3. Construct a separate heuristic Cv0-compensated seed.
4. Constrained minimax SLSQP, coarse/fine meshes, six complete RF settings; select only candidates passing ≥30dB H2/H3 on 28×1001 finite grid.
5. For the best finite-grid compliant candidate, independent 7×7 MNA and power/positive-passivity checks on 28×3 probes.
6. Write full metadata, frozen/reoptimized vectors, constraint hash, SHA, solver convergence and failed runs to `results/EXP-050/area3_rft007.json`. These runtime results must be checked and curated into Git before being claimed as retained numeric evidence.

## Executed result — first step only (2026-10-19)

[GitHub Actions 39256882711](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/actions/runs/39256882711) **completed with SUCCESS** for the code and finite-grid evaluation. Numerical source: artifact `exp050-rft007-area3-run`, ID 12186859455; artifact ZIP SHA256 `698c128206d67f9fe7707d810933687b4d644f653592287b0337b021bb2081eb`, raw JSON member SHA256 `51b93ca5e130f3d4aa45fe4dbca93a659b953cfa4dc1e89bf7a821195909df3a`. Complete selected 26-element vector and independent checks were curated to [checkpoints/area3_rft007_best.json](checkpoints/area3_rft007_best.json), with hash recorded in the manifest.

| State | worst IL dB | minimum H2 dB | minimum H3 dB | 30dB finite-grid |
|---|---:|---:|---:|---|
| Historical saved RF-T005 candidate (no extra parasitic) | 0.944268363 | 30.020000 | 30.019923 | PASS under **T005** |
| SAME vector evaluated under T007 with 0.5pF/Q40 | **1.160748579** | **22.435890** | **21.298500** | FAIL |
| T007 Cv0 compensated heuristic, no parameter optimization | 0.941654212 | 30.073134 | 30.021732 | PASS |
| T007 SLSQP retuned, numerical best-found | **0.938309198** | **30.020000** | **30.019969** | PASS |

SLSQP coarse/refined stages reported success for both attempted starts; source goal H2/H3≥30.02dB during coarse/fine search. Final best worst-IL location B8 960 MHz; min H2 B8 1830MHz; min H3 B8 2693.34MHz. Frequency check: 28 disjoint intervals ×1,001 samples. Independent **7×7 branch-current MNA 84 probes PASS**, max discrepancy **1.421e−13dB** and power residual **7.806e−18W**, non-negative constituent dissipations, L matrix min eigenvalue **3.2421nH**. Additional Q40 parasitic is modeled as a physically distinct branch in the independent MNA.

**Interpretation:** Simply appending the physical parasitic makes the old T005 settings numerically noncompliant. Retuning all fixed/variable parameters produces a new T007-compliant local candidate. The T005-to-T007 worst-IL comparison across different constraints is **not** evidence that parasitics improve IL.

**Provenance correction:** The first numeric job ran after main EXP-050 reservation, but the required `manifest.json` was inadvertently omitted in the first PR head, causing an unrelated smoke audit to fail. The complete manifest and derived experiment index were then added as an explicit post-run provenance backfill; source execution commit and artifact hashes are retained. This is not falsely represented as a pre-run manifest. The audit must pass before the PR can be merged.

**Unperformed:** None of the six prescribed topology points; further robustness and 4L re-optimization remain, continuous-frequency extrema, real Q(f)/SRF, RF layout/EM, tolerance distributions, physical simultaneous coupling or hardware characterization. Phase 2 continues. No Phase 3 approval.


## Local reproducibility

```bash
git fetch origin main
uv sync --frozen
uv run --frozen python scripts/experiment_id_registry.py --experiment-id EXP-050 --owner MasayaTakagi
OPENBLAS_NUM_THREADS=1 uv run --frozen python experiments/chatgpt_topology_search/runs/EXP-050/area3_rft007.py --starts 2 --maxiter 100 --coarse 9 --refine 21 --dense 1001 --mna-points 3
```

## Second step: area 3⅔ EXP-045 (2026-10-19)

[GitHub Actions run 39260000528](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/actions/runs/39260000528) SUCCESS; original raw JSON SHA256 `0ea7db5a622e0e1b9edd0078ccec7bd925ffbbb0d31e83348658cefa1c1bf99d`. Full vector: [checkpoint](checkpoints/area3p667_rft007_best.json); independent 84-point MNA: [validation](validation/area3p667_independent_mna.json).

| Condition/setting | worst IL dB | min H2 dB | min H3 dB | Verdict |
|---|---:|---:|---:|---|
| RF-T005 saved, no shunt parasitic | 0.895180009 | 30.008000 | 30.008000 | Historical T005 PASS |
| RF-T007 same original vector | 1.076529383 | 20.534928 | 19.774387 | FAIL |
| RF-T007 Cv0-compensated only | 1.076529383 | 20.534928 | 23.167561 | FAIL |
| **RF-T007 local reoptimized** | **0.909728967** | **30.020000** | **30.020000** | **PASS**, finite 28×1001 grid |

The electrical model separately stamps shunt GJM Cp (Q80) and the 0.5pF DTC fixed parasitic (Q40). Only shunt DTC Cv0 receives the parasitic; Cv1/Cv2 are not grounded. The full 7×7 independent coupled-L MNA passed 84 boundary/midpoint probes: IL difference ≤1.5632×10⁻¹³dB, power residual ≤5.2042×10⁻¹⁸W, minimum L matrix eigenvalue 3.21549nH. The result is a numerical Phase 2 best-found local point; H2/H3 30dB margin only ~0.02dB, and physical/tolerance/continuous-band feasibility is not established. Steps 4–6 are not yet executed.

## Third step: area 4⅓, EXP-043 2-GJM/1-PCB (2026-10-19)

[GitHub Actions 39263830869](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/actions/runs/39263830869) numerical success; raw JSON SHA256 `34577596653c875cc730358aa68c7f2d3d5a62b82c01b4ae92a5974cf8ee5c1d`, artifact ZIP SHA256 `6a6ddef6467d8c5e8832681c45511bb7c513ff4550bb3866af8b1b90938e9e21`. Full candidate: [checkpoint](checkpoints/area4p333_rft007_best.json); independent [7×7 MNA](validation/area4p333_independent_mna.json).

| Candidate | Worst IL dB | Minimum H2 dB | Minimum H3 dB | H2/H3 30dB |
|---|---:|---:|---:|---|
| RF-T005 original | 0.879244690 | 30.020000 | 30.020000 | historical T005 PASS |
| RF-T007 original vector unchanged | 1.120636486 | 24.573618 | 16.517922 | FAIL |
| RF-T007 Cv0 compensation heuristic only | 1.120636486 | 24.573618 | 16.749606 | FAIL |
| **RF-T007 local reoptimized** | **0.891827011** | **30.020000** | **30.020000** | **PASS finite-grid 28×1001** |

Area unchanged: 3 LQP02HV (Q25), 2 GJM Cf0/Cp (Q80), 1 PCB Cf1 (Q40), 3 DTC (Q35). The **only grounded DTC Cv0** receives fixed 0.5pF/Q40. Fixed GJM and parasitic remain independent lossy branches; Cv1/Cv2 are non-ground. The independent 84-probe 7×7 branch-current MNA passed, maximum worst-IL difference 1.7053×10⁻¹³dB, power balance residual 7.8063×10⁻¹⁸W, minimum L matrix eigenvalue 2.61961nH. Minimum H2/H3 margins are only ~0.02dB; continuous-frequency extrema and physical tolerance are not verified. Still Phase 2. Remaining area 5⅓ and 6 checkpoints are pending.

## Fourth step: area 4⅔, 4L EXP-042 (2026-10-19)

[GitHub Actions 39265210817](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/actions/runs/39265210817) success; original raw JSON SHA256 `0bae54a9c3e979ede4a88da4672b9c30e3a5398bac3047f2b08da861e7c4a4d9` and ZIP SHA256 `83e7b507d136dc4177b23171ff6cd6deb6576fb432ce70c774fff5d8b1ca3cb1`. Full candidate saved as [initial nonconverged checkpoint](checkpoints/area4p667_rft007_initial.json) with separate [9×9 independent MNA](validation/area4p667_independent_mna.json).

| State | Worst IL | Minimum H2 | Minimum H3 | Finite 30dB |
|---|---:|---:|---:|---|
| Historical T005 | 0.819565 dB | 30.020dB | 30.020dB | historical PASS |
| T007 unchanged vector | 1.908049dB | 7.645896dB | 7.059332dB | FAIL |
| T007 heuristic both-shunt-C compensation | 1.336290dB | 7.025834dB | 7.977956dB | FAIL |
| **T007 first local search candidate** | **1.744673dB** | **30.005880dB** | **30.014461dB** | PASS |

Only Cv0 and Cv1 are grounded and each receives permanently fixed 0.5pF/Q40; non-ground bridge Cv2 receives no such parasitic. Four LQP02HV Q25, one GJM Cf0 Q80, three PCB-C Q40 remain unchanged in count/area. Important solver distinction: **selected first-start SLSQP was nonconverged (coarse/fine iteration caps hit)**, although its frozen output meets H2/H3 30dB across 28×1001 finite samples. An alternate start did not improve IL. Independent explicit 9×9 MNA verified 84 frequencies, max IL difference 2.274×10⁻¹³ dB, power residual 7.806×10⁻¹⁸W and minimum L-matrix eigenvalue 3.61448nH. This is a provisional screened candidate, not proof of optimum or a robust design; it is Pareto-dominated in area/IL by the T007 area4⅓ 3L candidate. Further multi-start and/or topology changes may improve it. Step 6 remains pending, Phase 2 only.

## Fifth step: area 5⅓, EXP-042 4L 2 GJM / 2 PCB (2026-10-19)

[GitHub Actions 39266499539](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/actions/runs/39266499539) SUCCESS. Raw JSON SHA256 `6684a22a0a246c1224c8f058200f9b59b7522b48026cf95f1cd8550e46026f3d`; artifact ZIP SHA256 `bc84206ba90dec2d5f15780213b877b2c6cb501f7a5c41128cc8c729b35d426e`. Complete candidate [checkpoint](checkpoints/area5p333_rft007_best.json); [independent MNA](validation/area5p333_independent_mna.json).

| State | Worst IL dB | Minimum H2 dB | Minimum H3 dB | Strict finite 30dB |
|---|---:|---:|---:|---|
| Historical T005 saved | 0.811306586 | 30.020000 | 30.020000 | T005 PASS |
| T007 unchanged source vector | 1.920216749 | 7.900110 | 7.065674 | FAIL |
| T007 two-shunt Cv compensation | 1.353438308 | 7.288567 | 7.931260 | FAIL |
| **T007 SLSQP reoptimized** | **1.054411931** | **30.020000** | **30.020000** | **PASS** |

4 starts x max180 local SLSQP: two converged, two nonconverged; selected start=1 converged coarse/refined. Four LQP02HV Q25, fixed Cf0/Cf2 GJM Q80, Cf1/Cp PCB Q40, with two independent fixed shunt parasitics (Cv0 and Cv1, 0.5pF/Q40 each). Bridge Cv2 has none. The 28×1001 frequency-mesh candidate passed H2/H3≥30dB; independent 9×9 coupled-L MNA passed 84 samples, maximum IL difference 8.455×10⁻¹³dB, power residual 1.301×10⁻¹⁷W, minimum L eig 2.63774nH. This locally converged design is nonetheless chip-area/IL Pareto-dominated by the area4⅓ 3L T007 candidate. Physical/Q(f)/SRF/EM/tolerance and continuous frequency extrema are not verified. All six listed topology adaptations have been numerically performed.

## Sixth step: area 6 EXP-042 4L, final RF-T007 adaptation (2026-10-19)

Initial 4-start [Actions 39267630715](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/actions/runs/39267630715): at least one strict H2/H3≥30dB numerical candidate was found, but its worst IL was **4.205431961dB**. Another candidate had worst IL **1.238320696dB**, H2=**29.989127447dB** and H3=30.012056550dB, so was **NOT RF-T007 compliant**. The near-miss was retained explicitly as a failure diagnostic with full vector, not a compliant candidate. Original raw JSON SHA256 `1450bee1ed5dff9a8a92c0022b5aaf9af45ddee7645bf0dcd39476c31d6d49cb`.

Controlled extra 3-start [Actions 39268341205](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/actions/runs/39268341205) reoptimized the near-miss with RF-T007 two grounded 0.5pF/Q40 fixed parasitics. **3/3 refinements converged**, best full finite-grid candidate: worst IL **1.233552323dB**, min H2 **30.020000dB**, min H3 **30.020000dB**; 28×1001 sample strict PASS. Frozen full 29-parameter vector: [best checkpoint](checkpoints/area6_rft007_best.json), [independent 9×9 coupled-L MNA](validation/area6_independent_mna.json), [initial near-miss record](validation/area6_initial_nearmiss_diagnostic.json). Refined JSON SHA256 `1e33f8b95b633e6c6dda27197f0028882e7b7566a2d8dc27b255ad6d50762711`; ZIP SHA256 `4b73374c26385b5be8067c6f87815ddd69b07caabbf9c63adcd9511482a46e20`. MNA (84 probe points) max IL difference 1.5632×10⁻¹³dB, power balance residual 5.2042×10⁻¹⁸W, L matrix min eig 1.98321nH. This is a converged local seed result, **not** a global minimax or continuous-band guarantee.

## Consolidated Phase 2 RF-T007 local Pareto findings (six original RF-T005 topology checkpoints)

| Historical area | L | RF-T005 saved worst IL dB | RF-T007 retuned worst IL dB | Strict H2/H3≥30dB finite-grid | Independent coupled-L MNA | Status within sampled RF-T007 six |
|---:|---:|---:|---:|---|---|---|
| **3** | 3L | 0.944268 | **0.938309** | PASS | PASS 84pt | **Non-dominated** |
| **3⅔** | 3L | 0.895180 | **0.909729** | PASS | PASS 84pt | **Non-dominated** |
| **4⅓** | 3L | 0.879245 | **0.891827** | PASS | PASS 84pt | **Non-dominated; minimum IL of six** |
| 4⅔ | 4L | 0.819565 | 1.744673 | PASS | PASS 84pt | **Dominated**, selected SLSQP nonconverged |
| 5⅓ | 4L | 0.811307 | 1.054412 | PASS | PASS 84pt | **Dominated**, selected SLSQP converged |
| 6 | 4L | 0.805149 | 1.233552 | PASS | PASS 84pt | **Dominated**, near-miss refinement SLSQP converged |

**Comparison rule:** Original RF-T005 numbers are archival results under a DIFFERENT trial and must not be used as direct improvements or as RF-T007-verified metrics. Only the RF-T007 IL numbers above form the sampled Pareto relationship. All six maintain their original chip-area formula and PCB component-count ceilings. All 3L topologies had exactly one grounded DTC with fixed parasitic; all EXP-042 4L topologies had two grounded DTCs. T007 adds no parasitic to any non-ground bridge DTC. Chip cost for unavoidable DTC shunt parasitic remains zero, but practical PCB/IC physical implementation overhead is NOT modeled.

**Scope of completion:** Original six historical topology checkpoints were adapted and evaluated using RF-T007; 19 total local starts (12 converged/7 nonconverged), 28×1001 finite mesh, 84 point independent MNA per selected checkpoint. This completes the **specified sequential pilot** only; neither global minimax, continuous-frequency extrema, component-specific Q(f)/SRF, tolerance, simultaneous physical k, distributed PCB EM nor actual prototype measurements have been verified. Further four-L multistart/topology redesign could change the frontier. Phase 2 continues; Phase 3 is stopped pending owner approval.

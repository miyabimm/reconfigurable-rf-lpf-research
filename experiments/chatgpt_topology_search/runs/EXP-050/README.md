# EXP-050 — Sequential RF-T005 Pareto adaptation to RF-T007 (Phase 2)

**Experiment reservation:** EXP-050 was committed to `main:data/experiment_number_registry.csv` on 2026-10-19 (request `rft007-t005-pareto-sequential-20261019`). This is one shared trial/goal covering the six saved non-dominated T005 topology checkpoints in increasing chip-area order; each topology is a separate serialized step and retained checkpoint. RF-T005 baseline results are preserved unchanged.

**Constraints:** Explicit trial RF-T007 (formal RF-F003 base; up to three 0..3pF/Q35 DTC branches). Every DTC whose ends include GND gets a separate **fixed 0.5pF/Q40** shunt-to-GND even when DTC is programmed to 0pF. Bridge/series DTC gets none. No other PCB-C count or nominal Q/area rules change. There is **no** RF-T006 3..6GHz additional stopband in RF-T007.

## Sequence (saved RF-T005 chip area ascending)

| Step | Source | Area | L | Original T005 IL dB | T007 adaption status |
|---|---|---:|---:|---:|---|
| 1 | EXP-043 `checkpoints/zero_gjm_double.json` | 3 | 3 | 0.944268363 | **Executed: 0.938309198dB / H2≥30.020 / H3≥30.019969, independent MNA PASS** |
| 2 | EXP-045 `checkpoints/t3l_extra_pcb_out_0p2_prelim.json` | 3⅔ | 3 | 0.895180009 | **Executed: 0.909728967dB, H2/H3≥30.02dB, independent MNA PASS** |
| 3 | EXP-043 `checkpoints/gjm_cf0_cp.json` | 4⅓ | 3 | 0.879244690 | Pending |
| 4 | EXP-042 `checkpoints/pcb_both.json` | 4⅔ | 4 | 0.819564515 | Pending |
| 5 | EXP-042 `checkpoints/pcb_cf1.json` | 5⅓ | 4 | 0.811306586 | Pending |
| 6 | EXP-042 `selected_checkpoints_rft005.json` (EXP042-30m005) | 6 | 4 | 0.805148668 | Pending |

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

**Unperformed:** Next four Pareto steps, continuous-frequency extrema, real Q(f)/SRF, RF layout/EM, tolerance distributions, physical simultaneous coupling or hardware characterization. Phase 2 continues. No Phase 3 approval.


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

The electrical model separately stamps shunt GJM Cp (Q80) and the 0.5pF DTC fixed parasitic (Q40). Only shunt DTC Cv0 receives the parasitic; Cv1/Cv2 are not grounded. The full 7×7 independent coupled-L MNA passed 84 boundary/midpoint probes: IL difference ≤1.5632×10⁻¹³dB, power residual ≤5.2042×10⁻¹⁸W, minimum L matrix eigenvalue 3.21549nH. The result is a numerical Phase 2 best-found local point; H2/H3 30dB margin only ~0.02dB, and physical/tolerance/continuous-band feasibility is not established. Steps 3–6 are not yet executed.

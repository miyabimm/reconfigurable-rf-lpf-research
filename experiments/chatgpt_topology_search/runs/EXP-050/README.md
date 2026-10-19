# EXP-050 — Sequential RF-T005 Pareto adaptation to RF-T007 (Phase 2)

**Experiment reservation:** EXP-050 was committed to `main:data/experiment_number_registry.csv` on 2026-10-19 (request `rft007-t005-pareto-sequential-20261019`). This is one shared trial/goal covering the six saved non-dominated T005 topology checkpoints in increasing chip-area order; each topology is a separate serialized step and retained checkpoint. RF-T005 baseline results are preserved unchanged.

**Constraints:** Explicit trial RF-T007 (formal RF-F003 base; up to three 0..3pF/Q35 DTC branches). Every DTC whose ends include GND gets a separate **fixed 0.5pF/Q40** shunt-to-GND even when DTC is programmed to 0pF. Bridge/series DTC gets none. No other PCB-C count or nominal Q/area rules change. There is **no** RF-T006 3..6GHz additional stopband in RF-T007.

## Sequence (saved RF-T005 chip area ascending)

| Step | Source | Area | L | Original T005 IL dB | T007 adaption status |
|---|---|---:|---:|---:|---|
| 1 | EXP-043 `checkpoints/zero_gjm_double.json` | 3 | 3 | 0.944268363 | **Implementation prepared; numeric run pending** |
| 2 | EXP-045 `checkpoints/t3l_extra_pcb_out_0p2_prelim.json` | 3⅔ | 3 | 0.895180009 | Pending |
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

**Status:** Workflow/script registered, numerical RF-T007 results unexecuted until CI run concludes. Finite grid is not continuous-band proof. No part-specific Q(f)/SRF/PCB EM/production tolerance or Phase 3 implementation.

## Local reproducibility

```bash
git fetch origin main
uv sync --frozen
uv run --frozen python scripts/experiment_id_registry.py --experiment-id EXP-050 --owner MasayaTakagi
OPENBLAS_NUM_THREADS=1 uv run --frozen python experiments/chatgpt_topology_search/runs/EXP-050/area3_rft007.py --starts 2 --maxiter 100 --coarse 9 --refine 21 --dense 1001 --mna-points 3
```

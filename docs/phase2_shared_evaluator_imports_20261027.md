# Phase 2 evaluator imports (2026-10-27)

## Scope and status

EXP-042 (RF-T005), EXP-055 (RF-T007), and EXP-058 (RF-T008 v3) remain
**frozen historical experiment sources**. This refactor introduces reusable
forward-evaluation modules under `src/lpf/phase2_models/`; it does not rewrite
their run summaries, checkpoints, optimization outcomes, constraint versions, or
independent MNA evidence. It does not reserve or execute a new EXP and does not
authorize Phase 3.

The external-port model is the same fixed input S2P → LPF → fixed output S2P
chain, with 50 Ω source and 60−j40 Ω load. All 28 frequency intervals and all
six settings remain in the model. RF-T007 permanent Q40 shunt parasitic and
RF-T008 v3 composite fixed Q60 / variable Q35 C are separate circuit models,
not interchangeable constraints.

## Stable nominal evaluator APIs

| Legacy source | Reusable import |
| --- | --- |
| `EXP-042/optimize.py` (`Evaluator`, topology/Q constants) | `lpf.phase2_models.exp042` |
| `EXP-055/adapt_f003_4l.py` (4L T007, independent 9×9 MNA, legacy optimizer stage) | `lpf.phase2_models.exp055` |
| `EXP-058/sweep_area3.py` (3L T008, independent 7×7 MNA, stage helper) | `lpf.phase2_models.exp058_area3` |
| `EXP-058/sweep_area4.py` (4L T008, zero GJM, independent 9×9 MNA) | `lpf.phase2_models.exp058_area4` |
| `EXP-058/sweep_area4l_gjm.py` (4L T008, GJM/PCB, independent 9×9 MNA) | `lpf.phase2_models.exp058_area4l_gjm` |

The common `_grid` module builds only sampled band arrays, ordered setting
labels, fixed S2P ABCD arrays, and three-inductor helpers. Forward evaluation
is *not* independent verification: the separate branch-current MNA algorithm
must still pass for any new candidate. The models are not a continuous-band
proof or physical Q(f), SRF, EMC/EM, tolerance, layout or Phase 3 model.

## Imports and compatibility

EXP-056, EXP-059–065, EXP-066, and EXP-067 use shared evaluator/solver
imports rather than adding EXP-042/055/058 directories to `sys.path`.
EXP-058 and earlier run programs keep their original import graph for source
provenance. Checkpoint *data* paths referencing historical EXP IDs remain
intact, because data provenance is distinct from executable dependency.

Some later EXP scripts still compose each other's specialized search classes
and dynamically change class/module globals (notably EXP-059–068). Those are
**remaining technical debt**, not evidence that the common evaluator interface
supports concurrent multi-experiment execution within one Python process.
The new shared module is intended to replace frozen evaluator imports, not to
serve as a new optimization runner or to replace `slsqp-staged-v2`.

## Verification

The `tests/test_phase2_shared_exp_evaluators.py` regression compares the
saved source vectors on 28×3 finite grids against the frozen source
implementations for all three model families, including off/on RF-T007
parasitic, separate RF-T008 IC fixed/variable C, six settings and external
two-port matrices. It also invokes separate 7×7 and 9×9 branch-current MNA
checks and guards against reintroducing the listed direct imports. The PR's
Phase 2 smoke workflow runs this test suite and compiles the package.

**Interpretation:** passing CI establishes numerical compatibility on the
sampled vectors and scripts tested. It does not reproduce the original
multi-start optimizations, change EXP performance records, or prove feasible
analog hardware.

# EXP-053 — RF-T007 four-inductor electrical topology exploration

**2026-10-19 owner direction:** Continue **new 4L topologies**, not H2/H3 margin growth or physical magnetic-k realization studies. All existing RF-T007 numerical limits, including **mandatory H2/H3≥30dB**, remain unchanged. Phase 2 only; Phase 3 requires explicit separate approval. Main ledger EXP-053 reservation `rft007-fourl-inductor-graph-sweep-20261019` must be verified before running.

## Reference and topology dimension

Freeze the complete [EXP-052 best PCB-C bridge candidate](../EXP-052/checkpoints/cf1_input_output_best.json), also copied byte-for-byte to [reference_exp052_cf1_bridge.json](reference_exp052_cf1_bridge.json) so EXP-053 has an immutable source. PR #131 has since merged into main; the byte content has been cross-checked with the main checkpoint. EXP-052 reported 4L, area **5⅓**, worst IL **0.88518932585dB**; the source is **different** from prior EXP-051 0.88899289dB.

Constant electrical C/DTC graph for all trials:

- GJM Cf0/Q80 (0,1); **PCB Cf1/Q40 (0,2)** crossing the series path; GJM Cp/Q80 (4,GND). Two GJM and one PCB capacitor, unchanged component budgets. Cf1 0.02–0.2pF, GJM each within approved capacitance range.
- IC DTC/Q35, individually 0–3pF: Cv0 (4,GND), Cv1 (0,1), Cv2 (1,2). **Exactly one** fixed Cpar (4,GND) 0.5pF/Q40, separate from Cv0, always present including Cv0=0.
- Four LQP02HV/Q25 each 0.4–27nH; chip area 4 + 2×⅔ = **5⅓**. Fixed physical row L0–LsA–LsB–L1 with adjacent numeric |k|≤0.10 and full M matrix SPD, no nonadjacent mutuals. *Checking algebraic model constraints is not a study of physical magnetic realization.*
- Six RF settings, 28 disjoint UL/DL/H2/H3 segments with external fixed input/output S2P, source 50Ω and load 60−j40Ω.

**Change only the four L connections** among nodes 0..4. All 12 graph variants have four distinct non-loop L edges, form a connected five-node spanning tree, and preserve the same C graph above. The reference is `[(0,1),(1,2),(1,3),(3,4)]`.

| Graph variant | 4L edge graph (L0,L1,LsA,LsB) | Structural idea |
|---|---|---|
| reference | (0,1),(1,2),(1,3),(3,4) | EXP-052 best |
| shunt_from_input | (0,1),(1,2),(0,3),(3,4) | Shunt originates at input |
| shunt_from_output | (0,1),(1,2),(2,3),(3,4) | Shunt originates at output |
| split_input_shunt_center | (0,3),(1,2),(3,1),(1,4) | Split input-side series branch |
| split_output_shunt_center | (0,1),(3,2),(1,3),(1,4) | Split output-side series branch |
| split_input_shunt_output | (0,3),(1,2),(3,1),(2,4) | Split series; shunt taps output |
| split_output_shunt_output | (0,1),(3,2),(1,3),(2,4) | Split series; output shunt |
| shunt_mid_tap_after_output | (0,1),(3,2),(1,3),(3,4) | Main path through shunt midpoint |
| line_to_shunt_via_output | (0,1),(1,3),(3,4),(4,2) | Shunt DTC at series-line node |
| line_through_shunt_node | (0,3),(3,1),(1,4),(4,2) | Main series path through tuned node |
| reordered_chain_output | (0,1),(1,4),(4,3),(3,2) | Reordered series chain |
| output_branch_input_tap | (0,3),(3,2),(3,1),(1,4) | Input-to-output direct branch and side network |

## Preregistered execution matrix

- Reproduce EXP-052 source checkpoint **0.88518932585dB** on the exact reference L graph using same S2P and RF-T007 parasitic, then search 12 L connection graphs with 2 seeded SLSQP starts each (24 total).
- Coarse 7 and refinement 17 points in each frequency segment, 28×1001 dense screening of all selected candidates. Minimize six-setting worst IL subject to mandatory **H2/H3≥30dB**; 30.005dB internal numerical guard only for precision, identical to EXP-052 and **not** a new harmonic margin objective.
- For every topology with a strict eligible candidate, **independently solve 9×9 coupled-inductor branch-current MNA** (84 probes), check max IL agreement and passive power balance.
- Keep solver convergence, strict failure and any experimental non-success separately. Archive complete 29-parameter L/C/k vector and six separate Cv sets only after execution.

**Pre-run status:** EXP-053 code and evidence only; numeric results must not be inferred from EXP-051/052. No SRF, Q(f), PCB EM, tolerance, physical coupling realism or Phase3 studies are performed under this instruction.


## Executed Phase 2 topology-sweep result — 2026-10-19

[GitHub Actions run 39284039531](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/actions/runs/39284039531) completed **SUCCESS**: source ledger check, Git-only pre-run audit, 12-graph uniqueness and source regression (2 unit tests), 12×2 SLSQP starts, 28×1001 point six-setting frequency evaluation, and independently assembled 84-probe 9×9 coupled-inductor MNA for each of the 12 strictly compliant selected graph points. **24 starts attempted: 19 converged, 5 nonconverged**; all 12 graphs yielded at least one strict compliant local point. For `split_output_shunt_output`, the selected IL1.986495dB is valid on grid and independent-MNA verified **but was not SLSQP-converged**. It is not counted as converged.

Original full 24-start raw artifact ID `12202397886` (file `inductor_graph_sweep.json`): raw SHA256 `b684316bd98141ffce2f36ad5f33be256e443ca86116dce251d69db52c775338`, artifact ZIP SHA256 `499452c354f4dffc5e07e8f1d3fcbb8f0a5d526b5d6074f406bb338874a341fe`, code execution SHA `e15fc8276737344eee8eb195cc000e98b45dd99b`.

| RF-T007 4L graph | Chip area | Worst IL dB | Minimum H2 dB | Minimum H3 dB | Selected SLSQP | Independent 9×9 MNA |
|---|---:|---:|---:|---:|---|---|
| **split_input_shunt_center** | **5⅓** | **0.875794664** | 30.005 | 30.005 | converged | PASS (84 pt) |
| reference (EXP-052 bridged PCB-C) | 5⅓ | 0.885189326 | 30.005 | 30.005 | converged | PASS |
| shunt_mid_tap_after_output | 5⅓ | 0.885850821 | 30.005 | 30.005 | converged | PASS |
| split_output_shunt_center | 5⅓ | 0.885973356 | 30.005 | 30.005 | converged | PASS |
| output_branch_input_tap | 5⅓ | 0.899521354 | 30.005 | 30.005 | converged | PASS |
| line_to_shunt_via_output | 5⅓ | 0.982207990 | 30.005 | 30.005 | converged | PASS |
| reordered_chain_output | 5⅓ | 1.081287061 | 30.005 | 30.005 | converged | PASS |
| shunt_from_input | 5⅓ | 1.183941167 | 30.005 | 30.005 | converged | PASS |
| split_output_shunt_output | 5⅓ | 1.986495315 | 30.005 | 30.005 | **nonconverged** | PASS |
| shunt_from_output | 5⅓ | 2.085695246 | 30.005 | 30.005 | converged | PASS |
| split_input_shunt_output | 5⅓ | 2.200820827 | 30.005 | 30.005 | converged | PASS |
| line_through_shunt_node | 5⅓ | 4.021160429 | 30.005 | 30.005 | converged | PASS |

[Full table + 24 start convergence counts](run_summary.json), [new best full 29-value L/C/k vector and six DTC states](checkpoints/split_input_shunt_center_best.json), [reference checkpoint](checkpoints/reference_best.json), [independent 9×9 MNA for new best](validation/split_input_shunt_center_independent_mna.json). Also retained [shunt-mid-tap diversity candidate](checkpoints/shunt_mid_tap_after_output_best.json). SHA-256 entries for all curated Git evidence are pinned by `manifest.json` and `storage_record.json`.

### Novel best graph

The changed inductor edges (L0,L1,LsA,LsB) are **(0,3), (1,2), (3,1), (1,4)**, while Cf0 GJM/Q80 (0,1), PCB Cf1/Q40 **(0,2)**, Cp GJM/Q80 (4,GND), Cv0 (4,GND), Cv1 (0,1), Cv2 (1,2), and the separate fixed Cv0 parasitic 0.5pF/Q40 (4,GND) are **unchanged**. L0 = **0.894241338 nH**, L1 = **7.845134776 nH**, LsA = **0.965238223 nH**, LsB = **4.031836128 nH**. Cf0 = **4.035414247 pF**, PCB-Cf1 = **0.0909539303 pF**, Cp = **0.760673235 pF**. The independent coupled-inductor L matrix minimum eigenvalue is **0.826205869 nH** (numerical SPD only). The 84-point independent 9×9 MNA's maximum IL difference is **4.4054×10⁻¹³ dB** and maximum power residual **5.2042×10⁻¹⁸ W**; PASS.

The new graph improves nominal worst IL from **0.885189325850** to **0.875794664236 dB**—a **0.009394661614 dB** improvement—without changing chip area or installed component counts. It is a **new observed RF-T007 area5⅓ best**, not a global minimum or proof about hardware. H2/H3 mandatory 30dB were enforced, but their extra attenuation margin was not an objective. Physical mutual-k feasibility, Q(f), SRF, PCB EM, variations, measurements, and Phase3 are not included.

**Execution status:** Original pre-run plan above is superseded by this actual Actions result; formal RF-F003 remains unchanged, RF-T007 remains a Phase2 trial. No Phase3 promotion is implied.

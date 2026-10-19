# EXP-053 — RF-T007 four-inductor electrical topology exploration

**2026-10-19 owner direction:** Continue **new 4L topologies**, not H2/H3 margin growth or physical magnetic-k realization studies. All existing RF-T007 numerical limits, including **mandatory H2/H3≥30dB**, remain unchanged. Phase 2 only; Phase 3 requires explicit separate approval. Main ledger EXP-053 reservation `rft007-fourl-inductor-graph-sweep-20261019` must be verified before running.

## Reference and topology dimension

Freeze the complete [EXP-052 best PCB-C bridge candidate](../EXP-052/checkpoints/cf1_input_output_best.json), also copied byte-for-byte to [reference_exp052_cf1_bridge.json](reference_exp052_cf1_bridge.json) so EXP-053 has an immutable source even while EXP-052 PR #131 remains unmerged. EXP-052 reported 4L, area **5⅓**, worst IL **0.88518932585dB**; the source is **different** from prior EXP-051 0.88899289dB.

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

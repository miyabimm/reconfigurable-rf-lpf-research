# Issue #163 — Stage 1 / first increment: immutable circuit placements

**Status:** proposed code under PR review; not a completed Stage 1 and not a new
EXP. The archived experiment scripts, RF policies, numeric result JSON, and
checkpoint data remain unchanged.

## New reusable structural API

`lpf.phase2_models.circuit_layout` exposes:

- `InductorTree(node_count, edges, source_node=0, load_node=2)`:
  immutable, orientation-preserving labelled L tree; checks distinct branches,
  hot-node connectivity, endpoints, and input/output ports. L-vector and
  signed-k ordering is **not** inferred or reordered.
- `CapacitorPlacement(node_count, fixed_edges, variable_edges,
  ic_fixed_edges)`: immutable ordered branch placement. When an IC-fixed
  capacitor set is specified, its branch positions must match the variable-C
  set one-to-one, including off-state retention. This class is structural and
  does not itself enforce component Q, capacity, branch-count or trial policy.
- `incidence_matrix` and `normalized_capacitor_edge`:
  zero-based hot nodes, ground -1. Incidence preserves explicit winding sign;
  capacitor normalization is for comparison, not L orientations.

For example, the electrical graph alternatives from EXP-060 can now be passed
as data:

```python
from lpf.phase2_models.circuit_layout import InductorTree
from lpf.phase2_models.exp058_area4l_gjm import Evaluator, independent_mna

graph = InductorTree(5, ((0, 1), (0, 3), (1, 4), (1, 2)))
model = Evaluator(policy, "input_output", ("cf0",), 3, l_edges=graph)
s2p_il = model.il(saved_vector)
proof = independent_mna(
    policy, "input_output", ("cf0",), saved_vector, l_edges=graph
)
```

This is a reusable **evaluation input**, not evidence that the alternate
topology was optimized or meets required RF performance.

## Integration scope

The existing Phase-2 shared RF-T007 four-L and RF-T008-v3 four-L models
(`exp055`, `exp058_area4`, `exp058_area4l_gjm`) accept an optional
`l_edges` argument for their evaluator and independent MNA. The default is
still the exact EXP-055/058 archived graph, and the immutable graph is retained
per evaluator instance. No `old4.L_EDGES` or `parent.Evaluator` monkeypatch
is required to test graph variations through this new interface.

Three-L and four-L structural checks, orientation retention, model isolation,
and independent MNA on a second four-L electrical graph are covered by
`tests/test_phase2_circuit_layout.py`. Existing frozen-source parity checks
still apply via `tests/test_phase2_shared_exp_evaluators.py`.

## RF-T008 v3 C-layout numerical integration (same PR)

New `lpf.phase2_models.rft008_layout.RFT008CapacitorLayout.for_policy`
binds a `CapacitorPlacement` to the resolved RF-T008 v3 policy, using the
existing `validate_variable_c_connections`,
`validate_trial_pcb_pattern_c_branches`, and
`ic_fixed_c_branches` validators. It retains immutable ordered C-branch
positions, per-branch Q and capacity bounds, and explicit variable-connection
roles. Ground PCB-C uses Q60/0.02–1pF; hot-hot PCB-C uses Q40/0.02–0.2pF;
GJM uses Q80, maximum 100pF and the EXP-058 *study* lower bound 0.02pF.
Variable DTC uses Q35/0–3pF; its paired, six-setting-invariant IC-fixed C
uses Q60 with 0.5–3pF grounded or 0.2–3pF hot-hot. There is **no** RF-T007
0.5pF/Q40 parasitic in RF-T008. The full policy permits 0, 1 or 2 installed
composite IC-DTC branches; source-shaped EXP-058 model wrappers still require
exactly 2 and retain their historical 22/24/25-dimensional vector layout.

The shared `sampled_admittance` function performs lossy, frequency-vectorized
capacitor stamping only; the numeric forward evaluator inserts those
admittances into its own nodal matrix. `validate_values` is a separate
**explicit** six-setting candidate-policy check: a caller must invoke it
for an externally supplied candidate before promoting a RF-compatible design.
Optimization bounds are generated from the approved per-connection policy,
but they do not replace this final candidate check.

All three source-shaped RF-T008 v3 evaluators accept
`capacitor_placement=CapacitorPlacement(...)`; their independent 7×7/9×9
MNA reconstruction accepts the same placement. The independent branch-current
algorithm is not rewritten as a call to the forward nodal stamp, preserving
solver independence. Existing EXP-058 scripts and saved evidence are intact.

```python
from lpf.phase2_models.circuit_layout import CapacitorPlacement
from lpf.phase2_models.exp058_area4l_gjm import Evaluator, independent_mna

capacitors = CapacitorPlacement(
    5, fixed_edges=((0, 1), (4, -1), (1, 2), (0, 3)),
    variable_edges=((4, -1), (0, 3)),
    ic_fixed_edges=((4, -1), (0, 3)),
)
ev = Evaluator(policy, "input_output", ("cf0",), 3,
               capacitor_placement=capacitors)
# Preserve the original EXP-style vector ordering and its capacitance bounds.
# No result from this alternative layout is claimed to satisfy RF limits.
numeric_samples = ev.il(test_vector)
mna = independent_mna(policy, "input_output", ("cf0",), test_vector,
                      capacitor_placement=capacitors)
```

`tests/test_phase2_rft008_layout.py` covers 0–2 installed composite
branches, incorrect PCB-count and Q bounds, independent Cfixed retention at
Cv=0, different 3L/4L capacitor placements, and independent 7×7/9×9 MNA.

## Common coupled-L/C network and EXP-compatible parameter schemas

`src/lpf/phase2_models/coupled_lc.py` now includes three new shared
components:

- `CoupledLCTopology(InductorTree, coupling_pairs, inductor_q,
  capacitor_edges, capacitor_q)`: explicit L winding/orientation, ordered
  signed-k matrix slots, per-L Q, ordered C edges and Q. RF policy bounds
  and physical coupling admissibility remain **separate** checks.
- `ParameterVectorSchema(n_inductors, n_fixed, n_coupling, n_ic_fixed,
  n_variable, constant_caps_pf=())`: a frozen, reversible mapping of
  `[L, Cfixed, k, IC-Cfixed, 6×Cvariable]` into 6 setting-specific,
  correctly ordered C vectors `[fixed, variable, IC-fixed, constant]`.
  The six-setting-invariant IC fixed values and permanent shunt parasitics
  cannot be silently reinterpreted as setting-variable values.
- `CoupledLCEvaluator(policy, points, topology, schema)`: a **forward**
  vectorized coupled-L nodal Y-stamp plus per-Q capacitor stamp; Schur
  reduction and external frozen S2P cascade in the same 28×6 sampled
  grid as the previous evaluators. Inputs are immutable and instance-local,
  without imports from historical EXP run scripts.

`tests/test_phase2_generic_coupled_lc.py` compares the new generic
evaluator at saved vectors against already-extracted EXP-042 RF-T005,
EXP-055 RF-T007 (with and without the constant DTC parasitic), and the
three distinct RF-T008-v3 EXP-058 area3/4/4L-GJM evaluator families.
It also checks an alternate 4L electrical tree, six-setting value
round-trip, SPD rejection, input shape validation and fixed-C invariance.
This is an **additional independent forward implementation** for numerical
parity, not the algorithmically independent branch-current MNA; current
7×7/9×9 MNA checks remain elsewhere and Stage 2 generic MNA remains open.

A schematic use by new Phase-2 code (the topology and Q are illustrative
configuration data, not automatic formal RF-policy approval):

```python
from lpf.phase2_models.circuit_layout import InductorTree
from lpf.phase2_models.coupled_lc import (
    CoupledLCTopology, CoupledLCEvaluator, ParameterVectorSchema,
)

network = CoupledLCTopology(
    InductorTree(5, ((0, 1), (1, 3), (1, 4), (1, 2))),
    ((0, 1), (1, 3), (3, 2)),
    (25., 25., 25., 25.),
    ((0, 1), (4, -1), (1, 2), (0, 3),
     (3, -1), (0, 3), (1, 2), (3, -1)),
    (80., 80., 40., 40., 35., 35., 35., 40.),
)
schema = ParameterVectorSchema(
    4, 4, 3, 0, 3, constant_caps_pf=(0.5,)
)
evaluation = CoupledLCEvaluator(policy, 3, network, schema)
sample_il_db = evaluation.il(saved_vector)
```

This wrapper's numerical parameter schema is deliberately *not* an RF
candidate approval or a claim that the values satisfy current physical
placement, Q, L/k or branch-count rules. A new EXP must validate the
resolved policy and independent MNA before any candidate is recorded.

## Still outstanding (do not close Stage 1)

- Extend the explicit `CapacitorPlacement` integration beyond source-shaped RF-T008 3L/4L: include RF-T005/T007, arbitrary C-branch counts and solver vector schema, and RF-policy-correct physical coupling slots.
- Connect the now-implemented generic 3L/4L L/C stamp and vector schema to
  final RF policy verification and EXP-043 variations. An immutable generic
  forward evaluator exists, but no complete policy-gated candidate API yet.
- Enforce the **resolved RF policy** at the final circuit-model creation
  boundary. Topological validity alone is not RF/physical admissibility.
- Continue Stage 1 against frozen EXP-042/043/055/058 vectors and Stage 2
  independent numeric regressions. Avoid modifications to archived scripts.
- Stage 3 uses `slsqp-staged-v2`; this increment runs no optimizer or new EXP.

The project remains **Phase 2**. Physical Q(f), SRF, EM, production tolerance,
and continuous-band proof are outside the performed checks.

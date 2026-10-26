# Issue #163 — Stage 1 / first increment: immutable circuit placements

**全体アーキテクチャ・公開API・完了基準の正規資料：**
[Stage 1 共通コア設計／DoD](issue163_stage1_core_architecture.md)。このファイルは個々の機能追加・数値互換の実装メモとして保持し、今後のStage 1判定は[Issue #165](https://github.com/miyabimm/reconfigurable-rf-lpf-research/issues/165)で管理する。

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

`tests/test_phase2_generic_exp043.py` additionally loads the **frozen**
EXP-043 `search_3l.py` only as a read-only regression oracle. It verifies
`zero_gjm_double` (3 PCB-Cs) and `two_gjm_bridge` (2 GJM + 1 PCB-C),
both 26-element RF-T005 three-L source vectors, against the very same generic
solver and schema. This covers the one-shunt L graph and two distinct
fixed-C type/variable-C connection combinations without a new EXP run.
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

## Stage-1 RF-T008 v3 resolved-policy validation boundary

`src/lpf/phase2_models/rft008_policy_circuit.py` adds the immutable
`PolicyBoundRFT008Circuit.from_policy` constructor for **new nominal
Phase-2 candidates**. It explicitly requires a registry-resolved,
unaltered RF-T008 revision-3 trial and stores a fingerprinted JSON copy.
A caller may not pass an altered dictionary merely relabelled RF-T008.
The connection and L/Q validation rules are read from current RF-F003 /
RF-T008 constraints rather than copied into a separate set of RF limits.

The constructor accepts `InductorTree`, named L series, physical chip
order, ordered signed-k slots, `CapacitorPlacement`, named GJM01 or
PCB_PATTERN_C fixed branches, and the explicit connection role of each
variable C. It constructs both the generic `CoupledLCTopology` and the
reversible `ParameterVectorSchema` without importing historical EXP
runners. It uses these already-approved checkers:

- `validation.validate_inductor_coupling` on the **full coupling matrix**
  including implicit zero off-diagonal entries, passing converted L
  inductances in **henries** (the new source model stores nH). Nominal
  nonadjacent chip couplings must be zero, adjacent chip pairs obey the
  resolved |k| bound, chip–PCB coupling is checked, and M must be SPD.
- LQP02HV uses the explicit RF-F003 series bounds 0.4–27nH/Q25;
  LQP02HQ uses 0.2–56nH/Q20; PCB_L uses positive L ≤2nH/Q12.
  Bare `LQP02` (no HV/HQ series), LQP01 (unconfirmed range) and
  currently unmodeled LQW04 bounds **fail closed** rather than silently
  inheriting the historical fixed-Q25 assumption. Support may be
  expanded when a fully specified range is available.
- `RFT008CapacitorLayout.validate_values` and the existing IC/PCB
  validators enforce fixed types and bounds, Q/parallel IC-fixed
  metadata, all six variable settings, 0–2 installed composite IC-C
  branches, one setting-invariant Q60 IC-fixed C per variable branch,
  Q35 variable C, and the RF-T008 prohibition on the former RF-T007
  Q40 shunt parasitic. There is **no formal GJM-count hard cap**; GJM
  usage participates in the area objective and its 0.02pF lower bound
  in this adapter is an explicitly documented EXP-style *search bound*.

`validate_candidate(vector)` returns component/placement verification
and the actual resolved-policy fingerprint, **not** RF filter approval.
`checked_summary(vector, points=3)` validates first, then returns
finite-grid forward metrics *separately*; independent branch-current
MNA, dense-frequency verification, optimizer convergence and physical
Q(f)/SRF/EM/tolerance checks remain mandatory before research-result
promotion. Direct `CoupledLCEvaluator.il()` intentionally remains
available for historical numerical parity but is **not a policy gate**.

Example with configuration derived from the same legal RF-T008 family:

```python
from lpf.constraint_versions import load_constraint
from lpf.phase2_models.circuit_layout import CapacitorPlacement, InductorTree
from lpf.phase2_models.rft008_policy_circuit import PolicyBoundRFT008Circuit

p = load_constraint("RF-T008", allow_trial=True)
v = ((0, 3), (1, 2))
c = PolicyBoundRFT008Circuit.from_policy(
    p,
    inductor_tree=InductorTree(
        5, ((0, 1), (1, 3), (1, 4), (1, 2))
    ),
    inductor_types=("LQP02HV",) * 4,
    physical_order=(0, 1, 3, 2),
    coupling_pairs=((0, 1), (1, 3), (3, 2)),
    capacitor_placement=CapacitorPlacement(
        5, ((0, 1), (4, -1), (1, 2), (0, 3)), v, v
    ),
    fixed_c_types=("GJM01", "PCB_PATTERN_C",
                   "PCB_PATTERN_C", "PCB_PATTERN_C"),
    variable_roles=("bridge", "bridge"),
)
component_check = c.validate_candidate(saved_vector)
sampled_report = c.checked_summary(saved_vector, points=3)
# NOT independent MNA verification, dense RF approval or a new EXP.
```

`tests/test_phase2_rft008_policy_circuit.py` checks saved EXP-058 3L
and 4L numerical parity under the new component policy; RF-T008 0/1/2
vs forbidden 3 installed C branches; false PCB/GJM/IC C bounds and
variable settings; physical chip adjacency, signed k and PCB mixed k;
HV/HQ/PCB-L value/Q differences; rejection of unsupported L series,
bad or altered policy dictionaries, and isolation of immutable
snapshots. These tests were added to the normal Phase-2 smoke CI.

## RF-T005/T007 policy-bound nominal circuit integration

`src/lpf/phase2_models/rft005_t007_policy_circuit.py` adds
`PolicyBoundRFT005T007Circuit.from_policy`. It creates a generic
`CoupledLCTopology` / `ParameterVectorSchema` from immutable, explicitly
typed 3L or 4L `InductorTree` and `CapacitorPlacement` inputs. The
fully resolved trial is authenticated against the current checked-in
registry via `load_constraint(id, allow_trial=True)` and the canonical
`constraint_fingerprint`. Any relabelled, modified or stale constraint
dictionary is rejected. Historical experiment runners are not imported.

**The T005/T007 distinction is structural, not just a policy label.**

- RF-T005: maximum **three** installed independent variable C branches
  (0–3 allowed), 0–3pF/Q35 each, **no** constant shunt DTC parasitic
  and **no** IC-fixed-C counterpart.
- RF-T007: the same variable-C branch limit, but **every installed
  ground-shunt DTC** has one extra constant **0.5pF/Q40** fixed capacitor
  between the same hot node and ground. It stays in the nodal stamp when
  `Cvar=0`, consumes none of the PCB_PATTERN_C count, and is *never*
  added to non-ground bridge/series DTCs. This is derived by calling
  `lpf.trial_shunt_dtc.shunt_dtc_parasitic_branches`; the number of
  parasitic branches varies with the installed physical DTC graph.
- Both: GJM01 fixed C Q80, positive nominal capacity ≤100pF
  (the formal policy does not specify a GJM numerical minimum);
  PCB_PATTERN_C fixed C Q40/0.02–0.2pF and maximum three fixed PCB
  branches. All fixed C values and L/k are six-setting-invariant.
  Exactly one installed physical variable-C branch per setting column,
  including correctly preserved zero-capacitance/series-open states.

`src/lpf/phase2_models/nominal_inductors.py` is reused by RF-T005,
RF-T007 and RF-T008 adapters for the explicit RF-F003 L-series
Q/bounds and nominal physical-chip-row adjacency, chip-PCB k=0,
full signed k matrix with unlisted pairs 0 and SPD check. It calls
the existing `validation.validate_inductor_coupling` with the
required nH→H unit conversion. Unconfirmed series ranges are *not*
inferred from archived Q25 shortcuts.

`validate_candidate(vector)` is a **component and placement** check.
`checked_summary` provides separate *sampled* metrics from the generic
forward evaluator. Neither function certifies dense RF compliance,
independent MNA, optimizer convergence or physical implementation.

`tests/test_phase2_rft005_t007_policy_circuit.py` tests:
EXP-042 (T005 4L), EXP-043 (T005 two distinct 3L configurations),
EXP-055 (T007 4L) saved-vector forward numerical parity; EXP-055's
historical two-DTC placeholder mapped to a *true two-variable-branch*
23-value vector; one/two/three installed shunt parasitics and Cv=0;
RF-T005 absence of parasitics; invalid roles, IC-fixed injection,
wrong/faked trial, k/physical coupling and L/C bounds. Frozen
EXP-055's independent 9×9 MNA is run separately. This is regression
evidence, not a new RF design.

## Still outstanding (do not close Stage 1)

- Extend the explicit `CapacitorPlacement` integration beyond source-shaped RF-T008 3L/4L: include RF-T005/T007, arbitrary C-branch counts and solver vector schema, and RF-policy-correct physical coupling slots.
- Connect the now-implemented generic 3L/4L L/C stamp and vector schema to
  final RF policy verification and additional topology/variable-C variants;
  EXP-043's two source layouts are already covered by frozen-vector parity.
  An immutable generic forward evaluator exists, but no complete
  policy-gated candidate API yet.
- Extend the **resolved RF policy** validation boundary (now available for
  RF-T005/T007/T008, LQP02HV/HQ/PCB_L) to other fully specified component
  series, formal RF-F003, and the final research-candidate/MNA evidence gate.
  Structural/policy validity is not proof of RF or physical feasibility.
- Continue Stage 1 against frozen EXP-042/043/055/058 vectors and Stage 2
  independent numeric regressions. Avoid modifications to archived scripts.
- Stage 3 uses `slsqp-staged-v2`; this increment runs no optimizer or new EXP.

The project remains **Phase 2**. Physical Q(f), SRF, EM, production tolerance,
and continuous-band proof are outside the performed checks.

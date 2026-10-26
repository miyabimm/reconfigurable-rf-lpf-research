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

## Still outstanding (do not close Stage 1)

- Generalize explicit GJM/PCB-C connections, allowed Q/bounds, variable-C
  placements, and coupling slots across the forward evaluators; the new
  `CapacitorPlacement` class is not yet connected to all numerical models.
- Extract the generic 3L/4L coupled-L and capacitor stamping engine and the
  optimization vector schema, rather than subclassing each EXP-shaped model.
- Enforce the **resolved RF policy** at the final circuit-model creation
  boundary. Topological validity alone is not RF/physical admissibility.
- Continue Stage 1 against frozen EXP-042/043/055/058 vectors and Stage 2
  independent numeric regressions. Avoid modifications to archived scripts.
- Stage 3 uses `slsqp-staged-v2`; this increment runs no optimizer or new EXP.

The project remains **Phase 2**. Physical Q(f), SRF, EM, production tolerance,
and continuous-band proof are outside the performed checks.

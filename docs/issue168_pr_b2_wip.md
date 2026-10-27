# Issue 168 PR-B2 — WIP evidence

Base: `e7226e67c6e5eef2d85d00f43dcd8e8dc7f97b35`. This is an incomplete draft, not Stage 2 completion or certification.

- Frozen EXP-042, EXP-043 (zero_gjm_double and two_gjm_bridge), EXP-055 and EXP-058 vectors: RF-T005/T007/T008 trial policies, 28 canonical case-linked intervals × 3 endpoints/midpoint = 420 comparisons, not the six-setting cross product. Assertions enforce absolute IL error < 1e-9 dB, power residual < 1e-12 W and passive loss tolerance. Forward nodal/matrix methods are mocked to fail during MNA.
- Two-point real EXP-042 cross scan: 6 × 28 segments (336 samples); synthetic 3-point cross scan tests local refinement and distinguishes mandatory 30 dB from nominal 35 dB. Local refinement only detects sampled interior extrema, not arbitrary hidden features. No continuous-frequency guarantee.
- Local `uv run --frozen` unittest: independent RF 3 tests, public API 6, branch MNA 6, EXP-043 generic 1, T005/T007 policy circuit 8: 24 tests passed (subtests included in their parent test). No large dense run or optimization.
- Attempted wider `test_phase2*.py` suite before final fix: failed due to a temporary test syntax error (subsequently fixed) and a pre-existing history check referencing `26a5d4a:docs/archive/maintenance_notes_20261027.md`, absent in the local Git history. Full suite has not been rerun after the fix; CI result must be verified separately.

## Required before review / remaining work

- Record actual maximum IL error and power residual with vector, setting and frequency; currently only assertion thresholds are established. Record refined synthetic numerical evidence and final head SHA.
- Strengthen local-extremum failure and non-finite/non-passive tests, boundary/label assertions, explicit flag separation and per-role worst-case summaries. Review dense completion semantics and threshold handling. Verify exact-head Actions actually runs the amended test.
- Full Stage 1 regression and history audit remain outstanding. Promotion gate integration and final history/DoD audit are PR-B3. No independent review yet; do not merge this draft.
- RF-F003 and RF-T006 remain unsupported by the Stage 1 API. No fixed policies, RF thresholds, S2P, historical EXP artifacts, Phase 3 or physical validation were changed or authorized.

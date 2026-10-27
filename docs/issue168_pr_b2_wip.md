# Issue 168 PR-B2 — finite-grid evidence

Base: `e7226e67c6e5eef2d85d00f43dcd8e8dc7f97b35`. Draft, not Stage 2 completion or certification. Changes after reviewed WIP head `75bed7c0228c590c88ce268fb43196cc1ddf860e` address the review; the PR head identifies the resulting code and tests.

## Five-vector parity

`uv run --frozen python -m unittest discover -s tests -p test_phase2_independent_rf.py -v`: 5 saved vectors × 28 canonical case-linked intervals × 3 endpoints/midpoint = 420 samples, not the six-setting cross product. Component policy, ID, fingerprint and six settings are checked; forward nodal/matrix methods are mocked to fail during MNA. IL error < 1e-9 dB, power residual < 1e-12 W and passive loss tolerance are asserted. Local measured maxima:

- |ΔIL| = **4.476419235288631e-13 dB**, EXP-058 area4p667, RF-T008, setting 4, segment 23, 2442 MHz; policy fingerprint `7de08611f8dd15b40fdfb7946e8c93de5796d026641bdca0f12e992962d05fd4`.
- |power residual| = **5.833007687972014e-17 W**, EXP-043 zero_gjm_double, RF-T005, setting 0, segment 1, 652 MHz; fingerprint `59a451775ab4914cf9f0e51785ebfb62b36217af7735e7c93e9fe70f2323e67c`.

Input SHA-256 (read only):

- `experiments/chatgpt_topology_search/runs/EXP-042/preliminary_js_5pt.json`: `c1a1dcdb61cb49ed983256cc4a115425342d6fb60ed1e095c4fb5aaf5d750930`
- `experiments/chatgpt_topology_search/runs/EXP-043/checkpoints/zero_gjm_double.json`: `8578a6b39d5af0e71028b7ffcd0237d2ffc6101e9b19d3642b5fc3d525dfa975`
- `experiments/chatgpt_topology_search/runs/EXP-043/checkpoints/two_gjm_bridge.json`: `7408b3639deb31d5f3bfb4acfc1626b8ac87374837cf3ea5c8109b6abcafcbed`
- `experiments/chatgpt_topology_search/runs/EXP-055/checkpoints/cv1_input_tip_best.json`: `65d0d637e8a233c97e6a76b39dca2a15aaf90e46b2380ffaae1b6ea1689361cb`
- `data/pareto_snapshots/rf_t008_exp058_area4p667_20261020.json`: `f1a63cf5bcc95fc1b1f31f0bb7c20b2f52b035ac8084e89289ec76f794b6fca9`

## Scan evidence and limitations

Two-point real EXP-042 cross scan: 6 × 28 segments (336 samples); synthetic 3-point cross scan exercises local peak and stopband minimum refinement, labels, tie order, and distinguishes mandatory 30 dB from nominal 35 dB. Two-point refinement is rejected; numerical errors and unsuccessful/non-finite optimizer results fail closed. A successful refinement only examines sampled interior extrema and cannot guarantee detection of an invisible feature or prove a continuous-frequency bound. Summaries separately report pass, UL, DL, H2, H3 worst with location, for the requested canonical or cross mode. Cross is diagnostic, not a canonical RF verdict.

Local `uv run --frozen python -m unittest discover -s tests -p 'test_phase2*.py'`: 109 tests passed, including Stage 1 regressions and history check. The earlier history failure was resolved when the missing Git object was fetched; no test was relaxed. Exact-head Actions and independent re-review are pending; do not merge before both. Full historical audit and promotion gate integration are PR-B3. No large dense run, optimization, Phase 3 or physical validation. RF-F003 and RF-T006 remain unsupported by the Stage 1 API. Formal policies, RF thresholds, S2P and historical EXP artifacts are unchanged.

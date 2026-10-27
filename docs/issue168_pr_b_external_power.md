# Issue 168: PR-B1 independent external-port sample and power audit

Base: main `37d8e570bf40d1a778835204df71a052ea403472` (PR-A). This is a **partial PR-B**, not completion of Issue #168. The exact code revision is the PR head.

`evaluate_independent_sample` uses the normalized circuit and the resolved policy held by its adapter. It reads the existing SHA-verified 50-ohm RI S2P files. Each S matrix is converted to port admittance directly; the source and load endpoints are eliminated before calling the independent branch-current solver. No LPF forward Y, Schur or ABCD matrix is used. Near-singular S conversion and boundary equations fail closed. Voltage/current are peak phasors: P = Re(V I*)/2. A 1 V peak Thevenin source gives available power 1/(8 Re(Zs)). Input power excludes source resistance loss; S2P power differences, L and C losses, and load absorption are counted once. Passive S2P validation and mutual-L SPD checks are provided by the existing loaders/solver.

## Limited local evidence

`uv run --with pytest pytest tests/test_phase2_branch_mna.py tests/test_phase2_independent_rf.py tests/test_phase2_public_circuit_api.py tests/test_phase2_generic_coupled_lc.py tests/test_phase2_generic_exp043.py tests/test_phase2_s2p_grid_cache.py tests/test_phase2_rft005_t007_policy_circuit.py tests/test_phase2_rft008_policy_circuit.py tests/test_phase2_circuit_layout.py tests/test_phase2_numeric_diagnostics.py tests/test_phase2_connection_roles.py -q`: **65 passed, 95 subtests passed**.

After review, the new parity test was converted to `unittest.TestCase` and added to the smoke workflow. Local `uv sync --frozen` and `uv run --frozen python -m unittest discover` for that test, the 13 other Stage 2 workflow modules and `test_github_actions_yaml_keys.py`: **85 tests passed**. The new test includes 168 sample subtests. The previous exact-head Actions [#40512697337](https://github.com/miyabimm/reconfigurable-rf-lpf-research/actions/runs/40512697337) succeeded at `7d50131daf33a8d2a458d5157b139769ea73e1b3` but did **not** run the new test; CI for the revised head must be checked separately.

For EXP-042, EXP-055 and EXP-058 saved vectors, two endpoints per canonical interval (56 samples per vector, each interval's associated setting, 168 total), fixed external S2P and policy source/load: maximum |independent − forward IL| **4.48e-13 dB** (RF-T008, 2442 MHz, setting index 4); maximum absolute power balance residual **4.27e-17 W**. Regression tolerance is 1e-9 dB and 1e-12 W. The test disables forward LPF node/matrix methods during each independent solve. These values are finite sampled numerical comparisons, not continuous-frequency or compliance guarantees.

## Still required before completing PR-B / Issue #168

- EXP-043 independent parity and broader frozen-vector evidence, including all settings and representative additional frequencies.
- Dense RF implementation and gate across all required intervals/settings, local extrema diagnostics and threshold evidence; any large dense run requires prior approval.
- Explicit separate certification flags and promotion-gate integration, including optimization/physical evidence and existing role blockers.
- Further boundary/passivity and invalid-input tests, full Stage 1 targeted regression, historical immutability audit and exact-head CI; independent review and owner approval before merge.

No EXP reservation, optimization, large dense run, Phase 3 transition or RF policy change is made here. The result deliberately keeps `rf_compliance_certified` false and candidate promotion blocked.

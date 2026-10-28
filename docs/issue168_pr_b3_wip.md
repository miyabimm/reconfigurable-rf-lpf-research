# Issue #168 PR-B3: audit gate WIP

Base: `52a57cd5fe2e598267e9116fb78131d237f6f711`. This is an **incomplete draft**, not a Stage 2 completion claim. Existing Stage 2 work is in #169, #171 and #176. No promotion or certification is enabled.

`audit_candidate` re-runs the existing component and L-tree role checks and preserves their blockers. Other evidence is explicitly not run, and the API does not accept caller-supplied checked flags. It cannot yet ingest or bind independent MNA, forward or dense results. Electrical role evidence is not physical proof.

## DoD status at this draft

| DoD | Status / evidence and limitations |
| --- | --- |
| S2-01–03 | Implemented in #169; this draft does not re-audit all cases. |
| S2-04–05 | Limited external boundary and power evidence in #171 and #176; final negative-case audit remains. |
| S2-06 | Limited 5-vector, 420 canonical sample parity in #176; not a dense run. |
| S2-07 | Finite-grid scan and local candidate refinement implemented in #176; production dense run not approved or performed; no continuous guarantee. |
| S2-08 | Existing failures tested in prior PRs; final missing-case review remains. Unsupported RF-F003/T006 adapters stay fail-closed. |
| S2-09 | Initial always-blocked report only. Identity-bound evidence integration and RF thresholds remain to implement. |
| S2-10 | Incomplete: full regression, immutable history/provenance audit, exact-head CI and independent review remain. |

## Local evidence

`OPENBLAS_NUM_THREADS=1 uv run --frozen python -m unittest discover -s tests -p test_phase2_independent_rf.py -v`: 6 tests pass, including the existing 420-sample parity test. In this environment its largest IL difference was 4.476419235288631e-13 dB (EXP-058, RF-T008, setting 4, segment 23, 2442 MHz); maximum absolute power residual 5.833007687972014e-17 W (EXP-043 zero_gjm_double, RF-T005, setting 0, segment 1, 652 MHz). These are limited numerical evidence, not independent review or RF certification.

Six further existing modules (public API, branch MNA, connection roles, S2P cache, T005/T007 and T008 policy circuits): 40 tests pass locally. Full CI and historical audits have not been run for this draft. No EXP, source data, policy, checkpoint or RF limits were modified; no optimization, production dense run or Phase 3 transition was performed.

## Remaining before review/merge

- Bind results to vector, definition, effective policy, code SHA, and exact canonical coverage; reject mismatches, stale/missing evidence, non-passivity and power imbalance. Do not equate cross or reduced grids to dense evidence.
- Report mandatory versus nominal thresholds and separate forward/MNA/dense/local/optimization/physical/owner evidence. Never promote or certify automatically.
- Complete negative-case tests, read-only reproducibility and historical protection audits, input SHA/source records and the S2-01–10 evidence table. Run full required regressions and verify exact-head Actions and independent review.

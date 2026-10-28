# Issue #168 PR-B3: audit gate WIP

Base: `52a57cd5fe2e598267e9116fb78131d237f6f711`. This is an **incomplete draft**, not a Stage 2 completion claim. Existing Stage 2 work is in #169, #171 and #176. No promotion or certification is enabled.

`audit_candidate` re-runs component and L-tree role checks and preserves their blockers. Optionally it recomputes a small canonical forward/MNA/power grid and binds the resulting observations to the candidate and current source/inputs. A prior record can be compared only after recomputation and cannot supply a pass by itself. Dense, physical and owner evidence remain not run. Electrical role evidence is not physical proof.

## DoD status at this draft

| DoD | Evidence and status | Limitations |
| --- | --- | --- |
| S2-01 | Implemented/CI verified: #169 `api.py`, `branch_mna.py`; `test_phase2_public_circuit_api.py`, `test_phase2_branch_mna.py`, [run 40509588025](https://github.com/miyabimm/reconfigurable-rf-lpf-research/actions/runs/40509588025), head `6026871`. | No archived evaluator import in MNA. |
| S2-02 | Implemented/CI verified: #169 `branch_mna.py`, `test_phase2_branch_mna.py`, same run. | Independent branch-current formulation, not physical proof. |
| S2-03 | Implemented/CI verified: #169 adapters and `test_phase2_rft005_t007_policy_circuit.py`, `test_phase2_rft008_policy_circuit.py`, same run. | Trial nominal models only. |
| S2-04 | Limited numerical evidence: #171 `independent_rf.py`, `test_phase2_independent_rf.py`, [run 40518103011](https://github.com/miyabimm/reconfigurable-rf-lpf-research/actions/runs/40518103011), head `7fbfc90`. | Fixed S2P and specified impedances, not EM measurement. |
| S2-05 | Limited numerical evidence: #171/#176 `independent_rf.py`, `branch_mna.py`, `test_phase2_independent_rf.py`, [run 40604184799](https://github.com/miyabimm/reconfigurable-rf-lpf-research/actions/runs/40604184799), head `8e8318b`. | #177 working-tree power acceptance awaits new CI/review. |
| S2-06 | Limited numerical evidence: #176 `test_frozen_external_parity_and_power`, run 40604184799; 5 saved vectors and 420 canonical samples. | Not dense or certification; source records below. |
| S2-07 | Implemented/CI verified: #176 `independent_scan.py`, `test_scan_coverage_and_refinement`, run 40604184799. | Production dense **not_run**; finite grid/refinement is not a continuous guarantee. |
| S2-08 | Implemented/CI verified: #169 `branch_mna.py`, `api.py`, diagnostics and associated tests, run 40509588025; #176 scan failures, run 40604184799. | Final integrated negative-case review remains; RF-F003/T006 adapters blocked. |
| S2-09 | #177 `candidate_audit.py`, `limited_candidate_evidence.py`, `test_phase2_independent_rf.py`: limited candidate-bound recomputation. | Working-tree changes not CI verified; dense/physical/owner not_run; promotion blocked. |
| S2-10 | **blocked**: local provenance/storage audits and regressions below. | Inventory mismatch, final matrix review, new exact-head CI and independent review remain. |

## Local evidence

`OPENBLAS_NUM_THREADS=1 uv run --frozen python -m unittest discover -s tests -p test_phase2_independent_rf.py -v`: 6 tests pass, including the existing 420-sample parity test. In this environment its largest IL difference was 4.476419235288631e-13 dB (EXP-058, RF-T008, setting 4, segment 23, 2442 MHz); maximum absolute power residual 5.833007687972014e-17 W (EXP-043 zero_gjm_double, RF-T005, setting 0, segment 1, 652 MHz). These are limited numerical evidence, not independent review or RF certification.

Six further existing modules (public API, branch MNA, connection roles, S2P cache, T005/T007 and T008 policy circuits): 40 tests passed locally at the earlier draft. Full CI and complete historical audits remain outstanding. No EXP, source data, policy, checkpoint or RF limits were modified; no optimization, production dense run or Phase 3 transition was performed.

## Incremental review response (working tree)

`scan_independent_rf` reports UL/DL nominal and H2/H3 mandatory and nominal comparisons from the resolved full-LPF policy. Equality meets the specified limits; a successful comparison is only `sampled_numeric_observation`, never certification. The report records canonical versus cross coverage and finite-grid versus locally refined scope. This is not a matching-only assessment and does not establish continuous-band compliance. The gate recomputes these observations on the same canonical grid as forward/MNA and power, using only 2 or 3 points per interval. An untrusted prior record is accepted only if the entire record matches a fresh recomputation; mismatches fail closed. It records definition/vector fingerprints, actual source tree hash, git HEAD and dirty state, band/S2P hashes, environment, every sample's setting/segment/frequency, and tolerances. It checks the approved effective policy, S2P hashes, finite values, losses, residuals and forward parity; solver SPD/S2P passivity checks remain in the existing implementations. The recorded HEAD alone does not identify a dirty worktree, and the source hash is not independent attestation. A persisted record alone is never authenticated or sufficient.

At HEAD `2d86d027c371bcaff1be98475f43d3b25ecd45e1`, [Actions #40653662881](https://github.com/miyabimm/reconfigurable-rf-lpf-research/actions/runs/40653662881) verified 7 independent RF tests. Subsequent working-tree local regression on Python 3.12.15 with `OPENBLAS_NUM_THREADS=1 uv run --frozen`: 17 Stage 1/2, constraint, provenance and storage modules passed 122 tests, including 11 independent RF tests. The other 22 modules in the existing smoke workflow passed 122 tests; `verify_phase2_cleanup_w1_links.py --active-only` also passed. `audit_provenance()` passed; `audit_new_experiment_storage.py audit` passed, with EXP-058 running and its committed readback false. `audit_experiment_inventory.py` and its 2-test module failed: inventory count/missing experiments; this checkout has 70 tracked manifests but 45 inventory records. No history was edited to make the audit pass. These working-tree results are not exact-head CI or independent review.

## Read-only frozen input audit

At local HEAD `2d86d027c371bcaff1be98475f43d3b25ecd45e1`, the following working files matched `git show HEAD:<path>` byte-for-byte. SHA-256 values describe inputs to the limited parity tests, not claims about the historical execution environment. EXP-058 is a preserved snapshot, not a reclassified manifest. No historical originals were edited.

| Input | SHA-256 |
| --- | --- |
| `experiments/chatgpt_topology_search/runs/EXP-042/preliminary_js_5pt.json` | `c1a1dcdb61cb49ed983256cc4a115425342d6fb60ed1e095c4fb5aaf5d750930` |
| `experiments/chatgpt_topology_search/runs/EXP-043/checkpoints/zero_gjm_double.json` | `8578a6b39d5af0e71028b7ffcd0237d2ffc6101e9b19d3642b5fc3d525dfa975` |
| `experiments/chatgpt_topology_search/runs/EXP-043/checkpoints/two_gjm_bridge.json` | `7408b3639deb31d5f3bfb4acfc1626b8ac87374837cf3ea5c8109b6abcafcbed` |
| `experiments/chatgpt_topology_search/runs/EXP-043/search_3l.py` | `15fbc70d81cc6926a07ae0ea9c6f571a050588138aece8613e0ef9eb7cca37c9` |
| `experiments/chatgpt_topology_search/runs/EXP-055/checkpoints/cv1_input_tip_best.json` | `65d0d637e8a233c97e6a76b39dca2a15aaf90e46b2380ffaae1b6ea1689361cb` |
| `data/pareto_snapshots/rf_t008_exp058_area4p667_20261020.json` | `f1a63cf5bcc95fc1b1f31f0bb7c20b2f52b035ac8084e89289ec76f794b6fca9` |
| `data/bands.csv` | `1b1182e4c947059cb263c1af52ddf64236bd1fd9e83770cc844126576c7865fe` |
| `data/parasitics/circuit1_ant_coupler_0_6ghz.s2p` | `ad266111ba1dc2b92f235d39f4a647ff271050bc11941c217661dd299ee59945` |
| `data/parasitics/circuit2_poc_through_0_6ghz.s2p` | `b3cfc861bc0c8221f49328598c9d7d0766a6e94e42e990b6a50f6c90bf9a84da` |

Resolved trial fingerprints: RF-T005 `59a451775ab4914cf9f0e51785ebfb62b36217af7735e7c93e9fe70f2323e67c`, RF-T007 `c6f0fc685464964fff2abedf8b99dda0064c99bbe133ec8fecd91c4f60d2b430`, RF-T008 `7de08611f8dd15b40fdfb7946e8c93de5796d026641bdca0f12e992962d05fd4`. These are current overlays, not relabeling of original historical manifests.

## Remaining before review/merge

- Review the recompute-and-compare evidence contract and complete integrated negative cases. Do not equate cross or reduced grids to dense evidence.
- Complete negative cases and independently review the frozen-input SHA/blob audit and S2-01–10 matrix. Investigate the inventory mismatch without changing historical records. Verify new exact-head Actions and independent review.
- Maintain separate forward/MNA/dense/local/optimization/physical/owner states; never promote or certify automatically.

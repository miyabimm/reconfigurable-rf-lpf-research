# Issue #168 PR-B3: limited candidate audit gate — review evidence

Initial base: `52a57cd5fe2e598267e9116fb78131d237f6f711`. PR-B3 provides limited candidate-bound recomputation, **not RF compliance certification**. Stage 2 prior work is in #169, #171 and #176. Historical inventory reconciliation is tracked separately in [Issue #170](https://github.com/miyabimm/reconfigurable-rf-lpf-research/issues/170), by owner direction. No promotion or certification is enabled.

`audit_candidate` re-runs component and L-tree role checks and preserves their blockers. Optionally it recomputes a small canonical forward/MNA/power grid and binds the resulting observations to the candidate and current source/inputs. A prior record can be compared only after recomputation and cannot supply a pass by itself. Dense, physical and owner evidence remain not run. Electrical role evidence is not physical proof.

## DoD status at this draft

| DoD | Evidence and status | Limitations |
| --- | --- | --- |
| S2-01 | Implemented/CI verified: #169 `api.py`, `branch_mna.py`; `test_phase2_public_circuit_api.py`, `test_phase2_branch_mna.py`, [run 40509588025](https://github.com/miyabimm/reconfigurable-rf-lpf-research/actions/runs/40509588025), head `6026871`. | No archived evaluator import in MNA. |
| S2-02 | Implemented/CI verified: #169 `branch_mna.py`, `test_phase2_branch_mna.py`, same run. | Independent branch-current formulation, not physical proof. |
| S2-03 | Implemented/CI verified: #169 adapters and `test_phase2_rft005_t007_policy_circuit.py`, `test_phase2_rft008_policy_circuit.py`, same run. | Trial nominal models only. |
| S2-04 | Limited numerical evidence: #171 `independent_rf.py`, `test_phase2_independent_rf.py`, [run 40518103011](https://github.com/miyabimm/reconfigurable-rf-lpf-research/actions/runs/40518103011), head `7fbfc90`. | Fixed S2P and specified impedances, not EM measurement. |
| S2-05 | Limited numerical evidence: #171/#176 `independent_rf.py`, `branch_mna.py`, `test_phase2_independent_rf.py`, [run 40604184799](https://github.com/miyabimm/reconfigurable-rf-lpf-research/actions/runs/40604184799), head `8e8318b`; #177 limited power acceptance [run 40662780520](https://github.com/miyabimm/reconfigurable-rf-lpf-research/actions/runs/40662780520), head `5f20e89`. | Finite samples, not physical validation. |
| S2-06 | Limited numerical evidence: #176 `test_frozen_external_parity_and_power`, run 40604184799; 5 saved vectors and 420 canonical samples. | Not dense or certification; source records below. |
| S2-07 | Implemented/CI verified: #176 `independent_scan.py`, `test_scan_coverage_and_refinement`, run 40604184799. | Production dense **not_run**; finite grid/refinement is not a continuous guarantee. |
| S2-08 | Implemented/CI verified: #169 `branch_mna.py`, `api.py`, diagnostics and associated tests, run 40509588025; #176 scan failures, run 40604184799. | Final integrated negative-case review remains; RF-F003/T006 adapters blocked. |
| S2-09 | Limited candidate-bound recompute and fail-closed gate in #177: `candidate_audit.py`, `limited_candidate_evidence.py`, `test_phase2_independent_rf.py`. [Exact-head run 40665848367](https://github.com/miyabimm/reconfigurable-rf-lpf-research/actions/runs/40665848367) passed at `d6f1589` with 11 independent RF tests; aggregate blocker-consistency correction follows in this PR. | Historical source identity `not_checked`; full dense/physical/owner `not_checked`; promotion always blocked. New correction needs its own exact-head CI. |
| S2-10 | **Review/CI pending** for final PR head; earlier required regression and provenance/storage audits below. | Pre-existing inventory 45/66 mismatch is an explicit **known FAIL** managed in #170; this exception does not waive any other S2-10 requirement or change the auditor. |

## Local evidence

`OPENBLAS_NUM_THREADS=1 uv run --frozen python -m unittest discover -s tests -p test_phase2_independent_rf.py -v`: 6 tests pass, including the existing 420-sample parity test. In this environment its largest IL difference was 4.476419235288631e-13 dB (EXP-058, RF-T008, setting 4, segment 23, 2442 MHz); maximum absolute power residual 5.833007687972014e-17 W (EXP-043 zero_gjm_double, RF-T005, setting 0, segment 1, 652 MHz). These are limited numerical evidence, not independent review or RF certification.

Six further existing modules (public API, branch MNA, connection roles, S2P cache, T005/T007 and T008 policy circuits): 40 tests passed locally at the earlier draft. Full CI and complete historical audits remain outstanding. No EXP, source data, policy, checkpoint or RF limits were modified; no optimization, production dense run or Phase 3 transition was performed.

## Incremental review response

`scan_independent_rf` reports UL/DL nominal and H2/H3 mandatory and nominal comparisons from the resolved full-LPF policy. Equality meets the specified limits; a successful comparison is only `sampled_numeric_observation`, never certification. The report records canonical versus cross coverage and finite-grid versus locally refined scope. This is not a matching-only assessment and does not establish continuous-band compliance. The gate recomputes these observations on the same canonical grid as forward/MNA and power, using only 2 or 3 points per interval. An untrusted prior record is accepted only if the entire record matches a fresh recomputation; mismatches fail closed. It records definition/vector fingerprints, the current `src/lpf/**/*.py` source tree hash, git HEAD and dirty state, band/S2P hashes, environment, every sample's setting/segment/frequency, and tolerances. This source hash does not include historical EXP checkpoint/source files, attest loaded in-memory code, or establish a vector's historical origin; those remain `not_checked` in the limited report. It checks the approved effective policy, S2P hashes, finite values, losses, residuals and forward parity; solver SPD/S2P passivity checks remain in the existing implementations. The recorded HEAD alone does not identify a dirty worktree, and the source hash is not independent attestation. A persisted record alone is never authenticated or sufficient.

At HEAD `5f20e899a8871c2419d8b33992c928644bdc8d0a`, [Actions #40662780520](https://github.com/miyabimm/reconfigurable-rf-lpf-research/actions/runs/40662780520) verified 11 independent RF tests. Earlier working-tree local regression before this commit on Python 3.12.15 with `OPENBLAS_NUM_THREADS=1 uv run --frozen`: 17 Stage 1/2, constraint, provenance and storage modules passed 122 tests, including 11 independent RF tests. The other 22 modules in the existing smoke workflow passed 122 tests; `verify_phase2_cleanup_w1_links.py --active-only` also passed. `audit_provenance()` passed; `audit_new_experiment_storage.py audit` passed, with EXP-058 running and its committed readback false. `audit_experiment_inventory.py` and its 2-test module failed: inventory count/missing experiments. See the corrected scope analysis below. No history was edited to make the audit pass.

Earlier working-tree review-response regression (before the latest blocker-consistency correction): public circuit API 6, connection roles 5, branch MNA 6 and independent RF 11 tests passed (28 total). `test_phase2_public_circuit_api.py` covers rejected RF-F003/T006; `test_phase2_connection_roles.py` covers unproved series role. `test_prior_evidence_requires_recomputation_and_exact_match` rejects a changed source/worktree indicator; the SHA is not a digital signature. The subsequently pushed threshold/provenance revision passed [exact-head Actions 40665848367](https://github.com/miyabimm/reconfigurable-rf-lpf-research/actions/runs/40665848367), 11 independent RF tests. The latest blocker-consistency correction and its regression test require fresh exact-head CI.

## Inventory scope and discrepancy (read-only)

At HEAD `5f20e899a8871c2419d8b33992c928644bdc8d0a`, `git ls-tree`, `git ls-files` and the auditor's immediate `runs/EXP-*/manifest.json` glob each yield the **same 66** manifest paths; `git status --short --untracked-files=all` was clean. The inventory has **45** records. The exact missing ID set is EXP-048 through EXP-068 inclusive (21 IDs); there are no glob/tree or index/tree differences. The earlier 70 figure was wrong: the broad `git ls-files 'experiments/chatgpt_topology_search/runs/EXP-*/manifest.json'` pathspec also matched four nested archived source copies under `EXP-020/source_pr38/EXP-016` through `EXP-019`, which the auditor's immediate glob does not count. They are not four extra active manifests or untracked files.

`docs/result_record_corrections_20261014.md` describes a 39-experiment projection at that historical date; the present `check_inventory` contract explicitly requires all current manifests. This does not establish that a historical-only scope is currently authorized. The mismatch predates this PR, and the smoke workflow does not run this inventory audit. **Ownership/scope decision:** The owner has transferred the pre-existing 45/66 inventory discrepancy and its remediation to [Issue #170](https://github.com/miyabimm/reconfigurable-rf-lpf-research/issues/170), not as a PR-B3 merge prerequisite. The inventory audit **still FAILS**; no code/test/data have been weakened or backfilled to hide it. S2-10 for PR-B3 must still demonstrate all other required regressions, provenance/storage checks, source/EXP immutability, current exact-head CI, and independent review. Important inventory data or audit-contract changes require separate owner approval.

## Latest focused correction and acceptance boundary

The top-level `promotion_blockers` previously retained `forward_sampled_not_checked` and `independent_mna_not_checked` even when the recomputation returned `passed_limited`. This PR removes **only those two stale aggregate blockers after a successful limited recomputation**. The underlying Stage-1 component audit remains unchanged and is preserved in `component_policy`; dense RF, local extrema, optimization convergence, physical evidence and owner approval remain blocked. A focused regression asserts both the absence of contradictory aggregate reasons and the continued absence of certification or promotion. This is a reporting-consistency correction, not a gate relaxation.

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

- Verify the new aggregate blocker-consistency regression on the final exact HEAD; the original Stage-1 `component_policy` subreport remains unchanged, while the top-level report no longer says forward/MNA are `not_checked` after successful **limited** recomputation. All dense/physical/owner gates remain blocked.
- Independently verify frozen-input SHA/source provenance and the S2-01–10 evidence table against the final diff and required regression suite. Report the existing inventory audit FAIL as an explicit #170 exception, not a PASS.
- Complete final exact-head Actions and independent PR review before merge. Do not equate cross/reduced grids to dense evidence or automatically certify/promote any candidate.

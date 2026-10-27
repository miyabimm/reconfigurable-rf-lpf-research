# Issue 174: CI 検出能力の棚卸し（暫定）

この表はモジュール単位の初期棚卸しであり、削除の承認ではない。特に保存値パリティの類似テストは、入口 API、寄生、回路構造、参照実装が異なるため、重複と決めつけない。今回テストメソッドは削除・統合していない。

| ID | 主な検査と現状の扱い |
| --- | --- |
| T01 | 通常: `test_rf_f003_t005`, `test_phase2_candidate_catalog`; 追加通常: `test_experiment_provenance`（正式指紋、試験分離、不正拒否） |
| T02 | 通常: `test_evaluate`, `test_phase2_s2p_grid_cache`（6設定、28区間、欠落拒否） |
| T03 | 通常: `test_rf_f003_t005`, `test_phase2_s2p_grid_cache`, `test_phase2_independent_rf`（固定S2P、SHA、カスケード、独立電力検査） |
| T04 | 通常: `test_circuit`, `test_phase2_circuit_layout`, `test_phase2_branch_mna`, `test_phase2_generic_coupled_lc`（向き、符号、SPD） |
| T05 | 通常: `test_phase2_rft008_layout`, `test_phase2_rft008_policy_circuit`, `test_phase2_rft005_t007_policy_circuit`（Q・枝・寄生・政策境界） |
| T06 | 通常: `test_phase2_generic_coupled_lc`, `test_phase2_rft008_policy_circuit`, `test_phase2_public_circuit_api`（固定状態と可変C） |
| T07 | 通常: `test_phase2_shared_exp_evaluators`（凍結実装対照）、`test_phase2_generic_coupled_lc`, `test_phase2_generic_exp043`, `test_phase2_rft005_t007_policy_circuit`, `test_phase2_rft008_policy_circuit`, `test_phase2_public_circuit_api`（それぞれ別の評価入口・モデル境界）。統合候補の精査は未完了 |
| T08 | 通常: `test_phase2_branch_mna`, `test_phase2_independent_rf`、各回路ポリシーの独立MNAケース。T07とは統合しない |
| T09 | 通常: `test_phase2_numeric_diagnostics`, `test_phase2_generic_coupled_lc`, `test_phase2_s2p_grid_cache`, `test_phase2_zero_branch_projection`（特異・非有限・不正入力等） |
| T10 | 通常: `test_phase2_candidate_catalog`, `test_exp047_legacy_manifest_adapter`, `test_phase2_connection_roles`; 追加通常: `test_experiment_provenance`（出典、未収束・未実行） |
| T11 | 追加通常: `test_slsqp_budget`（v2停止・回復・未収束、v1互換も含む）。依存を漏らさないため当面常時実行 |
| T12 | 追加通常: `test_experiment_number_reservation`（重複・再利用・push競合）、`test_new_experiment_storage.test_main_reservation_is_authoritative_and_matches_manifest`（一時Git履歴でmain台帳との照合）。当面常時実行 |
| T13 | 追加通常: `test_new_experiment_storage`, `test_experiment_provenance`（manifest、SHA、選別、未追跡成果等）。既存の狭いパス条件を撤廃し当面常時実行 |

その他通常実行の `test_github_actions_yaml_keys` はCI構文、`test_phase2_current_status_review` とリンク検査は文書・証拠への入口を守る。共有探索13モジュールは変更時経路を維持する。push全体（before〜head）を比較し、未知の履歴・手動実行では実行する。依存を見落とさないよう対象パスは広めに取り、`test_shared_search_ci_trigger` が一時Git履歴で複数コミットpushとPRを検証する。その他の `tests/` は履歴・専門検証として現行CIの対象外であり、削除しない。全テストのメソッド単位の完全な棚卸しは未完了。

## T07/T08 メソッド単位の棚卸し（保持、統合候補未確定）

下記の各行は名前の `test_` 接頭辞を省略。値の似た比較でも参照と入口が違う。削除候補・代替先は現時点で確定していない。特に凍結実装との一致を省けば共通側同士が同じ誤りを共有するリスクがあり、独立MNAを省けばforward同士の一致だけでは物理・電力を検出できない。

| モジュール | メソッドと固有の検査 |
| --- | --- |
| `phase2_shared_exp_evaluators` | `exp042_rf_t005_full_s2p`: 凍結EXP-042対共通、28区間IL・ラベル・S2P・summary。`exp055_rf_t007_shunt_parasitic`: 凍結055対共通、有無2構成とMNA。`exp058_3l_rft008_composite`: 3L GJM有無・凍結対照・MNA。`exp058_4l_zero_gjm`: 4LゼロGJM・凍結対照・MNA。`exp058_4l_mixed_gjm_pcb`: 4L混合・凍結対照・MNA。`shared_library_import_boundary_and_new_exp_guard`: 実験ソースへの依存境界 |
| `phase2_generic_coupled_lc` | `exp042_t005_4l_three_variable_c`, `exp055_t007_4l_ground_parasitic_or_absent`, `exp058_t008_3l_with_ic_fixed_q60`, `exp058_t008_4l_no_gjm`, `exp058_t008_4l_mixed_gjm`: 汎用schemaのencode/decode・typed/vector・共通EXP評価器とのIL・ラベル・最悪/H2。`exp055_alternative_tree_does_not_mutate_other_instances`: 別トポロジーとインスタンス隔離。`typed_forward_rejects_setting_dependent_fixed_or_ic_values`: 固定C/IC/寄生の設定間不変。`schema_finite_shape_fixed_state_and_spd_guards`: 非有限・形状・非SPD・重複結合等 |
| `phase2_public_circuit_api` | `one_entry_t005_exp042`, `one_entry_t007_exp055_and_fixed_parasitic`, `one_entry_t008_exp058_composite`: 公開入口で各trialの保存ベクトル・ポリシー指紋・IL・未認証表示、T007寄生/T008 Q。`immutable_definition_and_defensive_metadata`: 定義/メタデータ不変。`policy_bound_five_l_graph_without_exp_specific_class`: 5L公開入口と昇格阻止。`fail_closed_for_unreviewed_policy_and_wrong_model`: 未対応条件・モデル拒否 |
| `phase2_rft005_t007_policy_circuit` | `t005_exp042_four_l_saved_vector_matches_without_parasite`: T005ポリシーと寄生なし。`t007_exp055_four_l_saved_vector_and_independent_mna`: T007固定寄生/Q・保存値・独立MNA・未検証表示。`t007_zero_variable_only_fixed_parasitic_remains`: OFFで寄生残存。`t007_zero_to_three_shunts_and_no_hot_hot_parasites`: 枝数と接続別寄生。`t007_two_dtc_placeholder_legacy_vector_mapping`: 旧ベクトルの枝対応。`t005_zero_gjm_exp043_3l_and_two_gjm_case`: 凍結043対照とGJM数。`reject_wrong_trial_and_unauthorized_legacy_composite_c`: 偽造条件・役割拒否。`reject_out_of_range_caps_q_spd_and_nonadjacent_k`: 値範囲・非隣接結合・固定値変更拒否 |
| `phase2_rft008_policy_circuit` | `saved_4l_candidate_component_gate_and_forward_parity`: 保存4L・指紋・6設定・SPD・未検証。`saved_3l_zero_and_one_gjm_parameter_policy`: 保存3LのGJM数別。`formal_gjm_values_below_exp058_study_floor_are_not_rejected`: 正式下限と探索下限の分離。`zero_one_two_dtc_branches_policy_not_exactly_two`: 可変枝数とOFF時固定C。`wrong_policy_missing_roles_and_types_fail_closed`: 条件・部品・接続拒否。`l_limits_adjacency_and_explicit_series_q`: L範囲・隣接・Q。`pcb_l_cap_limits_and_six_setting_invariance`: PCB L/C境界・設定不変。`forged_resolved_policy_is_rejected_against_registry`: 偽造条件拒否。`retains_protected_resolved_policy_snapshot`: 条件スナップショット保護 |
| `phase2_independent_rf` / `phase2_branch_mna` | `frozen_external_parity_and_power`: 独立branch-current MNA・S2P・電力、T07と別目的。branch MNAの `references`, `branched_tree_hot_hot_and_signed_couplings`, `nonfinite_mutual_classification`, `orientation_and_signed_coupling`, `off`, `invalid`: 参照回路・分岐・符号・OFF・不正入力 |

**契約外・退役:** 確定した候補はまだない。T07のこれらは保存値・公開API・trial境界・独立計算の契約に関わるため、類似のみを根拠に退役しない。残りのモジュールは実際の入力・実行契約を確認して分類する。契約外の専用ケースを特定できた場合は根拠を記載し代替テストを作らない。

## 科学的評価ゲート

軽量CIの成功は候補昇格ではない。新規候補には別途、承認済み制約と `data/bands.csv` による全帯域の有限格子、独立MNA、SPD、受動性・電力保存、収束/未実行の区別、制約・ソース指紋と完全ベクトルの保全を確認する。高密度評価や新規EXPはこの変更で開始しない。

## ローカル実測

`OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1`、`.venv/bin/python -m unittest discover -s tests -p <module> -q` で実行。元の通常21モジュールは114件・14.52秒でPASS。追加4モジュールは50件・合計3.37秒でPASS（SLSQP 14件、予約8件、出典14件、保存14件のうち保存14件は従来も条件付き）。時間はプロセス起動を含むローカル実測で、CIの計測値ではない。共有探索の条件付き13モジュール、ストレージ監査コマンド、リンク検査と高密度評価はこの計測に含まない。この時点で通常実行は164件。今回は削減ではなく検査経路の欠落防止を優先した。

レビュー対応後、通常167件（既存164件＋トリガー2件＋予約照合1件）、条件付き共有探索69件の合計236件と、リンク検査・ストレージ監査がPASS、合計18.28秒（高密度評価は除外）。既存の通常契約内の失敗検出11メソッドを個別に実行しPASS: `test_formal_registry_and_compat`, `test_formal_pending_or_modified_snapshot_is_rejected`, `test_sha_and_network_identity_fail_closed`, `test_band_coverage_rejects_missing_or_duplicated_regions_subbands`, `test_schema_finite_shape_fixed_state_and_spd_guards`, `test_typed_forward_rejects_setting_dependent_fixed_or_ic_values`, `test_reject_out_of_range_caps_q_spd_and_nonadjacent_k`, `test_forged_resolved_policy_is_rejected_against_registry`, `test_source_blob_mismatch_fails_closed`, `test_formal_trial_swap_is_rejected`, `test_policy_bound_five_l_graph_without_exp_specific_class`。これらは元々の異常入力/昇格阻止検査であり、契約外の架空故障を追加していない。

## 未完了

- T07の比較を含む全モジュールの各assertionを照合し、統合・契約外退役の可否を実証する。削除はまだ行っていない。
- 広い共有探索の変更条件は、実依存との対応を引き続き精査する。
- T01–T10の境界ごとの完全な検出能力の監査と、統合を行った場合の同一HEAD比較は未完了。通常契約内の代表的異常は上記の既存検査を実行。
- PR上のCIとトリガーの実証、独立レビュー、承認・main上のCI確認は別途必要。

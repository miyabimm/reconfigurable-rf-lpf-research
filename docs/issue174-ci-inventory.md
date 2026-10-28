# Issue 174: CI 検出能力の棚卸し（暫定）

この表はモジュール単位の初期棚卸しであり、未分類ケースの削除の承認ではない。保存値パリティの類似テストは入口 API、寄生、回路構造、参照実装が異なるため、重複と決めつけない。退役した契約外のケースは下表に記録する。

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

その他通常実行の `test_github_actions_yaml_keys` はCI構文、`test_phase2_current_status_review` とリンク検査は文書・証拠への入口を守る。共有探索13モジュールも通常CIで常時実行する。以前の変更検知はworkflowの起動条件とほぼ同じで実質的にskipしないため、helperとそのテストを廃止した。その他の `tests/` は履歴・専門検証として現行CIの対象外であり、削除しない。全テストのメソッド単位の完全な棚卸しは未完了。

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

## 契約外・退役

| テスト・アサーション | 根拠 |
| --- | --- |
| `test_phase2_numeric_diagnostics.test_coupled_inductor_solve_failure_is_not_rf_failure` | 正のL/Q、SPDの有効な行列に対し `np.linalg.solve` 自体を強制失敗させるライブラリ故障模擬。通常の数値入力で生じた特異行列の検査ではない。SPDは `test_mutual_spd_failure_has_stable_error_code` 等で保持。 |
| `test_phase2_numeric_diagnostics.test_nonfinite_cascade_reports_stage` | 固定S2Pから構築した内部 `ev.pre` を直接NaNに書き換える。入力経路からS2Pを改竄した場合のSHA拒否は `test_phase2_s2p_grid_cache.test_sha_and_network_identity_fail_closed` で保持。 |
| `test_phase2_branch_mna.test_nonfinite_mutual_classification` 内の `eigvalsh` NaN返却patch | 有限SPD行列の固有値計算を強制的にNaN化するライブラリ故障模擬。非SPD拒否の同一メソッド内アサーションと `test_invalid` は保持。 |
| `test_shared_search_ci_trigger` の2メソッドとhelper | workflowのパス条件と同じ対象を再判定する不要な分岐と、その一時Gitテスト。共有探索を常時実行するので比較範囲・未知履歴の処理自体が不要。 |

### 保持・調査結果

- `test_nonfinite_mutual_classification` の `1e308` 入力: `solve_branch_mna` は部品ポリシーを別途検証する裸のソルバーと明記され、`evaluate_independent_sample` もポリシー範囲を先に検証しない。正の有限入力によるオーバーフローを契約外と断定できない。
- `test_batched_schur_singular_has_diagnostic`: mockの全ゼロ節点Yは実回路そのものではない。`InductorTree` は全hotノードの連結木を強制し、正のL/Q・SPDと非負Cの理想算術では内部Schurブロックは非特異（接地ポートを基準に木の損失の実部が正）。ただし数値悪条件や有限精度での解法失敗は別で、公開schemaはRF部品範囲に制限されず、S1-09の失敗分類も要求するため、実装の特異診断を保持する。このfixtureが物理的浮遊ノードや具体的な悪条件回路の再現であるとは主張しない。独立MNAの実際の浮遊境界の拒否は `test_phase2_branch_mna.test_invalid` に残る。
- `test_transfer_zero_has_indexed_diagnostic`: 単位行列は人工fixtureであり、実回路の零点を再現した証拠ではない。一方、阻止帯の極深ノッチ・S21ほぼゼロは `docs/rf_f003_phase2_rebaseline_plan_20261016.md` でfail-closedが必要な実RF上の境界として明記されている。伝達特異診断とsample indexを保持し、物理的に達成可能な正確な零点がこのfixtureから証明されるとは扱わない。

T07の保存値・公開API・trial境界・独立計算は類似のみを根拠に退役しない。

### T09・入力境界の分類

| 対象 | 判定と理由 |
| --- | --- |
| `test_phase2_numeric_diagnostics` | 保持。非SPD・非有限vector・周波数/設定・ポート・接続の拒否は公開入力境界。残る2つのmockは上記の通り失敗分類の単体検査であり、物理的到達の証拠ではない。 |
| `test_phase2_s2p_grid_cache` | 保持。固定S2PのSHA・範囲・キャッシュ隔離と28区間の欠落・重複は実データ/科学的再現性の境界。 |
| `test_phase2_generic_coupled_lc` | 保持。非有限・形状・設定間固定値・SPD・符号付き結合はschemaと数値評価の契約。 |
| `test_phase2_zero_branch_projection` | 保持。保存済みベクトル移行時のゼロ値、枝・寄生・試験条件の保全は実データ契約。 |
| `test_phase2_branch_mna` | 保持。巨大有限値は裸のソルバー入力、浮遊境界・非SPDは独立MNAの安全な失敗。`test_nonfinite_mutual_classification` 内の非SPD呼出しだけは `test_invalid` と同じ回路・入力・境界・例外のため統合し、`test_invalid` に機械可読 `code` の検査も残す。 |
| `test_phase2_independent_rf` | 保持。forwardの利用を禁止するmockは故障注入ではなく、独立計算法の検証。受動性・損失・電力収支はT07の保存値比較とは別目的。 |

この範囲で他の契約外ケースは確定していない。分類は網羅的な全assertion棚卸しを意味しない。

## 科学的評価ゲート

軽量CIの成功は候補昇格ではない。新規候補には別途、承認済み制約と `data/bands.csv` による全帯域の有限格子、独立MNA、SPD、受動性・電力保存、収束/未実行の区別、制約・ソース指紋と完全ベクトルの保全を確認する。高密度評価や新規EXPはこの変更で開始しない。

## ローカル実測

`OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1`、`.venv/bin/python -m unittest discover -s tests -p <module> -q` で実行。元の通常21モジュールは114件・14.52秒でPASS。追加4モジュールは50件・合計3.37秒でPASS（SLSQP 14件、予約8件、出典14件、保存14件のうち保存14件は従来も条件付き）。時間はプロセス起動を含むローカル実測で、CIの計測値ではない。共有探索の条件付き13モジュール、ストレージ監査コマンド、リンク検査と高密度評価はこの計測に含まない。この時点で通常実行は164件。今回は削減ではなく検査経路の欠落防止を優先した。

HEAD `3c1303a` では通常167件（既存164件＋トリガー2件＋予約照合1件）、条件付き共有探索69件の合計236件と、リンク検査・ストレージ監査がPASS、合計18.28秒（高密度評価は除外）。既存の通常契約内の失敗検出11メソッドを個別に実行しPASS: `test_formal_registry_and_compat`, `test_formal_pending_or_modified_snapshot_is_rejected`, `test_sha_and_network_identity_fail_closed`, `test_band_coverage_rejects_missing_or_duplicated_regions_subbands`, `test_schema_finite_shape_fixed_state_and_spd_guards`, `test_typed_forward_rejects_setting_dependent_fixed_or_ic_values`, `test_reject_out_of_range_caps_q_spd_and_nonadjacent_k`, `test_forged_resolved_policy_is_rejected_against_registry`, `test_source_blob_mismatch_fails_closed`, `test_formal_trial_swap_is_rejected`, `test_policy_bound_five_l_graph_without_exp_specific_class`。これらは元々の異常入力/昇格阻止検査であり、契約外の架空故障を追加していない。

次のレビュー対応後は、PR単独HEAD `398acdc` のローカルで通常163件＋共有探索69件＝常時232件とリンク検査・ストレージ監査がPASS、合計17.59秒。同じローカル環境・コマンドで、変更前は236件・18.28秒。差分は不要な変更検知2件と契約外数値診断2件の退役で、MNA内のpatch 1アサーションも削除。変更前の診断9件・MNA6件は別途PASSし、変更後は診断7件・MNA6件を含む。

追加整理では `2712241` と同じ作業HEAD・固定入力で、上記6モジュールを各 `python -m unittest discover -s tests -p <module>.py -q` で実行し、非SPDアサーションの統合前後とも33件PASS（それぞれ5.13秒・4.33秒、プロセス起動込み）。メソッドは削除していない。`test_invalid` は `mutual_not_spd` の例外型・文字列・機械可読codeを維持する。

同HEADのGitHub ActionsはPR merge評価で当時のmain `e7226e6` の `test_retired_docs_remain_git_recoverable` が加わり233件PASS（smoke 21秒）。ローカル232件はmain統合前のPR単独HEADの結果で、環境・比較対象が異なる。main `e7226e6` をPRへ統合した後のローカルは233件・19.77秒、リンク検査・ストレージ監査もPASS。初回は履歴回復テストの固定コミット `26a5d4aff7d197754f17991123acc44e8b356b83` がローカルに存在せず失敗したため、`git fetch origin 26a5d4aff7d197754f17991123acc44e8b356b83` の後に再実行した。この固定コミットはmainから到達できず、新規checkoutでの取得可能性はCI結果を確認する必要がある。高密度RFや科学的候補評価は実施していない。

## #174 最終判定と残るゲート

**実装・テスト整理は完了可能。** 網羅的な全アサーション列挙を目的化せず、正式制約・6設定/28区間・外部S2P SHA/カスケード・SPD/受動性/電力保存・独立MNA・凍結EXPパリティ・出典/EXP予約/保存整合性という科学的に必要な検出能力を保持した。T01–T13の対応と、保持／統合／契約外退役の根拠は上記を正本とする。契約外と判断できないケースは推測で削除せず保持した。

- 通常CIは共有探索13モジュールを含めて常時実行。重複したpaths変更判定helperを廃止。T11–T13も通常CIで実行し、依存漏れを回避する。
- 契約外の故障注入テスト2メソッド、固有値計算の強制NaNアサーション、変更判定専用2メソッドを退役。同一MNA入力の非SPD重複アサーションは統合し、`check_invalid()`に例外型・メッセージ・機械可読`code`の検査を残した。`code`の検査にはPython最適化モードでも無効化されない`unittest.TestCase().assertEqual`を使用。
- ローカル比較：main同期後の関連6モジュール33件が非SPDアサーション統合前後ともPASS（5.13秒→4.33秒）。同じ契約内の重要な検出機能を維持。前後の全CI件数・実行時間の推移は上記の実測欄を参照。
- GitHub Actions [#40616391444](https://github.com/miyabimm/reconfigurable-rf-lpf-research/actions/runs/40616391444) はMNA `assertEqual`修正を含むPR HEAD `bc8d870` の評価でSUCCESS、**236件PASS**。直前の233件との差3件は、その間にmainへ追加された独立RFスキャン系テスト。リンク検査はローカルリンク欠損0、ストレージ監査もPASS。
- 本Issueの完了判断は**コード／CIの整理について**であり、新規候補の科学的RF適合、dense RF全帯域検証、研究実験実施を意味しない。外部リンク到達性など軽量CIが対象外とする検証も引き続き対象外。

**残る工程はPRの最終レビュー・承認範囲でのマージと、main上のCI成功確認だけ。** Issue #174をclosedにするのはmain検証後とする。未知の契約外ケースを探すための無期限の棚卸しは行わない。

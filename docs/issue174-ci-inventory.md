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
| T12 | 追加通常: `test_experiment_number_reservation`（重複・再利用・push競合）。main予約照合の実装はストレージ監査にあるが、その独立した回帰テストの追加は未完了。当面常時実行 |
| T13 | 追加通常: `test_new_experiment_storage`, `test_experiment_provenance`（manifest、SHA、選別、未追跡成果等）。既存の狭いパス条件を撤廃し当面常時実行 |

その他通常実行の `test_github_actions_yaml_keys` はCI構文、`test_phase2_current_status_review` とリンク検査は文書・証拠への入口を守る。共有探索13モジュールは既存の変更時経路を維持する。その他の `tests/` は履歴・専門検証として現行CIの対象外であり、削除しない。全テストのメソッド単位の完全な棚卸しは未完了。

## 科学的評価ゲート

軽量CIの成功は候補昇格ではない。新規候補には別途、承認済み制約と `data/bands.csv` による全帯域の有限格子、独立MNA、SPD、受動性・電力保存、収束/未実行の区別、制約・ソース指紋と完全ベクトルの保全を確認する。高密度評価や新規EXPはこの変更で開始しない。

## ローカル実測

`OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1`、`.venv/bin/python -m unittest discover -s tests -p <module> -q` で実行。元の通常21モジュールは114件・14.52秒でPASS。追加4モジュールは50件・合計3.37秒でPASS（SLSQP 14件、予約8件、出典14件、保存14件のうち保存14件は従来も条件付き）。時間はプロセス起動を含むローカル実測で、CIの計測値ではない。共有探索の条件付き13モジュール、ストレージ監査コマンド、リンク検査と高密度評価はこの計測に含まない。通常実行は計164件となる。今回は削減ではなく検査経路の欠落防止を優先した。

## 未完了

- T07等の各メソッド固有のassertionを照合し、統合可能性を実証する。削除はまだ行っていない。
- 共有探索の条件は依存漏れや複数コミットpushの比較範囲を精査する必要がある。今回変更していない。
- T01–T10の境界ごとの完全な検出能力の監査、整理後スイートとの同一HEADでの比較と異常入力の追加実証は未実施。
- PR上のCIとトリガーの実証、独立レビュー、承認・main上のCI確認は別途必要。

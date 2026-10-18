# W5：Phase 2リポジトリ整理の読み取り専用総合監査（2026-10-18）

> **位置づけ：W5の出典・保全・未完了ゲート審査。** この監査がSUCCESSでもW4の研究原本・旧workflowの削除完了を意味しない。研究は**Phase 2継続**。Phase 3は所有者の明示承認まで着手禁止。

## 正本・基準と検証方法

- **基準main：** `bda522d6e8dc3f5d4667c46507b7d1005c93b20e`（[PR #87](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/pull/87)でEXP-046/047 131原本を保全監査後）。
- **運用正本：** [プロジェクト指示](chatgpt_project_instructions.md)、[正式RF-F003・試験RF-T005](../data/constraints/registry.json)、[6設定・28区間](../data/bands.csv)。
- **実行コード：** [非破壊検証器](../scripts/verify_phase2_w5_closure.py)。現行Git原本SHA/サイズ、承認台帳、固定ZIPのSHA-256・CRC、候補台帳の条件別件数を照合する。元研究コード・RFモデルを実行しない。GitHub Actionsで[W5専用CI](../.github/workflows/phase2_w5_readonly_closure.yml)を実行し、ゲートごとの判定CSVを固定する。
- **固定結果の保存先：** [機械可読W5総合監査](../data/repository_reviews/w5_phase2_readonly_closure_20261018.json)と[14ゲートの対応表](../data/repository_reviews/w5_phase2_gate_matrix_20261018.csv)。最初のCIで実数値が確定するまで、監査結果を成功と断定しない。

## W0～W5の作業と削除権限の区別

| 工程 | 根拠・監査対象 | 現行判定の意味 |
|---|---|---|
| W0 | [整理候補23行](../data/repository_reviews/phase2_cleanup_deletion_candidates_20261017.csv) | 歴史的なT-001～T-010は台帳上`not_started_unapproved`。**現在も本文が未修正という証明ではなく、T区分の現時点照合は別課題** |
| W1 | [文書・リンク整合CI](../scripts/verify_phase2_cleanup_w1_links.py) | 相対リンク等の検証。古い日付の記述を削除・意味修正できる自動判定ではない |
| W2 | [24候補台帳](../data/catalog/phase2_candidate_catalog_20261017.csv)・[条件別パレート](../data/pareto_snapshots/rf_t005_rf_f003_20261017.json) | 現在の保存済み代表としてRF-T005試験6点、RF-F003正式4点。歴史的14候補の未抽出構造は推測しない |
| W3 | [D-001～007承認・出典台帳](../data/repository_reviews/w3_document_disposition_20261017.csv)／[歴史統合文書](archive/w3_consolidated_documents_20261017.md) | 所有者承認の**D-001～004のみ現行treeから削除**済み。原blobを固定コミットから復元可能。**D-005～007は保全** |
| W4 — 元46／225件 | [Step4旧46件](../data/repository_reviews/step4_retention_46_20261017.csv)、[W4元225件](../data/repository_reviews/w4_unindexed_225_review_20261017.csv)、[225件再実行依存](../data/repository_reviews/w4_replay_dependency_225_20261018.csv) | 静的参照、元blob・構文の監査は実行済み。元実験再計算や削除可能性の証明ではない |
| W4 — EXP-042 | [10個の元Actions ZIP](../data/repository_reviews/w4_exp042_actions_original_zip_b64_20261018.json)、[19ファイルのZIP↔Git照合](../data/repository_reviews/w4_exp042_member_crosswalk_20261018.csv)、[6元JSON復元](../data/repository_reviews/w4_exp042_missing_variant_source_review_20261018.json) | 元ZIPバイト・CRC・SHAを保存。数値候補の同定、別run段階と未選別の歴史証拠を保持。独立MNAの新規再実行は**未実施** |
| W4 — EXP-046/047 | [131元ファイル個別台帳](../data/repository_reviews/w4_exp046_exp047_131_20261018.csv)・[出典監査報告](phase2_w4_exp046_exp047_source_review_20261018.md) | RF-T005探索35原本、正式RF-F003探索96原本の出典と訂正を分類。原実行seed・environment・Code Mode環境の欠損は未復元 |
| W4 — workflow | [歴史39workflow実行履歴](../data/repository_reviews/w4_workflow_runs_20261017.csv)・[W4削除判断](../data/repository_reviews/w4_cleanup_decision_gates_20261017.csv) | 過去時点でのAPI可視履歴であり、現在の全workflowの実行履歴ではない。E-001/E-002/W-001/W-OTHERに削除承認なし |
| **W5** | 本監査のGitHub Actionsと14ゲート判定 | **読み取り専用の総合監査を実施すること自体は可能**。W4の実際の削除・旧workflow停止・Phase 3承認とは完全に分離する |

## 現時点で解消していない重要項目

1. **削除承認と保全：** W3の旧二次文書4件の承認は、実験の生出力やworkflowには及ばない。旧46件・D-005～007・W4元225件・131件、EXP-042元ZIPは保持する。W4は実験・workflow退役判定を未完了とする。
2. **再現性：** EXP-046にはdirty作業ツリー、seed・環境未記録、EXP-047には元実行commit・seed・環境・strict manifest欠損が残る。元JSONに28×1001／84点独立MNAの記録があっても、今回の監査で再計算したものではない。
3. **数値条件の峻別：** 正式RF-F003は最大2可変C、試験RF-T005は最大3可変C。両条件のbest-found有限格子記録を同条件の大域最適解や物理的成立とみなさない。30dBは必須、35dB公称、最悪IL≤0.30dBは未達。
4. **研究継続ゲート：** RF-F003共通探索runnerによる同条件の再検証、連続帯域最悪点、Q(f)/SRF、EM、実部品同時磁気結合・公差・温度・量産・実測は未完了。
5. **削除に先立つ手順：** 個別run、元Git revision／SHA、動的参照・中断再開・workflow dispatch、代替原本の同一性、独立RF再検証の要否を確認し、対象別に所有者承認が必要。旧workflowの0履歴は「使われない」の証明ではない。

## 状態

- **このPRは既存RF制約、原実験run、checkpoint、Git履歴、旧39 workflow、候補パレートを変更しない。**
- **W5成果物は追加の監査・索引であり、原本置換でも削除実施でもない。**
- **W5を閉じてもW4の削除工程は未完了**。次の工程は必要に応じて個別削除承認の審査、または独立したPhase 2研究・再現性検証。Phase 3への移行は禁止。

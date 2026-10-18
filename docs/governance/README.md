# Phase 2：研究運用・保存ルールの案内（2026-10-17）

**本ページはナビゲーション用の分類。** 以下の原文は作成時点の提案・方針・監査記録を含み、すべてが現行実装済みとは限らない。数値制約の正本は[制約レジストリ](../../data/constraints/registry.json)が選ぶRF-F003、運用指示の正本は[プロジェクト指示](../chatgpt_project_instructions.md)。

## 現行運用での優先参照

| 内容 | 参照 |
|---|---|
| ChatGPTプロジェクトの研究・承認・実験運用 | [運用指示の正本](../chatgpt_project_instructions.md) |
| RF数値・正式／試験条件 | [RF制約レジストリ](../../data/constraints/registry.json) |
| EXP番号のmain事前予約 | [実験番号予約方針](../experiment_number_reservation_policy_20261015.md)、[台帳](../../data/experiment_number_registry.csv) |
| 実行状態と独立検証の分離 | [実験マニフェストの説明](../experiment_manifests.md)、[実験索引](../../data/experiment_index.csv) |
| GitHub-only研究証拠・研究結果の昇格 | [保存方針提案（部分導入）](../experiment_result_storage_policy_proposal_20261015.md) |
| 旧保全判断と未リンク証拠 | [46件の旧レビュー](../phase2_evidence_triage_20261015.md)、[Step 4新分類](../phase2_repository_step4_review_20261017.md) |

## 過去の監査・訂正・ブランチ経緯

W3でD-001～D-004を[歴史統合資料](../archive/w3_consolidated_documents_20261017.md)に保存した。下記の旧題名のリンクは該当章と元の固定コミット出典へ導く。D-005～D-007は保持。

- [研究結果管理の初版（2026-10-14）](../archive/w3_consolidated_documents_20261017.md#d-002)：RF-F002や当時の候補数など**旧時点の記述**がある。現在のRF-F003や24候補のビューと混同しない。
- [記録の訂正経緯](../result_record_corrections_20261014.md)。
- [古いリポジトリ容量監査](../archive/w3_consolidated_documents_20261017.md#d-004)と[2026-10-15 GitHub-only保全レビュー](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/blob/12b1dfd7a91ab466a6cfbbb8b4db968715e91d5f/docs/phase2_repository_optimization_review_20261015.md)。
- [2026-10-15証拠トリアージ](../phase2_evidence_triage_20261015.md)。
- [当時のリポジトリ引継ぎ計画](../archive/w3_consolidated_documents_20261017.md#d-001)。
- [2026-10-14ブランチ削除の実行記録](../maintenance/branch_cleanup_20261014.md)：**過去の実行済み事項**。2026-10-17に新たに削除した意味ではない。
- [2026-10-17 Actions修復記録](../archive/w3_consolidated_documents_20261017.md#d-003)。現在のEXP-047 manifestに関するCI問題とは区別する。
- [条件別旧候補の保全・Pareto](../phase2_storage_pareto_review_20261015.md)。旧RF-F002/RF-T004条件の保存資料。

## 物理移動・削除の承認ゲート

1. 元研究結果、manifest、ログ・task、source_pr、固定S2PとRF正式制約の変更・移動・削除を本整理では行わない。
2. 同一Git blobでも、元PR provenance、再開試験の出典、元実験の復元性が異なれば**同一内容＝不要**とはみなさない。
3. 個別のソース役割レビュー・参照更新・CI・保存先の検証が終わるまで、元pathは維持する。
4. ブランチ削除・Git履歴変更は別途所有者承認。Phase 3移行も所有者の明示承認が必要。

[歴史資料目次](../archive/README.md) ／ [Step 4重複・保全監査](../phase2_repository_step4_review_20261017.md) ／ [現行パレート](../pareto_rf_t005_rf_f003_20261017.md)

# 研究ドキュメント案内 — Phase 2

**更新基準：2026-10-17。** このページは文書の**入口・所在案内**であり、RF条件や候補値の数値正本ではない。最新の公式条件は [RF制約レジストリ](../data/constraints/registry.json) が指定する正式JSON、帯域は [bands.csv](../data/bands.csv) を参照する。研究はPhase 2であり、Phase 3は所有者の明示的承認まで開始しない。

## 最初に読むページ

| 目的 | 参照先 |
|---|---|
| 今日の正式条件、最新の検証成果、制約未達事項 | [Phase 2現行サマリー](current/phase2_status.md) |
| RF-T005 / RF-F003の3L・4Lとパレート解 | [結果の入口](results/README.md) |
| 面積–ILパレートの元レポート | [2026-10-17保存スナップショット説明](pareto_rf_t005_rf_f003_20261017.md) |
| 作業計画・過去の変更履歴 | [ロードマップ](roadmap.md) |
| 日常の軽量CI・必要時の独立数値検証 | [Step Aスモーク／手動検証](phase2_stepA_smoke_and_on_demand_checks_20261018.md) |
| Step Bの旧監査workflow退役案・復元元 | [第1弾17件の対象一覧](phase2_stepB_workflow_retirement_20261018.md) |
| 未解決の研究・実装・再現性ゲート | [未解決課題](current/open_research_questions.md) |
| RF-F003の仕様要約 | [設計仕様](specification.md) |
| 研究運用の指示正本 | [ChatGPTプロジェクト運用指示](chatgpt_project_instructions.md) |

## 数値正本と実験証拠

- **正式RF-F003：** [レジストリ](../data/constraints/registry.json) → [RF-F003 JSON](../data/constraints/formal/RF-F003.json)。互換用 [design_constraints.json](../data/design_constraints.json) はコピー。旧RF-F001/F002を正式現況へ流用しない。
- **試験RF-T005：** [RF-T005 JSON](../data/constraints/trial/RF-T005.json)。正式条件ではなく、IC可変Cの上限を2枝から3枝へ緩和した別条件。
- **帯域と固定S2P：** [bands.csv](../data/bands.csv)、[入力S2P](../data/parasitics/circuit1_ant_coupler_0_6ghz.s2p)、[出力S2P](../data/parasitics/circuit2_poc_through_0_6ghz.s2p)。パス・SHA-256の固定を維持する。
- **保存済み結果の数値原本：** [パレートJSON](../data/pareto_snapshots/rf_t005_rf_f003_20261017.json)、[候補・検証・実験の所在](../data/README.md)、[実験インデックス](../data/experiment_index.csv)、[実験原本フォルダの案内](../experiments/README.md)。
- **コード：** [scripts索引](../scripts/README.md)。スクリプトやCSV上の旧仕様値は必ず条件IDと保存日を見て判断する。

## 文書の世代と使い分け

1. **現行への入口：** `current/` と `results/README.md`。閲覧しやすい説明資料。数値の出典は必ず上記正本へ戻る。
2. **現行の仕様・手順：** [設計仕様](specification.md)、[運用指示](chatgpt_project_instructions.md)、[実験番号予約方針](experiment_number_reservation_policy_20261015.md)、[RF-F003再ベースライン計画](rf_f003_phase2_rebaseline_plan_20261016.md)。作成日の「未実行」は当時の記録であり、最新EXP-047の局所探索成果と区別する。
3. **過去時点の成果と保管判断：** [研究履歴索引](historical_results.md)、[2026-10-15証拠棚卸し・Pareto](phase2_storage_pareto_review_20261015.md)、[保全レビュー](phase2_repository_optimization_review_20261015.md)、[証拠トリアージ](phase2_evidence_triage_20261015.md)。その文書内の「現行RF-F002」などは**作成当時の表現**。
4. **導入未完の提案：** [GitHub-only研究結果保存方針（提案）](experiment_result_storage_policy_proposal_20261015.md)。提案中の事項を実施済みとみなさない。

## ドキュメント移動に関する方針

**W3削除実施追補（2026-10-17）：** 条件付き旧文書D-001～D-004の[固有資料と出典](archive/w3_consolidated_documents_20261017.md)を保存し、元4pathのGit追跡を削除。D-005～D-007と旧46件保全対象、RF制約・実験原本は保持。

**整理Step 1～5は[PR #71でmainに統合済み](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/pull/71)**。追加整理の[#72（計画）](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/pull/72)・[#73（W0監査）](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/pull/73)・[#75（W1）](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/pull/75)・[#78（W2）](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/pull/78)も2026-10-17にmain統合済み。**W3の7旧文書は[個別レビュー](phase2_cleanup_w3_document_review_20261017.md)で引き続き保全**し、所有者によるpath別承認前に削除しない。元実験46件の保全審査とは別管理する。

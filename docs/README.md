# 研究文書の入口

日常的な研究運営には、現役の少数文書だけを用います。日時別の報告は当時のRF条件・実行状態を記す履歴であり、現状を示しません。

| 目的 | 参照先 |
|---|---|
| 運用方針・承認権限 | [chatgpt_project_instructions.md](chatgpt_project_instructions.md) |
| 開発状況と次のゲート | [roadmap.md](roadmap.md)／[Issue #163](https://github.com/miyabimm/reconfigurable-rf-lpf-research/issues/163) |
| RFモデルと評価指標 | [specification.md](specification.md) |
| 結果・検証証拠 | [results/README.md](results/README.md)／[実験索引](../data/experiment_index.csv) |
| 理論・解析方法の所在 | [methods/README.md](methods/README.md) |
| 実験保存ポリシー | [governance/phase2_experiment_storage_policy.md](governance/phase2_experiment_storage_policy.md) |
| 過去の文書整理と分類 | [Issue #170](https://github.com/miyabimm/reconfigurable-rf-lpf-research/issues/170) |

数値正本は[registry.json](../data/constraints/registry.json)が選ぶ正式版、[bands.csv](../data/bands.csv)と固定S2Pです。実験原本は[experiments](../experiments/README.md)です。日付別の作業経緯はIssue・PR・Git履歴に記録し、この入口に追記し続けません。原本の削除・移動は別レビューで判断します。

## 過去の現況文書の出典

次の旧入口は最新の開発状況を示さないため、現役ツリーから整理しました。本文はGit履歴の固定版で閲覧できます。

- [2026-10-18時点の研究ステータス](https://github.com/miyabimm/reconfigurable-rf-lpf-research/blob/0bf0e3a41e2ed2a5ae4e734ccec71bc530c19a53/docs/current/phase2_status.md)：EXP-048/049の当時の実行範囲・試験条件の記録。
- [2026-10-17時点の未解決課題](https://github.com/miyabimm/reconfigurable-rf-lpf-research/blob/0bf0e3a41e2ed2a5ae4e734ccec71bc530c19a53/docs/current/open_research_questions.md)：当時のRG課題・出典欠損の整理。
- [旧governance目次](https://github.com/miyabimm/reconfigurable-rf-lpf-research/blob/0bf0e3a41e2ed2a5ae4e734ccec71bc530c19a53/docs/governance/README.md)：整理当時の運用・監査資料へのリンク。

現在の状況は[ロードマップ](roadmap.md)とGitHub Issues、計算結果は[EXP原本](../experiments/README.md)を参照します。旧文書の内容を現在のRF性能や未解決事項として読み替えません。

旧い管理・CI運用案、廃止時点の対象一覧、元blobの固定参照は[旧管理資料の保存索引](archive/maintenance_notes_20261027.md)へ集約しました。現行の実行ルールではありません。

# data/：RF制約・候補・証拠台帳の案内（2026-10-17）

> **ファイルの所在案内。** このREADMEはRF数値仕様ではない。規約と数値正本は [constraints/registry.json](constraints/registry.json)、[bands.csv](bands.csv)、固定外部S2PとそのSHA-256によって規定される。Phase 2継続。

## 正本と役割

| ファイル／フォルダ | 用途・取扱い |
|---|---|
| [constraints/registry.json](constraints/registry.json) | 有効な**正式RF制約ID**の唯一の選択台帳（2026-10-17時点でRF-F003） |
| [constraints/formal/RF-F003.json](constraints/formal/RF-F003.json) | 現行正式RF設計制約の機械可読正本 |
| [design_constraints.json](design_constraints.json) | 現行正式条件の互換コピー。正式JSONと一致させる。独立の仕様源にしない |
| [constraints/trial/RF-T005.json](constraints/trial/RF-T005.json) | RF-F003を基準に可変Cの上限だけ最大3独立枝とする**試験条件** |
| [bands.csv](bands.csv) | 6設定のUL/DL/H2/H3対象周波数帯の正本 |
| [parasitics/](parasitics/) | RF-F003がSHA-256で固定する入力S2P・出力S2P。実測ではなく回路モデル由来 |
| [pareto_snapshots/rf_t005_rf_f003_20261017.json](pareto_snapshots/rf_t005_rf_f003_20261017.json) | 2026-10-17の**保存済みbest-foundパレート**（RF-T005 6点、RF-F003 4点）。新しい値で上書きしない |
| [experiment_number_registry.csv](experiment_number_registry.csv) | 新規EXP番号のmain事前予約正本。欠番EXP-018/019再利用禁止 |
| [experiment_index.csv](experiment_index.csv) | 実験ID別の制約・実行状態・原manifestの検索入口 |
| [research_candidate_register.csv](research_candidate_register.csv) | 現行の旧仕様中心選別候補台帳。2026-10-17時点の旧14件は[固定CSV](catalog/research_candidate_register_20261017.csv)として別保存 |
| [research_review_issues.csv](research_review_issues.csv) | 歴史的RG課題を含むレビュー問題台帳 |
| [validation/](validation/) | 独立MNA検証、事後再評価、数値・実行の証拠。元ファイルを改変しない |

## 現行パレートと旧候補台帳の統合ビュー

2026-10-17パレートは、正式RF-F003最大2Cv／試験RF-T005最大3Cv、外部固定S2P付き、必須H2/H3≥30dBの有限格子における保存候補を分離している。どちらもIL≤0.30dB・35dB公称は未達。実行や検証の詳細は [結果の閲覧入口](../docs/results/README.md) と [原レポート](../docs/pareto_rf_t005_rf_f003_20261017.md) に記載する。

旧14件の[固定スナップショット](catalog/research_candidate_register_20261017.csv)とRF-T005/RF-F003の最新10点は、[統合24件CSV](catalog/phase2_candidate_catalog_20261017.csv)に**出典付き派生ビュー**として収録済み。[条件・検証深度・不変入力の説明](catalog/README.md)を参照。正式／試験／旧仕様間で比較条件を混ぜない。

## 証拠保全上の注意

- 元実験の完全ベクトルは [experimentsの案内](../experiments/README.md) → `runs/EXP-NNN/` を参照する。元checkpointと検証overlayを区別する。
- 別の格子幅・別の独立MNAで確認したことは、条件を揃えた再検証と同じではない。
- 未リンク、同一Git blob、古いログ・lockだけでは削除可否を決めない。[統合済みPR #71](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/pull/71)により整理Step 1～5を実装。[W0保全監査](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/blob/727de04781cf42e6a9aaa710dc33f0ab0fb78b6d/docs/phase2_cleanup_w0_current_main_audit_20261017.md)では要レビュー46件の原SHAが全件一致し、削除は未承認。
- GitHubを長期保全先とし、期限付きActions artifactを唯一の根拠としない。

[プロジェクトREADME](../README.md) ／ [文書一覧](../docs/README.md)

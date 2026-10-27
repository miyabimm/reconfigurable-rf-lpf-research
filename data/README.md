# data/：数値正本と研究データ

RF数値仕様の正本は[constraints/registry.json](constraints/registry.json)のactive正式JSON（現在RF-F003）、[bands.csv](bands.csv)、固定S2PとそのSHAです。説明文書は数値の正本ではありません。

| 場所 | 管理対象 |
|---|---|
| [constraints/](constraints/) | 不変のformal版と明示trial版 |
| [bands.csv](bands.csv)／[parasitics/](parasitics/) | 6設定の対象帯域／固定外部S2P（モデル由来、実測ではない） |
| [experiment_number_registry.csv](experiment_number_registry.csv) | 新EXPのmain事前予約 |
| [experiment_index.csv](experiment_index.csv) | 実験ID・実行/検証状態・原manifestへの入口 |
| [catalog/](catalog/)／[pareto_snapshots/](pareto_snapshots/) | 保存日時点の候補集計・凍結比較資料 |
| [validation/](validation/)／[repository_reviews/](repository_reviews/) | 旧追試・出典復元・監査の証拠（未審査削除不可） |

[design_constraints.json](design_constraints.json)は正式RF-F003の互換コピーであり独立の正本ではありません。重複の整理は参照コード・原本の復元性の検証後に実施します。詳細は[実験原本](../experiments/README.md)と[Issue #170](https://github.com/miyabimm/reconfigurable-rf-lpf-research/issues/170)を参照してください。

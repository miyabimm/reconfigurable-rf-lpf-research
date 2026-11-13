# data/：実験番号台帳と互換パス

**正式RF数値の正本は[rf/constraints/registry.json](../rf/constraints/registry.json)、[rf/bands.csv](../rf/bands.csv)、[固定S2P](../rf/parasitics/)です。** `data/constraints/`・`data/bands.csv`・`data/parasitics/`・`data/design_constraints.json`は履歴互換symlinkであり、現役RFの独立した正本ではありません。

## 残す現役データ

- [experiment_number_registry.csv](experiment_number_registry.csv)：新規正式EXPの**main事前番号予約（G0）**。
- [experiment_index.csv](experiment_index.csv)：実行状態と検証状態の中央索引。旧EXPの行と元manifestは勝手に書き換えない。
- 候補登録、研究条件・外部S2Pの機械入力、保存容量規則など、現役監査・将来の研究判断に必要なデータ。消去可否はcallerと科学的価値から判定する。
- EXP-050以降の保存は[保存ポリシー](../project/experiment_storage_policy.md)と[各EXP原本](../experiments/README.md)を使用する。未実行・未収束・数値検証・独立検証・保存完了を分離する。

## 整理済みの旧資産（Issue #397）

- RF-T008の派生Paretoは[PR #403](https://github.com/miyabimm/reconfigurable-rf-lpf-research/pull/403)で削減。SHA登録済み6件はEXP-058/059配下へ同一blob移動。
- 旧`data/validation/`の**182件・4,351,659 bytesは全削除**（[PR #407](https://github.com/miyabimm/reconfigurable-rf-lpf-research/pull/407)）。EXP-047の旧索引用overlayと専用adapterも退役した。元の非標準manifestは固定Git blob SHAでindex-only照合し、現存証拠SHAと新規EXPの厳格監査を維持する。
- 旧実験の知見は[methods](../project/methods.md)／[results](../project/results.md)に統合。削減前の原文は[固定Git tree](https://github.com/miyabimm/reconfigurable-rf-lpf-research/tree/246444b93fb6e6b082af6ece3c5bfc7bcaff05c9/data/validation)から参照できるが、現行treeで旧runを完全再現できるとは主張しない。

今後の削減は[Issue #397](https://github.com/miyabimm/reconfigurable-rf-lpf-research/issues/397)で管理。RF正本・正式EXP原本・重要checkpoint・新規G0〜G5を保護し、現在作業中の`project/diagnostics/`には触れない。

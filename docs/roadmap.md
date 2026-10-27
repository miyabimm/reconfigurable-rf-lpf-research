# RF-LPF研究ロードマップ

現在の開発ゲートだけを管理します。日付別の経過はIssue・PR、実験結果と独立検証はEXP原本を参照します。正式数値制約は[registry.json](../data/constraints/registry.json)のactive ID、帯域は[bands.csv](../data/bands.csv)です。

## 現在地（2026-10-27）

| 対象 | 状態 | 出典・次の条件 |
|---|---|---|
| Stage 1：共通回路コア | **完了** | [PR #164](https://github.com/miyabimm/reconfigurable-rf-lpf-research/pull/164)、[Issue #165](https://github.com/miyabimm/reconfigurable-rf-lpf-research/issues/165)。既存EXPの凍結ベクトルとのパリティを確認 |
| Stage 2：独立MNA・外部端子評価 | **進行中** | [Issue #163](https://github.com/miyabimm/reconfigurable-rf-lpf-research/issues/163)／[Issue #168](https://github.com/miyabimm/reconfigurable-rf-lpf-research/issues/168)。[裸回路MNA設計](issue163_stage2_mna_core.md)だけでは外部S2P込みのRF適合判定は未完了 |
| Stage 3以降：共通探索・実行基盤 | **未完了** | 前工程のDoDと独立検証を確認して進める |
| 文書・データの再編 | **進行中** | [Issue #170](https://github.com/miyabimm/reconfigurable-rf-lpf-research/issues/170)。文書の簡素化と原本保全を別に検証 |

## 優先事項

1. 共通回路API・独立枝電流MNA・外部固定S2P・全6設定/28不連続区間の評価を整合させる。
2. 正式RF-F003とRF-T005/T006/T007/T008の結果を条件ID・実効SHA・検証深度で区別する。
3. 回路理論による新トポロジー発案と有限グラフ探索を併用する。面積–ILの比較では、H2/H3減衰、収束、物理実現リスクを確認する。
4. SPD・受動性・電力保存・独立MNA・再現性を省略しない。Q(f)、SRF、EM、公差、実測が未確認なら未確認と記録する。

新しいEXPと大規模計算は別途承認とmain事前予約を必要とします。代表候補は[結果の入口](results/README.md)と[実験索引](../data/experiment_index.csv)で確認してください。**IL≤0.30dB、公称H2/H3≥35dBの達成を、本ロードマップから推定しません。**

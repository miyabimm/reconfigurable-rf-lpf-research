# RF-LPF研究ロードマップ

現在の開発ゲートだけを管理します。日付別の経過はIssue・PR、実験結果と独立検証はEXP原本を参照します。正式数値制約は[registry.json](../rf/constraints/registry.json)のactive ID、帯域は[bands.csv](../rf/bands.csv)です。

## 現在地（2026-10-29、main `6b8cf91`確認）

| 対象 | 開発DoD | 根拠と対象範囲 |
|---|---|---|
| Stage 1：共通回路コア | **完了** | [#165](https://github.com/miyabimm/reconfigurable-rf-lpf-research/issues/165) / [PR #164](https://github.com/miyabimm/reconfigurable-rf-lpf-research/pull/164)。凍結ベクトルの限定パリティ |
| Stage 2：共通評価・独立MNA | **完了（限定回帰）** | [#168](https://github.com/miyabimm/reconfigurable-rf-lpf-research/issues/168) / PR #169・#171・#176・#177。固定S2P、独立MNA・電力収支、5ベクトル×28区間×3点のパリティと有限格子監査。当時の歴史inventory不整合は例外として#170へ移管、後続PR #201で行数整合 |
| Stage 3：目的・初期値・SLSQP v2統合 | **完了（mock配線＋単一start実SciPy smoke）** | [#180](https://github.com/miyabimm/reconfigurable-rf-lpf-research/issues/180) / PR #187・#188、[後続#198](https://github.com/miyabimm/reconfigurable-rf-lpf-research/issues/198) / [PR #199](https://github.com/miyabimm/reconfigurable-rf-lpf-research/pull/199)。RF-T005の既存3L・1 startで実SciPy配線を限定確認。fine固定GJM C=0 pFで部品/box FAIL、有限格子厳密FAIL。本番探索・RF認定なし |
| Stage 4：有限トポロジー・候補・Pareto | **完了（限定回帰）** | [#189](https://github.com/miyabimm/reconfigurable-rf-lpf-research/issues/189) / PR #190・#191。有限候補記録・証拠深度別比較、候補昇格はblocked |
| Stage 5A/5B：共通実行入口・保存／監査ゲート | **完了（synthetic/mock・隔離fixture）** | [#192](https://github.com/miyabimm/reconfigurable-rf-lpf-research/issues/192) / [PR #193](https://github.com/miyabimm/reconfigurable-rf-lpf-research/pull/193)、[#194](https://github.com/miyabimm/reconfigurable-rf-lpf-research/issues/194) / [PR #195](https://github.com/miyabimm/reconfigurable-rf-lpf-research/pull/195)。#195はmain `8eb25f0` に統合、PR最終HEAD通常CI 305件・Pi sparse 79件PASS、main smoke 305件PASS |
| 文書・実験証拠の整理 | **継続** | [#170](https://github.com/miyabimm/reconfigurable-rf-lpf-research/issues/170)。[PR #201](https://github.com/miyabimm/reconfigurable-rf-lpf-research/pull/201)で不足21行を追記してinventory66行へ整合。完全checkoutのinventory監査PASSは#201で記録済み（科学的RF検証とは別） |

**開発DoDと科学的成果は別判定。** Stage 1〜5の完了は限定コード・回帰の完了であり、新規EXPの番号予約、実SciPyの**本番探索**、本番dense/独立RF計算、RF-F003適合認定、候補昇格、連続帯域保証や実装成立を意味しません。Stage 5Bの共通入口はsynthetic/mock診断とEXP事前検査・証拠監査の接続までで、実EXP runnerではありません。実EXP開始は所有者承認とmain事前番号予約を別途要します。

[親Issue #163](https://github.com/miyabimm/reconfigurable-rf-lpf-research/issues/163)の57項目は棚卸し一覧であり、Stage完了により全項目を一括消化しません。次工程は[Issue #202](https://github.com/miyabimm/reconfigurable-rf-lpf-research/issues/202)の実SciPy出力→候補記録・不適合除外の限定接続検証（未着手）。少なくともD05（RF-T006追加停止帯域対応）・D07（一般感度／モード解析）は未実装の後続課題です。正式activeはRF-F003、現nominal adapterの限定対象は明示trial RF-T005/T007/T008（F003/T006はfail-closed）です。

## 優先事項

1. 共通回路API・独立枝電流MNA・外部固定S2P・全6設定/28不連続区間の評価を整合させる。
2. 正式RF-F003とRF-T005/T006/T007/T008の結果を条件ID・実効SHA・検証深度で区別する。
3. 回路理論による新トポロジー発案と有限グラフ探索を併用する。面積–ILの比較では、H2/H3減衰、収束、物理実現リスクを確認する。
4. SPD・受動性・電力保存・独立MNA・再現性を省略しない。Q(f)、SRF、EM、公差、実測が未確認なら未確認と記録する。

新しいEXPと大規模計算は別途承認とmain事前予約を必要とします。代表候補は[結果の入口](results.md)と[実験索引](https://github.com/miyabimm/reconfigurable-rf-lpf-research/blob/main/data/experiment_index.csv)で確認してください。**IL≤0.30dB、公称H2/H3≥35dBの達成を、本ロードマップから推定しません。**

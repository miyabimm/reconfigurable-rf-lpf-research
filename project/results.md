# RF-LPFの保存結果と検証証拠

本書は**ナレッジベースの結果索引**。RF-F003、RF-T005〜T008、旧RFの代表結果・検証範囲はテーマ別文書を読む。数値原本は[data/experiment_index.csv](../data/experiment_index.csv)と正式EXP manifest。保存された有限格子値を連続帯域・実測や独立MNAと混同しない。

**参照原則：** 条件ID・effective SHA、全6設定／28区間、格子、source、実施/未実施・未収束を区別。短縮ではなく関連する知識を複数ページへ配置し、旧見出しのリンク先を維持する。

## 正式RF-F003旧版とRF-T005〜T007試験の固定比較（2026-10）
[RF-F003旧版とRF-T005〜T008の代表結果](knowledge/formal_trial_results.md) — 条件実効SHA別のPareto、面積・IL・減衰、独立MNA深度、trial条件差。

## RF-T008 v3の横断比較（2026-10-20の固定履歴）
[RF-F003旧版とRF-T005〜T008の代表結果](knowledge/formal_trial_results.md) — 条件実効SHA別のPareto、面積・IL・減衰、独立MNA深度、trial条件差。

## RF-T008旧条件の多初期値と座標A/B比較
[探索手法・Pareto・数値判定の教訓](knowledge/optimization_lessons.md) — RF-F003対trialの比較境界、多初期値・座標・格子、Paretoと旧RF-F002の失敗、実行済みA/B数値。

## 開発Pilotの未収束と限定性能診断（2026-11）
[非EXP PilotとMinimalWorkerの性能計測](knowledge/pilot_performance.md) — 未収束Pilot、測定契約・inclusiveタイマー、#401の実測・限界（正式EXPではない）。

## 旧data/validationの整理とRF-F002の教訓（Issue #397）
[旧RF条件の成果・出典・訂正記録](knowledge/legacy_evidence.md) — 旧RF-F001/F002/T003/R2の代表結果、EXP-017/042/046/047の訂正・原本境界。

## 旧RF-F001/T003・R2の成果と限界
[旧RF条件の成果・出典・訂正記録](knowledge/legacy_evidence.md) — 旧RF-F001/F002/T003/R2の代表結果、EXP-017/042/046/047の訂正・原本境界。

## 訂正・回収・再現性（元記録を上書きしない）
[旧RF条件の成果・出典・訂正記録](knowledge/legacy_evidence.md) — 旧RF-F001/F002/T003/R2の代表結果、EXP-017/042/046/047の訂正・原本境界。

### EXP-016/017と旧RF-F002 runner
[旧RF条件の成果・出典・訂正記録](knowledge/legacy_evidence.md) — 旧RF-F001/F002/T003/R2の代表結果、EXP-017/042/046/047の訂正・原本境界。

### EXP-042、046/047の原本と訂正
[旧RF条件の成果・出典・訂正記録](knowledge/legacy_evidence.md) — 旧RF-F001/F002/T003/R2の代表結果、EXP-017/042/046/047の訂正・原本境界。

## 枝スタンプ前計算の3方式比較（Issue #413）

[現役KB](knowledge/pilot_performance.md#枝qスタンプ前計算と小行列縮約issue-413)・[報告と原記録](diagnostics/issue413_report.md)。RF-T008 rev3 trial／full_lpf・70点に限定した開発診断。事前枝Qスタンプのsix-matmul／direct-matmulは固定100 vectorの完全RF forwardとSolver plainで2batch改善方向を観測。six-matmulを独立レビュー第一候補とするが**本番未採用**。全S／全指標／mandatoryの許容差内一致・代表全70点独立MNAとSTOP回帰を確認、ビット非一致・Solver経路差・全88 Solver run未収束。正式RF適合や汎用速度率を認定しない。

## six-matmul採用後mainのRF forward内訳（Issue #417）

[現役KB](knowledge/pilot_performance.md#six-matmul採用後mainのrf-forward内訳issue-417)・[報告／全run raw／再現](diagnostics/issue417_report.md)。#416後HEAD `523f3ab8`、RF-T008 rev3 **trial opt-in**／full_lpf、同一の既存100 vector・固定S2P・6設定／28別区間／70 samples。plain中央値49.140ms/100 forward。deep inclusiveではpower_response 12.705ms、Schur相当のrun別`port−node`差8.590ms、decode 7.186msを次候補として観測。ただしdeep/plain paired計器差は中央値+5.955ms、最大+20.298msで不安定、inclusiveは合算不可。全24runのS/全metric・mandatory_g digestはplain/deepで一致し、既存RF Core／branch-current MNA／production-stamp回帰PASS。正式RF性能・全100独立MNA・連続帯域保証ではなく、高速化実装なし。

## 完全RFResponse維持の行列組立て診断（Issue #410）

[非EXP性能診断の知見](knowledge/pilot_performance.md#完全rfresponse維持のc組立て診断issue-410)・[詳細と原記録](diagnostics/issue410_report.md)。固定C分離は遅く不採用、全6設定先行はplain再測定で効果未確定・本番不採用。全S／IL/APL／両RLを保持し、固定100候補で許容差内だがビット非一致・Solver軌道差を確認。正式RF適合・収束の認定ではない。

## MinimalWorker性能診断（Issue #401）
[非EXP PilotとMinimalWorkerの性能計測](knowledge/pilot_performance.md) — 未収束Pilot、測定契約・inclusiveタイマー、#401の実測・限界（正式EXPではない）。

## 文書統合と固定監査の読み方（Issue #352）
[旧RF条件の成果・出典・訂正記録](knowledge/legacy_evidence.md) — 旧RF-F001/F002/T003/R2の代表結果、EXP-017/042/046/047の訂正・原本境界。

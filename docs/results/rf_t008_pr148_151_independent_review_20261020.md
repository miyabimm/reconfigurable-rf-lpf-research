# RF-T008 v3 Phase 2 — PR #148–151 独立クロスレビュー

2026-10-20、PR #148～151の試験記録・回路チェックポイントを横断してレビューした。対象はEXP-062～065。**RF-F003正式制約は変更しない。研究Phase 2を継続し、Phase 3は未承認。**

## レビューの独立性と範囲

- 新規の独立**読み取り専用**監査 `scripts/review_rft008_exp062_065.py` を作成。EXPのSLSQP最適化・回路評価コードをimportせず、保管済みcheckpoint・run_summary・manifest・storage_recordと実験台帳を比較する。
- 10件のチェックポイントについて、L型/Q25/定数範囲、GJM01 Q80/チップ面積、GND PCB C Q60/Hot-Hot PCB Q40/容量上限、IC内固定C Q60と各バンド可変C Q35の接続一致と制約、全6設定の保存ベクトルを独立に照合。
- 結合インダクタの相互係数から新たに相互インダクタンス行列を組み立て、**固有値・SPDを独立計算**して各84点の独立7×7/9×9 MNA保存記録とクロスチェック。
- 28区間×1001点の結果とMNA最大IL差・電力収支は**既存実行結果の検証記録を監査**したものであり、全回路の3つ目の独立RF解析器による再計算ではない。この限界を保存する。
- 収束していない終了状態を収束済みに変更せず、途中の旧失敗ログを隠さない。すべての結果で制約fingerprint `7de08611f8dd15b40fdfb7946e8c93de5796d026641bdca0f12e992962d05fd4` を要求する。

## 試行・検証実績

| 実験 | 回路/コスト | 試行数 | 両段階収束 | 非収束 | 保管済み独立MNA |
| --- | --- | ---: | ---: | ---: | --- |
| [EXP-062 / PR #148](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/pull/148) | 4L 2/3/4 GJM | 24 | 23 | 1 | 9×9 |
| [EXP-063 / PR #149](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/pull/149) | 3L 0/1/2 GJM | 24 | 24 | 0 | 7×7 |
| [EXP-064 / PR #150](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/pull/150) | 4L 0 GJM | 24 | 24 | 0 | 9×9 |
| [EXP-065 / PR #151](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/pull/151) | 4L 2 GJM | 192 | 178 | 14 | 9×9 |
| **計** | | **264** | **249** | **15** | **選択保存10解をチェック** |

保管監査PASS、数値結果のRF/H2/H3必須30dB、別方程式系の独立MNA pass、およびL行列SPDを個別に検査した。非収束15件にはパレートの適格性を与えない。

## 横断パレート

| チップ面積 | 最良観測 worst IL [dB] | 出典/位置づけ |
| ---: | ---: | --- |
| 3 | 1.010350255 | EXP-058（EXP-063再照合） |
| 3⅔ | 0.934027580 | EXP-058（EXP-063再照合） |
| **4** | **0.929126781** | **EXP-064で新非支配点** |
| 4⅓ | 0.928118761 | EXP-058（EXP-063再照合） |
| 4⅔ | 0.837133749 | EXP-059 |
| **5⅓** | **0.829711540** | **EXP-065で更新**（EXP-062旧0.833505430） |
| **6** | **0.827841148** | **EXP-062で更新** |

面積6⅔・IL0.837795449は面積6解より高ILで支配される。

機械可読な統合スナップショット：`data/pareto_snapshots/rf_t008_exp062_065_integrated_20261020.json`。クロスチェックActions：[review_rft008_pr148_151.yml](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/blob/exp065-rft008-wide-4l2gjm-20261020/.github/workflows/review_rft008_pr148_151.yml)。

## 発見した運用上の問題と是正

- 4つのPRは旧main上で別々に作成されたため、各`data/experiment_index.csv`末尾追記が競合した。各実験の保存ファイルを保持しつつ、mainの既存行を優先してEXP-062→063→064→065を重複なく追加し、各段階でsmoke CIを実行。
- EXP-064/065の保管Actionsは完了済みのmanifestに対して事前準備用preflightを再適用すると失敗する。既に完了している場合には**読み取り専用監査**へ分岐するよう改修。数値結果・保存checkpointの内容は不変更。
- EXP-065の初期smokeが一時失敗したのはGit未分類の追加EXPファイルが保管処理前に存在したため。後続の保管監査済み状態と統合branch状態のCIを別々に再確認する。

## 検証の限界

現在の観測パレートは、あくまで探索したトポロジーとSLSQPの局所解に対する**公称定Qの有限格子結果**。全トポロジー大域最適性、連続帯域極値、Q(f)/SRF、相互結合の同時物理実現、EM、実部品許容差、PCB/IC真面積、実測は未確認。公称35dB停止帯域目標およびIL0.30dB目標の達成を主張しない。

このレビューはPR差分と保存済み数値記録の整合性を確認するものであり、人手による別研究者の承認、製造・実装承認、Phase 3移行承認を代行しない。

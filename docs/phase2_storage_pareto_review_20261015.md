# Phase 2：証拠逆引き・保管区分・条件別Pareto（2026-10-15）

> **保全用の歴史記録（2026-10-15基準）。** このページの旧 `scripts/build_reference_inventory.py` は軽量化によりmainから退役。元コードは [固定Git原本](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/blob/f0337963688d2a7155b8e28488d6723f2578e73e/scripts/build_reference_inventory.py) から復元できる。古いActions artifactは恒久保管先ではなく、以降の最新CI構成を説明しない。Pareto計算コード `scripts/report_research_pareto.py` と数値分類テストは引き続き保持する。

本書は既存結果の非破壊的な管理方法を定める。研究Phase 2を継続し、Phase 3開始、正式制約RF-F002の変更、歴史的証拠の移動・削除は行わない。PR #50の証拠棚卸し成果を起点として開発し、PR #50はmainへSquash Merge済み（統合コミット `7881f2e624621fb0053eb9ba36d0aa891eec7da4`）。本PR #51のbaseはmain。

## 保全と逆引き

 scripts/build_reference_inventory.py は、Git追跡ファイルを起点に、39実験のmanifestのevidence、候補台帳のcheckpointとverification、補助証拠、事後再計算overlayから逆引きする。次の出力を生成する。

- reference_inventory.csv：追跡ファイルのパス、サイズ、Git blob SHA-1、manifestの実験ID、候補ID、補助証拠の実験ID、保全判定。
- reference_summary.json：分類件数とファイル合計サイズ、参照に基づく保全状況。

保全判定は、approved_or_historical_policy / original_experiment_manifest（正本・履歴）、registered_manifest_evidence / registered_runtime_evidence / curated_checkpoint / curated_validation_evidence / historical_supplemental_source（参照あり、保持）、unlinked_runtime_diagnostic / unlinked_validation_artifact / unlinked_historical_source（レビューのみ、削除権限なし）等に分ける。

「索引から未参照」は「用途がない」の意味ではない。README・文書中のリンク、Git全履歴、元チャットのZIP、外部研究成果はこの自動逆引きでは網羅しない。停止再開試験ではlock、task、manager.log等が一次証拠になり得るため、拡張子だけで削除しない。Git blob SHA-1はmanifestが使うSHA-256とは異なり、混同しない。

## 13登録候補の暫定Pareto

 scripts/report_research_pareto.py は選別台帳の13候補を8つの比較区分に分け、同一制約ID・有効制約SHA・目的・減衰要求・記録の成立区分の内部でチップ面積と最悪ILの2軸Paretoを求める。候補以外の最適化やRF再計算は行わない。以下は登録値からのスナップショットであり、グローバル最適性や完全な探索網羅性の主張ではない。

| 制約 | H2/H3要求 | 成立区分 | 面積–IL非劣後候補（面積、最悪IL[dB]） |
|---|---:|---|---|
| RF-F002 正式 | 30dB | strict_finite_grid | RFF002-P2-4L-2C-30DB-01 (5.333, 0.381014) |
| RF-F002 正式 | 35dB | strict_finite_grid | RFF002-P2-4L-2C-35DB-01 (5.333, 0.460180)、EXP017-LQW2-H35 (9.333, 0.378798) |
| RF-F002 正式 | 30dB | tolerance_only | EXP-041-30DB-STAGE (9.333, 0.318693) |
| RF-F002 正式 | 35dB | tolerance_only | EXP-041-35DB-STAGE (9.333, 0.378349) |
| RF-T004 試験 | 30dB | reported_finite_grid | EXP016-HV30-V053 (6.667, 0.450901)、EXP016-LQW2-30-V053 (10.667, 0.377520) |
| RF-T004 試験 | 35dB | reported_finite_grid | EXP016-HV35-V009 (6.667, 0.539439)、EXP016-LQW3-35-V009 (12.667, 0.433221) |
| RF-T004 試験 | 35dB | strict_finite_grid | EXP018-C13.667 (13.667, 0.297114) |
| 旧2026-10-10 | 35dB | historical_only | LPF-007 (6, 0.513168)（旧条件の参考値のみ） |

RF-F002正式35dB strictでは、最小面積点と最小IL点が違うため2候補が非劣後。RF-F002のstrict区分ではIL≤0.30dBを達成した登録候補は現時点でない。ただし未登録候補全体での不存在を証明していない。RF-T004のIL0.297114dBは3可変C trialの結果で、RF-F002の達成を意味しない。

tolerance_onlyでは減衰の生値が要求値を微小に下回るためstrictと分離する。reported_finite_gridは元の報告値であり、EXP-016の事後CI再実行成功はoverlayとして別保存されている。比較区分が同じでも周波数格子、ソルバ、検証深度が異なる場合、厳密な候補間の優劣を主張する前に同一条件での再検証が必要。面積はハード上限ではない。物理SRF・Q(f)・温度公差・EM・寄生・量産性は未検証。

## CIの成果物と再生成

GitHub ActionsのPhase 2 regressionが下記の成果物を生成し、phase2-storage-and-pareto-reports というartifact名で30日間保持する。

- reference_inventory.csv / reference_summary.json
- pareto_candidates.csv / pareto_summary.json / pareto.md

上記の生成処理は読み取り専用。CIの実験数値チェックや既存の証拠監査は従来どおり実行し、ここで新規RF計算が行われるわけではない。再実行には上記2本のスクリプトを使い、出力を無視対象である artifacts/phase2_reports/ に保存できる。

## 次のゲート

- まず保存する価値があるデータの参照元を逆引きし、機械的な未参照を要レビューとして隔離する。削除候補に自動昇格しない。
- 本文・Git履歴・元チャット成果物の参照を追加調査した後、保管場所変更と保存期間を別PRで提案する。
- 正式RF-F002候補間の共通格子・独立MNA比較は別途実施する。今回は未実行。
- PR #50統合後に本変更のベースをmainへ更新し、PR #51の6ファイルの差分とCIを再検証する。PR #51のmain統合、既存研究証拠削除、RF制約変更、研究Phase 3移行はいずれも別承認を必要とする。

本表は2026-10-15時点の13件限定スナップショット。新規候補追加後の最新表はCIの生成物を参照する。

## GitHub Actionsでの実測分類

[Phase 2 regression run 38590510799](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/actions/runs/38590510799) は成功した。追跡データ領域535ファイルを分類し、manifestから直接参照されるファイルは391件。保全区分別には preserve_immutable **60件**、preserve_referenced **429件**、review_only_no_deletion **46件**となった。最後の46件は削除可能と判断したファイルではない（内訳：実験ディレクトリ18、旧候補2、validation領域26）。別パスで内容が一致するGit blobは33グループ、追加の同一blob参照37件。これらも重複だけで削除しない。機械可読な参照先がないものの保存根拠を追査するためのレビュー対象である。Git追跡ファイルの削除・移動は0件。

同CIで13候補・8グループのPareto生成と全回帰テストが成功。生成CSVとJSONはCIのartifact「phase2-storage-and-pareto-reports」から参照できる。この数値は当該ブランチの対象スナップショットに限る。

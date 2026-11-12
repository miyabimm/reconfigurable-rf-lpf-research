# RF-LPF研究ロードマップ

**現況：2026-11-13／Phase 2継続。** 本書は開発の到達度と未検証項目の入口。日付別履歴はIssue/PR、保存数値は[results.md](results.md)と[EXP索引](../data/experiment_index.csv)を参照。正式条件は[active registry](../rf/constraints/registry.json)、帯域は[bands.csv](../rf/bands.csv)。

現役の診断・限定実証の入口は[diagnostics/README.md](diagnostics/README.md)です（本整理では同ディレクトリの変更を行いません）。研究の承認境界は[運用正本](instructions.md)。

## 現行開発の到達点

| 系統 | main統合済み／確認済みの範囲 | 未実施・制限 |
|---|---|---|
| 科学・実行基盤 #306 | #307閉区間/schema2・履歴保護、#309 RF Core、#311性能、#313静的preflight、#315固定stage、#317 Worker、#319逐次親、#321開発CLI、#323依存整理 | 統合だけでRF目標達成や探索収束を認定しない |
| Campaign #325 | schema2 Plan、data-only提案、Controller/Worker、隔離Git fixtureによるG0〜G5の限定配線 | `run_campaign()`自動loopは`not_ready`、本物の正式Campaign EXPの実運用は未実証 |
| 実SciPy非EXP #330 | 開発Jobと隔離の架空EXP、各616/616 samples、独立terminal各1 spotを実行 | 予算終了・**未収束**、全9 batchのstrict finite-gridはFAIL。全面MNA／正式EXPではない |
| 実行基盤 #301 | 固定順逐次・明示提出API | scheduler、parallel、retry/resume、自動ライフサイクルは未提供 |
| 保存CI #332 / PR #334 | 保存専用と確実に分類できる変更だけ一般RF回帰を省略。G0/保存/provenance常時監査 | CI PASSは科学的RF再計算の実施を意味しない |
| 旧資産整理 #397 | PR #398/#399/#403/#405/#406/#407をmainへ統合。#407は210ファイル/4,445,242 bytes純削除、post-merge [smoke PASS](https://github.com/miyabimm/reconfigurable-rf-lpf-research/actions/runs/43255474036) | 現役文書と残りの旧資産は継続整理。`project/diagnostics/`は**対象外** |
| 性能診断 #401/#408 | PR #402・[#409](https://github.com/miyabimm/reconfigurable-rf-lpf-research/pull/409)統合。現役MinimalWorkerベンチは[scripts](../scripts/README.md) | 計測外乱があるため普遍的高速化率は未確定。#408のIssue状態はGitHubを確認 |

## 科学的な到達度（判断を分離）

| 判定 | 現在の根拠・限界 |
|---|---|
| ソフトウェアPASS | 対象PR/commitの限定テスト・CIに限る。独立回路MNAの再実行実績とは別 |
| solver収束 | #330は未収束。旧条件EXPの収束を現行RF-F003へ昇格しない |
| RF strict | #330有限格子FAIL。IL≤0.30dB／公称H2/H3≥35dBの現行正式達成を本書から推定しない |
| 新規EXP G0〜G5 | ソフトウェアゲートを実装・限定回帰。正式Campaign実運用／G5のraw実削除は未実証 |
| 独立検証 | #330はJobごとに1 terminal spotのみ。dense・全帯域独立MNAの成立ではない |
| 物理成立 | 連続帯域極値、Q(f)、SRF、EM、公差、実測、大域最適性は未確認 |

## 次の開発と研究判断

1. 現役の全6設定・28不連続区間、UL/DLとH2/H3、固定S2P、SPD、受動性・電力保存、独立枝電流MNAを維持する。
2. 回路理論に基づくトポロジー発案と有限探索を併用し、面積–IL・H2/H3・実装リスクを同一RF条件／同一検証深度で比較する。
3. 大規模本番計算と新規EXPは具体的Issue・ユーザーの着手指示、main中央番号G0予約、完全checkout/G1を前提とする。
4. 過去のStage 1〜5成果は限定的な開発到達記録。旧詳細は[Issue #163](https://github.com/miyabimm/reconfigurable-rf-lpf-research/issues/163)とPR #164/#169/#187/#190/#193/#195を参照。研究Phase移行は別途決定する。

実際のコマンドは[Campaign操作ガイド](campaign_workflow.md)、数値結果と仮説の区別は[methods.md](methods.md)／[results.md](results.md)。

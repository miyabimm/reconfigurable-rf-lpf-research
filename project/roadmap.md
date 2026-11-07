# RF-LPF研究ロードマップ

現在の開発ゲートだけを管理します。日付別の経過はIssue・PR、実験結果と独立検証はEXP原本を参照します。正式数値制約は[registry.json](../rf/constraints/registry.json)のactive ID、帯域は[bands.csv](../rf/bands.csv)です。

## 現在地（2026-11-07更新、基準main `11572ba`）

操作は[Campaignガイド](campaign_workflow.md)、限定証拠は[診断索引](diagnostics/README.md)を参照。
研究は**Phase 2のまま**。ソフトウェアStageと研究段階は別である。

| 対象 | ソフトウェア実績 | 未実施・未検証／次ゲート |
|---|---|---|
| [#306](https://github.com/miyabimm/reconfigurable-rf-lpf-research/issues/306) 主要科学基盤 | #307閉区間/schema2移行・履歴保護、#309共通RF core、#311区間別性能評価、#313静的preflight、#315固定stage、#317 Worker、#319逐次親、#321開発CLI、#323現役依存整理がmainに実装。詳細は各診断記録 | 基盤実装・限定回帰は探索収束やRF適合の認定ではない。旧Stage番号の完了を新基盤の全DoDへ読み替えない |
| [#325 Campaign](diagnostics/issue325_campaign.md) | PR #326〜#329：schema2 envelope、data-only逐次提案、2予算/予約/raw照合、明示G0/G1・G2・G3/G4・G5 eligibility。隔離Git fixtureで検査 | `run_campaign()` 自動loopは `not_ready`。正式EXP運用の実績なし、G5実削除なし |
| [#330 実SciPy非EXP](diagnostics/issue330_real_scipy.md) / PR #331 | 開発＋隔離Git架空EXP各1 Job、実SciPy内RF callbackを限定確認。各616/616 samples、独立terminal 1 spot。配線・保存のソフトウェア検査PASS | 予算終了で **未収束**、全9 batchの **strict finite-grid FAIL**。SciPy success/statusはnull。正式EXPではない |
| [#301](https://github.com/miyabimm/reconfigurable-rf-lpf-research/issues/301) 実行基盤 | 固定順逐次実行と明示提出APIあり | Scheduler／parallel／retry／resumeは未完了。自動提案・自動ライフサイクルも未提供 |
| 文書・保存CI | #333で現行操作と歴史資料を分離。#332保存専用CIは基準mainに未統合 | #170の広域docs/data棚卸しとは分担し、元証拠を変更しない |

| 科学・運用判定 | 現時点の範囲 |
|---|---|
| ソフトウェアPASS | 上記の限定回帰・#330配線検証。通常/sparse CIの結果は対応PR/HEAD単位で確認する |
| solver収束 | #330は未収束。少量callback到達は正常収束ではない |
| RF strict | #330の有限格子はFAIL。条件・参照面・格子・深度が異なる旧結果と混合しない |
| 正式Campaign EXP | 実行していない。本物の中央予約・実運用G0/G1・GitHub実験証拠保存は未実証 |
| 独立検証 | #330は1 spot/Jobのみ。dense・全帯域独立MNAの実施実績ではない |
| source/import同一性 | 隔離Git fixtureのダミーsource bytesと実importは異なる。実運用同一性は未検証で、正式EXP前に確認が必要（修正は本Issue外） |
| 科学的未検証 | 連続帯域、SRF、Q(f)、EM、公差、実測、物理成立、大域最適性を認定しない |

正式EXP開始は[運用正本](instructions.md)の具体的Issue範囲＋ユーザー起動に従い、完全checkout・main事前予約G0・G1を満たす。
開発APIや隔離架空EXPを正式EXPへ遡及昇格しない。D05/D07等の親Issue残件も個別に管理する。

## 旧共通化Stageの到達記録（2026-10-29、main `6b8cf91`）

| 対象 | 開発DoD | 根拠と対象範囲 |
|---|---|---|
| Stage 1：共通回路コア | **完了** | [#165](https://github.com/miyabimm/reconfigurable-rf-lpf-research/issues/165) / [PR #164](https://github.com/miyabimm/reconfigurable-rf-lpf-research/pull/164)。凍結ベクトルの限定パリティ |
| Stage 2：共通評価・独立MNA | **完了（限定回帰）** | [#168](https://github.com/miyabimm/reconfigurable-rf-lpf-research/issues/168) / PR #169・#171・#176・#177。固定S2P、独立MNA・電力収支、5ベクトル×28区間×3点のパリティと有限格子監査。当時の歴史inventory不整合は例外として#170へ移管、後続PR #201で行数整合 |
| Stage 3：目的・初期値・SLSQP v2統合 | **完了（mock配線＋単一start実SciPy smoke）** | [#180](https://github.com/miyabimm/reconfigurable-rf-lpf-research/issues/180) / PR #187・#188、[後続#198](https://github.com/miyabimm/reconfigurable-rf-lpf-research/issues/198) / [PR #199](https://github.com/miyabimm/reconfigurable-rf-lpf-research/pull/199)。RF-T005の既存3L・1 startで実SciPy配線を限定確認。fine固定GJM C=0 pFで部品/box FAIL、有限格子厳密FAIL。本番探索・RF認定なし |
| Stage 4：有限トポロジー・候補・Pareto | **完了（限定回帰）** | [#189](https://github.com/miyabimm/reconfigurable-rf-lpf-research/issues/189) / PR #190・#191。有限候補記録・証拠深度別比較、候補昇格はblocked |
| Stage 5A/5B：共通実行入口・保存／監査ゲート | **完了（synthetic/mock・隔離fixture）** | [#192](https://github.com/miyabimm/reconfigurable-rf-lpf-research/issues/192) / [PR #193](https://github.com/miyabimm/reconfigurable-rf-lpf-research/pull/193)、[#194](https://github.com/miyabimm/reconfigurable-rf-lpf-research/issues/194) / [PR #195](https://github.com/miyabimm/reconfigurable-rf-lpf-research/pull/195)。#195はmain `8eb25f0` に統合、PR最終HEAD通常CI 305件・Pi sparse 79件PASS、main smoke 305件PASS |
| 文書・実験証拠の整理 | **継続** | [#170](https://github.com/miyabimm/reconfigurable-rf-lpf-research/issues/170)。[PR #201](https://github.com/miyabimm/reconfigurable-rf-lpf-research/pull/201)で不足21行を追記してinventory66行へ整合。完全checkoutのinventory監査PASSは#201で記録済み（科学的RF検証とは別） |

この表は当時の限定コード・回帰の到達記録であり、現行Campaignの機能一覧ではない。
[親Issue #163](https://github.com/miyabimm/reconfigurable-rf-lpf-research/issues/163)の57項目を一括完了とはしない。
当時の#202「次工程」表示とnominal adapterの対象制限は、現行schema2の対応状況を表さない。
現行 `rf_core`／設計合法性はF003/T005/T006/T007/T008を検査し、trialは明示opt-in。
T006追加帯域の大規模検査や一般感度／モード解析の完了は主張しない。

## 優先事項

1. 共通回路API・独立枝電流MNA・外部固定S2P・全6設定/28不連続区間の評価を整合させる。
2. 正式RF-F003とRF-T005/T006/T007/T008の結果を条件ID・実効SHA・検証深度で区別する。
3. 回路理論による新トポロジー発案と有限グラフ探索を併用する。面積–ILの比較では、H2/H3減衰、収束、物理実現リスクを確認する。
4. SPD・受動性・電力保存・独立MNA・再現性を省略しない。Q(f)、SRF、EM、公差、実測が未確認なら未確認と記録する。

新しいEXPと大規模計算もIssueで定義した範囲とユーザーの着手指示に従い、main事前予約を必要とします。範囲外の作業・大幅な条件や予算の拡張は別途ユーザーの意思決定と記録を要します。代表候補は[結果の入口](results.md)と[実験索引](https://github.com/miyabimm/reconfigurable-rf-lpf-research/blob/main/data/experiment_index.csv)で確認してください。**IL≤0.30dB、公称H2/H3≥35dBの達成を、本ロードマップから推定しません。**

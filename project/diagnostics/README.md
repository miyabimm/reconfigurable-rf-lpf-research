# 診断・旧仕様の索引

**通常の操作入口は [Campaignガイド](../campaign_workflow.md)**。本ディレクトリのIssue番号付き資料は
そのIssueのスコープ・当時の検証結果・レビュー証拠であり、現行状態は[ロードマップ](../roadmap.md)とmain実装を確認する。
古い「Draft」「レビュー待ち」「未接続」を現況へ読み替えない。[Issue #397](https://github.com/miyabimm/reconfigurable-rf-lpf-research/issues/397)では知見抽出済みの旧診断原資料を削減する。削減後の主要解釈は[methods](../methods.md)・[results](../results.md)、逐語原文は固定Git履歴を参照。
#343で隔離された旧Pythonコピーは#362で現行treeから削除済み。[履歴索引](../../archive/issue343/README.md)の元commit・元パスから `git show` で取得する。

## MinimalWorkerの現役性能診断

[単一ベンチ入口](../../scripts/benchmark_minimal_worker.py)のplain/timed/deep、[操作・出力境界](../../scripts/README.md#minimalworker開発ベンチ)、[#401の方法](../methods.md#minimalworker性能診断の運用401408)・[結果](../results.md#minimalworker性能診断issue-401)。固定入力 [starts](issue401_starts_1002.json) と [baseline](issue377/baseline.yaml) は保持。#401専用raw・報告・単発driverは[PR #402時点の固定履歴](https://github.com/miyabimm/reconfigurable-rf-lpf-research/tree/26427c9ce08fe166d5dec31640f417c8dfe2ec79/project/diagnostics)にあり、現役treeへ移動・複製しない。他Issueの歴史診断はこの整理の対象外。

### Issue #410：完全RFResponse維持のC組立て診断

[報告・再現方法](issue410_report.md)、[明示opt-in試作](issue410_probe.py)、[全A/B・deep原記録](issue410_ab.json)、[固定100候補の同値性・micro原記録](issue410_equivalence.json)。固定C分離は遅く不採用、全6設定先行もplain再測定で効果未確定につき本番不採用。`src/`とRF契約は未変更。少数の固定候補は独立MNAを実行、全Solver runは未収束。汎用fast-path／正式RF適合の認定ではない。

### Issue #423：dB異常値検査の集約

[報告・再現方法・全run](issue423_report.md)。当初は実RF forwardの外乱により本番不採用と判断。その後のユーザー方針更新により、保存済み局所plain A/Bを根拠として検査1行を本番実装。最新mainでの追加比較と科学・STOP回帰は報告の追記参照。完全forwardの改善率は未確定。

### Issue #413：枝Qスタンプ前計算の3方式

[報告・全runへのリンク・再現方法](issue413_report.md)、[明示opt-in試作](issue413_probe.py)、[限定診断driver](issue413_benchmark.py)。固定100 vectorの実RF forwardで3案、Solver plainで上位2案を旧新交互・2batch比較。six-matmulをレビュー第一候補とするが本番未採用。 大容量測定raw5件は現役treeから整理し、報告中の固定commitリンクで全run原本を参照する（数値同値性rawは現役treeに保持）。全S／全指標／mandatoryを許容差内で保持し、代表全70点独立MNA・異常STOPを回帰。ビット非一致、Solver経路差、全Solver未収束、正式RFへの一般化不可を区別する。

### Issue #417：six-matmul採用後mainのRF forward内訳

[報告・再現条件](issue417_report.md)、[全24runのcompact raw](issue417_forward_timing.json)、[固定vector plain/deep診断driver](issue417_forward_timing.py)。#416後main `523f3ab8`、RF-T008 rev3 trial opt-in／full_lpfに限定。plain固定100-forward中央値49.140ms、deep inclusive計測はtimer負荷を伴う。power_responseが第一候補、Schur/decode/matricesは相対順位未確定。応答・mandatory g digest一致と既存科学回帰PASS。新しいSolver runや高速化実装なし。正式RF-F003・RF合格・連続保証ではない。

## 分類と用途

分類は現存資料の用途を示すもので、保存ポリシーのA/B/C判定ではない。過去の正式証拠・現役機能とは別に旧専用診断を退役させる。
同じ資料に現役APIの説明があっても、現行フローを重複して転記しない。

| 分類 | 所在 | 用途・現行ガイドとの関係 |
|---|---|---|
| 現行汎用フロー | [campaign_workflow.md](../campaign_workflow.md) | 操作を一読する入口。承認・数値・保存の正本は参照のみ |
| 限定実証・レビュー証拠 | [#307](issue307_constraints.md)、[#309](issue309_rf_core.md)、[#311](issue311_performance.md) | 制約移行・科学コア・性能評価の実装と限定回帰 |
| 限定実証・レビュー証拠 | [#313](issue313_preflight.md)、[#315](issue315_fixed_stage.md)、[#317](issue317_fixed_worker.md)、[#319](issue319_parent_runner.md)、[#321](issue321_development_cli.md) | schema2静的検査→固定stage→Worker→親→固定definition CLIの実装契約 |
| 限定実証・レビュー証拠 | [#323](issue323_layer_dependencies.md)、[#325](issue325_campaign.md) | 現役依存境界、Campaign各増分と隔離G0〜G5検査。実験の実施指示ではない |
| 限定実証・レビュー証拠 | [#343 PR-C](issue343_pr_c_cleanup.md)、[D1](issue343_d1.md)、[D2](issue343_d2.md)、[D3](issue343_d3_cleanup.md)、[D4](issue343_d4_cleanup.md)、[E1](issue343_e1_cleanup.md)、[E2](issue343_e2_cleanup.md) | 構造正本・保存ゲートの旧caller分離、科学回帰の現役API化、旧入口・候補・RF wrapper撤去と歴史資料の隔離。D4の残存matching旧layoutと未検証範囲に注意 |
| 限定実証・レビュー証拠 | [#330報告](issue330_real_scipy.md)・[再現コード](issue330_real_scipy.py) | 実SciPy callback非EXP検証、旧実行との差、source/import制限。再現コードはRF計算を行うので文書確認時に起動しない |
| 限定実証・レビュー証拠 | [#361 Pilot中断レビュー](issue361_pilot_review.md)、[#367少数forward時間診断](issue367_timing.md)、[#369開発用100-forward予約](issue369_forward_window.md) | 中断・未照合費用・原本所在不明、時間診断とmock限定の保存比較。Pilot再実行の指示ではない |
| 歴史的開発診断（知見統合済み） | [#372/#375の結果と限界](../results.md#開発pilotの未収束と限定性能診断2026-11)・[探索の教訓](../methods.md#開発pilotの未収束と性能計測の教訓rf-t008-schema2issue-372375389391393) | 非EXPの二つのPilotとwindow100固定vector照合。専用入力・派生summary・旧診断コードを#397で削減、逐語原文は[整理前Git](https://github.com/miyabimm/reconfigurable-rf-lpf-research/tree/504058c52b360e02e37649f509d257dea139ad64/project/diagnostics) |
| 開発ツール・限定検証 | [#387 checkpoint境界](issue387_checkpoint.md) | 非active切替の限定修正、非RF旧新比較・異常注入 |
| 開発ツール・限定検証 | [#378 共通監視](issue378_monitor.md)、[#381 py-spy](issue381/README.md)、[#383 内部タイマー](issue383_timing.md)・[非RFベンチマーク](issue383_benchmark.py)、[#385 短時間実RF内訳](issue385_timing.md) | 開発CLI監視・限定合成負荷・短時間実RF内訳。#381の子起動と#383の内部計時は別モード |
| 開発ツール・限定検証 | [#389/#391/#393の結果](../results.md#開発pilotの未収束と限定性能診断2026-11)・[現在も使う性能計測器](issue391_benchmark.py) | 旧Worker置換前の限定同等性と計測の教訓をKBへ統合。単発raw・専用A/Bコードを削減し、後続#394にも使用された再利用可能なplain/timed/profile計測器は残す |
| 限定実証・レビュー証拠 | [#254](issue254_curated_storage.md) | 旧共通curated保存と容量STOPの実測。現保存規則の代わりではない |
| 歴史・旧仕様 | [#235報告](issue235_scaling.md)・[JSON](issue235_scaling.json)、[#239](issue239_optimizer_comparison.md) | 旧座標正規化・optimizer比較契約・診断。保存vector/SHAは原証拠 |
| 歴史・旧仕様 | [#241](issue241_scipy_de_preview.md)、[#243](issue243_de_exploration_boundaries.md) | DE mock接続と評価境界。本番runnerの存在を意味しない |
| 歴史・旧仕様 | [#245選抜](issue245_start_selection.md)・[設計prototype](issue245_designed_starts.md)、[#248報告](issue248_generic_starts.md)・[JSON](issue248_generic_starts.json)・[コード](issue248_generic_starts.py) | 旧opt-in初期値の仮説・限定診断、実固定S2Pでの制限。数値JSONと再現コードを保持 |
| 歴史・旧仕様 | [#259 dense JSON](issue259-source-dense1001.json) | 旧2候補のread-only診断。新Campaignの最終検証ではない |
| 限定実証・レビュー証拠 | [#281](issue281_hybrid.md)、[#282](issue282_minimax.md)、[#283](issue283_pipeline.md)、[#291](issue291_generic_slsqp.md) | 汎用solver／合成関数の検証。RFの収束・適合とは別 |
| 歴史・旧仕様 | [#284](issue284_rf_pipeline_adapter.md)、[#285](issue285_rf_comparison_plan.md) | 旧RF adapterの限定検証と未実行比較案。実行承認・凍結済みPlanではない |
| 歴史・旧仕様 | [#302](issue302_sequential_search.md) | schema1 fixture runnerの実装時契約。現Campaignの正式G2とは別 |
| 限定実証・レビュー証拠 | [静的schema2 fixture](../fixtures/issue313_preflight.yaml) | #313/#315等のテスト入力。`definition: null`の基底例であってCampaign研究計画ではない |
| 歴史・旧仕様 | [旧Stage候補記録](../stage4_candidate_records.md)・[有限列挙](../stage4_topology_enumeration.md)、[legacy Git replay](../legacy_git_replay.md) | 旧候補／履歴再取得の詳細。現ガイドの通常事前参照にはしない |
| 歴史・旧仕様 | [旧共通CLI入力](../experiments/) | Issue限定YAML/starts/definitionとschema1 fixture。旧実験CLIは廃止済み（[project README](../README.md#廃止済み旧探索入口)）。未凍結templateを起動しない |
| 未整理（本Issue外） | 広域 `docs/`・`data/`・旧EXP | [#170](https://github.com/miyabimm/reconfigurable-rf-lpf-research/issues/170)の棚卸し領域。ここでは完全な歴史証拠auditを実施したとはしない |

## 履歴文書監査（通常CIとは別）

通常smokeは現行入口・リンクのみを文書検査し、履歴監査を実行済みとは扱わない。
以下は完全evidence checkout（`docs/`・`data/`・`experiments/`を含む）で必要時に明示実行する。

```bash
uv run --frozen python scripts/verify_phase2_cleanup_w1_links.py
```

この手動監査はGit commit `055b222c79c73c7fbeacb19383f21c1da0625195` のobjectと対応するblobを要する。
通常の全祖先fetchでも祖先外objectは保証されない。必要なobjectを取得可能な環境で確保し、
取得不可・未実行なら監査不可／未実行と記録する（skipや通常CI PASSで代用しない）。
全追跡Markdown検査は歴史資料のリンクも対象とする。外部URL・fragmentの到達性は検証しない。
履歴監査結果は現行RF／EXP保存の合否とは別で、広域棚卸しは#170に残す。

#339前後のCI保護の照合：`audit.yml` の `smoke` は保存専用と確定した場合だけ
一般回帰を省略し、不明・混在はfail-closedで一般回帰を実行する。常時の保存audit、
予約・provenance・storage・分類テストは不変。一般回帰のRF/optimizer/Runner/G0/G1、
予算STOP、固定S2P・独立MNA等も不変。6設定28区間・G0/G1等の現役検査も不変。
W1の固定commit依存だった原本保護は `test_experiment_provenance.py` の固定SHA-256で
EXP-004 README、EXP-047 manifest、旧bandsおよび移行前F003/T005原byteを常時照合する
（旧 `design_constraints.json` は同一F003原byte）。他のmanifest証拠SHA検査・新EXP保存audit、
移行archiveの履歴照合は通常CIとは別。固定の旧文書存在・台帳件数だけを検査する旧手動テストは#359で退役した。

## 整理候補と残す理由

基準main `11572ba` で `project/`、README、src/scripts/tests、CIの参照を検索し、原資料の用途を確認した。
GitHub上のIssue/PR全リンクや全EXPの参照完結性までは監査していない。**今回の削除対象はゼロ**。

| 候補 | 参照・証拠性の確認 | 判断／別途必要な確認 |
|---|---|---|
| 旧StageごとのREADME長文（#317/#319/#325） | 各診断にAPI/費用/ゲートが残る。READMEは入口の重複説明 | 今回は短い索引へ置換。原診断と固定definition CLIの契約は保持 |
| #302の一時的な「本番未接続」説明 | READMEと専用schema1 fixture/testsが参照。現Campaignには古いが旧CLIの説明には必要 | 将来の旧schema1経路廃止時に文書削除候補。先にcaller/テスト廃止とGit復元リンクを確認 |
| #235/#248診断のmd/JSON/py | #239が#235 JSONのvector/SHAを参照。#248 mdがJSON・再現コードを参照。単なる一時ログではない | **削除候補から除外**。証拠分類・復元性の審査なく分離しない |
| #259 dense JSON、#254容量診断 | 旧CLI注意書き／旧保存比較の根拠。dense値や容量実測はガイドに転記しない | **保持**。旧経路廃止後も科学的/保存レビュー証拠性を別途審査 |
| #330 md/py | mdに実行ログ/raw SHA・旧失敗との区別、コード再現手順がある。tmpは永続保管ではない | **保持**。再現コードだけの削除も根拠喪失になる。rawの自動削除・移動はしない |
| `project/fixtures/` | #313/#315テストと診断・CLI説明が直接参照 | **保持**。ファイル名だけで不要な一時資料にしない |
| #285未実行比較案 | 旧比較仮説・未承認予算を記録。汎用操作に不要 | 歴史参照へ分類済み。将来削除する場合もIssue/PRで参照とGit復元性を確認してから |

#333は現役 `project/` の入口整理のみ。#170の広域inventory修復、元raw/旧EXPの保存方式変更や削除、
source/import修正、pilot、保存専用CIの実装は対象外。

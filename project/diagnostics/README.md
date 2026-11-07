# 診断・旧仕様の索引

**通常の操作入口は [Campaignガイド](../campaign_workflow.md)**。本ディレクトリのIssue番号付き資料は
そのIssueのスコープ・当時の検証結果・レビュー証拠であり、現行状態は[ロードマップ](../roadmap.md)とmain実装を確認する。
古い「Draft」「レビュー待ち」「未接続」を現況へ読み替えない。ここでは原資料を改変・移動・削除しない。

## 分類と用途

分類は用途の整理であり、保存ポリシーのA/B/C判定ではない。「歴史・旧仕様」でも証拠は保持する。
同じ資料に現役APIの説明があっても、現行フローを重複して転記しない。

| 分類 | 所在 | 用途・現行ガイドとの関係 |
|---|---|---|
| 現行汎用フロー | [campaign_workflow.md](../campaign_workflow.md) | 操作を一読する入口。承認・数値・保存の正本は参照のみ |
| 限定実証・レビュー証拠 | [#307](issue307_constraints.md)、[#309](issue309_rf_core.md)、[#311](issue311_performance.md) | 制約移行・科学コア・性能評価の実装と限定回帰 |
| 限定実証・レビュー証拠 | [#313](issue313_preflight.md)、[#315](issue315_fixed_stage.md)、[#317](issue317_fixed_worker.md)、[#319](issue319_parent_runner.md)、[#321](issue321_development_cli.md) | schema2静的検査→固定stage→Worker→親→固定definition CLIの実装契約 |
| 限定実証・レビュー証拠 | [#323](issue323_layer_dependencies.md)、[#325](issue325_campaign.md) | 現役依存境界、Campaign各増分と隔離G0〜G5検査。実験の実施指示ではない |
| 限定実証・レビュー証拠 | [#330報告](issue330_real_scipy.md)・[再現コード](issue330_real_scipy.py) | 実SciPy callback非EXP検証、旧実行との差、source/import制限。再現コードはRF計算を行うので文書確認時に起動しない |
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
| 歴史・旧仕様 | [旧共通CLI入力](../experiments/) | Issue限定YAML/starts/definitionとschema1 fixture。動作中CLIの注意書きは[project README](../README.md#旧経路のcli設定契約必要時のみ参照)に保持。未凍結templateを起動しない |
| 未整理（本Issue外） | 広域 `docs/`・`data/`・旧EXP | [#170](https://github.com/miyabimm/reconfigurable-rf-lpf-research/issues/170)の棚卸し領域。ここでは完全な歴史証拠auditを実施したとはしない |

## 履歴文書監査（通常CIとは別）

通常smokeは現行入口・リンクのみを文書検査し、履歴監査を実行済みとは扱わない。
以下は完全evidence checkout（`docs/`・`data/`・`experiments/`を含む）で必要時に明示実行する。

```bash
uv run --frozen python tests/phase2_historical_status_audit.py -v
uv run --frozen python scripts/verify_phase2_cleanup_w1_links.py
```

前者はGit commit `0bf0e3a41e2ed2a5ae4e734ccec71bc530c19a53`・
`26a5d4aff7d197754f17991123acc44e8b356b83`、後者は
`055b222c79c73c7fbeacb19383f21c1da0625195` のobjectと対応するblobを要する。
通常の全祖先fetchでも祖先外objectは保証されない。必要なobjectを取得可能な環境で確保し、
取得不可・未実行なら監査不可／未実行と記録する（skipや通常CI PASSで代用しない）。
後者の全追跡Markdown検査は歴史資料のリンクも対象とする。外部URL・fragmentの到達性は検証しない。
履歴監査結果は現行RF／EXP保存の合否とは別で、広域棚卸しは#170に残す。

#339前後のCI保護の照合：`audit.yml` の `smoke` は保存専用と確定した場合だけ
一般回帰を省略し、不明・混在はfail-closedで一般回帰を実行する。常時の保存audit、
予約・provenance・storage・分類テストは不変。一般回帰のRF/optimizer/Runner/G0/G1、
予算STOP、固定S2P・独立MNA等も不変。Pi sparseの `test_issue307_history`、
`test_issue307_snapshot_equivalence` と6設定28区間・G0/G1等も不変。
W1の固定commit依存だった原本保護は `test_experiment_provenance.py` の固定SHA-256で
EXP-004 README、EXP-047 manifest、旧bandsおよび移行前F003/T005原byteを常時照合する
（旧 `design_constraints.json` は同一F003原byte）。他のmanifest証拠SHA検査・新EXP保存audit、
Pi sparseの移行archive全体照合も引き続き別途実行する。文書の歴史的復元性は上記手動監査の範囲。

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

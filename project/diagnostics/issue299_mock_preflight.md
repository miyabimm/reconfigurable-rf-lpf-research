# Issue #299 — mock専用4群配線の部分実装（本番STOP）

基点 `381bae2bb58b3abb3cc4a855e8c00e7b7baa6685`。**IssueのDoDは未完了。** 本番G0/G1/G2、pilot/remaining、実候補の17点・1001点・独立MNAは `not_run`。mock実行は共通CLI・実験runnerに接続されておらず、本番比較を実行可能にしない。

## 実装と検証範囲

`src/lpf/phase2_models/comparison_mock_preflight.py` は `unittest.mock.Mock` のforwardを必須とし、`/tmp`等の新規fixtureだけに既存 `atomic_write_json` でmarker・観測・終了を保存する。各群に新しい `SampleBudgetCost` 派生meterを作り、既存pipelineの `sobol_m=0, starts=(), max_evaluations=0` で生成したvectorを `PhysicalComparison.validate_vector` でbox・開端・部品・role・SPD検査後に使用。AはC1 seedとreplayを課金し、物理xの変更がないことを検査。B/C/Dは既存Hybrid/SLP/pipelineをmock forwardで呼ぶ。Aのstageは**mock**であり、実SciPy収束を検証しない。`returned_unverified` は収束やRF合格ではない。例外・予算停止・中断・未開始は分離する。

Aのseed・replay・stage観測とB/C/Dを共通meterのforward完了後に観測する。有限・完全なRF配列と物理box/role/SPDが合法のときだけ最後のxを記録し、小予算のmilestone/終端17点mock scanを同一meterに課金する。終端476 samplesを事前予約し、途中scanは予約を侵さない。scanはmilestoneを跨いだ**後の最後の合法観測**を測定し、scan完了時の費用を記録する。格子長および利用可能なstage名別のrequested/completed/calls/failuresを記録し、callback数やソルバー内部目的値をRF順位としない。これは有限のmock観測であり実候補scanではない。Aの実SciPy callback経路は未試験。

再現：

```bash
uv run --frozen python -m unittest discover -s tests -p 'test_phase2_comparison_mock_preflight.py' -v
```

既存 `test_phase2_rf_pipeline_adapter.py` には2点/区間の既存read-only fixture forwardが含まれる（実最適化や17点ではない）。既存共通CLIテストは一時checkoutのsynthetic EXP fixtureを作るが、実EXPの予約や保存ではない。

## 残余ブロッカーとSTOP

- 4群の共通観測とAの予算停止時終端scanはmockで確認したが、Aはmock stageであり実SciPy・実RFにおける公平性や全callback観測を認定しない。milestone scanも実候補には使っていない。
- mock-only APIは実行用共通CLI/YAML、既存実験保存・監査・G0/G1へ未接続。実行権限を付与せず、実forwardへの一般化や既存schemaの緩和も行わない。格子別とmock callback名別の部分費用だけであり、有限差分/選別/回復ごとの完全な費用分類、全群のstage別永続化、未収束の統一分類も未完了。
- 既存CLIの `comparison-readiness --allow-trial` はread-onlyの部分確認だけを追加。RF-T008 SHA、bands/6設定28区間、S2P、definition、ローカルcheckpoint byte（存在時）、HEAD/dirty・uv.lock・環境を報告する。checkpoint不在は `not_checked`。seed/vector・格子/重み/予算/保存は未凍結として常に `production_readiness=not_ready`、G0/G1/G2は `not_run`。不一致は例外でSTOPし、runや既存schemaを変更しない。
- read-only確認：明示opt-in RF-T008 effective SHA `7de08611f8dd15b40fdfb7946e8c93de5796d026641bdca0f12e992962d05fd4`、bands `1b1182e4c947059cb263c1af52ddf64236bd1fd9e83770cc844126576c7865fe`、入力S2P `ad266111ba1dc2b92f235d39f4a647ff271050bc11941c217661dd299ee59945`、出力S2P `b3cfc861bc0c8221f49328598c9d7d0766a6e94e42e990b6a50f6c90bf9a84da`、`uv.lock` `52144cfd0dfc7249e78c24942bac69fddc8dc3ae088799d9cf31d0d90e824e0b`。既存definition JSONのcanonical SHAは `bc50042a1b0b1ebf19c0272fb2ee944b52cd76e14eb8d44673bfa57f6033c068`、参照checkpointファイルはissue270 YAML固定SHAと一致。ただし原manifest・枝順等の完全な原証拠照合、remote byte readbackは `not_checked`、G1 PASSではない。checkpointを初期候補に使っていない。
- 将来のG1では実行コミット・dirty差分、環境・単一thread、seedと全vector、source/checkpoint原本、RF ID/SHA・S2P/bands、6設定28区間、格子・重み・予算・milestone・保存容量と選別規則を凍結・remote照合する必要がある。上記read-only確認は自動G1検証器の完成を意味しない。
- 本番には独立レビューとmain統合後、上記ブロッカー解決・G0/G1・明示的な後続実行Issueとユーザー起動が必要。後続Issueではpilot/remainingのseed・各群requested上限・終端予約・途中停止保存・選抜・dense/MNA費用・保存容量を具体的に定める。計画値は承認や実消費を意味しない。

有限格子、Q(f)、SRF、EM、公差、実測、連続周波数、物理実装、大域最適性は未検証。正式RF-F003や既存証拠は変更しない。

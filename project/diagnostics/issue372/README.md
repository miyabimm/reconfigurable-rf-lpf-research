# Issue #372：事前照合と診断途中の停止（レビュー待ち）

**STOP。window100の実RF比較・速度・checkpointゲートは未実施。Pilot 1001/1002、Main、Extension、正式EXPは未開始。** これはPilot結果ではない。後続を自動再試行・再開しない。診断用スクリプト `diagnose.py` は下記の既知の例外を含む実行時原本であり、そのまま再実行しない。

## 事前照合

- GitHub main `a5bec5656decefd539ae6277e810be4c6001f0aa`、PR #370 merge commit同一、最終head `b7ba6e55b3cebeef0bba1f1b651c408dbab05c30`、CI run [42489435626](https://github.com/miyabimm/reconfigurable-rf-lpf-research/actions/runs/42489435626) SUCCESS。shallow repositoryであり履歴全体の監査はしていない。
- 実行source HEAD `69b7f954ee81aebeb43b801ad966191c0996b5cc`、実行前git status clean、source identity SHA `d5e96823c26797c2590e19d7dd750848987f8619cf4888965b75ee3583351dd3`、対象source dirty patch SHA `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`。Python 3.12.15、NumPy 2.5.4、SciPy 1.18.1、Linux WSL2 x86_64、OPENBLAS/OMP/MKL各1 thread。`uv sync --frozen`実行。`uv.lock` byte SHA `52144cfd0dfc7249e78c24942bac69fddc8dc3ae088799d9cf31d0d90e824e0b`。
- 正式activeはRF-F003、今回はtrial RF-T008明示opt-in、effective SHA `e682165c72d3a8b9f1384a2529f71bacfebfc9d17164d4af5af879e4a138b532`。6設定・28区間・full_lpf。bands byte SHA `1b1182e4c947059cb263c1af52ddf64236bd1fd9e83770cc844126576c7865fe`、入力S2P `ad266111ba1dc2b92f235d39f4a647ff271050bc11941c217661dd299ee59945`、出力S2P `b3cfc861bc0c8221f49328598c9d7d0766a6e94e42e990b6a50f6c90bf9a84da`。70点grid SHA `6805740a36f6100d7dec3e7308924242e909255f1ea2d287b7c734c400f98f26`。
- 元Pilot YAML byte SHA `27f5fc515403805a956cd799d638328a81a1fee7c1eb59913e1e30765a75166a`、Plan SHA `8e472fd5a223eaef4aab24cc48e9dbcae6796f3930355b7871b62d3c76ab9ac4`（旧worktreeの一時definition実体により静的検査）。[新Pilot YAML](pilot.yaml) はdefinition pathのみ変更、byte SHA `20dd1319bded4c6de9cc1b6c389c70ecd24748f0e63cd64c403ba3f033e7094a`、Plan SHA `0abfb03063e41d7cc428a054663d1d0f7a1aa34801c45b7a9ac796e0055f4f2f`。新Plan静的preflightは1 Job 250,000内の上限予約221,064（探索220,000、selection 336、terminal 476、anytime 252）、dense別枠。Pilot自体は未起動。
- [definition](../issue361/definition.json) byte SHA `e8ac857c063e0b9d2eb8eaf629c2e4b700a694e9241f3bbc596d99f6374487f6`、内容SHA `bc50042a1b0b1ebf19c0272fb2ee944b52cd76e14eb8d44673bfa57f6033c068`。[starts](../issue361/pilot-starts.json) byte SHA `8fb74c3ceaa9627de6dcc2bf6a3bf538b265e07538a2205331335b05a23069f2`。再生成と完全vectorが一致、1001 vector SHA `49f9f53b0220f4e81332fbe94cebe2482e436b1a313aaabbae696a6b015761e5`、1002 `6203467121a4e37baaa51c471aaecb3174f3374f9ab955d6fbf101f7b5ce935f`。両方component policy PASS、L最小固有値それぞれ `1.56892805649937e-09 H`、`5.204340157276986e-10 H`。物理実装の証明ではない。

## 今回の独立診断と停止理由

[診断Plan](diagnostic.yaml) byte SHA `59e283ca3ccc32ecc1245313e31df8391cd14d510a75627f99026167180d44e1`、Plan SHA `2b6473ae28c0e86b3a6b2c88750c2502a03854e15a4ac18ebd5b9c3d7ad5dc28`。seed1001、探索上限7,000 samples（100 forward分予約）、solver fixture callback上限20、selection最大336、terminal 476、anytimeなし、Job cap10,000、静的予約合計7,812。旧方式1 callbackと新方式20 callbackを同一vectorで比較する設計であり、探索・最適化ではない。

旧方式だけ実行後、診断集計側でlegacy summaryに存在しない `summary['io']` を参照し `KeyError: 'io'` によりプロセス異常終了した。これは集計スクリプトの欠陥で、RF数値不一致や保存装置の故障を確認したものではない。集計値や実測wall/CPUは失われた。**window100 Jobは起動していない**。速度median・100-forward予約の実RF時の検証・方式間全S/requirements/Hybrid一致はいずれも未検証。今回の異常を隠してPilotに進めず、原因と保全状況をレビューに提出する。

旧方式Jobは親・worker・summaryの実ファイルreadbackおよびSHAを再照合できた。非収束fixtureの通常終了を意味するexit code 4であって実solver収束結果ではない。search 70、selection 84、terminal 476、合計 requested=completed=630、reserved=0、unknown=0。粗格子では worst IL `24.999944738674145 dB`、max violation `25.224754407591835 dB`、sum violation `323.4272113345574 dB`、strict=false。raw内のmandatory_gから再計算したHybrid sum `22511.121105913582`。この1 vectorを最良結果・Pilot性能と扱わない。benchmark再評価、独立MNA/受動性/電力、dense、連続帯域、Q(f)/SRF/EM、実測はnot_run。

## 原本と残課題

- 原本 `/tmp/issue372-legacy-20261109/` を保持、コピー `/home/user/issue372-evidence-20261109/legacy/` を作成しbyte SHAを比較。永続領域のバックアップ・将来の可用性は未検証。新window出力 `/home/user/issue372-diagnostic-20261109` は作成されていない。
- 各SHA: `development-hybrid-1001.json` `2dd174cd1e99bc3970b88f7abf0ddb715f50357c0a116fe466c710eec879feb9`、`run.json` `c72138da75a51d8c73463692d98841d7006614faffac890924eb8965eff3654c`、`summary.json` `0b9848d746c69f9185e91b418daf169e0e64212d58c71135dcaa5175315a1607`。親/summary記録されたworker/parent SHAも一致。
- 前回#361の消失原本やunknown Jobの250,000上限予約を変更・解放・相殺していない。今回の630 samplesは診断の別枠で、Pilot予算には含めない。
- 次はこの停止と原本を独立レビューし、診断の集計欠陥を修正・適切な小規模テストを実施したうえで、改めて手順と予算・sourceを凍結し、実RF数値/速度/保存ゲートを完了すること。正常通過まではPilotを始めない。Pilotの通常window100では全forward履歴は残らず、途中停止では最大1 window分の未保存forward証拠が失われ得る。

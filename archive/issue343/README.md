# Issue #343 D2 — 非現役の履歴資料

これらは**実行可能な現役APIではない**。通常のPython import・CIは参照しない。
元source・依存関係を含む実行環境が必要なら、元Git commitを隔離checkoutし、
対応する実験記録・条件・環境を確認する。このコピーからの直接実行は保証しない。
元EXP/historyおよび過去のsource fingerprintは変更しない。

元main: `681dabee30a7804d63bacc3afa5932e320c1d11a`。
以下は内容バイト不変の移動であり、SHA-256はファイル内容、blobはGit blob ID。

|元パス|元blob|内容SHA-256|保存理由と対象|
|---|---|---|---|
|`src/lpf/phase2_models/experiment_config.py`|`4b2a02ab46ae272a8b4326e48598ecdee3f04669`|`964a9405ee2296fd3ff8814f89f29d36c87efac4bf3681cf335544a74a8a4768`|旧schema4/5 continuation計画、EXP-116 nominal input参照、固定SHAと準備方式の解釈。schema2と同値ではない。|
|`scripts/prepare_issue250_comparison.py`|`cd2a7391eabb16f1bb0035d2a706aac1e522e660`|`164d7566d943b029b28dd6e78822e98dc74b31ed1ab22207d3c5c121a4c28e35`|Issue #250のEXP-062参照・比較start準備の歴史的意味。|
|`scripts/diagnose_phase2_scaling.py`|`a7c5d2e200009917f98cf26bccbd1258e9d0fdf0`|`6d18d6126dad8268942ecbb2a5a5f5ff47e2c539c05f6fe65408edd8efdef194`|Issue #235のEXP-086〜094の保存初期値、seed replayと有限差分尺度診断。旧RF条件に依存し、現役schema2とは同義でない。|

これらは旧RF-T008 effective SHA `7de08611f8dd15b40fdfb7946e8c93de5796d026641bdca0f12e992962d05fd4` に関係する。現行条件とは異なり、再評価・現行RF合格として読み替えない。元ファイルを読む例（Gitのobjectが存在する場合）:

```sh
git show 681dabee30a7804d63bacc3afa5932e320c1d11a:src/lpf/phase2_models/experiment_config.py
git show 681dabee30a7804d63bacc3afa5932e320c1d11a:scripts/prepare_issue250_comparison.py
git show 681dabee30a7804d63bacc3afa5932e320c1d11a:scripts/diagnose_phase2_scaling.py
```

旧source固定の歴史integrationや実EXP再現はこの移設では実行しない。

## D3：旧post-searchの歴史的手法

元main `0698a87925b30ccaf11531a5197a5dc611d3f681` からバイト不変で移動。
17点・独立84点・dense等の旧検証段階、候補証拠の再計算・source結合は
現役G3/G4の保存検査とは同義でない。以下は直接importや実行を保証しない。
旧条件・対象EXPの正確な対応は元manifestと元commitで確認する。完全証拠checkoutでの
履歴再現は未実施。旧RF-T008の例は上記旧effective SHAであり現行条件に読み替えない。

|元パス|元blob|内容SHA-256|保存理由|
|---|---|---|---|
|`src/lpf/phase2_models/post_search_evidence.py`|`64c8fed2f1d7952c30eb2542c80aab8af8643cb5`|`c8a7a42eb7a36d1848c5d5ec99681b3df741cf8fca5032eeee28601a57c631ff`|旧候補の証拠形式と検証意味。|
|`src/lpf/phase2_models/post_search_validation.py`|`88ac720d8ea41bb59e8958d654b79bc3e27a9a51`|`b9e3939bfb60777595dd985b8998b834db22b897f6208aa7706a3e4130c6e1e2`|旧17/84/dense検証手順と段階分類。|

`git show 0698a87925b30ccaf11531a5197a5dc611d3f681:src/lpf/phase2_models/post_search_validation.py` で元sourceを参照できる。

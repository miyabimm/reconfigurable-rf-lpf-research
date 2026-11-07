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

両者は旧RF-T008 effective SHA `7de08611f8dd15b40fdfb7946e8c93de5796d026641bdca0f12e992962d05fd4` に関係する。現行条件とは異なり、再評価・現行RF合格として読み替えない。元ファイルを読む例（Gitのobjectが存在する場合）:

```sh
git show 681dabee30a7804d63bacc3afa5932e320c1d11a:src/lpf/phase2_models/experiment_config.py
git show 681dabee30a7804d63bacc3afa5932e320c1d11a:scripts/prepare_issue250_comparison.py
```

旧source固定の歴史integrationや実EXP再現はこの移設では実行しない。

# Issue #377：途中結果・安全条件の相違により停止

**未完了 / Draft用資料。** 最新main `9b0a83cf5411a283740114170269fbf7effcdd3e` で短いbaselineを1回実行した。3,000評価Job、変更後の実RF同値性・速度比較、独立MNA、Stage C/Dは **not_run**。60秒／20秒の達成判定はできない。

## 停止理由

Issue #377は各RF forward前のsource/import同一性を明記している。しかし現行 `window100` の `ForwardJournal._save()` は窓や状態の境界で `validate_inputs()` を実行し、`begin_forward()` は既予約窓とinflightのみを検査する。`WindowJobEvaluation._assess()` は各候補の値・SPD・費用を検査するが `_contract()` は呼ばない。#369の[仕様](../issue369_forward_window.md)も入力再読込は窓境界と明示し、`test_window_meter_keeps_normal_mock_forwards_in_memory` は通常forwardで `_contract` とファイル読込を禁止する。開発 `window100` の各forward import-origin照合も確認できない。これは本Issueに書かれた前提と現行契約の相違であり、今回緩和したものではない。

各forwardの同一性確認を新設するか、現行の窓境界確認を採用するかは、安全契約と比較条件に影響する。これを暗黙に決めず、追加RF実行を停止した。前者なら実装・回帰検査・時間評価が必要、後者ならIssueの条件変更が必要。どちらも本記録で決定しない。

加えて #378 監視のlocal-run eventが0件だった。`worker.py` 内で `import json` が関数内変数となり、Hybrid callback内で未初期化参照され、その例外が監視失敗として握り潰される。科学rawに1 local runが存在するため、event件数0の `unverified` を成功とは解釈しない。対象のローカルimportを除く最小修正と**RFなし**Worker回帰を追加した。実RFでの修正後確認は未実施。

## 固定条件・費用

- RF-T008 rev3 **trial** 明示opt-in、effective SHA `e682165c72d3a8b9f1384a2529f71bacfebfc9d17164d4af5af879e4a138b532`、full_lpf、6設定28個別区間、既存S2P。formal RF-F003は不変。
- seed1002の既存25変数start SHA `6203467121a4e37baaa51c471aaecb3174f3374f9ab955d6fbf101f7b5ce935f`、search grid 70 samples SHA `6805740a36f6100d7dec3e7308924242e909255f1ea2d287b7c734c400f98f26`。Python 3.12.15、NumPy 2.5.4、SciPy 1.18.1、BLAS/OMP/MKL各1 thread。
- 実行前に凍結した最大割当はbaseline Job cap 8,000 + 変更後短計測 cap 8,000 + 3,000評価Job cap 212,000 + 他の全RFテスト・audit枠 22,000 = **250,000**。baseline Plan SHA `8ac7bab9567918ae5c656fd449807ad2c38c1e1cad9e39c8ed217b95a569043e`、source identity SHA `fcbfc45411e3502f780ed68e73920e953daf064c550d8d6e63962c14084a4adb`。静的最大予約はbaseline 7,812、未実行benchmark 211,064。preflight byte SHA `c7c6da521148418da55cd0e4e0fcaffb4fcc33e392c559cc78bc90f3f7c393d6`。
- 実費用は search `100×70=7,000`、selection `2×84=168`、terminal `476`、計 requested=completed **7,644**、reserved=unknown **0**。独立MNA/denseは0。変更後短計測・3,000評価・別RFテストは未実行。旧#361 unknown予約および#372/#375のrawを変更・相殺しない。
- 実行前sourceでの結果：nfev 100、nit 1、evaluation budget exhausted、solver未収束、exit 4。terminal有限格子 strict FAIL。科学rawの親・worker SHAはsummaryと照合した。形式的G0/G1・保存監査・物理実装性・連続帯域は未検証。

## 現行window100の短時間プロファイル

#378共通監視1秒周期、別途 `sitecustomize.py` により科学子プロセス全体を `cProfile` 計測。`--profile` のpy-spyは未インストールで統計sample取得なし。以下はcProfileの**inclusive時間**で重複を含み、トレーシングの大きなオーバーヘッドを含む；加算・無計測のforward時間への外挿はできない。Hookとpstats原本は外部保存。監視全体wall 39.461秒、プロセスCPU最終観測38.21秒（短命子欠測の可能性）、観測peak RSS 141,242,368 bytes（真のpeakではない）。local-run event欠測のためlocal wall/CPUは未取得。

| 呼出し | 回数 | inclusive秒 |
|---|---:|---:|
| window `_save`（contract・snapshot・保存を内包） | 20 | 30.316 |
| `WindowJobEvaluation.snapshot` | 20 | 18.453 |
| `plain`（再帰を含む全job） | 18,235,240 / 原始2,003,326 | 26.835 |
| `_contract`（source照合を内包） | 21 | 8.592 |
| `source_identity` | 23 | 0.514 |
| `atomic_verified`（JSON・fsync・readbackを内包） | 24 | 4.230 |
| `validate_values`（準備時を含む） | 113 | 0.378 |
| RF evaluator `evaluate` | 103 | 0.154 |
| requirements | 103 | 0.187 |
| SciPy `_dense_difference` | 4 | 3.542 |

SciPy差分の97 callbackは全100 search residual callの内数であり、line searchを含む残り3との厳密な分離や時間外挿はしていない。SPDは `validate_values` 内包、独立したwallは未計測。前回#367のlegacy保存profileと現行window100は別物。#372のseed1002 Job概算121.78秒は3,000評価／非cProfile／別HEAD・異なる局所条件で、今回の100評価Jobとは比較不能。#375の236.71秒は6,500評価Job全体でlocal-run wallではない。

本環境の別の整数演算合成負荷（各1回・0.1秒監視）は、監視なし起動wall 2.762秒、監視あり 2.663秒、py-spy試行あり 2.968秒（未インストール）。順序固定・変動を含むので、差はオーバーヘッドの因果推定でもRFへの外挿でもない。有効なpy-spyのオーバーヘッドは未検証。cProfileのオーバーヘッドも未測定。

## 候補改修と限定確認

`storage.plain` は実profileで呼出しが突出したため、JSON組込みscalarの**exact type**に限り従来と同じ値をそのまま返す短絡を追加。subclass、dataclass、NumPyなどは従来経路のまま。RF演算、窓予約、保存・fsync/readback、solver、格子、費用を変更しない。旧checkpoint payload（実rawから読取、再RFなし）を同一processで旧実装→新実装の順に4回ずつ変換：wall中央値約0.342→0.213秒、全変換byte SHA `b1b9f179c32a371b431276d8d905b944ac4109f00a61726c2cba739e79f9be92` で一致。変換単独の固定順・小標本であり、Job高速化の実証ではない。

`test_issue377_plain`、監視Worker無RF回帰、`test_issue378_monitor` 計12件、ForwardJournal/atomic失敗・境界およびmock RFの窓テスト12件PASS。修正前の監視Worker無RF回帰はevent空でRED、修正後GREEN。変更後のSパラメータ・IL/H2/H3・mandatory g・Hybrid目的・SPDの実RF比較は未実施であり、完成や科学同一性PASSを主張しない。

## 原本と保全

- Git外永続raw・監視・入力 `/home/user/issue377-rf-profile-20261110/`。マニフェストSHA `2c0b8263ad7146d0d39c9dc4d8f0fd84a4d6c7d5474272fb970ec73251f5884c`、全現存ファイルを実byte読戻し・SHA記録、manifest自身はatomic verified。外部バックアップは未検証。
- 短時間hookは `/tmp/issue377-profile-hook-1000-1484683/` にも残存（同じ内容を上記inputsに保存）。作業worktree `/home/user/src/reconfigurable-rf-lpf-issue377` はレビュー用に保持。
- 正式EXP、Main/Extension、100 restart、変更後3,000評価、アルゴリズム／勾配／restart政策変更は **not_run**。Phase 2のまま。科学的最適性・物理実装性・連続周波数保証は主張しない。

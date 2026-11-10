# Issue #381：restart生成時間とpy-spy限定検証

## 状態・境界

**未完了：共通CLIの `--monitor-dir ... --profile` による実プロファイルは取得できていない。** Linux Yamaによる同一ユーザーattach拒否のため、インストールだけを成功と扱わない。公式の子起動方式は非RF合成負荷で成功したが、共通監視への統合はしていない。以下の独立手順は終了状態や監視の契約を代替しない。ChatGPT独立レビュー待ち。

- `main` 基点 `9b0a83cf5411a283740114170269fbf7effcdd3e`。PR #380 HEAD `de8651f9455f9a60e1892c4329f7eed098c54ae5` の記録・差分を確認。#377の3,000 residual/Objective評価、60秒／stretch 20秒、`max_restarts=0` は変更も再実行もしていない。
- RF追加探索、実RF 100 restart、正式EXP、本番計算はnot_run。RF条件、solver・Job/Plan、予算・checkpoint、科学rawは変更しない。RF condition ID/SHAはこの非RF計測には適用なし。
- Hybridにopt-inの `restart_start_generated` を追加。乱数呼出しと順序は変更せず、run 0を除く。正規乱数・clipと物理開始点構築の2区間のみを加算し、event書込みは時間外。workerの `json` のローカルimportが監視callbackを壊すmain上の既知不具合はPR #380と同様に除去。イベント欠落は観測できる場合 `incomplete`、それ以外も `unverified` であり科学rawとの照合を要する。
- mock Hybrid 100 local runsで99個の生成イベントとseed/index/時間を確認し、監視有無およびcallback書込み失敗時の完全なHybrid結果が一致。イベント欠落、workerへのjob/arm/step付与、終了コード・SIGINT・保存障害は限定テストで確認。時間は測定値であり科学rawに書かれない。

## 実プロファイルと権限

環境: WSL2 Linux 6.18.58.1 x86_64、Python 3.12.15、psutil 7.2.2、`uv tool install py-spy` で別途導入した **py-spy 0.4.3**。科学本番依存には追加していない。`/proc/sys/kernel/yama/ptrace_scope=1`、同一ユーザー、sudo・恒久設定変更・権限付与なし。記録日時の共有負荷・キャッシュ・CPU周波数は非制御。

1. 共通監視の既存方式 `py-spy record --pid <CLI PID> --rate 100 --format speedscope --output ...` を同一の数秒CPU負荷で3回実行。毎回profiler exit 1、stderr `Permission Denied`、ファイル／サンプルなし。科学子は各exit 0。CLI PIDを対象にしたがattach失敗のため何もサンプリングしていない。現在の `develop` Runnerは `execute_development_job` を同一CLIプロセス内で直接呼ぶ（別Workerプロセスを起動しない）；一般に将来の子孫は既定の `--subprocesses` なしでは対象外。
2. 独立方式 `py-spy record --rate 100 --format speedscope --output ... -- <python> ...` を合成負荷で成功確認。子Python自体をサンプリング、100Hz、CPU sampling、native/idle/subprocessesなし。4秒の別負荷では子PID 10093、非空の正当なspeedscope JSON、413 samples、1 frame、py-spy exit 0。後述の再現スクリプトの3回はそれぞれ204/193/196 samples、`workload` のinclusive countは204/191/196。サンプルは統計的stack出現回数であり厳密な関数実時間ではない。
3. **終了コードの重大な違い：** 合成Pythonをそれぞれ0/2/3/4で終了させると、py-spy wrapperは全て0で終了した。wrapper exitを科学CLI exitと同一視できない。子stdoutとpy-spy自体のメッセージも混在し得る。共通監視の既存attach経路は科学子終了コードとprofiler終了コードを分離し、SIGINT転送と保存障害時の既知子exit保持を維持する。子起動方式を統合するには科学子exitの確実な別経路、SIGINT/process group、stdout/stderr、ログ障害とraw非改変を含む設計・検証が必要であり、このIssueでは複雑な管理を導入しない。

独立方式の再現（RFは実行しない）：

```sh
uv tool install py-spy  # または既存の0.4.3を使用、科学依存には追加しない
uv run --frozen python project/diagnostics/issue381/benchmark.py
# 個別確認例: PROFILE は未存在のGit外ファイル
py-spy record --rate 100 --format speedscope --output "$PROFILE" -- \
  uv run --frozen python project/diagnostics/issue381/benchmark.py --workload /tmp/issue381-workload-result.json
```

後者はuv自体を子にするとPython workloadが別プロセスになる可能性があるため、**対象を厳密に限定するには `.venv/bin/python` を直接指定**する。出力先は使い捨ての未存在ファイルに変更すること。benchmarkは `.venv` のPython実行ファイルを直接使用し、各speedcopeのsamplesとframeからinclusive countsを集計する。通常の共通監視の `profile-functions.json` の実生成はattach失敗のため未検証（mockのみ）。独立子方式での関数集計成功を共通CLIのDoD達成と混同しない。

## 非RFオーバーヘッド比較

同じ整数演算30,000,000回、各3回、条件順をrotation。監視間隔0.1秒（通常は1秒）、100Hz、全workload checksum 12285。各値は実測、統計的信頼区間ではない。最初のbaseline実行はテストと並行しており負荷差が大きい。child方式はpsutil監視を併用していないため、共通監視＋成功py-spyのオーバーヘッドを示さない。

| 条件 | 起動〜終了wall秒 各3回 | workload CPU秒 各3回 | workload ru_maxrss KiB 各3回 | profiler samples |
|---|---|---|---|---|
| 監視なし | 2.351, 1.939, 1.922 | 2.300, 1.902, 1.887 | 17112, 17556, 17556 | なし |
| psutilのみ | 2.164, 1.942, 1.938 | 2.087, 1.862, 1.896 | 17240, 17556, 17556 | なし |
| psutil＋attach試行（失敗） | 2.150, 2.007, 2.048 | 2.083, 1.935, 1.978 | 17428, 17556, 17556 | なし |
| 独立py-spy子起動（psutilなし） | 2.122, 1.982, 2.004 | 2.033, 1.891, 1.924 | 14612, 14828, 14684 | 204, 193, 196 |

起動wall中央値は順に1.939/1.942/2.048/2.004秒。監視なし中央値との差は約+0.2%/+5.6%/+3.4%だが、3回・順序・環境変動を含む記述統計であり因果的推定やRFへの外挿ではない。psutilの観測peak RSSは3回それぞれ15,138,816/15,024,128/15,077,376 bytes（psutilのみ）、15,101,952/15,134,720/14,974,976 bytes（attach試行）。workload内 `ru_maxrss` とサンプリングpeakは方法・単位が違い直接比較不可。子processのCPUはprofiler自身を含まない。共通CLIで成功したprofilingのオーバーヘッドは**未検証**。

一時観測ファイルは `/tmp/issue381-observations/` に保持：`benchmark.json` SHA256 `41fdca5c8a28a05824b05913fee532cf94feea75ca77641ee99a2667a0f514c9`、独立4秒 `child.speedscope.json` SHA256 `6f11796582f529b54d4e60f9d67316355dd42758755154ba9e4b45596b8f2aab`。これらは非RF合成診断であり永続研究rawではない。benchmark内部の一時profileは集計後に削除される。観測ファイルはGit外ローカルであり外部保存は未検証。

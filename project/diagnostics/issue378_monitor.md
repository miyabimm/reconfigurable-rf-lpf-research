# Issue #378：開発CLIの任意監視

既存 `develop` の外側から同一CLIを**一度だけ**起動する。監視なしの経路は従来どおり。これは開発実行の観測であり、正式EXP・production・科学的妥当性を承認しない。監視ディレクトリは未存在かつ既存のGit worktree外で、科学出力と別にする。親ディレクトリは事前に存在すること。`window100` の科学出力は `/tmp` 等のsystem tempを使用できない。以下は `CONFIG` と `STARTS` に既存の正当な入力、`PERSISTENT_PARENT` に事前に存在する永続的なcheckout外親ディレクトリ、`MONITOR_DIR` に別の未存在パスを設定した使用例。科学出力の `fresh-rf-output` も未存在にする。

```sh
uv run --frozen python scripts/run_rf_search.py develop \
  --config "$CONFIG" --starts "$STARTS" --storage-mode window100 \
  --output "$PERSISTENT_PARENT/fresh-rf-output" --monitor-dir "$MONITOR_DIR"
# 上記に --profile を追加すると任意の外部 py-spy (PATH上) をCLI PIDにattach。
```

監視オプションを除く引数はそのまま子CLIへ渡す。`--profile` 単独は拒否する。終了コードはprofilerではなく子CLI（通常0/2/3/4、signal終了は負のsignal番号）に由来する。SIGINTはCLI側の新規process groupへ転送して終了を待ち、再試行・再開・強制停止はしない。監視ディレクトリ作成前のエラーはCLIのexit 2。子の終了後に監視ログのflush/closeや集計・保存が失敗した場合は、可能なら親のstderrに `monitoring incomplete` と出力し、既知の子exitを保持する。summaryが欠落または不完全な場合もあるため、成功した監視と見なさない。監視ログへのstdout/stderr格納は画面への転送ではない。

## 成果物と解釈

- `process.jsonl` は約1秒間隔でmonotonic時刻、CLI PIDとその子孫ごとのuser/system CPU秒・RSSを記録する。CPU秒はOS累積値でCPU%ではない。RSS集計最大は**同時観測値の最大**で、瞬間最大ではない。重複せず子孫を列挙するが、サンプリング間に終了した短命子のCPUやRSSは欠落し得る。最後のCPUも実終了時の厳密値ではない。
- 時系列中のprogressは `run.json` のjob/seed/status/requested/completed/reservedと、存在するwindow rawの `checkpoint_number`、`confirmed`、`uncertain_upper`、`window` をそのまま読取ったもの。親の値とworker checkpointは別時点・別用途。観測時刻はmonitor側の時刻であり、checkpoint確定時刻ではない。欠測の補間や未確定forwardの確定はしない。親/worker rawと既存のatomic readbackが正本。
- `optimizer-events.jsonl` はHybridのSciPy local run開始/終了と、`run_index>=1` の `restart_start_generated`。後者は正規乱数摂動・clipと次の物理開始点構築のwall/CPUの和であり、その間の別処理やevent I/Oを含まない。run 0は凍結入力でイベントなし。seed/job/arm/step/run_indexでworker rawの既存solver結果・vectorに対応できる。wallとprocess CPU、終了時nfev/nit・success/status/messageを記録する。`success` は個々の数値solverの状態であり探索全体の終了とは別。予算切れ等はstatus null、異常割込みもendを試みるが、強制終了や記録障害時には開始のみ残り得る。イベントの記録失敗は科学処理を停止させず、イベント不在は「探索が存在しなかった」証明ではない。全固定boxはSciPyを呼ばないので対象外。
- `monitor-summary.json` は閉じた時系列・イベントの読戻しから集計する。forward/sは全jobのwindow checkpointを観測できるときの**確定済みforward数/全wall**であり、途中の速度や未確定分を推定しない。欠測はnull。局所run時間合計とプロセス全体は別。`optimizer_event_status` は読戻し失敗、start/end数の不一致、観測されたrestartのlocal startに対応する生成イベントの欠落を `incomplete`、その他を `unverified` とする。`restart_generated_count` と `restart_missing_key_count` は観測されたイベントのみの集計であり、全件欠落や生成後の中断は完全には判定できない。数が一致してもイベント書込み失敗や全件欠落を否定できず、科学rawとの完全な照合はしていない。コマンド、Plan/source SHA、exit、サンプリング間隔、欠測と制限も残す。比較には同じRF条件・入力・負荷・サンプリング・実行環境・計測成功状態が必要。
- `--profile` は追加依存にしない `py-spy record --pid ... --rate 100 --format speedscope`。既定CPU sampling、idle/native/subprocessなし。`profile.speedscope.json` と `profile-functions.json`（各functionがstackに含まれたsample数、同一stack内の再帰は1回）を保存する。これは統計的inclusive sample数であり正確な関数実行時間ではない。`profile-stderr.txt`、profiler独自exit、sample数、availableを確認する。未導入・権限拒否・空/不正出力は取得失敗として記録し、RF子CLIのexitと混同しない。nativeは未調査、権限緩和は前提としない。

科学raw・費用台帳は監視が変更しない。詳細なRF内部タイミング、性能改善、本番探索は対象外。Yama環境での実attach失敗と独立した子起動方式の制約・限定計測は [#381](issue381/README.md) を参照。

## 合成負荷の限定観測

再現: `uv run --frozen python project/diagnostics/issue378/benchmark.py`。PATHにpy-spyがあれば3条件目でattachを試す。一定回数の整数演算だけを実行し、RF/EXPを使わない。測定用ディレクトリはsystem tempで自動削除する。実行例はLinux、Python 3.12.15、psutil 7.2.2、py-spy 0.4.3、0.1秒間隔（通常の1秒より高頻度）、各条件1回。子内計測と監視による観測を区別する。

| 条件 | 子内wall秒 | 子内CPU秒 | 子内ru_maxrss KiB | 観測peak RSS bytes | 起動〜監視終了wall秒 |
|---|---:|---:|---:|---:|---:|
| 監視なし | 2.656 | 2.643 | 16040 | 未取得 | 2.680 |
| psutil | 2.860 | 2.848 | 16168 | 12607488 | 2.895 |
| psutil + py-spy試行 | 2.977 | 2.966 | 16612 | 12603392 | 3.035 |

同一checksum 12285、全子exit 0。起動wallの単純差は監視なし比で約+8.0%、profiler試行で+13.2%だが、各1回の順序固定測定で環境変動を含み、監視固有の因果的オーバーヘッド推定ではない。子内ru_maxrssとmonitorのRSS観測は取得方法・単位が異なる。py-spyはexit 1、stderr `Permission Denied`、sample数不明・取得不可だったため、**有効なプロファイリング時のオーバーヘッドと実プロファイルは未検証**。権限変更はしていない。関数sample集計はmockデータでのみ検証。

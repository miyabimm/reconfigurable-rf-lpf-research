# Issue #383：内部タイマー（開発CLI限定）

## 実行と解釈

`develop` に任意の `--timing-output <未存在のGit外JSONファイル>` を指定する。親ディレクトリは既存、科学出力とは別にする。`--monitor-dir` / `--profile` との同時使用は拒否する。`--timing-output` は既存の設定、明示starts、output、storage-modeを置換しない。

```sh
uv run --frozen python scripts/run_rf_search.py develop \
  --config "$CONFIG" --starts "$STARTS" --storage-mode window100 \
  --output "$FRESH_SCIENTIFIC_OUTPUT" --timing-output "$FRESH_EXTERNAL_JSON"
```

これは実行許可ではない。適切な既存入力・保存先・承認が必要。非RF再現テストのみなら下記の unittest と benchmark を使う。計測は同一プロセス、標準ライブラリ時計、Jobごとのメモリ内集計であり、forwardごとの診断I/O・外部監視・イベント蓄積は行わない。終了時に未存在ファイルを排他作成してJSONを一度保存する。科学raw/費用台帳が正本。保存失敗はstderrに報告し既知の終了コードを変えない。普通の例外では `incomplete` として保存を試みる。SIGKILL等はファイル欠落や途中書込みがあり得る。ファイルが存在するだけで完全としない。完了と未収束は別で、`summary.exit_code`、各Jobの `status` と科学rawを確認する。

各Jobの `plan_sha256`、`source_sha256`、solver名と区間の `count`、`wall_ns`、`mean_wall_ns`、`failed` を記録する。未実行Jobは `not_started`、呼出中例外等は `unknown`。未観測区間は欠測であり0秒・未実行の証明ではない。Hybridイベントは既存のlocal run終了／restart生成計測をインメモリ集計し、forwardイベントへは接続しない。イベントそのものの既存意味・欠測可能性は #378 / #381 のまま。全固定boxでSciPy local runは記録されない。計時器例外等の観測完全性は科学rawとの照合なしに保証されない。

**包含時間**：`total` はCLI内の入力読込から科学finalizeまで（診断JSON保存を除外）、`job_worker` はWorker全体、`solver:<step>:<solver>` はWorkerからのsolver呼出し全体。`hybrid_local_run:<step>` / `hybrid_restart_generation:<step>` はsolver内。`solver_callback` はsolverからの残差・制約呼出し（`evaluation` を含む）。`evaluation` は物理検査、RF forward、requirements、場合によりcheckpointを含む。選別・terminal・anytimeのevaluationはsolver外にもある。`window_checkpoint_save` は窓予約・照合・atomic保存/readback全体で `source_contract` を含み、evaluation外にもある。`checkpoint` とも重複する。`evaluation_initialization` はmeter生成のみ、Worker全体の初期化全てではない。各値は自己時間でなく**重複しているため合算・100%表示不可**。区間は必ずしも完全に親子分類できず、別処理も各区間に含まれる。タイマー無効時に時計取得や診断I/Oは追加しない。

## 非RF合成オーバーヘッド観測

`uv run --frozen python project/diagnostics/issue383_benchmark.py`。固定整数演算 2,000回 × 1,500 chunk = 各300万反復、各条件5回、交互順。onは1,500 region呼出し／3,000時計取得、offは0。checksumはいずれも82,384,500。全体は準備・集計を含むがプロセス起動とJSON出力は含まない。wall秒、Linux 6.18.58.1 WSL2、Python 3.12.15。共有環境・周波数・負荷は非制御。

| 条件 | 処理本体 各5回 (秒) | 本体中央値 [min,max] | 全体中央値 [min,max] |
|---|---|---|---|
| off | 0.204767, 0.181795, 0.179101, 0.185164, 0.179949 | 0.181795 [0.179101, 0.204767] | 0.181796 [0.179102, 0.204768] |
| on | 0.184956, 0.182189, 0.183653, 0.187297, 0.184127 | 0.184127 [0.182189, 0.187297] | 0.184144 [0.182200, 0.187303] |

本体中央値差 +2.332 ms（約+1.28%）、全体中央値差 +2.348 ms（約+1.29%）。ばらつきが差より大きく、因果的なオーバーヘッド推定やRFへの外挿はできない。ゼロコストとは主張しない。元の非RF JSONは `/tmp/issue383-synthetic-benchmark.json`、SHA256 `a2d33fd917243df999dcd22221345f48d78d4760658c8af3d8c3d13bd9e8e6d1`、外部バックアップ未確認。

## 限定検証と境界

- `PYTHONPATH=src:tests uv run --frozen python -m unittest discover -s tests -p 'test_issue383*.py' -v`：9件。mock RFの2 Job `window100` で計測有無のrawとforward列が一致し、Job collector非混在。mock Hybrid→SLP Workerでもraw・乱数列一致、イベントファイルなし。実Hybridの非RF関数ではrestart列・結果・回数が一致。実SLSQP/SLPの非RF関数を共通Workerラッパーで実行し結果・callback列が一致。CLI一括保存、例外、保存失敗、既存・Git内・raw内拒否を模擬確認。
- `test_issue369_forward_window.py` 9件、`test_issue319_parent_runner.py` 18件、`test_issue317_fixed_worker.py` 26件、`test_issue321_development_cli.py` 8件、`test_issue378_monitor.py` 11件、`test_issue381_profile.py` 9件（2件skip）、`test_hybrid_optimizer.py` 11件を実施。既存Worker/Runner等の回帰には小規模実RF・独立MNAが含まれ、samplesは未計測（0ではない）。新規研究Job/EXPではない。
- 実RFの3,000評価、100 restart、本番、EXP、実測性能改善・独立科学認定は **not_run**。合成計測はRF条件ID/SHA適用外。各実JobのRF同一性は科学rawで検証すること。CI、ChatGPT独立レビューは別判定。

# Issue #511 — 事前準備・実行保留（未完了）

正式EXPではない。80 Job は**未開始**、本比較の Search / Terminal / MNA 消費はすべて0。結果・最良設定・paired比較は存在しない。実行許可はユーザーの本Issue指定に含まれるが、下記の既存Runnerの停止動作と要求の衝突を解決するまで実行しない。

## 事前確認（RF forward 0）

main `22ddd2f7f90ce4e933f1d1c63bbed74baf997066` で `prepare.py` を実行。RF-T010 trial effective SHA `d50e6c9fef3e41b8258c00cbd14436a3bcb1d84444d50cf4a445ccf5d288e417`、base RF-T008 `e682165c72d3a8b9f1384a2529f71bacfebfc9d17164d4af5af879e4a138b532`。Sobol 20件を再生成し、全25変数について初期vector SHAを `issue465/paired.csv` の `new_initial_sha` と照合、一致。4 Run各20 Jobの凍結Plan、seed→arm順、物理bounds、6設定・28区間、Search 70点、Terminal 476点、固定S2P原byte SHA、MNA spot、3費目予約を確認した。予約上限は RunごとRF forward 2,000,020、RF samples 140,009,520、MNA 40（4 Run合計はその4倍）。

Plan canonical SHA（順に Run 1〜4）:

- `78a1fafb12cbcf79d7892d699703254876910901f643dd18b106bfd4f55faa57`
- `3b86e689ea4efba2870f0848f1be1f2a4f1a071d298b71b867fe81d947ccde01`
- `32328472cfa28977c4052c8dffd04af98de66bf2d413b18b48261def37c9ee5b`
- `a49df24ef8be3c5a2489a204654b45ef14d462fbbb1de536adb6dfac920b88be`

再現例（新規のsystem tmpパスを使用）:

```sh
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
 uv run --frozen python project/diagnostics/issue511/prepare.py /tmp/<fresh-issue511-preflight>
```

生成物は `/tmp/issue511-preflight-final-1795452696/`。先行版 `/tmp/issue511-preflight-1795452511/` も保持。両者は比較Run rawではなく、入力・Planを含む一時ファイルであり、永続性は保証しない。強化したS2P検査の最初の実行は、この準備スクリプト内の期待SHAの転記ミスでassert停止し、出力を作らなかった。修正後、実ファイルと登録SHAが一致した。前記の確認はIssueの全DoDや実行可否のPASSではない。

## 実行前STOP：異常時の後続Job

IssueはRF/数値例外やscientific監査異常でfail-closed、かつ20 Jobを1 Runとして既存CLIで実行することを要求し、Runner/Worker本番コード変更を対象外としている。現mainではTRF `status < 0` をWorkerが `solver_failure` に分類する一方、`_development_runner._verify_receipt` は `not_converged` を完了として受理し、その後のJobへ進む。通常の予算枯渇による数値未収束（exit 4）とは異なる。

実証：既存テストの構成を使う決定的な2 Jobテストで、TRF結果を両方 `status=-1` に置換したところ、solverは2回呼ばれ、各 `stop_reason=solver_failure` にもかかわらず親台帳は両Job `completed` / Run `completed` となった。テスト専用にSearch 2 forward・Terminal 2 forward・独立MNA 4 sampleを使用し、一時出力は削除済み。本比較の予算消費には含めない。既存 `test_issue509_trf_restart.py` の14 testsもPASS（小規模な決定的ソフトウェアテストであり、比較Runではない）。

またRunnerの `timed` 計測はJob wallを記録するが、Job全体のCPU時間は記録しない。TRF local-run別CPUは記録されるものの、その合計をJob全体CPUと同一視できない。IssueのJob別CPU要件の計測方法も決定が必要。

**要判断**：既存Runnerに異常停止とJob CPU計測を追加する別Issue/明示的なスコープ変更、または適切な別手段を提示する。正常な予算枯渇を異常扱いしないこと、4 Runの全額予約・順序・再試行禁止・科学条件は維持する。対応決定後、再度全入力とPlanをRF forward 0で照合してから開始する。未実施の80 Job、集計、科学監査、レビューを完了と扱わない。

# #447：RF-T009 G2 Worker の小規模 CPU／保存量比較（非EXP）

比較は [`run_profile_development`](../../src/lpf/search/_development_runner.py) 1 Job の plain 呼び出し。変更前は `893bb041ddecf3917382a03d5c7167b23f1195b1`、変更後は `b43a485804bc4a165b49c67d0db2cbe5d3213868`。どちらも測定対象ソースに未コミット差分なし。別プロセスで旧→新、新→旧を交互に実行。各版の最初の1回をウォームアップとして除き、各6回を集計。AMD Ryzen 7 PRO 4750G (x86_64)、Python 3.12.15、NumPy 2.5.4、SciPy 1.18.1。OPENBLAS/OMP/MKL の各スレッド数は1。時間は Python `process_time`（子プロセスのCPU時間を含まない）と `perf_counter`。Plan・fixture準備と出力検査／削除は計時外。RF、source照合、保存・readbackは計時内。保存量は一時出力の全 JSON の実byte合計で、ファイルシステムの物理I/O量・遅延ではない。

| 指標 | 変更前 | 変更後 |
|---|---:|---:|
| CPU秒（中央値、最小–最大） | 0.342 (0.331–0.437) | 0.507 (0.472–0.526) |
| wall秒（中央値、最小–最大） | 0.446 (0.424–0.546) | 0.619 (0.578–0.637) |
| JSON 実byte／ファイル数 | 202,542／9 | 151,003／10 |

変更後は約25%小さく、CPU・wall はこのfixtureで増加。監査深度が異なり、追加のsource/RF同一性確認、forwardの物理・電力検査、原byte照合などを含む。各内訳の時間は測定していない。大きな予算／格子に外挿しない。

## 条件と照合

- RF-T009 trial 実効SHA `d1ebefaf4cb6735898467b9c2affcc57b9590d4a6c9f53a0dd84d1f1f2f8b18d`、物理ベースRF-F003 `e12c42b11d12db7f20983c48cfa441ea96e362e533450d5862aa8a271c82af86`。bands／S2Pは[プロファイル文書](../minimax_profile.md)と同じ固定入力。
- [`test_profile_worker_multistep_passes_only_final_x`](../../tests/test_issue450_minimax.py) と同じ `make('RF-F003')` fixture・config・seed 23。`demo` の `step0` SLSQP/sum、`step1` SLP/signed_max、`step2` Hybrid/sum。格子は区間あたり順に2/3/4点、Terminalは5点。各stepの予算2、SLSQP/SLP `max_iterations=1`、他の設定は固定既定値。物理 box 全体、checkpoint間隔1、Terminal spotは index 0。各版で1 Job を新規出力先に実行。
- config SHA: `64f136c8cfdcc467ae6c8e1f0c6d610ae692305e9291595af611f9be2935fae4`。初期vector SHA: `8219198da8b3b7da872cfbdbcc8af54a463e97c0cd58123985cf55e377d82085`。同一configだが、旧性能ruleをgridの凍結に含めなくなったため Plan SHA は変更前 `b3498e337426d42f9e1e82eb1a800719419993a556a093303c0109ca9055043d`、変更後 `21030e94305c3fd4a620fe76783e58386ad80f896776211d50e58ef6dafccc12`。Search／Terminalの各格子SHAは両版一致。
- 各 Job は Search 6 forwards / 504 RF samples、Terminal 1 forward / 140 RF samples、独立MNA 1 spot。`steps` の各 `solver_result`、`costs`、Terminalの `vector_sha256`／`response`／`terminal_signed_max_margin_db`／`performance_feasible` をcanonical JSONで比較し、全回一致（SHA `9b59177873391411c982ea9a7927a9e2776dd722a73dac899b9010288171dbe1`）。監査深度・raw書式まで同じという意味ではない。正式EXP・G0予約・正式Campaignの実行なし。

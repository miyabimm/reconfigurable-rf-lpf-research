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

## 追加レビュー対応後の再測定（非EXP）

上記と同じfixture・config・seed・grid・checkpoint間隔・Terminal spot・RF fingerprints、同じCPU/Python/NumPy/SciPy/スレッド条件。ソース差分なしで `893bb041`（#452直後のmain）、`a2764171`（旧レビューHEAD）、`877026f9`（修正後）を比較。mainとPR間は上記の通りPlan SHAが異なり、PRの修正前後は同一。各版1回の独立プロセスを1組として `main → 旧レビュー → 修正後` と逆順を交互に計7組。初回をウォームアップとして除き各6組を集計した。Jobは毎回新規出力のplain `run_profile_development()` 呼び出しで、上記と同じ計時境界（PythonプロセスCPU時間にはGit子プロセスのCPUを含まない）。

| 指標（中央値、最小–最大） | #452直後 main | 旧レビューHEAD | 修正後 |
|---|---:|---:|---:|
| Search forward単体 CPU µs/forward | 648 (633–757) | 1,850 (1,787–1,982) | 516 (514–589) |
| Job CPU 秒 | 0.358 (0.350–0.370) | 0.485 (0.480–0.500) | 0.303 (0.299–0.311) |
| Job wall 秒 | 0.459 (0.450–0.473) | 0.620 (0.614–0.638) | 0.379 (0.373–0.392) |
| Job JSON 実byte／ファイル数 | 202,542／9 | 151,003／10 | 151,003／10 |

- **Search forward単体**: 各プロセスのJob測定後に別Workerを生成し、`demo/step0`（56 samples）のEvaluatorを事前構築、同一初期vectorで10回ウォームアップ後に300回ループを一括で `process_time` 計時した。カウンタは毎回リセットし、mainでは `_activate('demo/step0')` 後にSearch中の `_evaluate(x)`（旧profile格子判定を含む）、PRでは `_forward(evaluator, x, 'demo/step0')` を呼んだ。Solver、目的値通知、checkpoint I/O、格子構築は計時外。旧レビューHEADではbox・全物理・詳細電力を含むが、修正後はSearchで行わず、Optimizer boundsとRF CoreのSPD・数値異常検査に依存する。Search独立MNAはいずれも指定なし。従って表は実行経路の比較であり、同一監査深度でのRF Core単体高速化の測定ではない。
- **数値・費用照合**: 全21 Jobで3 stepの `solver_result` 全体、Terminalの最終vector SHA・全S/IL/APL/両RL/格子・最大マージン・適合判定、費用が完全一致（canonical SHA `8f045be45d4957946c0af86b896230d44afe8274be6411bb2968ca26bdc1ebc2`）。main rawにない各点マージンは保存済みILと同じ閾値から復元し、PR両版のrawと一致（SHA `549f7ab2ff6b29e52f20e1859f70507acda905464bef5a41392c2dab23842f93`）。Search 6 forwards / 504 samples、Terminal 1候補・1 forward / 140 samples、独立MNAはTerminal 1 spot。単体Search forwardの全Sと4応答指標も完全一致。Terminalの詳細電力検証はPR両版で有効（mainはspot電力照合のみ）。
- 小規模fixtureでは修正後の単体forward・Jobとも短縮した。検証配置・保存内容が異なり、大きな格子や予算への外挿はしない。入口／出口照合は実行中の変更が出口前に復元された場合の検出を保証しない。正式EXP・G0予約・正式Campaign・RF条件変更なし。

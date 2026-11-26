# #521 C+D1 採用候補のdeep原因調査（独立レビュー待ち）

## 結論と採否

**C+D1は指示に従いPR上に再適用した候補であり、採用・マージの承認ではない。** 約6秒のCLI差をそのままC/D式の普遍的な高速化とすることはできない。このWSL2環境では、baselineでminor page faultとsystem CPUが著増する現象が観測され、glibc allocatorの診断設定を変えるとその現象と大半の時間差が同時に消えた。既定設定差とallocator挙動の強い関連を示すが、具体的なallocation/freeの因果機構、他のlibc・ホストでの再現性は未証明。**運用環境のallocator設定変更を推奨・実施したわけではない。** 固定vector単体・allocator条件を揃えたCLIではC+D1の効果はずっと小さい。

既存の20 seedは全条件未収束で、Terminal品質の大幅改善と悪化が混在、統計的同等性は未証明。先行比較の[品質・制約](cli_report.md)と[数値上の留保](report.md)は変わらない。時間近似6800予算も環境依存であり、採否の根拠は同一forward比較を中心にすべき。独立レビュー・採否判断と最終CIを待ち、mainへマージしない。

## 固定対象と方法

- 計時実装を揃えたbaseline `ea01eb9eb530ef11a82609414696c7f08305d4e8`（永続参照 `origin/issue-521-timing-base`）、C+D1 `e08c8097587d51e2036ead09f2816d5e9a1e2113`。計時以外の実装差は `model.py` のC/D式とその例外処理・対応テスト。#519 A+B、forward、4複素S感度、固定gridとRunner契約を維持。計時commit前の比較対象はbaseline `7957fd60`、C+D1 `4d3def8f`。先行計時版 `77c8fc5c` / `e5513a42` でも同様の診断を実施。
- 各固定commitの清潔なworktreeから標準 `scripts/run_rf_search.py develop` を直接起動。trial RF-T010 effective SHA `d50e6c9fef3e41b8258c00cbd14436a3bcb1d84444d50cf4a445ccf5d288e417`、固定5000 forward、28別区間、6設定、Search 70 / Terminal 476点、TRF exact、terminal MNA 2点。入力manifest SHA `b1aecd560566cf57364c73fffc43d85a03af4ea08386a79e958170f06edd8db4`。Plan/source SHA・各runの選択vector、checkpoint、計時region、個別時刻とCPU状況は [`deep_results_final.json`](deep_results_final.json)。旧計時版は [`deep_results.json`](deep_results.json)。
- 代表seed 1001/1010/1020 × 3 cycle × 2版 × plain/deep、加えて1001各版・各modeのwarmup 4 job。順序はseed/cycleごとに反転し各1 jobずつ実行。Python 3.12.15、NumPy 2.5.4、SciPy 1.18.1、WSL2/glibc 2.39、Ryzen 7 PRO 4750G、CPU affinity `[0]`、OpenBLAS/OMP/MKL各1。CPU周波数・温度はWSLから取得不可、host負荷やスケジューリングは制御不能。結果は有限の観測。
- plain/deepは各版・各seedで科学的結果（wall/cpuフィールドを除いたresult）、checkpoint全ファイルSHA、消費・停止・選択vectorが反復間も一致。各jobはRF 5001 forward / 350476 samples（5000 search + terminal）、MNA 2点、予算停止、terminal MNA pass。旧20 seedの元結果とも各seed/版のstep・terminalが一致。異なる版間では探索軌跡・restart数・選択結果は異なり得る。
- 追加の別process非計時トレースでWorker入力5000個の生byte列・順序のSHAが各版/seedでplain=deep。`sys.setprofile`は**この別実行のみ**で、計時対象では未使用。CPU状態・計器の摂動を排除した証明ではないが、計時modeによる探索差は検出されなかった。
- 現在のdeepはRF内forward/感度、旧C/Dのprepare/solve/reshape、新C/Dのprepare/product、前後cascade、node Jacobian、TRF/Worker各区間を計測。各親はinclusive。内訳は重複しない直接子の和を親から引き、`other`を負値も含めそのまま保存。cascadeのfirst/secondは既存cascade全体regionの外側を測るため、既存regionと足してはならない。meanはそのregionの`wall_ns/count`。plainでは新規deep時計を呼ばないことをテスト。deep観測に計時overheadが含まれるためplain差にdeep内訳を加算しない。

## 結果：plainとdeep

全9計測runの中央値［min, max］秒。CPUは子process user+system。計時付きとplainを混ぜない。

| 条件 | plain wall | plain CPU | deep wall | deep CPU |
|---|---:|---:|---:|---:|
| baseline | 22.830 [22.266,23.334] | 22.721 | 24.020 [18.587,24.619] | 23.897 |
| C+D1 | 16.916 [16.758,17.396] | 16.784 | 17.920 [17.709,18.209] | 17.803 |

baseline deepの18.587秒は除外していない。計器の影響・allocatorの非決定性を含めて評価する必要がある。各regionの秒数・count・平均は上記JSONに全run分保存。代表的な全9 deep run中央値（秒、全て5000呼出）は次の通り。行は包含関係があるため合算不可。

| region | baseline 合計 / ms/回 | C+D1 合計 / ms/回 |
|---|---:|---:|
| RF評価全体 | 19.428 / 3.886 | 13.504 / 2.701 |
| 旧/新 Y→S 全体 | 1.827 / 0.365 | 1.721 / 0.344 |
| 　prepare | 1.019 / 0.204 | 0.030 / 0.006 |
| 　旧 solve / reshape | 0.785 / 0.157、0.008 / 0.0016 | — |
| 　新 product | — | 1.678 / 0.336 |
| 旧/新 電力波 全体 | 3.685 / 0.737 | 1.902 / 0.380 |
| 　prepare | 2.894 / 0.579 | 0.220 / 0.044 |
| 　旧 solve / reshape | 0.752 / 0.150、0.006 / 0.0013 | — |
| 　新 product | — | 1.668 / 0.334 |
| **未変更** node Jacobian expand | 2.402 / 0.480 | 0.832 / 0.166 |
| **未変更** 感度reorder | 1.148 / 0.230 | 0.287 / 0.057 |

例としてseed1001/cycle0 deepではbaseline→候補のCLI 23.601→17.709秒、search 22.721→16.766秒、RF 19.159→13.406秒。RF差-5.753秒の直接子には、電力波-1.750秒、node Jacobian全体-1.652秒、感度reorder-0.828秒、cascade Jacobian-0.353秒、Y→S -0.100秒が含まれる。RF未分類は1.257→0.418秒。未変更の処理にも大差があり、C/Dの式削減時間だけでは説明できない。

同seedでTRF `least_squares`は22.692→16.738秒、そのうち全`calc`は20.446→14.539秒。差引き2.246→2.198秒はSciPy内部・callback外の包括残差で、SVD等の個別内訳は未測定。9 runでSciPy残差はparentのbaseline中央値10.36%、候補13.26%。solver親では`trf/local`等を引いた純other中央値は両版0.01%以下、search純otherは0.1%未満。RF評価の純otherは中央値6.56% / 3.15%、node Jacobian内は1.67% / 2.21%、TRF calc内は0.35% / 0.47%。これらは測定・Python実行・allocator等を含む残差であり、すべてが特定されたとは主張しない。

## 固定vector・allocator診断

同一9固定vector（3 seedそれぞれ初期・3000・5000 checkpoint）を各版で1 processごと40回plain + 40回deep、各版3 process、CPU affinity等は同じ。各vector/process内のplain中央値のさらに中央値はbaseline **2.528 ms**、C+D1 **2.425 ms**（約0.104 ms/回、5000回換算約0.52秒）。全27中央値の範囲は2.491–4.377 / 2.380–3.714 ms。deep計時の電力波平均中央値は0.463→0.375 ms/回、node expandは0.155→0.158 ms/回、reorderは0.056→0.060 ms/回。固定vector replayは連続同一入力であり、実探索のallocator履歴・軌跡や時間差を再現するものではない。

seed1001 plain、各regime 2回ずつ交互実行し、`/usr/bin/time`で測定：

| allocator環境 | baseline wall / system CPU / minor fault | C+D1 wall / system CPU / minor fault |
|---|---:|---:|
| 既定 | 22.58–22.88 s / 4.39–4.43 s / 約218万 | 16.62–16.89 s / 0.16–0.20 s / 約2.2万 |
| `MALLOC_MMAP_THRESHOLD_=16777216` と `MALLOC_TRIM_THRESHOLD_=2147483647` | 17.64–17.67 s / 0.12–0.20 s / 約2.1万 | 16.76–16.90 s / 0.16–0.17 s / 約2.1万 |

単独設定も実施しJSONに保存。threshold単独で両版が遅くなり、trim単独では候補で約88万faultを観測、したがって「trimだけが原因」とは言えない。両設定は診断介入で、RSS、allocator挙動や他環境に副作用があり得る。いずれも各版内の結果・checkpointは既定実行と一致。

両設定下の別deep（3 seed、各版1回）ではRF中央値14.146→13.378秒、電力波2.445→1.909秒、Y→S 1.768→1.717秒。未変更node expandは0.833→0.813秒、reorderは0.281→0.279秒。seed1001の対応値ではRF 14.081→13.376秒（-0.705）、そのうち電力波-0.492、Y→S -0.013、node Jacobian -0.072、cascade Jacobian -0.069秒；純RF other差は丸めて0秒。solver 17.430→16.696秒（-0.734）、SciPy callback外残差2.176→2.169秒。各版の軌跡は異なり（njev 4095 / 4198、restart 3 / 9）、この1組を独立した因果推定や一般性能保証とはしない。allocator条件を揃えて初めて、電力波由来の差が固定vector replayと概ね同規模になる。

## 実施、再現、保存

```sh
# 指定commitのworktreeを /tmp/issue521-deep-base, /tmp/issue521-deep-cd1 に用意。
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1
PY="$PWD/.venv/bin/python"
"$PY" project/diagnostics/issue521/deep_cli.py /tmp/NEW/compare-v2 --python "$PY" --inputs /tmp/issue521-cli-data/inputs-5000-v2
"$PY" project/diagnostics/issue521/input_trace_cli.py /tmp/NEW/trace-v3 "$PY" /tmp/issue521-cli-data/inputs-5000-v2
"$PY" project/diagnostics/issue521/allocator_cli.py /tmp/NEW/allocator-v2 "$PY" /tmp/issue521-cli-data/inputs-5000-v2
# deep_replay.pyは各worktreeからCPU affinity 0で起動、各3 process。
# 上記の両allocator設定を環境変数に与え、各seed/版の標準CLIをdeepで各1回起動。
"$PY" project/diagnostics/issue521/analyze_deep.py /tmp/NEW /tmp/NEW/summary.json 2
```

前提worktreeのpathはスクリプト定数。固定入力の再生成は[先行report](cli_report.md)を参照。`analyze_deep.py`は各CLI receiptファイルのSHA/size、RF消費・MNA、版/seed内の結果・checkpoint一致とtrace SHAを検査し、非重複regionの残差を計算する。絶対pathや時刻・数値は再実行で変わる。現行計時版の主要74 CLI jobは合計RF 370074 forward / 25935224 samples、MNA 148点。固定replayは6 process × 9 vector ×（warmup 3 + plain 40 + deep 40）=4482評価 / 313740 samples。前計時版でも同じ規模の主比較、trace、allocator、controlled deepおよびreplayを実施。事前preflight、追加resource診断と単体テストは別。すべて開発診断で正式EXPは0。

- raw、checkpoint、計時JSON・stderr・resourceログは `/tmp/issue521-deep-data/`、入力は `/tmp/issue521-cli-data/inputs-5000-v2` に保留。圧縮集計には各計測runのregion/call/failure、result/checkpoint・timing SHA、replay、allocator情報を含むがrawの代替となる完全アーカイブではない。
- 作成したworktree `/tmp/issue521-deep-base`、`/tmp/issue521-deep-cd1` は比較用に保留。先行比較の `/tmp/issue521-cli-base`、`/tmp/issue521-cli-d1`、`/tmp/issue521-cli-cd1`、raw `/tmp/issue521-cli-data/` も保留。未整理の診断や証拠を自動削除しない。
- 候補・baseline双方で#499、#519、#503、候補で#521を実行し成功。final commitの通常CI相当・保存監査とGitHub Actionsの結果はPRコメントで別途報告する。前回HEADのCI成功を再適用後の成功として扱わない。

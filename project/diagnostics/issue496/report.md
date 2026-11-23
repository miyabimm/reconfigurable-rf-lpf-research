# Issue #496 案B単独評価

**結論：現時点では高速化目的での採用を推奨しない。** 再測定では70要素のmicro中央値に改善を観測したが、100k plainでは組ごとのばらつきに対して全体改善が明確でない。差がないと証明したわけではない。これは正式EXPでなく開発性能診断。Draft PRは比較・独立レビュー用であり、マージ推奨ではない。

## 再測定（2026-11-23）

前回と**同じclean実装HEAD** A `c3891f019898b203deee3050f2481c7cbd7655c9`、B `7ccc26b96d850c88fbdf59d20d9d2a4786668f85`、同じRF条件・Plan・Python/NumPy/SciPy・1 thread設定。CPU 8にaffinity指定、同一の312 forward warmupと `A B / B A / A B` のセットを**2回**、各回別のtrace A/B。合計plain各6回を全掲載し、前回結果とも混ぜず保存。全runは独立プロセスであり、前後の `/proc/stat`、CPU pressure、cgroup CPU統計を新たに取得。CPU 8のsiblingはCPU 9。仮想LinuxでのCPU 9のbusyは各plainで0〜2 tick（100 tick/秒）だが、ホスト側の競合は不可視。CPU周波数・governorはWSLから取得できず制御もしていない。実thread数未確認。BLAS等の環境指定のみ1。測定者自身はCPU 8に固定せず子プロセスだけ固定、スナップショットは子の前後でありplain Runner計測区間外。rawと全値・環境・各検証は [repeat1 JSON](repeat1_measurements.json)、[repeat2 JSON](repeat2_measurements.json)。

| セット・組（順序） | A Runner秒 | B Runner秒 | B−A秒 |
|---|---:|---:|---:|
| 1-1 (A→B) | 22.2229 | 22.1791 | -0.0438 |
| 1-2 (B→A) | 22.3767 | 21.5695 | -0.8072 |
| 1-3 (A→B) | 20.4899 | 19.9352 | -0.5548 |
| 2-1 (A→B) | 19.9616 | 20.2646 | +0.3031 |
| 2-2 (B→A) | 20.0845 | 20.0650 | -0.0194 |
| 2-3 (A→B) | 19.9203 | 19.9959 | +0.0756 |

各6回のA中央値20.2872秒（範囲19.9203–22.3767）、B中央値20.1648秒（19.9352–22.1791）。組ごとのB−Aの平均-0.1744秒、中央値-0.0316秒、標本SD 0.4187秒。セット1では順序とともに短縮、セット2は約20秒で安定したが差の符号が混在。セット1のCPU 8 `iowait` tickは各run 205→197→148→141→51→38と減少し、セット2は37〜39。これはLinux側の観測であり原因の確定ではない。測定条件に時間的ドリフトがあるため各セット・全runを残し、平均速度差を改善の証拠とはしない。process CPU時間、loadavg、全CPU tickはJSON参照。頻度未固定・外乱・6組という限定下で、plainの全体改善は判断不能。

同じCPU 8で関数単体も2セット実施（各長さ・各方式30000回×7、交互順、1000回warmup）。70要素の中央値はセット1 A 2552.4→B 2425.6 ns（約5.0%）、セット2 A 2530.8→B 2423.7 ns（約4.2%）。それぞれrangeはA 2512.1–3568.2／B 2395.0–2540.9 ns、A 2513.5–2561.8／B 2400.1–2864.3 nsで重複。micro上の傾向は改善方向だが外れ値もあり、全Runnerにその比率を適用できない。8・1024要素を含む全測定と順序はJSON。

両セットそれぞれ全10 runについてreceipt・Plan SHA、source以外のresult全体・99 checkpointを検証。初回と再測定2セットのA result・checkpointはsourceも含め完全一致。別trace replay各A/Bの100022候補vector/目的値順序SHAは初回と同じ `becf8d2705f0f2def10d356645dc4aa924401ef98f63c9dc29cff060be0cb448`、cache countersも一致。全Terminal応答・6設定・L SPD・格子受動性/電力保存・MNA 2 spotも前回同様。plain run自体の全候補列は保存せず別replayで確認。Search 100022／7001540 samples、Terminal 1／476、MNA 2、予算停止・未収束。非正式診断かつ有限格子で、連続周波数・実測・物理実装性等の保証はない。

再現コマンドは下記と同じで、計測CPUを例えば `ISSUE496_CPU=8` で明示し、microは `taskset -c 8` で起動。測定中のsnapshotは [measure.py](measure.py) が保存する。今回のrawは `/tmp/lpf-issue496-repeat1/`、`/tmp/lpf-issue496-repeat2/` に保持（system tmpは永続保証なし）。

## 初回の比較条件・再現

- A基準main `c3891f019898b203deee3050f2481c7cbd7655c9`、B計測時clean実装HEAD `7ccc26b96d850c88fbdf59d20d9d2a4786668f85`。source manifest内のファイル差は `src/lpf/optimizers/_objectives.py` のみ。後続コミットは診断成果物のみ。案A #495は含めない。A/B source SHAはそれぞれ `7877c63887611cf7bf688f48475d2260d8938790799d5777b5a893441e98114e` / `f543c0ea61a9eaeb3488fe571333ffbd93ed339f0fe12e6d393583fdb7ffcab7`。
- WSL2 Linux 6.18.58.1、Ryzen 7 PRO 4750G、Python 3.12.15、NumPy 2.5.4、SciPy 1.18.1。独立プロセスをCPU 0に固定、OPENBLAS/OMP/MKL各1 thread指定。実thread数とCPU周波数は未確認。開始時loadavg 0.92/0.61/0.33、終了ごとの値はJSON。ホスト負荷・競合を制御できていない。
- RF-T010 trial effective SHA `d50e6c9fef3e41b8258c00cbd14436a3bcb1d84444d50cf4a445ccf5d288e417`、seed 1013、4L2C・25変数・6設定、Hybrid L-BFGS-B sum、batch+partial FD、cache `lk`、Search 70、Terminal 476、MNA [0,111]、checkpoint 1000、名目100000 Search forwards。
- Plan SHA `0e2d62841f286281eb9b2c662382a50238f865193b16eafabf6aa3227ba18d90`、raw Plan SHA `360989f8f2a09626bc314de420254dca1b4f8733ef41218f14e6e0df505c69cc`、初期vector SHA `6e06d271e0ea54eecb547cfff045a6edda4850bfaa1f9c23bf9f3037ab867131`、Search grid SHA `6805740a36f6100d7dec3e7308924242e909255f1ea2d287b7c734c400f98f26`、Terminal grid SHA `28ee5b630e4842b183a7c36fd610cc32e2509c0044c6a5848ce2fbd147a22e29`。bands・固定S2P・source全ファイルのSHA等は [measurements.json](measurements.json)。
- [measure.py](measure.py) は既存 `issue487/measure.py` のplain child、`issue491/cache_replay.py` の別trace childを使用。各312 forward warmup後に `A B / B A / A B`、さらに時間評価に使わないtrace A/B。全run fresh output・除外なし。[analyze.py](analyze.py) はreceipt/Planと各result・checkpointを検証。[micro.py](micro.py) は別CPU 15でclean両HEADの実関数を読み、固定seed・8/70/1024要素・無重み・各30000回×7、順序交互、1000回warmup。各値はJSON。
- 例：同一Python環境で `python project/diagnostics/issue496/measure.py BASELINE_WORKTREE CANDIDATE_WORKTREE NEW_OUTPUT_DIR`、`python project/diagnostics/issue496/micro.py BASELINE_WORKTREE CANDIDATE_WORKTREE > NEW_OUTPUT_DIR/micro.json`、`python project/diagnostics/issue496/analyze.py NEW_OUTPUT_DIR > summary.json`。測定には両worktree cleanと比較対象HEADの固定が必要。候補は実装HEADをcheckoutする。

## plain時間（秒）

| 順 | A | B |
|---|---:|---:|
| 1 A→B | 25.0204 | 42.5254 |
| 2 B→A | 42.3542 | 42.2535 |
| 3 A→B | 42.5077 | 42.5182 |
| 中央値 | 42.3542 | 42.5182 |
| 範囲 | 25.0204–42.5077 | 42.2535–42.5254 |

1-Aはprocess CPU 20.82秒／wall 25.52秒、それ以降はCPU約21.5秒／wall約43秒。並行負荷の影響が強く疑われるが原因は未特定。測定全体で15秒以上の時間変動があり、微小な寄与の判定はできない。都合のよいrunの除外や速度比の主張はしない。trace付きは時間比較に使わない。

micro中央値（ns/call、A→B）は8要素 2980.8→2781.6、70要素 2673.5→2767.0、1024要素 3840.6→3654.3。全ケースでレンジ重複、ばらつきが大きく、70では改善を観測していない。microは配列を固定した関数呼出の比較で全体性能を示さない。

## 数値・RF検証

全10 runのreceipt各ファイルSHA/size、Plan SHAを検証。各予算群内で、source identityを除いたresult全体と99 checkpoint全内容がA/B一致（各checkpointのsource SHAのみ除外）。Terminal全S/IL/APL/両RL各476点有限かつ同一、6設定、成分条件、L行列SPD、Terminal格子の受動性・電力保存、独立MNA [0,111] pass。別trace replayの100022候補全vector/目的値の順序付きbinary64 SHAは両者 `becf8d2705f0f2def10d356645dc4aa924401ef98f63c9dc29cff060be0cb448`。別replayのcache countersも一致（lookup 100022、hit 73102、miss 26920、computed samples 4308640）。plain各runの全候補は保存しておらず、候補列比較は別replayである。

Search 100022 forward／7001540 requested samples、Terminal 1 forward／476、MNA 2。group完了による名目超過22、`evaluation_budget_exhausted`、**未収束**。Terminal signed max margin 0.747758285 dB。有限格子での観測でありRF適合、連続周波数、SRF、Q(f)、EM、公差、実測、物理実装性の保証ではない。

## ソフトウェア確認・保管

分離B worktreeで `test_optimizer_objectives.py` 9、`test_hybrid_optimizer.py` 14、`test_generic_slsqp.py` 8、`test_slsqp_budget.py` 14、`test_slp.py` 13、`test_issue441_hybrid_restarts.py` 4、`test_issue482_batch_fd.py` 8、`test_issue484_partial_fd.py` 9、計79件PASS。旧式とbit単位の比較、非有限・overflow・underflow raise、重み0、入力不変・非共有、既存solver停止分類を含む。正常値、signed zero、readonly strided配列も確認。

raw run/receipt/checkpoint/logは `/tmp/lpf-issue496-ab/` に保持（system tmpのため永続保証なし、削除していない）。基準および候補worktreeは作業時 `/tmp/lpf-issue496-baseline`、`/tmp/lpf-issue496-candidate`。正式EXPではない。独立レビューと採否判断待ち。

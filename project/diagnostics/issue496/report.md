# Issue #496 案B単独評価

**結論：現時点では高速化目的での採用を推奨しない。** 70要素のmicro中央値は旧2,673.5 ns、新2,767.0 ns（約3.5%遅い）がレンジは重複。100k plainも外乱が非常に大きく、改善を判定できない。差がないと証明したわけではなく、再測定するならCPU競合と周波数を管理する。これは正式EXPでなく開発性能診断。Draft PRは比較・独立レビュー用であり、マージ推奨ではない。

## 比較条件・再現

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

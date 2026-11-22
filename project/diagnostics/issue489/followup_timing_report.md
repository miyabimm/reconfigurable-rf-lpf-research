# #489 実装後：次の高速化対象を分類する deep 内訳

本測定は正式EXPではなく、同一条件の性能診断。測定HEAD `f96f5fbbdfe9ffb68bd95bf3759b3ebf27ce1c57`、source identity `0c0ab2d37328a79940f6c75b2bdabe07f27fa16116a2644cf6d99e86905dd939`、実行時clean。PR #490の実装を含むがmainへのマージ・独立レビューを意味しない。[#489 A/B報告](report.md)とは別時刻・別測定であり、直接A/Bとして両者の絶対秒数を比較しない。全run・全timing行・照合結果は [followup_timing_measurements.json](followup_timing_measurements.json)。

## 条件と再現

RF-T010 **trial** effective SHA `d50e6c9fef3e41b8258c00cbd14436a3bcb1d84444d50cf4a445ccf5d288e417`、物理RF-T008 rev3 SHA `e682165c72d3a8b9f1384a2529f71bacfebfc9d17164d4af5af879e4a138b532`。固定C条件：seed 1013、4L2C・25変数・6設定・28分離区間、Hybrid/L-BFGS-B sum、sigma 0.1、batch+partial FD、`rf_cache_mode=lk`、Search 70点、Terminal 476点、MNA `[0,111]`、checkpoint 1000、名目100000 Search forwards。Plan `0e2d62841f286281eb9b2c662382a50238f865193b16eafabf6aa3227ba18d90`、initial vector `6e06d271e0ea54eecb547cfff045a6edda4850bfaa1f9c23bf9f3037ab867131`、Search grid `6805740a36f6100d7dec3e7308924242e909255f1ea2d287b7c734c400f98f26`、Terminal grid `28ee5b630e4842b183a7c36fd610cc32e2509c0044c6a5848ce2fbd147a22e29`。bands・両S2PのSHAは[条件報告](report.md)を参照。

WSL2 Linux 6.18.58.1、Ryzen 7 PRO 4750G、CPU affinity 0、Python 3.12.15、NumPy 2.5.4、SciPy 1.18.1、OpenBLAS/OMP/MKL各1 thread指定。実thread数・周波数・ホスト負荷は未確認。各モード312 forwardの独立プロセスwarmupを除外し、`plain,timed,deep` / `timed,deep,plain` / `deep,plain,timed`、別途plain/deep trace replay。失敗・外れ値の恣意的除外なし。

```sh
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  uv run --frozen python project/diagnostics/issue487/measure.py /tmp/UNUSED-100K
uv run --frozen python project/diagnostics/issue487/analyze.py /tmp/UNUSED-100K > summary.json
```

raw・receipt・checkpoint・全diagnosticは `/tmp/lpf-issue489-followup-timing-f96f5fbb/` に保持。system tmpのため永続保証はない。上記JSONは集計と全timing行をGitに記録しているが、raw全体の永続保存ではない。

## 計時負荷と全run

| 順序 | run | Runner wall s | process wall s | CPU s | max RSS KiB |
|---:|---|---:|---:|---:|---:|
| 1 | 1-plain | 20.036419 | 20.437756 | 19.470557 | 93608 |
| 2 | 1-timed | 20.047049 | 20.442669 | 19.482580 | 93392 |
| 3 | 1-deep | 20.813211 | 21.215532 | 20.221753 | 93504 |
| 4 | 2-timed | 20.082775 | 20.482882 | 19.511740 | 93176 |
| 5 | 2-deep | 20.737132 | 21.130646 | 20.137496 | 93624 |
| 6 | 2-plain | 20.051562 | 20.446637 | 19.350267 | 93344 |
| 7 | 3-deep | 21.164300 | 21.637773 | 20.643106 | 93532 |
| 8 | 3-plain | 19.848959 | 20.392844 | 19.428781 | 93596 |
| 9 | 3-timed | 20.303378 | 20.731451 | 19.771895 | 93316 |

Runner中央値（範囲、標本SD）はplain 20.036419秒（19.848959–20.051562、0.112856）、timed 20.082775秒（20.047049–20.303378、0.138833）、deep 20.813211秒（20.737132–21.164300、0.227861）。deep中央値はplain比+3.88%。計器負荷と順序・OSばらつきは分離できない。**deep区間をplainの確定秒数に転用しない。**

## 全体構造（1-deep、inclusive）

Runner 20.813211秒はJob 20.677932秒を含み、その差0.135279秒はrunner側残余。JobはSearch 20.323888秒を含み、差0.354044秒はTerminal・worker等（Terminal RFのみ0.004840秒）。Searchはsolver 20.301267秒とsetup 0.021745秒等を含む。solverは RF評価13.281841秒、checkpoint 1.006160秒（99回）、mask 0.355960秒のほか、**未分解残余5.657306秒**を含む。同残余は2/3-deepでも5.636783/5.748660秒。

この残余は目的値・残差集計、callback、予算管理、SciPy、Python等の混合であり、**SciPy単体でも全量削減可能な時間でもない**。RF評価7694回はscalar 3847回とbatch入口3847回。内側batch 10.657090秒を引いた2.624751秒はscalar RFとbatch入口検証・wrapper等を含み、純scalar時間ではない。

## batch主要区間（秒）

3847 batch、batch内96175候補＋scalar 3847候補＝100022。以下7区間は同じbatch内の主要部分で、最後の残余は `batch − 7区間の和`。子のdecode/matricesはdecode_lkに包含される。

| 区間 | 1-deep | 2-deep | 3-deep | 回数/run |
|---|---:|---:|---:|---:|
| decode_lk | 1.697638 | 1.684215 | 1.740115 | 3847 |
| select | 0.040441 | 0.040314 | 0.040411 | 3847 |
| stamp | 1.239180 | 1.237678 | 1.270409 | 3847 |
| schur_solve | 1.583692 | 1.595732 | 1.600824 | 3847 |
| schur_update | 0.546161 | 0.526270 | 0.540488 | 3847 |
| y_to_s | 1.253012 | 1.231855 | 1.262766 | 3847 |
| output | 1.293624 | 1.286023 | 1.320687 | 3847 |
| 未分解残余 | 3.003342 | 2.993622 | 3.072622 | — |
| batch全体 | 10.657090 | 10.595708 | 10.848322 | 3847 |

1-deepのdecode_lk内はbatch decode 0.152027秒/3847回、batch matrices 1.227995秒/23555回、差0.317616秒（key・LRU・wrapper等）。scalar matrices 0.398163秒/3365回はbatch外。L/k lookup 100022、hit 73102、miss 26920＝batch matrices 23555＋scalar matrices 3365。全記録タイマーfailed 0。

batch残余にはcascade、power response、配列添字、wrapper等が含まれる。下記は**scalarとbatchの合算**であり、batch残余に全量を加減算できない：1-deepのpower_response 2.714155秒/7694回、うちwave build 0.642967秒、wave solve 1.291514秒、dB指標0.533720秒。cascade 0.712358秒/15388回。その他の全行はJSON参照。

## 分類と次の確認

1. **まず計測：solver未分解残余** 約5.6–5.7秒。`_development_worker.py`の目的値・残差集計、callback、課金・進捗とoptimizer側を切り分け、計器負荷・呼出回数・包含関係を検証する。SciPy内部と決めつけない。
2. **RF数値核：** batch Schur solve約1.6秒、Y→S約1.2秒。配列生成とsolveを分解し、特異・非SPD・例外分類、同一結果を維持する案だけを無計時A/Bで評価。
3. **RF未分解処理：** batch残余約3.0秒、scalar+batch合算のpower response約2.7秒。scalar/batchを分け、wave solve・cascade・変換・コピーを分類する。両値は重複する。
4. **メモリ・出力組立：** output約1.3秒、stamp約1.2秒。凍結・コピー・一時配列を調査。不変性、mask、6設定、RF数学を維持。
5. **L/k行列生成：** batch miss約1.2秒。LRU、SPD、数値失敗を維持した余地を調査。batch decode約0.15秒やmask約0.35秒は後順位。
6. **checkpoint：** 約1.0秒だが、頻度・耐久性・読戻し検証を緩める高速化は行わない。

いずれも現条件の仮説であり、deep比率から実際の改善率や普遍的優先順位を保証しない。候補ごとに同条件の交互plain A/B・異常系・科学的不変条件を確認する。

## 一致・限界

分析器はwarmup群・100k 9本・別trace 2本について各群のresult全体とcheckpoint `(forward_count, observation)`、全receiptファイルのサイズ/SHA、Plan raw SHAを照合し一致。plain/deep trace各100022候補のvector・目的値順序SHA `becf8d2705f0f2def10d356645dc4aa924401ef98f63c9dc29cff060be0cb448` 一致。Search 100022 forwards、要求7001540／計算4308640 samples、Terminal 1/476、MNA 2、checkpoint 99。Terminal格子で受動性・電力保存、成分条件・L SPD、独立MNA spotはpass。`evaluation_budget_exhausted`、未収束。有限格子の結果であり、連続帯域、SRF、Q(f)、EM、公差、実測、RF適合・物理実装性を保証しない。

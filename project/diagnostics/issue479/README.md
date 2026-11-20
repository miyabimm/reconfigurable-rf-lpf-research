# Issue #479 候補軸バッチ：RFcore単体診断

## 条件・再現

正式EXPではない。比較元main `1e502ae4b8f61b35995b10aca58875ce0e432e7f`、計測時は同HEADからの未commit実装差分あり。計測した `src/lpf/rf_core/model.py` SHA256 `8d8236b7b4dc6ecf78fb546cfc8b4172565f33ac54ddb3ccf41e3c8ec3618f21`、本ベンチscript SHA256 `56f70f0348fd7a22ee6d96aa8ae580b5607b63de05748bf4faf407099a67d973`。実装commitとPR HEADはGit履歴・PR参照。実装はTerminal、独立MNA、Optimizerを変更していない。

RF-T010 effective SHA `d50e6c9fef3e41b8258c00cbd14436a3bcb1d84444d50cf4a445ccf5d288e417`、物理base RF-T008 rev3 SHA `e682165c72d3a8b9f1384a2529f71bacfebfc9d17164d4af5af879e4a138b532`、固定S2P・定義・全物理bounds・seed1013は[#470](../issue470/README.md)と同じ。凍結PlanのSearch gridは70点、SHA `6805740a36f6100d7dec3e7308924242e909255f1ea2d287b7c734c400f98f26`、全6設定・28個の不連続区間。Search外部ポート応答を比較。

初期vectorに加え、Hybridと同じbounds正規化zにおけるSciPy L-BFGS-B既定絶対差分 `1e-8` を各free座標に一つずつ加え、境界では逆向き、physicalを既存Hybridと同じ `clip(lo+z*width,lo,hi)` で復元。探索やsolverは実行しない。候補列は開始点+25摂動、little-endian float64 C順バイトのSHA256 `138ab3ac724f02558a934c555bc4c7e3267e0515d6e5b542dfc1f51560862d0a`。B=1は開始点、B=5/10/25は先頭5/10/全25摂動。これらは実solver traceではなく初期点周辺の固定列である。

Linux WSL2、Ryzen 7 PRO 4750G、Python 3.12.15、NumPy 2.5.4、SciPy 1.18.1、OpenBLAS/OMP/MKL環境変数各1。実スレッド数・CPU周波数固定・CPU隔離は未確認。

```sh
PYTHONPATH=src OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  uv run --frozen python project/diagnostics/issue479/benchmark.py
```

各比較は新規Evaluator・空キャッシュ・同じ候補順。S2P/gridを用意するEvaluator生成時間は計時外。両経路各2回warmup後、各6回、毎回10回のfresh Evaluatorで評価した総plain wallを10で割る。AB/BAを交互にし外れ値を除外しない。下の範囲は6値の最小〜最大；[measurements.jsonl](measurements.jsonl)に全値・カウンタ・メモリ・最大誤差を記録。deep計時なし。メモリは別実行のtracemalloc peakでNumPy allocationを含む追跡値、RSSは同一processの累積最大であり方式別増分ではない。各B・modeは候補B、実RF sample 70B。計時・warmup・同値性・メモリ各実行を含む本表の計算は計10,496候補・734,720 samples、異常STOPなし。先行測定も同数実施（B=25が開始点+24摂動の旧列、`/tmp/issue479-benchmark-output.jsonl` に保持、正式証拠ではない）。

## plain速度・メモリ

単位ms/候補群。倍率は逐次中央値/バッチ中央値。全6実測はJSONLを参照。

| B | mode | 逐次 median (範囲) | batch median (範囲) | 倍率 | peak逐次→batch KiB | L/k hit/miss/実計算 |
|---:|---|---:|---:|---:|---:|---|
| 1 | off | 0.628 (0.612–0.710) | 0.610 (0.589–1.713) | 1.03 | 115→115 | 0/0/1 |
| 1 | lk | 0.644 (0.614–1.565) | 0.603 (0.593–0.627) | 1.07 | 115→116 | 0/1/1 |
| 5 | off | 2.529 (2.390–2.806) | 1.505 (1.477–1.516) | 1.68 | 148→672 | 0/0/5 |
| 5 | lk | 2.459 (2.411–2.814) | 1.593 (1.525–1.923) | 1.54 | 152→674 | 0/5/5 |
| 10 | off | 4.722 (4.662–4.775) | 2.746 (2.646–2.994) | 1.72 | 188→1092 | 0/0/10 |
| 10 | lk | 4.644 (4.527–4.829) | 2.652 (2.556–3.354) | 1.75 | 194→1093 | 3/7/7 |
| 25 | off | 11.884 (11.416–13.456) | 6.880 (5.963–7.045) | 1.73 | 307→2726 | 0/0/25 |
| 25 | lk | 10.764 (10.556–11.225) | 5.383 (5.272–6.805) | 2.00 | 314→2720 | 17/8/8 |

両方式のカウンタは全条件で一致。B=25は各1,750 samples。B=1の範囲は大きく重なり改善は不明。一方B=5以上は今回の全測定範囲でbatchが短く、RFcore単体の候補軸バッチとして採用・レビューを推奨する。ただしメモリ増、1 seed・1 grid・固定近傍・単一processであり、検索全体の高速化やSciPy接続の採用は未検証・別判断。response/bothはバッチ化せず既存逐次 `evaluate` に委譲する。

## 数値・STOP・回帰

測定候補すべてで複素S全4要素、IL/APL/入出力RLの最大絶対差・相対差は各0、bit一致。gridオブジェクトとsample/setting/segment順を維持。これは本入力・実装・環境上の観測で一般的なbit一致保証ではない。別テストで他schema（定数Cを含む）、閉区間C端点、混在候補、容量16超LRU順、非SPDと非有限、注入したY→S特異、sample_index付き異常の逐次replay、失敗候補のcache非保存を検査。sample_indexテストは故障注入であり実測回路の故障を意味しない。バッチ計算失敗時の投機的試行は統計に加えず、逐次replayのみを従来カウンタに反映する。

実行したunittest（各 `uv run --frozen python -m unittest discover -s tests -p '<name>' -v`、BLAS環境変数各1）：`test_issue479_rf_batch.py` 5、`test_issue476_rf_cache.py` 5、`test_issue309_rf_core.py` 8、`test_phase2_generic_coupled_lc.py` 2、`test_phase2_branch_mna.py` 6、`test_issue311_performance.py` 10、`test_issue419_power_probe.py` 4、全PASS。既存Terminal/check_power・受動性/電力保存・独立MNAの回帰を含むが、本バッチAPI自体はcheck_power/MNAを実行しない。CI・独立レビューは未確認。有限格子の比較であり、連続周波数、実装性、EM、SRF、Q(f)、公差、実測、全入力の同値性は未検証。

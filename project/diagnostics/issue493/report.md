# Issue #493: Hybrid Solver 境界の時間分解

**開発診断のみ、最適化なし、非正式EXP。** 測定コードHEAD `93174a4ecef2c3a1caf7fb439148b8b15f804904`（clean）、source identity `5a1a1b528f16846e43370603f3642959e7c3e58716633aac5280b8cbc068dd9a`。全run・全inclusive regionの回数/時間/failed、算術、環境、receipt検証結果は [measurements.json](measurements.json)、集計は [analyze.py](analyze.py)。実装途中の3回の100k診断と312 preflightも[earlier_measurements.json](earlier_measurements.json)に全run記録。測定HEADが異なるので最終版とは合算しない。

## 条件・再現・注意

#491と同一の RF-T010 **trial** effective SHA `d50e6c9fef3e41b8258c00cbd14436a3bcb1d84444d50cf4a445ccf5d288e417`、seed1013、4L2C/25変数、6設定・28分離区間、Hybrid/L-BFGS-B sum、batch/partial FD、L/k cache、Search 70点、Terminal 476点、MNA [0,111]、checkpoint1000、名目100000 forward。Plan SHA `0e2d62841f286281eb9b2c662382a50238f865193b16eafabf6aa3227ba18d90`、初期vector `6e06d271e0ea54eecb547cfff045a6edda4850bfaa1f9c23bf9f3037ab867131`、Search grid `6805740a36f6100d7dec3e7308924242e909255f1ea2d287b7c734c400f98f26`、Terminal `28ee5b630e4842b183a7c36fd610cc32e2509c0044c6a5848ce2fbd147a22e29`。bands `1b1182e4c947059cb263c1af52ddf64236bd1fd9e83770cc844126576c7865fe`、S2P in `ad266111ba1dc2b92f235d39f4a647ff271050bc11941c217661dd299ee59945`、out `b3cfc861bc0c8221f49328598c9d7d0766a6e94e42e990b6a50f6c90bf9a84da`。

WSL2 Linux 6.18.58.1、Ryzen 7 PRO 4750G、affinity CPU 0、Python 3.12.15、NumPy 2.5.4、SciPy 1.18.1、BLAS/OMP/MKL各1 thread指定。実thread数/周波数は未確認。独立312 warmupを除外し、100k plain/timed/deep各3回、`plain,timed,deep` / `timed,deep,plain` / `deep,plain,timed`、別プロセスtrace plain/deep、およびcache replay plain/deep。全成功、選別なし。

```sh
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1
uv run --frozen python project/diagnostics/issue487/measure.py /tmp/UNUSED-493 100000
CPU=$(uv run --frozen python -c 'import os; print(min(os.sched_getaffinity(0)))')
for mode in plain deep; do
  taskset -c "$CPU" uv run --frozen python project/diagnostics/issue491/cache_replay.py "$mode" "/tmp/UNUSED-493-cache-$mode" | tee "/tmp/UNUSED-493-cache-$mode.log"
done
uv run --frozen python project/diagnostics/issue493/analyze.py /tmp/UNUSED-493 /tmp/UNUSED-493-cache-plain /tmp/UNUSED-493-cache-deep > summary.json
```

最終版のRunner wall中央値（範囲・標本SD）は plain **22.352** (22.280–22.591・0.162) 秒、timed **22.515** (22.285–22.616・0.169)、deep **24.790** (24.580–24.903・0.164)。deep/plain中央値比 +10.9% は既存deepを含む観測差で、新タイマー単体の負荷や高速化率ではない。最終版ではprocess wallとCPUに約2.7〜3.4秒の差があり、checkpoint wallは2.78〜3.28秒（#491約1秒）で外部負荷/待機の影響を疑うが原因未確定。直前の計測版でも2-deep wall 28.9秒/CPU 22.9秒の大きな乖離があり、そのまま記録した。時計・dispatchのoverheadも含むdeep秒数をplainに換算せず、時間順位は仮説とする。

## 包含関係と排他的な閉包

```text
solver
 ├─ minimize (SciPy/周辺dispatchを含む)
 │   ├─ scalar objective ─ prepare ─ raw_scalar ─ scalar RF入口 + post_RF
 │   │                    └─ value(C) / state(D) ─ scalar group callback
 │   ├─ batch_map親 ─ list / vectors(A) / residuals_batch ─ mask + batch RF入口
 │   │   ├─ apply ─ SciPyのfun(z)等 ─ batch objective ─ prepare / raw_batch ─ consume(B)
 │   │   │                                       └─ value(C) / state(D)
 │   │   └─ batch group callback ─ checkpoint
 │   └─ SciPy callback
 └─ force group callback等 ─ checkpoint
```

`prepare` はbudget確認・座標変換/初期値copy・課金を含む（有効候補100022回＋停止1回）。scalarの `x.copy()` はraw_scalar内。batchの `next(pending)` はraw_batch内でBを内包し、Bはyield中の停止時間を含まない。raw_scalarはRF入口とpost_RF、検証・課金・audit等を内包。callback親をcheckpointに足さず控除。今回checkpoint countはすべて26の倍数、scalar callbackは26の倍数+1なのでDとcheckpointは重複しない。一般の非batch/fallbackにはこの今回専用の式を流用しない。

`M=minimize, P=batch親, O_s/O_b=scalar/batch objective, K=scipy callback` とすると、**SciPy/周辺dispatch未分解残余 = M - P - O_s - K**。ライブラリ純内部とは限らない。`apply - O_b` はSciPyが渡す `fun` のwrapper/dispatchとPythonループを含み、SciPy本体だとは断定しない。`batch_other = P - list - A - residuals_batch - apply - batch group callback`。`objective wrapper残余 = O_s + O_b - prepare - raw_scalar - raw_batch - C - D`。`raw_batch-B`、`raw_scalar-scalar RF入口-post_RF` も別計上。RFのscalar子は既存RF入口を包む追加タイマーなので、batch RFは形式上 `RF全体 - scalar RF子` として計算し、子の計時器自身の微小な境界差をbatch RF外残余に含める。`batch residuals - mask - batch RF` を別計上する。callbackとsolverのその他は `batch group callback + solver - M - checkpoint`。以上は今回の正常group/forced checkpointの配置に限る。式は[集計コード](analyze.py)に全記載、各値が非負で合計は各solverとナノ秒単位で一致。

| 排他的区間、秒 | 1 deep | 2 deep | 3 deep |
|---|---:|---:|---:|
| RF入口 | 13.582 | 13.497 | 13.514 |
| checkpoint | 3.042 | 2.783 | 3.285 |
| mask | 0.368 | 0.367 | 0.363 |
| 候補 vectors(A) + list | 0.943 | 0.971 | 0.939 |
| RF後処理 consume(B) + scalar post | 0.716 | 0.708 | 0.685 |
| objective prepare | 1.243 | 1.236 | 1.212 |
| objective value(C) | 1.287 | 1.303 | 1.260 |
| state(D) + SciPy callback | 0.176 | 0.174 | 0.172 |
| SciPy/周辺dispatch残余 | 1.021 | 0.998 | 0.999 |
| batch applyからobjectiveを引いたdispatch | 1.065 | 1.078 | 1.030 |
| objective wrapper残余 | 0.348 | 0.360 | 0.337 |
| scalar rawその他 | 0.042 | 0.049 | 0.046 |
| batch rawその他 | 0.146 | 0.140 | 0.138 |
| batch RF外その他 | 0.054 | 0.053 | 0.051 |
| batch親その他 | 0.193 | 0.187 | 0.186 |
| callback/solverその他 | 0.013 | 0.013 | 0.013 |
| **solver** | **24.240** | **23.915** | **24.230** |

丸め前の差額はゼロ。`batch/apply` 約4.7秒はobjectiveを内包するため上表にそのまま足さない。約1.03〜1.08秒のapply残余は1段追加して呼出境界まで隔離したがSciPy wrapperとPythonの区別は未確定。SciPy境界残余も約1秒でブラックボックスとして隔離し内部改造していない。

## 一致・異常経路・科学的限界

312 preflightで12 scalar、12 batch×25、全312候補traceがplain/deepで一致。最終100kの別traceでも100022候補のvector/目的値順序SHA `becf8d2705f0f2def10d356645dc4aa924401ef98f63c9dc29cff060be0cb448` 一致。全runのresult/checkpoint99・receiptファイルSHA/サイズ一致、search 100022 forward・7001540 requested samples、Terminal 1/476、MNA 2、`evaluation_budget_exhausted`・未収束。group完了により名目を22超過。全timed/deepのcacheと別plain/deep cache replay一致（lookup 100022、hit 73102、miss 26920、computed samples 4308640）。全100k runでtrace個別保存はしておらず別traceで順序比較した。

停止 `_Stop` がminimize外へ伝播して捕捉されるので、正常予算停止でも `objective/prepare`、`objective/scalar`、`scipy/minimize` は各failed=1。他のregion failed=0。既存テストと追加テストでscalar/batch、callback例外、batch例外、強制checkpoint、課金順、generator停止・復帰、fallback、時計復元を検査。有限476点全S/IL/APL/両RL、L SPD、受動性・電力保存、独立MNA spotsを検証。有限格子のみであり連続帯域、SRF、Q(f)、EM、公差、実測、RF適合、実装可能性や大域最適は未検証。

## 次の候補（修正は別Issue）

1. **objective prepare** 約1.21–1.24秒（solver約5%）：同じ候補の変換/copyや配列操作の重複を検討。理論上限は計測inclusive全量未満、低〜中コストだが例外順位とcopy独立性が重要。
2. **C value** 約1.26–1.30秒：約5%。既存検証・二乗/aggregateの削減余地を小さく調査。理論上限は当該全量、低〜中コスト、invalid分類・数値順序の回帰が必要。
3. **batch apply dispatch** 約1.03–1.08秒：約4〜5%。理論上限は当該全量、SciPy wrapper依存・契約維持が難しく中〜高コスト。SciPy/周辺残余約1秒も同様に手を出す前にコストを検討。
4. **RF入口** 約13.5秒は最大上限だが内部は既存deep子を参照、実装・検証コスト高。A 約0.84秒、B 約0.65–0.68秒は次点。checkpointは負荷影響が大きく、頻度・耐久性の変更は対象外。

いずれもwall観測に基づく優先順位であり、plainでの改善率の予測ではない。同一条件A/Bと科学的不変条件・例外経路の独立検証が必要。

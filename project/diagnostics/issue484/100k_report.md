# #484 / #485：100,000 forward の3方式性能診断

正式EXPではない。同一試験条件・単一seedの開発性能診断。測定HEAD `a745055547e74fb52a0b46ca582236ba35f3893c`（PR #485 マージ後のmain）、source identity SHA `844dd37c4c8e5ee90e078ef2ffe47d7bfe0f70310e3710fab10679c9d079f983`。A/B/C はそれぞれ `(batch_fd,partial_fd)=(false,false)/(true,false)/(true,true)`、RF cacheはいずれも `lk`。Optimizer/RFCore・既定値は変更していない。

## 条件・再現

`issue470/config.json` と `starts.json` の seed 1013、初期vector SHA `6e06d271e0ea54eecb547cfff045a6edda4850bfaa1f9c23bf9f3037ab867131`。RF-T010 effective SHA `d50e6c9fef3e41b8258c00cbd14436a3bcb1d84444d50cf4a445ccf5d288e417`、物理RF-T008 rev3 `e682165c72d3a8b9f1384a2529f71bacfebfc9d17164d4af5af879e4a138b532`、4L2C 25変数、6設定/28分離区間、全物理bounds、Hybrid/L-BFGS-B、正のsigned margin二乗和、restart sigma 0.1。Search 70点、Terminal 476点、MNA indices `[0,111]`、checkpoint 1000、名目上限100,000。grid/S2P/bands fingerprints は [issue470](../issue470/README.md) と同一。予約は最大超過24およびTerminalを含む。Aは実際の契約上100001 RF forwardsを予約し、B/Cは100025を予約する。

測定はWSL2 Linux 6.18.58.1、AMD Ryzen 7 PRO 4750G、CPU affinity 0、Python 3.12.15 / NumPy 2.5.4 / SciPy 1.18.1、OPENBLAS/OMP/MKL各1。周波数・実thread数・ホスト側負荷は固定/確認していない。各方式312 forward設定のwarmupを1回実施して除外。6セットは指示順 ABC/BCA/CAB/CBA/ACB/BAC、各回独立プロセスとfresh output。deep/timed計器は使用していない。Runner wallは `runner.run` 呼出開始から完了までの `perf_counter`、process wallは子プロセス起動から終了まで、CPUと最大RSSはwait4のrusage。前者を性能比較に用い、後二者を含め全生数値は [JSON](measurements_100k.json) に保存（RSS KiB）。

再現（出力先は存在しない `/tmp` のパスを使う）：

```sh
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
 uv run --frozen python project/diagnostics/issue484/measure_100k.py /tmp/UNUSED-PATH
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
 uv run --frozen python project/diagnostics/issue484/analyze_100k.py /tmp/UNUSED-PATH > summary.json
# 別プロセス、計時外の候補順・目的値ハッシュreplay（各出力先はfresh）
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 taskset -c 0 \
 uv run --frozen python project/diagnostics/issue484/trace_100k.py B /tmp/UNUSED-TRACE-PATH
```

## 全18本のRunner wall秒

| set (順序) | A | B | C |
|---|---:|---:|---:|
| 1 ABC | 54.371398 | 35.455386 | 27.582425 |
| 2 BCA | 54.306149 | 31.338794 | 27.712825 |
| 3 CAB | 53.552884 | 31.909428 | 27.201187 |
| 4 CBA | 54.115879 | 31.874516 | 27.136326 |
| 5 ACB | 54.133577 | 31.742746 | 27.537251 |
| 6 BAC | 53.467276 | 31.128761 | 27.520105 |

| 方式 | 中央値 s | 平均 s | 最小–最大 s | 標本SD s | IQR s | 平均 ms/Search forward |
|---|---:|---:|---:|---:|---:|---:|
| A | 54.124728 | 53.991194 | 53.467276–54.371398 | 0.386310 | 0.569373 | 0.539912 |
| B | 31.808631 | 32.241605 | 31.128761–35.455386 | 1.604733 | 0.460918 | 0.322345 |
| C | 27.528678 | 27.448353 | 27.136326–27.712825 | 0.227782 | 0.290215 | 0.274423 |

IQRは線形補間Q3−Q1。forward当たりはRunner wall合計÷Search実forward合計で、Terminal等の固定費も含む。中央値wall比の短縮は **A→B 41.23%、B→C 13.46%、A→C 49.14%**（速度倍率ではない）。

対応差は前者−後者秒、比は後者/前者。セット順：

| 比較 | 対応差 s | 時間比 | 対応差平均の参考95% t区間 s |
|---|---|---|---|
| A→B | 18.9160, 22.9674, 21.6435, 22.2414, 22.3908, 22.3385 | .6521, .5771, .5958, .5890, .5864, .5822 | 20.227–23.272 |
| B→C | 7.8730, 3.6260, 4.7082, 4.7382, 4.2055, 3.6087 | .7779, .8843, .8524, .8513, .8675, .8841 | 3.127–6.460 |
| A→C | 26.7890, 26.5933, 26.3517, 26.9796, 26.5963, 25.9472 | .5073, .5103, .5079, .5014, .5087, .5147 | 26.165–26.921 |

B→Cは6/6セットすべて3.61秒以上短く、B/Cの全値も分離する。今回の環境・条件ではばらつきに対して明瞭な差。t区間は6組・独立性/正規性等の仮定付き参考値で一般性の証明ではない。B1は他より約3.5–4.3秒長く、CPU時間も長い（34.808秒 vs 他30.574–31.312秒）。OS待ちだけでは説明できず、周波数やホスト負荷の原因は未特定。除外せず、別途Bを追加実行：Runner 32.502993秒、process 32.911752秒、CPU 30.692892秒、RSS 91992 KiB、結果JSONはB1と一致（[追加値](extra_b_100k.json)）。追加は指定6セットの統計に混入しない。確定的なノイズ源は不明。

## 数値・予約・軌道

全18 runで各方式内のresult完全一致、全receipt記載ファイルのbytes/SHAを照合、run status completed、独立MNA pass、Terminal格子の受動性・電力保存チェック、全6設定の部品条件とL行列正固有値を確認。予算停止 `evaluation_budget_exhausted`、未収束であり RF合格ではない。初期vectorは共通。Plan SHAは指定オプション差によりA `9aea9d767b052a13bec15577a5854712d8b49c23eebe2b6bca4ceb8069e28550`、B `4a18ad90cd64308cba6552ef3a63c5e03ebb6b7302f147506377f98b216962f0`、C `0e2d62841f286281eb9b2c662382a50238f865193b16eafabf6aa3227ba18d90`。

- A: Search **100000** forward / **7000000** requested samples、Terminal 1 / 476、MNA 2。予約100001 forwards / 7000476 samples、解放0、不明0。checkpoint 101。
- B/C: Search **100022** / **7001540**、Terminal 1 / 476、MNA 2。予約100025 / 7002156、実消費100023 / 7002016、解放2 / 140、不明0。checkpoint各99。requested samplesは論理要求数であり、Cの実計算サンプル数ではない。
- B/Cの最終solver vector、objective `2.929380163370666`、3 local runの全詳細、Terminal全体（全S/IL/APL/入出力RL・MNA）、ledger、checkpoint `(forward_count, observation)` は完全一致。最終vector SHA `8cfdf946543a7f56a50b346b219d06e4b56060c1d3d65dd568308e61ae0f982e`、Terminal J `0.747758285205661`。
- Aのsolver objective `2.9293813500586237`、最終vector SHA `ca2769235507c96f237d2c28cf0a7e6c6aec3891aae7c9cfee7e47b66a8991fa`、Terminal J `0.747758346965893`。AとBは同一最終点ではない。solver vector最大絶対差 `9.99e-7`（各変数の単位に依存）、Terminal応答最大絶対差：Sの実部/虚部成分 `1.026e-6`、IL `9.484e-5 dB`、APL `9.450e-5 dB`、入力RL `1.889e-5 dB`、出力RL `1.495e-4 dB`。A/Bのcheckpointは保存境界と観測方法が異なり一致しない。
- local runの `(nfev,nit,status)` はA `(29874,953,0),(24648,924,0),(45478,1313,null)`、B/C `(29874,953,0),(24648,924,0),(45500,1314,null)`。先頭2回は相対目的減少による成功、最後は予算停止・未成功。

別の計時外replayはprogress/objective callbackの各vectorとobjectiveを順序通りbinary64 SHA256に加えた（計器付きのため時間比較には使わない）。先頭100000候補のハッシュは3方式とも `cba260f754cf7e0de59c12df552c5f946864f66ecee83c4162ea5e88d759a22b`、B/Cは全100022候補でも `becf8d2705f0f2def10d356645dc4aa924401ef98f63c9dc29cff060be0cb448` で一致（[値](traces_100k.jsonl)）。これはこの再実行における順序・値の一致であり、任意seedの保証ではない。A停止後の22候補はB/Cのみで評価され、同一予算境界の最終状態を比べているわけではない。checkpoint/receipt比較の詳細・全run数値はJSON参照。

replay初回Aは診断スクリプトがscalar側に存在しないcallbackを参照して `KeyError: progress_callback` で停止（RF評価前、未完了ディレクトリ保持）。修正後、fresh `trace2-A/B/C` で完走した。これは性能測定に含めない。

## 判断と限界

この限定条件では通常batchはAより明瞭に速く、partialはBよりさらに明瞭に速い。B/Cは実探索の結果・軌道が一致しており、**Cを今後の標準経路の有力候補として推奨**する。ただし他seed・回路・環境や障害条件への一般化、独立レビュー、標準化・既定値変更の承認は未了であり、今回既定値を変更しない。A対B/Cは22 forwardの差があり、秒数短縮は探索効率・収束改善の証明ではない。全ケース有限grid・未収束で連続周波数、SRF、Q(f)、EM、公差、実測の保証はない。

検証: `test_issue484_partial_fd.py` 8件、`test_issue482_batch_fd.py` 5件 PASS。raw Runner outputs、checkpoint、receipt、ログ、未完了replayは `/tmp/rf-lpf-484-100k-a7450555/` に保持（system tmpは永続保証なし、削除していない）。正式EXP原本・旧結果は変更なし。独立レビュー待ち。

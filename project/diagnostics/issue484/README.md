# #484 部分FD開発診断（正式EXPではない）

`benchmark.py` と [全値](measurements.json)。再実行：

```sh
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  uv run --frozen python project/diagnostics/issue484/benchmark.py
```

最終測定時の実装HEAD `b53afa1aed2654a8058b8759b276a8d492ad9014`、追跡済みdiffなし（診断ファイルは未追跡）。それに先立つ探索測定（部分失敗時の統計補正前）の[全値も保存](measurements_exploratory.json)。成功時のRF計算は同じだが、異なる実装状態として区別する。RF-T010、effective SHA `d50e6c9fef3e41b8258c00cbd14436a3bcb1d84444d50cf4a445ccf5d288e417`、seed 1013、`issue470` definition/start、70 Search点・476 Terminal点、固定S2P・grid SHAは記録JSONとPlan参照。Python 3.12.15、NumPy 2.5.4、SciPy 1.18.1、WSL2、BLAS等1 thread。正式制約変更や正式EXPは行っていない。

## 計算量と数値

固定近傍の25候補は最初の13候補が各70点、次の12候補が `[10,10,10,10,10,10,20,20,10,10,10,10]` 点で計 **1,050点**（既存1,750点）。基準の70点は別。設定を`grid.setting`で選択。変更設定が欠落するgridでは0点も可能。これは時間改善率ではない。

固定近傍では全候補のS、IL、APL、両RL、符号付き残差、sum二乗目的、正規化座標の差分勾配がbit一致（最大差0）。実Runner比較（312 Search forward）でもsolver result、local run詳細、Terminal全体、checkpoint observation、ledgerが一致。別の回帰では実SciPyの80 nominal forwardにおける全候補順・値・objective・best更新を比較しbit一致。異なるPlan SHAはオプション値が異なるため。両Runnerは予算停止・未収束、Search 312 forwards/21,840要求samples、Terminal 1 forward/476 samples、独立MNA 2点。Terminal格子で受動性・電力バランス、独立MNAをチェック。有限格子・該当候補の検証であり全条件の同値性や物理実現性の証明ではない。

## plain A/B（warmup除外、順序交互）

RF単体は同一25候補・同一base、`lk`、Evaluator生成と基準評価を計時外、各測定5回平均、6回。ms全値：

| | 値 | 中央値 ms |
|---|---|---:|
| scalar | 10.495, 10.842, 10.865, 11.021, 10.564, 13.139 | 10.853 |
| batch | 6.610, 9.152, 6.259, 6.266, 6.124, 6.228 | 6.262 |
| partial | 4.311, 4.255, 4.264, 4.203, 4.351, 4.694 | 4.288 |

同中央値比ではpartialは既存batch比約31.5%短縮。scalarとbatchに外れ気味の値があり、短時間の測定のため一般化しない。別のtracemalloc peakはscalar 323,168、batch 2,602,208、partial 1,591,224 bytes。NumPy追跡分を含むがRSSではなくプロセス全メモリの保証ではない。

Runner全体（Plan/source検証、checkpoint、Terminal、receipt含む）の秒、各4回：

- batch: 0.578674, 0.628520, 0.614225, 0.603589（中央値0.608907）
- partial: 0.557979, 0.580933, 0.630204, 0.618520（中央値0.599726）

中央値差約1.5%だが両分布が重なり、全体高速化を断定しない。探索測定ではbatch [0.611703, 0.629627, 0.624869, 0.639339]、partial [0.555102, 0.578362, 0.550407, 0.571513] 秒で中央値差約10.2%；異なる時点・実装状態でばらつきが大きい。別tracemalloc peakは4,616,001対4,615,703 bytes（partial -298 bytes）。代表診断に限りデフォルト採用はせず、opt-inのまま独立レビューを待つ。

## deep・計器負荷と制限

最終deep各1回のRunner wallはbatch 0.577711秒、partial 0.564960秒。inclusive Search RFは71.415対59.601 ms、Search solverは101.366対89.420 ms。一方、探索測定のdeep wallは0.579082対0.659183秒と逆転していた。計測負荷・OSノイズ等を含み、反復なしで原因の切り分けや速度結論はできない。領域は包含関係があり加算不可。現在の詳細内訳は主に単独RF経路で、バッチ内部のSchur等は個別計時されず、内訳からバッチ内部を推定しない。deep countersの実計算samplesは21,840対13,440、論理要求はいずれも21,840。詳細値はJSON。

測定スクリプトのRunner出力は専用一時ディレクトリに生成して処理後削除し、要約をJSONに記録。過去結果や正式証拠は変更していない。故障再生、LRU、非SPD、空・不連続grid、非有限入力等は `tests/test_issue484_partial_fd.py` と既存 #479/#482 回帰を参照。連続周波数、SRF、Q(f)、EM、公差、実測は未検証。

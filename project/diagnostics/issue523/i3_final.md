# #523 I3最終候補：本番反映と標準CLI比較

## 判断・範囲

2026-11-26追加指示により、先のI3見送り推奨を変更し、**I3を最終採用候補**とする。I2の既存20 seed品質受容は維持するが、I2の20 seedをI3の実測と混同しない。I3の20 seed・同一時間比較・正式EXPは実施していない。最終採否はDraft PRの独立レビュー・マージ判断待ち。

I3は `X=solve(H,B.T)`、`W=X@T`、非共役 `-(Wᵀ@dH@W)/scale` により直接Port投影し、dK・2回目solve・nodal_peakを本番経路から削除。C、圧縮、全4複素S感度、全列IL Jac、forward、Runnerと科学条件は不変。旧nodal関数は独立FD検証のため維持。残存X solve例外、dH/X/W/scale/dRL/C/dRの非有限検査と最終IL/残差Jac等は維持し、消えた演算の人工異常は再現しない。

実測I2 commit `41537084ca6cbe966efb35958df9dea7a504328f`、本番I3実測commit `59563500fa4a22efc804061a44f2570c838341a1`。診断版 `4a1fc0b0bbb8072ca3ff278ef3239785dced4e5f` とI3本番は `src/` に差分なし、`coupled_lc.py` のGit blobは両方 `2065180fdbd3aed5ee3b97662586aa9e7eb6cb9a`。既存 `i3_fixed_v1.json` / `i3_fixed_v2.json`、`i3_numerics.json`、`fd9_i3.json`、`edge_i3.json` を再利用。9点全列・4複素S FDの許容差超過0、残存solveの例外・NaN注入PASS。旧dY/dKの極端入力STOP完全同値は要求せず保証しない。有限格子・実用回路における異常や不明な品質差は以下を参照。

## 固定commit・標準CLI比較

RF-T010 effective SHA `d50e6c9fef3e41b8258c00cbd14436a3bcb1d84444d50cf4a445ccf5d288e417`、4L2C・25変数・6設定28別区間、Search70／Terminal476、TRF exact、ftol=1e-6、x_scale=1、restart_sigma=.1、CP1000、MNA [0,111]。seed 1001/1010/1020、各5000 forward、I2/I3のplain/deep各2反復。各seed・levelでI2先行とI3先行を1回ずつ、warmup各版level1回は集計除外。入力manifest SHA `b1aecd560566cf57364c73fffc43d85a03af4ea08386a79e958170f06edd8db4`、search grid `6805740a36f6100d7dec3e7308924242e909255f1ea2d287b7c734c400f98f26`、terminal grid `28ee5b630e4842b183a7c36fd610cc32e2509c0044c6a5848ce2fbd147a22e29`。Plan・starts・bounds・bands/S2P・source・各出力・receipt SHAは `i3_runner_results.json`、全region/count/failure・timing SHA・nonoverlap otherは `i3_runner_deep.json`。

source importを子processで確認：I2 `/tmp/issue523-i2deep/src/lpf/rf_core/coupled_lc.py` SHA256 `7f9b67669890f2d99a7d024acdb45c3fcb3da449beeb5439b407cbe07ca9b664`、I3 `/tmp/issue523-i3final/src/lpf/rf_core/coupled_lc.py` `b2524073e140183e7d6be03429c29fccaa0f3306594c7c5dbe33c4b69a0d0378`。同じ `model.py` SHA256 `103b8e4b188071c280397d61f50b3eae3fb0c2b6ced15d9872d3b4bdf93c82cc`。標準CLIは各worktreeの `src/` を優先する。Python・CPU等の環境、affinity、load、周波数・温度は各run記録；Ryzen 7 PRO 4750G、利用可能最小CPUへ固定、OpenBLAS/OMP/MKL各1、allocator既定。共有hostの負荷・温度は制御していない。

| 6測定jobの中央値 | I2 plain | I3 plain | I2 deep | I3 deep |
|---|---:|---:|---:|---:|
| process wall s | 14.002 | 13.135 | 14.824 | 14.089 |
| user CPU s | 13.697 | 12.870 | 14.508 | 13.808 |
| system CPU s | 0.187 | 0.173 | 0.200 | 0.186 |
| minor fault 範囲 | 21593–21880 | 21836–21870 | 21974–22008 | 21967–22011 |

major faultは全件0。RSSは `RUSAGE_CHILDREN.ru_maxrss` の**累積最大**で、全job最大92060 KiB、各job単独peakではない。対応するseed/cycleのI3−I2 plain wall差中央値 **−0.423 s**、範囲 −1.486〜−0.083 s（6/6短縮）。deep差中央値 −0.316 s、範囲 −1.594〜+0.873 s（2/6逆転）。process中央値の差と対応差中央値は別。CPU状態とsolver軌跡の差を含むため、この少数測定から普遍的改善率や固定vectorの3.8%厳密再現を主張しない。

### deep内訳

測定job 6本の中央値、各region count=5000、failure=0、単位秒。親子は加算しない。

| region | I2 | I3 |
|---|---:|---:|
| RF evaluator 親 | 9.823 | 9.287 |
| port Jacobian 親 | 1.907 | 1.687 |
| inductor solve | 0.218 | 0.091 |
| L/k projection（I3はW生成を含む） | 0.865 | 0.780 |
| C projection | 0.250 | 0.240 |
| finite | 0.179 | 0.202 |
| Y→S / wave | 1.143 / 1.353 | 1.120 / 1.315 |
| RF other / port other | 0.383 / 0.071 | 0.358 / 0.064 |

未分類otherは各runの親から非重複の直下区間を引いてから中央値を取る。親子の中央値を合算せず、計時負荷付きdeepをplainと混同しない。固定vector 8対応でI3のplain中央値差は以前 −0.004〜−0.112 ms、対応差中央値 −0.059 ms（3.80%）；固定vectorとRunnerは別の測定。

## 結果・停止・科学的限界

同じ版・seedについてplain/deep・2反復で最終vector、全checkpoint、消費、Search/Terminal J、STOPが一致。全28 jobは予算停止・非収束（`evaluation_budget_exhausted`）、Search nfev=5000。component policy・6設定の物理検査はpass、外部受動性・電力保存はTerminal gridで検査、独立MNAは各2点pass。いずれも有限点の検査であり、全帯域・実装可能性の保証ではない。

| seed | 版 | Search J | Terminal J | 最大違反 dB | worst IL / min H2 / min H3 dB | njev / restart |
|---:|---|---:|---:|---:|---|---|
| 1001 | I2 | 0.518 | 4.301 | 0.321 | 1.071 / 29.982 / 29.990 | 4010 / 7 |
| 1001 | I3 | 0.524 | 4.356 | 0.323 | 1.073 / 29.982 / 29.990 | 4072 / 4 |
| 1010 | I2 | 0.849 | 7.061 | 0.346 | 1.096 / 29.950 / 29.984 | 4136 / 15 |
| 1010 | I3 | 10.748 | 81.551 | 1.147 | 1.897 / 29.318 / 29.711 | 4387 / 8 |
| 1020 | I2 | 119.937 | 830.689 | 4.161 | 3.310 / 25.839 / 27.323 | 4262 / 10 |
| 1020 | I3 | 125.299 | 895.162 | 4.292 | 4.526 / 25.708 / 28.755 | 4386 / 14 |

seed1010でTerminal J 7.061→81.551、最大違反0.346→1.147 dBに悪化。3 seed・非収束探索であり、軌跡差の要因や母集団としての悪化・同等性は未確定。前報I2の20 seed品質受容をI3の統計的品質保証に拡張しない。SRF、Q(f)、EM、公差、実測、連続周波数適合も未検証。

## 再現・消費・保持

```sh
# /tmp/issue523-i2deep と /tmp/issue523-i3final を上記固定commitのclean worktreeに用意
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1
.venv/bin/python project/diagnostics/issue523/runner_i2_i3.py /tmp/NEW-i3-runner --python "$PWD/.venv/bin/python" --inputs /tmp/issue523-inputs --cycles 2
.venv/bin/python project/diagnostics/issue521/collect_cli.py /tmp/NEW-i3-runner /tmp/NEW-i3-compact.json
.venv/bin/python project/diagnostics/issue523/collect_deep.py /tmp/NEW-i3-runner /tmp/NEW-i3-deep.json
```

実測script `runner_i2_i3.py` SHA256 `9947b67494d0cd23612b9b15ca3ccfcbecf9820a1051ab337541ddb6721d9898`。28 jobで **140028 RF forward / 9813328 samples / MNA56点**、前報の消費に加算。全job・warmup・exit4を保持、初期/最終vectorとcheckpoint・receiptのSHAおよび全登録ファイルを `collect_cli.py` で照合。生データとcheckpoint `/tmp/issue523-i3-runner/`、集計 `/tmp/issue523-i3-runner-{compact,deep}.json`、入力 `/tmp/issue523-inputs/`、固定worktree `/tmp/issue523-i2deep`、`/tmp/issue523-i3final` を保持。以前のI2・I3診断rawとworktreeもそのまま残す。

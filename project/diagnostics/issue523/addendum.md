# #523 追加決定後の測定・I3診断

> この報告はI2採用時点の履歴。後続指示でI3を最終採用候補に変更し、標準CLIで追加比較した結果は [`i3_final.md`](i3_final.md) を参照。過去の測定値・判断経緯はそのまま保持する。

## 決定と範囲

2026-11-26 の #523 追加決定により、ユーザーは先の20 seed品質観測を受容し **I2を採用**。品質の統計的同等性は主張しない。I2本番候補のdeepを細分化し、3 seedで版順均衡の再測定を実施。I3は固定vectorだけの別commit診断であり、本番への採用は承認されていない。新しい20 seed探索・同一時間近似・正式EXPは実施していない。PRはDraft、独立レビュー待ち・未マージ。

- baseline `79f9edfd63aa1af07a2b355e38a957e57f742f54`、I2実測 `41537084ca6cbe966efb35958df9dea7a504328f`、I3診断 `4a1fc0b0bbb8072ca3ff278ef3239785dced4e5f`。I3は `issue-523-i3-diagnostic` に固定、PRには本番のI2のみ。`i3-diagnostic.patch` でもI2→I3を再構成できる。I3の変更は2回目solve/dK除去、W投影、消失したdK/旧nodal_peak検査を置換するX/W/dRL有限検査のみ。
- 試験 RF-T010 effective SHA `d50e6c9fef3e41b8258c00cbd14436a3bcb1d84444d50cf4a445ccf5d288e417`、入力manifest SHA `b1aecd560566cf57364c73fffc43d85a03af4ea08386a79e958170f06edd8db4`、search/terminal grid・bounds・S2P SHAと各runのPlan/source/starts SHAは `balanced_results.json`。条件は前報の4L2C、全6設定28区間、Search70/Terminal476、TRF exact、5000 forward、CP1000、MNA [0,111]。
- 現行計時スクリプト `runner_compare.py` SHA256 `91f521dc2eb9b0cbc6c53bb0b65ed67c04572a50e06e0537de71e84c4eb28596`、固定vector v2 `fixed.py` SHA256 `5418b000e245477e0ac97c7446b4b83d931c05ab8702c177071e9556db5927be`。v1固定vectorは前報の `fixed.py` SHA256 `499ef87bb8b6a10cd57fcf949dd5c1162d2cdc8a6298612fe00375554ae4ff14`。計測対象sourceは上記固定commitで、計時scriptの差は本番には反映していない。

## 旧順序の訂正とbalanced再測定

旧20 seedだけでなく旧3 seedの各plain/deepレベルでも、全seed・反復ともbase先行だった。旧記録は保持し前報を訂正した。新スケジュールは各seedで各levelにつき base→I2 / I2→base を1回ずつ実行、level先行順も交互。標準 `scripts/run_rf_search.py develop` を固定worktreeから起動し、3 seed×2反復×2版×plain/deep、各版level warmup1の計28 job。

| 測定中央値 | base plain | I2 plain | base deep | I2 deep |
|---|---:|---:|---:|---:|
| process wall s | 18.775 | 12.734 | 20.204 | 13.745 |
| user CPU s | 18.462 | 12.423 | 19.927 | 13.457 |
| system CPU s | 0.193 | 0.198 | 0.190 | 0.185 |
| minor fault 範囲 | 22342–22415 | 21835–21854 | 22106–22549 | 21973–22004 |

major fault全件0。`RUSAGE_CHILDREN.ru_maxrss` は逐次累積最大、最大92004 KiBであり、各run個別peakではない。CPU Ryzen 7 PRO 4750G、利用可能最小CPUへaffinity固定、OpenBLAS/OMP/MKL各1、allocator既定。共有hostの周辺負荷・温度は制御せず、旧測定との絶対時間差を同一条件の厳密差と扱わない。全28 job exit4の予算停止、MNA2点pass、同一版・seed・cycleのplain/deepで最終vector・全checkpoint・消費は一致。receiptおよび全登録ファイルを #521 `collect_cli.py` で検証。各runのwall/user/system/fault、環境、plan/source/grid、品質、checkpoint、timing SHAは `balanced_results.json`。

### deep内訳（6測定jobの中央値、各region count 5000、failure 0）

| 区間、単位 s | base | I2 |
|---|---:|---:|
| RF evaluator 親 | 15.235 | 9.190 |
| 旧 node Jacobian / reorder / Schur | 2.992 / 0.398 / 2.599 | — |
| lift / port Jacobian 親 | — | 0.082 / 1.786 |
| port の dH / H,B / solve | — | 0.081 / 0.089 / 0.204 |
| L/k projection / C projection | — | 0.822 / 0.235 |
| assemble / finite / port other | — | 0.062 / 0.167 / 0.063 |
| Y→S / cascade first / second | 1.815 / 0.618 / 0.477 | 1.100 / 0.447 / 0.387 |
| wave / IL / restore | 2.034 / 0.335 / — | 1.292 / 0.235 / 0.123 |
| RF evaluator other | 0.395 | 0.329 |

各値は異なるrunの中央値なので和は親中央値と一致しない。親と子を二重加算しない。`deep_records.json` は旧rawから回収できた20 timing＋新14 timing（warmup含む）の**全region、count、failure、各runの非重複RF other、細分化済みI2のport other、timing/Plan/source SHA**を保存する。旧データにはL/C別計時がなく生成していない。新しいclockはdeepのみ、plain clock非使用回帰PASS。

## 極端値とSTOP

独立レビューの合成反例を再現した（`edge_checks.py`／`edge_i2.json`）：`dK=1e300`, `T=1e5`, `scale=1e10` で旧 `(Tᵀ @ (dK/scale) @ T)` は `1e300` と有限、新 `((Tᵀ @ dK @ T)/scale)` は `inf+nanj`。任意liftによる算術例であり、実回路に到達すると主張しない。`nodal_peak` は元の巨大dYを再生成せずに実虚成分のmax/最小scaleを検査するが、旧複素除算の完全同値でも新中間overflowの防止でもない。現I2は例のような場合に最終有限検査でSTOPし得る。旧中間overflow検査目的の巨大dY・別fallbackは追加しない。実用上の根拠を保った上で極端値差は独立レビューの留保とする。

既存9 RF-T010固定vector（初期・3000・5000）の観測では、ω 3.877e9〜1.725e10 rad/s、scale最小3.877、|T|最大17.566、|dK|最大1.819、除算前L投影最大229.619。これら観測は合成値から桁違いに小さいが、全許容回路・全周波数についての有界性証明ではない。I2/I3とも forward後の残存X solve異常を別々に注入し、例外→`sensitivity_inductor_solve_failed`、NaN→`sensitivity_node_nonfinite`。既存のSPD・Schur・forward優先・zero transmission・非有限・物理/正規化FDを維持。旧nodal関数は `tests/test_issue499_sensitivity.py` と旧診断に実callerがあり、forwardと独立してnode感度の全列FDを検査する契約として保持。本番TRFからの呼び出しはない。

## I3固定vector診断（Runner探索なし）

I2/I3各4 process、順序 I2→I3、I3→I2、I2→I3、I3→I2 を2バッチ実施。各processで9 vector×plain50回、v1 deep1回、v2 deep10回。process全体・固定vector plain中央値は、v1 I2 `1.519/1.461/1.482/1.497 ms`、I3 `1.422/1.458/1.437/1.451 ms`；v2 I2 `1.597/1.516/1.563/1.543 ms`、I3 `1.525/1.426/1.539/1.430 ms`。8対応すべてI3が低いが、差は約0.004〜0.112 msでhost変動も大きい。v2のdeep evaluator全体中央値はI2 `1.944/1.701/1.851/1.873 ms`、I3 `1.692/1.638/1.919/1.655 ms`（1組は逆転）。v2のinductor solve中央値はI2 0.037–0.040→I3 0.013–0.019 ms、L投影0.157–0.165→0.140–0.159 ms。計器負荷・区間中央値とplainを混同しない。

I3は微小だが方向の揃う短縮を示した。一方、最小差は0.004 ms、deepでは1組逆転し、通常Runner効果は未測定。**現段階ではI2維持を推奨し、I3の本番採用は提案しない**。より価値があると判断するかは独立レビューに委ねる。`i3_fixed_v1.json`／`i3_fixed_v2.json` にprocess毎の全plain時間・対応vector SHA・deep region/count・import元・RSS・raw SHAを保存。`i3_numerics.json` の旧nodalとの9点最大絶対差はdR 3.973e-15、dcore 3.690e-15、dfull 3.696e-15、外部4複素S 4.242e-15、物理IL 1.848e-13、正規化残差 1.136e-11。forward 9点はI2とbit一致、I2/I3 Jacobian最大差1.422e-13。

全9点・全25列の独立FD（正規化刻み1e-6、境界は二次片側、IL rtol=1e-4/atol=1e-5、複素S各4成分 rtol=1e-4/atol=1e-7）でI2/I3とも許容差超過0、`fd9_i2.json`／`fd9_i3.json`。絶対差最大だけでは大きな勾配に対する相対誤差を表さない。I3で#499の6テスト、#523の2テスト、#521複素S・cascade等5テスト、残存solve異常注入をPASS。消えた2回目solveの人工異常は再現しない。I3はdK・旧nodal_peak非有限を検査せずX/dH/W/最終投影を検査するため、極端な有限値における旧STOPとの差は未承認であり、I3採用時には別途判断が必要。

## 再現・消費・保持

```sh
# 固定commit worktree /tmp/issue523-{base,i2deep,i3} と /tmp/issue523-inputs が必要
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1
.venv/bin/python project/diagnostics/issue523/runner_compare.py /tmp/NEW-balanced --python "$PWD/.venv/bin/python" --inputs /tmp/issue523-inputs --cycles 2
.venv/bin/python project/diagnostics/issue521/collect_cli.py /tmp/NEW-balanced /tmp/NEW-balanced-compact.json
.venv/bin/python project/diagnostics/issue523/collect_deep.py /tmp/issue523-runner-v2 /tmp/NEW-balanced /tmp/NEW-deep.json
.venv/bin/python project/diagnostics/issue523/fixed.py /tmp/issue523-i3 /tmp/NEW-i3.json --repetitions 50 --deep-repetitions 10
.venv/bin/python project/diagnostics/issue523/fd9.py /tmp/issue523-i3 /tmp/NEW-fd.json
.venv/bin/python project/diagnostics/issue523/edge_checks.py /tmp/issue523-i3 /tmp/NEW-edge.json
```

新CLI計28 jobで140028 RF forward／9813328 samples／MNA56点、全件保存。I3固定vector v1 3744 + v2 4392 = 8136 evaluator呼出、569520 samples。追加FDは各版9×(2 analytic + 50 forward) = 468呼出、両版計936／65520 samples。単体テスト・edge計算は別。消費は前報に加算し、失敗・非収束を除外していない。

raw/checkpointは既存 `/tmp/issue523-runner-v2/`、`/tmp/issue523-quality/` に加え `/tmp/issue523-balanced/`、I3固定raw `/tmp/issue523-i3-fixed/` と `-v2/`、生成入力 `/tmp/issue523-inputs/`、各compact/FD/edge結果 `/tmp/issue523-*` に保持。固定worktree `/tmp/issue523-base`、`/tmp/issue523-i1`、`/tmp/issue523-i2`、`/tmp/issue523-i2deep`、`/tmp/issue523-i3` は未削除。正式EXP、連続周波数、SRF、Q(f)、EM、製造公差、実測は検証していない。

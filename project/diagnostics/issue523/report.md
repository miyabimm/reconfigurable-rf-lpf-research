# #523 直接 Port 感度と方向圧縮：当初比較の記録

> 本文はI2採用時点までの履歴。後続決定によるI3最終候補化・標準CLI比較は [`i3_final.md`](i3_final.md) を参照。

## 結論

**2026-11-26追加決定：ユーザーは既存20 seedの品質結果を受容しI2採用を決定した。** Draft PRは未マージ、deep更新およびI3固定vector診断の独立レビュー待ち。同一5000 forwardの20 seedでTerminal品質は12改善・8悪化、うち数seedの悪化は非常に大きい。非収束有限探索の観測であり、統計的優劣・同等性・全帯域適合・物理実現性の証明ではない。

本PRの本番候補は I2（直接投影＋設定方向圧縮）。I1 は比較用commitのみ。I3 は前報時点では未着手、その後の固定vector診断は `addendum.md` を参照。旧 `node_admittance_with_jacobian` は本番TRFから外したが、`tests/test_issue499_sensitivity.py` の独立 nodal FD 契約が現役のため保持。旧診断スクリプトにも利用がある。

## 固定条件と再現

- base `79f9edfd63aa1af07a2b355e38a957e57f742f54`、I1 `91e1e1c9`、I2 `82920f7a4ae635242908c16b4e11b29b27d5edf3`（後続はテスト・診断のみ）。
- trial RF-T010 effective SHA `d50e6c9fef3e41b8258c00cbd14436a3bcb1d84444d50cf4a445ccf5d288e417`、4L2C・25変数・6設定28独立区間、Search70／Terminal476、TRF exact、ftol=1e-6、x_scale=1、restart_sigma=.1、CP1000、独立MNA [0,111]。正式EXPではない。bands、S2P、bounds、grid、Plan、starts、source、各結果およびreceiptのSHAは `results.json`。入力manifest SHA `b1aecd560566cf57364c73fffc43d85a03af4ea08386a79e958170f06edd8db4`。
- Python 3.12、NumPy及び各import pathは `results.json`。CPU Ryzen 7 PRO 4750G、OpenBLAS/OMP/MKL各1、allocator既定。固定vectorは元affinity、CLIは利用可能な最小CPUへaffinity固定。共有hostの負荷・温度は制御していない。
- 再現資産：`fixed.py` は固定vector専用、`numerics.py` は旧nodalとの内部量比較、`runner_compare.py` は標準CLIだけを子process実行、`summarize.py` は旧 #521 の `collect_cli.py` によるreceipt監査済み記録を集計する。入力は #521 `generate_inputs.py` で生成。詳細手順：

```sh
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1
# /tmp/issue523-{base,i1,i2} に上記commitのclean worktreeを用意
uv run --frozen python project/diagnostics/issue521/generate_inputs.py /tmp/NEW-inputs --budget 5000
uv run --frozen python project/diagnostics/issue523/fixed.py /tmp/issue523-i2 /tmp/NEW-fixed.json
uv run --frozen python project/diagnostics/issue523/numerics.py /tmp/NEW-numerics.json
.venv/bin/python project/diagnostics/issue523/runner_compare.py /tmp/NEW-runs --python "$PWD/.venv/bin/python" --inputs /tmp/NEW-inputs --cycles 3
uv run --frozen python project/diagnostics/issue521/collect_cli.py /tmp/NEW-runs /tmp/NEW-compact.json
```

`runner_compare.py` のworktreeパスとcommitは明示固定。20 seedは `--cycles 1 --plain-only --seeds $(seq 1001 1020)`。**実施した20 seedではスケジュールの反転処理により、意図に反し全seedでbaseが先、I2が後だった。** 上記再現コードはその欠陥を修正済み。20 seedの速度比較に順序バイアスが残る。3 seedの旧測定も、各level内は全組base先行であり、版順は均衡していなかった。固定vectorのprocess順は交互。探索品質と速度の解釈ではこの制約に注意。結果は全件保持し選別していない。

## 固定vector：base → I1 → I2

3 seed（1001/1010/1020）の初期・3000・5000、計9 vector、3 process、各30無計時評価/点、process順 base/I1/I2 → I2/I1/base → base/I1/I2。各processの全270評価wall中央値：base **2.461/2.441/2.419 ms**、I1 **1.676/1.692/1.685 ms**、I2 **1.383/1.364/1.388 ms**。これは固定vectorのみでRunnerではない。測定に使った3 processのpeak RSSはbase 110164–110896、I1 110764–111048、I2 109832–110872 KiB（プロセス全体、差は配列単独効果ではない）。deep評価はplainとbit一致。

全forward S/IL/APL/両RLは9点でbaseとbit一致。I1/I2の物理IL Jac最大絶対差 `1.706e-13`。旧nodalの独立組立とI2を比較した最大絶対差はdR `2.513e-15`、dcore `3.544e-15`、dfull `3.029e-15`、外部複素S全4成分 `3.394e-15`、正規化IL `1.704e-11`、正規化残差Jac `1.136e-11`（`numerics.json`）。既存 #499 全列FD・境界片側、#521 複素S11/S21/S22 FD、設定外C厳密ゼロを緩和せず実行。さらに任意の複素lift、欠落・順不同の設定、variableなし、逆port、internalなし、有限Q等を確認。全境界・全極端入力の証明ではない。

RF-T010の旧dYおよびreorderは各 `(70,25,5,5)` = 700000 bytes、新I2のdRは `(70,15,2,2)` = 67200 bytes、最終IL Jacは復元 `(70,25)`。dHは `(7,4,4)`、dKは `(7,5,5)`。各Cは投影で1度だけ評価。TやdK・C投影等の一時配列もあり、これらの差をpeak RSSに直接換算しない。

STOP: forward完了を優先、SPD・Schur・inductor感度solve・非有限・zero transmissionの既存回帰を維持。旧dY展開を再生成せず `dK` の実/虚部最大値と最小scaleで元の展開overflowも検査、C係数と投影も有限検査する。ただし極端な有限値の複素除算・丸めにおける旧STOPとの完全同値は未証明で、未承認のSTOP緩和を主張しない。採用前に独立レビュー要。

## 通常CLI性能（3 seed、各3反復）

base/I2のplain/deepを各warmup後に実施したが、**旧スケジュールは各levelで全seed・全反復ともbase先行だった**。9 job中央値（process wall、起動等を含む）：base plain **16.902 s**／I2 **11.166 s**、base deep **17.778 s**／I2 **11.982 s**。plain user中央値 16.620→10.860 s、system 0.178→0.189 s、minor fault範囲 21966–22393→21830–21871、major fault 0。RSSは `getrusage(RUSAGE_CHILDREN).ru_maxrss` の累積最大で個別peakではなく、全jobで最大91828 KiB。詳細・各jobのCPU・faultは `results.json`。同一版のplain/deepで最終vector・CP・実消費は全組一致。

9 deep jobの中央値、RF evaluator親内の非重複区間：旧node Jacobian＋reorder＋Schurは約 **5.240 s**、新lift＋port Jacobianは約 **1.656 s**。Y→S感度は1.725→1.061 s、感度cascade 2区間合計0.932→0.745 s、wave 1.914→1.211 s、IL 0.232→0.158 s、restore 0→0.097 s。`rf_evaluate` 親13.474→8.054 s、上記以外の各forward/組立等を分離した残りotherは約0.303→0.250 s。各区間中央値の和は親中央値と厳密には一致せず、親子を加算しない。portのinductor/C投影は同一projection計時区間で、個別内訳は未取得。deepは計測負荷を含みplainの差と混同しない。

## 20 seed・同一5000 forward：品質

| 指標 | base | I2 |
|---|---:|---:|
| Search J 中央値／平均／最大 | 15.185／212.866／2954.320 | 28.943／459.196／5137.182 |
| Terminal J 中央値／平均／最大 | 110.996／1322.685／17926.296 | 221.875／3218.763／37594.758 |
| Terminal 最大違反dB 中央値／最大 | 1.406／12.002 | 1.614／16.673 |
| worst IL dB 中央値 | 2.156 | 2.364 |
| min H2 / H3 dB 中央値 | 29.492 / 28.900 | 29.332 / 28.924 |
| 適合数 | 0/20 | 0/20 |
| njev中央値、restart中央値 | 4244.5、13 | 4205、12 |

Terminal J対応勝敗12改善/8悪化。特にseed1004は5.298→14801.773、最大違反0.324→16.673 dB、seed1011は110.348→37594.758、1.405→12.512 dB。反対にseed1002は900.118→4.361、seed1009は4135.638→4.502。全40本は予算停止・非収束、MNA 2点pass、component pass。受動性・電力保存記録は各jobを参照。20 seed各1回のため母集団の傾向は断定不可。時間近似比較は任意条件であり、重大な品質差の採否が未確定のため未実施。

## 消費・残課題

- 3 seed plain/deep：warmup4＋計測36 job、200040 RF forward／14019040 samples／MNA80点。20 seed：warmup2＋計測40 job、210042 forward／14719992 samples／MNA84点。全82 job exit 4（予算停止）、正式EXP 0。固定vectorは9 process×9点×（warmup1＋plain30＋deep1）＝2592 evaluator呼出、181440 samples。単体テストは別。初回に旧入力 `/tmp/issue521-cli-data/inputs-5000` を使用してftol文字列でCLI exit 2、forward 0；新規入力生成し全測定を実施。
- `results.json` は各jobの入力・source/Plan・出力SHA、CP、実消費と品質を記録。巨大raw・checkpointは `/tmp/issue523-runner-v2/`、`/tmp/issue523-quality/`、失敗は `/tmp/issue523-runner/`、生成入力 `/tmp/issue523-inputs/`、固定vector raw `/tmp/issue523-fixed/` に残す。これらを研究証拠として無断削除しない。
- 上記は当時の記録。ユーザーの追加決定では20 seedの追加実行・同一時間近似は不要、I3は固定vector診断のみ。極端入力STOP同値、deep細分化とI3に関する追加結果は補足報告を参照。PRはDraftのまま独立レビュー待ち。有限格子であり、SRF・Q(f)・EM・公差・実測や連続周波数適合は未検証。

# #521 追加指示：固定commit・標準CLI比較（採否保留）

## 推奨と区別

**採否は独立レビュー待ち。本PRの本番 `model.py` はbaselineへ戻し、mainにも反映しない。** 20 seedで同一forward・同一時間近似とも高速化を観測したが、一部seedでTerminal品質が大幅に悪化し、他seedでは大幅改善した。20 seed・各1回の非収束探索から統計的同等性・系統的悪化・改善は断定できない。Issueの「顕著な悪化がある場合や採否が不明なら本番反映を留保」に従う。固定候補commitは下記に残り、実装diff・回帰は再検証可能。オーナー承認の「旧中間overflow再現不要」は有効だが、数値・速度・品質・採用判断は別である。

## 固定入力・実装・検証

- baseline main `7957fd60e685b6afb2f62fcdc1551ab8bdbfc43d`、D1固定commit `729e12453c882bf23b91cf8d79c02cb0f31b4392`、CD1固定commit `4d3def8f636f14938097f22965315fc22d6ab7ca`。候補commitには実model式と適合するテスト変更がある。本PRではこれらを後続commitでrevertし、比較用経路を本番に残さない。
- trial RF-T010 effective SHA `d50e6c9fef3e41b8258c00cbd14436a3bcb1d84444d50cf4a445ccf5d288e417`、base RF-T008、4L2C/25変数、6設定28別区間、Search 70・Terminal 476、TRF exact、ftol `1e-6`、x_scale `1`、restart_sigma `.1`、checkpoint1000、独立MNA `[0,111]`。bands/S2P/profile/bounds/gridは `cli_results.json` のPlan識別子を参照。20 seedのstartsは#513のSHAと照合。固定forwardは5000、同一時間近似は**両候補6800**。
- D1/CD1の実コードと元の診断候補は9固定vectorの全forward S/IL/APL/両RLとIL Jacが**bit一致**：`production_equivalence.json`。変更後の実コードで#499感度6、#519感度6、#521診断6をD1/CD1それぞれ実行しPASS、CD1は#503 TRF/deep 7もPASS。複素S11/S21/S22の全列FD・設定外C厳密ゼロ、inductor感度solve異常を確認。各候補が削除したpacked solveについてのみ人工注入を整理。旧forward、zero transmission、非有限Jacと既存前段検査は維持。正式な9点FDで旧新共通のIL 12件と小刻みS超過は `report.md` のまま、許容差を緩めていない。
- レビュー承認により、旧式の不要な中間overflowや消えたsolveの人工故障は再現しない。固定Z合成反例の高精度参照・旧STOPとの差、極小Zの別の桁落ちは `report.md` に残す。汎用Zの保証・新fallbackはない。

## 再現と条件の凍結

Python 3.12.15、NumPy 2.5.4、SciPy 1.18.1、WSL2 Ryzen 7 PRO 4750G、CPU affinity固定なし、OpenBLAS/OMP/MKL各1。共有hostでCPU温度・周辺負荷は未制御。固定commitの清潔なworktreeごとに標準 `scripts/run_rf_search.py develop` を子process実行。通常runにmonkey patch・内部Runner API呼出・一時Runnerを使わない。`generate_inputs.py` は入力生成のみ、`cli_compare.py`/`quality_cli.py` は既存CLIを起動するだけ、`collect_cli.py` は保存済み結果の監査のみ。

```sh
# baseline/D1/CD1の3 detached worktreeをそれぞれ上記固定commitに用意。
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1
PY="$PWD/.venv/bin/python"
uv run --frozen python project/diagnostics/issue521/generate_inputs.py /tmp/NEW/inputs-5000 --budget 5000
"$PY" project/diagnostics/issue521/cli_compare.py /tmp/NEW/calibration --python "$PY" --inputs /tmp/NEW/inputs-5000
uv run --frozen python project/diagnostics/issue521/collect_cli.py /tmp/NEW/calibration /tmp/NEW/calibration-compact.json
uv run --frozen python project/diagnostics/issue521/freeze_budgets.py /tmp/NEW/calibration-compact.json /tmp/NEW/frozen.json
# 結果の両budgetが同じ場合のみ、以下の6800をその凍結値に置換。異なる場合は別入力を用意しCLI比較scriptの拡張が必要。
uv run --frozen python project/diagnostics/issue521/generate_inputs.py /tmp/NEW/inputs-time --budget 6800
"$PY" project/diagnostics/issue521/quality_cli.py /tmp/NEW/quality --python "$PY" --fixed-inputs /tmp/NEW/inputs-5000 --time-inputs /tmp/NEW/inputs-time --frozen /tmp/NEW/frozen.json
uv run --frozen python project/diagnostics/issue521/collect_cli.py /tmp/NEW/quality /tmp/NEW/quality-compact.json
uv run --frozen python project/diagnostics/issue521/analyze_cli.py /tmp/NEW/calibration-compact.json /tmp/NEW/quality-compact.json /tmp/NEW/frozen.json /tmp/NEW/results.json
```

スクリプトのcheckoutパスは今回の `/tmp/issue521-cli-{base,d1,cd1}` に固定されるため、再現時は指定commitを同パスに用意するか、それらの定数を再現環境に合わせ、変更後のスクリプトSHAを記録する。`quality_cli.py` の計画はseed順に固定3条件の順序を巡回/反転し、その後同一時間候補2条件を交互順で実行。baseline 5000は両比較に兼用。開始前に凍結したbudgetは事後変更していない。入力manifest SHA: 5000 `b1aecd560566cf57364c73fffc43d85a03af4ea08386a79e958170f06edd8db4`、6800 `0f98b9b5fcd3d3a47194541be817afd25ddb25f4555eda6216e3609260c21add`、凍結記録 `0f2c5461ffbb73c99ebbef1e0718a66c10dc785632d83c838d034010ff5a0607`。設定、starts、全Plan/grid、source、選択vector、checkpoint、receiptの個別SHAは `cli_results.json`。全130成功jobのreceiptと登録ファイルを照合した。

入力生成の初回は`yaml`の指数表記解釈でftolが文字列となりwarmup前にCLI exit 2、forward 0。YAML出力に修正し新規パスに生成し直した。失敗も `/tmp/issue521-cli-data/calibration/` に保存。計時と探索品質には混ぜない。

実行時スクリプトSHA256: 入力生成 `3195c436ac6f52b77f9806f05f5e2fec6032169206273d9e94c723e00f822e27`、初回calibrationの `cli_compare.py` `27d1ef8403082a6d99be78d2bb68869d32828133393c7ec80a140792f960c9dd`、品質CLI `8df401bb6b021687a67828293b09e168e9254edecf28d0c36900c717b98c54e8`。`cli_compare.py` は追加1001再測定のseed/cycle引数を後から加え、再測定時/現行SHAは `f100c74495c91f2cfa74097f04434492e10fbdd66fb0d843bb78825bc341fffb`。凍結・集計後に変更していない。

## plain速度・品質

3 seed×3交互反復のbaselineと候補wall対応差中央値はD1 **-6.870 s**、CD1 **-6.852 s**。全9対応wall比の中央値から6800を事前凍結。20 seed本番比較の中央値はbaseline 22.908 s、D1 17.016 s、CD1 16.882 s；対応差中央値はそれぞれ -5.954、-6.087 s（20/20短縮）。追加で1001のwarmup各1＋3ペア再測定もbaseline 22.47–22.57 s、D1 16.60–16.76 s、CD1 16.60–16.69 s。固定kernelではD1/CD1の差は約0.08–0.09 ms/forwardであり、上記Runner差をそのままkernelの削減時間とは解釈できない。別のcProfile実行はbaseline 20.16 s、CD1 19.73 sとplain測定と異なり、計器付き値はplain時間や節約量へ加算しない。異なる探索軌跡・solver作業・計器・CPU状態を含むため、乖離の原因は未確定。詳細比較には `recheck.json` と保存pstatsを使う。

各分布のq1/q3/平均/最悪、paired勝敗とseed別差、nfev/njev/restart、選択vector・checkpoint、wall/CPUは `cli_results.json`。以下のJは違反二乗和で小さいほど良い。TerminalはSearchより密な有限格子。

| 条件 | Search J 中央値 | Terminal J 中央値 | Terminal最大違反dB 中央値 | paired Terminal J 改善/悪化 | 適合数 |
|---|---:|---:|---:|---:|---:|
| base 5000 | 14.707 | 110.762 | 1.325 | — | 0/20 |
| D1 5000 | 42.658 | 273.356 | 2.201 | 11 / 9 | 0/20 |
| CD1 5000 | 15.185 | 110.996 | 1.406 | 9 / 11 | 0/20 |
| D1 6800 | 6.622 | 52.094 | 0.855 | 12 / 8 | 0/20 |
| CD1 6800 | 8.734 | 66.599 | 1.060 | 10 / 10 | 0/20 |

同一5000でD1 seed1004はTerminal J **4.893→16546.364**、最大違反 **0.317→11.867 dB**、CD1 seed1002は **4.509→900.118**、**0.320→4.366 dB**、seed1017は **4.352→830.134**、**0.311→4.183 dB**。反対にCD1 seed1006は **7207.818→59.423**、D1 seed1009は **7834.279→6.277**。いずれも一試行の非収束有限探索であり、結果差を式の誤りや母集団の傾向と断定しない。同一時間近似でも顕著な悪化・改善は残る。6800実wall中央値はD1 22.760 s／CD1 22.545 sでbaseline 22.908 sに近いがseed別時間差はゼロではない。

130 CLI jobはすべて予算停止・exit 4（非収束）、物理component/SPD 130/130、Terminal受動性・電力保存checked、独立MNA 2点 130/130 pass。これらは実測・EM・SRF・Q(f)・公差・連続周波数の保証でも、正式RF適合でもない。

## 消費と保存

- 主比較：warmup3＋calibration27＋品質100＝130 job、RF 722130 forward / 50601880 samples、独立MNA260点、子process wall計2702.72 s／CPU計2687.29 s。
- 追加再測定：warmup3＋比較9＝12 job、RF 60012 forward / 4205712 samples、独立MNA24点。`recheck.json` は全runの監査済みcompact結果。
- 別cProfile 2 job：RF 10002 forward / 700952 samples、独立MNA4点。計器付きでplainと混ぜない。最初のshellはcProfileが0を返したことでbaseのみ実行後に正常終了し、その後CD1を別途実行した。両raw・pstatsを保存。
- 上記合計 144 job、RF **792144 forward / 55508544 samples**、独立MNA **288点**。初回CLI入力不正はforward 0。追加固定vector速度再測定は120回の計時とwarmup3回（計123 forward / 8610 samples）、単位テスト・初回FD bring-upの消費は別で未集計。新しい正式EXPは0。
- 戻し後の通常CI相当と保存監査は終了0、ログ `/tmp/issue521-final-ci.log` と `/tmp/issue521-final-audit.json`。GitHub ActionsはPR上の実際の状態を確認する。
- raw・checkpointとprofileは `/tmp/issue521-cli-data/` に保持。今回作成した3 worktree `/tmp/issue521-cli-base`、`/tmp/issue521-cli-d1`、`/tmp/issue521-cli-cd1` は固定commitの再現用に残している。保全済みかつ安全と判断できるまで削除しない。

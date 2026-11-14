# Issue #421 — Schurブロック抽出

## 結論

**Bを本番採用、独立レビュー待ち。** `(source, load, *middle)`に一度並べ替え、4ブロックはslice viewとする。全行列コピーの費用込みで、局所抽出と完全RF forwardの双方で改善を観測。Aも改善したが、局所抽出でBがより速く、本番も簡潔。BとAのplain順位は外れ値のため断定しない。Cのindexキャッシュは不要と判断。`node_admittance`、`solve(E,V)`、`R-U@solve(E,V)`、他のモデル・指標は変更していない。正式EXPや探索ではない。

- 最新main確認時 `523f3ab8d0d89323fd521c9b6738728f8babc54b`。本番測定HEAD `ec20ab59f8c9b244cfd609c4204e41c64485fd76`、source identity `703a61c1f38eb6c3d155da53cde81c6ef8f6b55636384616c6505ee909f7b9d4`。それ以降はテスト・CI選択・報告・記録のみ。未追跡 `.issue361-definition.json` は既存のまま不使用。
- **RF-T008 rev3 trial opt-in**, full_lpf, effective SHA `e682165c72d3a8b9f1384a2529f71bacfebfc9d17164d4af5af879e4a138b532`。active formal RF-F003 SHA `e12c42b11d12db7f20983c48cfa441ea96e362e533450d5862aa8a271c82af86`。正式条件への速度一般化ではない。
- #410固定100 vector、個別SHAを照合、入力ファイル SHA `e87355eb364073a5743062e8e4ee7c90c3012cbfb5e38bef6283860381736ba0`。6設定、28別区間、70点、mandatory 42。Plan SHA `8ac7bab9567918ae5c656fd449807ad2c38c1e1cad9e39c8ed217b95a569043e`、grid SHA `6805740a36f6100d7dec3e7308924242e909255f1ea2d287b7c734c400f98f26`。seed1002、start vector SHA `6203467121a4e37baaa51c471aaecb3174f3374f9ab955d6fbf101f7b5ce935f`、starts file SHA `63b671ea269656843df118230b7d920e91515188235809b6dd0efd667ac997ab`。
- bands SHA `1b1182e4c947059cb263c1af52ddf64236bd1fd9e83770cc844126576c7865fe`、入力S2P `ad266111ba1dc2b92f235d39f4a647ff271050bc11941c217661dd299ee59945`、出力S2P `b3cfc861bc0c8221f49328598c9d7d0766a6e94e42e990b6a50f6c90bf9a84da`。Plan/grid等の生成条件は[#413](issue413_report.md)参照。
- WSL2共有host AMD Ryzen 7 PRO 4750G、Python 3.12.15、NumPy 2.5.4、OpenBLAS 0.3.34.106.0 ILP64、各子process CPU affinity 2、OPENBLAS/OMP/MKL各1。コア専有、温度・周辺負荷は未制御。

## 局所内訳

実際の100個のY生成は計時外。各区間は同一Yの計器付き逐次測定、ms/100、各3 process中央値（Bは6 runのうち最初の3）。抽出はindex配列作成とBの全コピーを含み、solveはbatched solve、合成は積と減算、検査はfinite。ポート/middle tuple生成、例外分岐、node、全体のPython呼出や他処理は未測定。区間の合計は全forwardではない。

| | 抽出 | solve | 積・減算 | finite |
|---|---:|---:|---:|---:|
| 旧 | 3.174 | 3.234 | 1.193 | 0.353 |
| A | 1.439 | 3.080 | 1.178 | 0.328 |
| B | 0.961 | 3.136 | 1.171 | 0.353 |

100回の各区間にはtimer呼出が入り、空の連続`perf_counter`間隔中央値は約0.040 µs（1境界の下限目安、timer/ループ負荷の完全補正ではない）。区間は相互に包含しないが、timerとassertの影響がありplainとの差には使用しない。shapeはR `[70,2,2]`、U `[70,2,3]`、V `[70,3,2]`、E `[70,3,3]`。A/Bは診断用のPython関数として呼び出すため本番Pそのものではない。

## 完全forward plain、旧新同時期測定

別process、各process内で100 forward warmup後、同一100 vectorの`RFEvaluator.evaluate()`全体をタイマー2個だけで測定。各方式さらにwarmup process 1つ（集計外）、次に10 pair、偶数pair新→旧、奇数旧→新。A/Bは診断関数へのmethod置換、Pは**実本番method**。本番測定での旧はmainの旧methodを診断scriptにそのまま複製しmethod置換（本番mainそのものの実測ではない）。本番実装前のA/B実測は旧main実methodで別途実施し方向を確認。初回はB配列の2外れ値（+6.644/+6.888 ms）、最終Bでは+17.446/−44.943 msを含み、選別しない。全run・setup・wall/CPU・順序・warmup・environmentは[本測定JSON](issue421_verified.json)、[初回JSON](issue421_results.json)に保存。

| 比較 | 旧/新wall中央値 ms/100 | pair差中央値 [最小,最大] ms | 新が速い |
|---|---:|---:|---:|
| 旧/A | 50.715 / 49.114 | −1.554 [−9.607,+0.323] | 9/10 |
| 旧/B診断 | 52.745 / 48.878 | −4.416 [−44.943,+17.446] | 9/10 |
| 旧/P本番 | 50.803 / 49.547 | −1.456 [−2.729,−0.507] | 10/10 |

Pの各pair（旧wall/CPU → 新wall/CPU、ms/100。全外れ値含む）：

| pair | 旧 | P |
|---:|---:|---:|
| warmup | 51.808/51.808 | 47.518/47.518 |
| 0 | 51.191/50.871 | 49.784/49.782 |
| 1 | 51.119/51.119 | 49.613/49.614 |
| 2 | 50.420/50.418 | 49.709/49.709 |
| 3 | 49.988/49.962 | 49.481/48.297 |
| 4 | 52.657/52.643 | 51.294/51.293 |
| 5 | 51.594/51.575 | 48.882/48.881 |
| 6 | 50.372/49.929 | 48.262/48.262 |
| 7 | 50.488/50.489 | 47.759/47.760 |
| 8 | 52.391/51.635 | 50.731/50.664 |
| 9 | 49.460/49.459 | 48.321/48.300 |

#417の計器付き8.590 msとの差を削減量と扱わない。初回旧main source identity `b701aee50fa2a506eaef942109fb93a96fe8405e7c0b1e7715b539f6293e467e`、初回driver SHA `2a5da046ea2befd3a9b41ce4f9e1560ead6fad21a3d5b6550e85d0586001912d`（当時の未commit版、同じバイトのdriverは現treeに未保存）。初回旧/Aは旧50.193→新48.714、pair差中央値−1.572、10/10、旧/Bは旧50.957→新48.433、−3.383、8/10。採否は再現可能な本測定に基づく。Solverは必要性が低く未実行。

## 科学・数値検証

本測定で旧/A/B/P全100 vector×70点を同順比較、全S複素4要素、IL/APL/両RL、worstIL、mandatory_g 42の最大絶対差は全項目**0、ビット一致**（許容atol 1e−9 / rtol 1e−11）。100入力でSTOPはいずれも0。代表vector 0/49/99の全70点をそれぞれ旧/A/B/Pで独立branch-current MNA比較、固定S2P・複素負荷、受動性、各枝損失と電力保存を確認。Pの独立値最大差2.2134e−12（許容絶対1e−9）。独立MNAにSchur変更なし。

追加3テストで非連続・逆順ポート、内部ノード0、複素対称非Hermitian E、実tree・接地/並列異Q/0 C、Y不変性、特異Eの`schur_solve_failed`と非有限Rの`schur_nonfinite` sample 1を確認、両STOPは旧複製とPで一致。既存回帰でnode_nonfinite先頭index、非SPD・各種例外、ゼロ透過、F003/T005/T006/T007/T008、T006追加区間、6設定と28別区間を確認。全ての異常入力で一致する証明ではない。

実行済み：`test_issue421_schur.py` 3、`test_issue410_c_assembly.py` 5、`test_issue309_rf_core.py` 7、`test_phase2_branch_mna.py` 6、`test_phase2_numeric_diagnostics.py` 3、`test_phase2_generic_coupled_lc.py` 2、`test_issue415_production_stamps.py` 3、`test_rf_f003_t005.py` 6、`test_issue307_constraints.py` 5、`test_ci_test_selection.py` 16。いずれもPASS。storage auditは正常終了したがEXP-058 running、EXP-116/117 preservation_incompleteを含み、全EXP完全性PASSではない。CIと独立レビューは別ゲート。

初回は44子process×200 forward＋capture 300＝9,100 forward、637,000 requested samples、detailで900 nodal assembly、独立MNA 630 samples。本測定は66子process×200＋capture 400＝13,600 forward、952,000 samples、detailで1,200 nodal assembly、独立MNA 840 samples。上記には単体テストを含まない。

## 再現・限界

```bash
uv sync --frozen
uv run --frozen python project/diagnostics/issue421_benchmark.py --output /tmp/issue421-new.json --pairs 10
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 uv run --frozen python -m unittest discover -s tests -p test_issue421_schur.py -v
```

出力先は未存在とする。driver SHA `a64e31ad313d577918406ddaafdeff40275064ca26b76219ce21b131a4edf988`。本測定JSON SHA `8b7cf76beb47bac20017a9f4046f7769d5a641e92d81afdbe122f01a1d3a6e94`、初回JSON SHA `8b07e3b94bd65d08b039490e7eeb653dad16256cc90ca1c8896e097db4bd9173`。JSONは各processのsource identityと全条件・結果を含む。プロファイルはこのハードウェアと有限grid・固定入力に限る。連続周波数、全vector MNA、EM、SRF、Q(f)、公差、実測や物理的実現性は未検証。

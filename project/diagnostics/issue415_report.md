# Issue #415 — 本番six-matmulの旧main比較

## 範囲・識別

- 旧main `c24c0c3b91ef78cbb7dcf72bf3c328387cca9d4f`、計測した新実装 `5d5cb7badd4924f201c8253678f8b9e5700b88fd`。以降のcommitはテスト・CI選択・報告のみ。旧／新source identity SHAはそれぞれ `decd146df1bcf3fe6915553c82e48faa1b467aba5e9a9f7205547017948334d7`／`731af4c90f2f698419a72e0bacea0b9686d9887f854e64badb436999e1f24500`。
- RF-T008 rev3 **trial opt-in**／full_lpf、effective SHA `e682165c72d3a8b9f1384a2529f71bacfebfc9d17164d4af5af879e4a138b532`。RF-F003や別CPUへの速度一般化はしない。active formal F003 SHA `e12c42b11d12db7f20983c48cfa441ea96e362e533450d5862aa8a271c82af86`。
- #410の固定100vector（ファイルSHA `e87355eb364073a5743062e8e4ee7c90c3012cbfb5e38bef6283860381736ba0`、個別SHAも照合）、6設定・28区間・70点、mandatory 42。plan SHA `8ac7bab9567918ae5c656fd449807ad2c38c1e1cad9e39c8ed217b95a569043e`、grid SHA `6805740a36f6100d7dec3e7308924242e909255f1ea2d287b7c734c400f98f26`、start vector SHA `6203467121a4e37baaa51c471aaecb3174f3374f9ab955d6fbf101f7b5ce935f`、starts bytes SHA `63b671ea269656843df118230b7d920e91515188235809b6dd0efd667ac997ab`。bands/S2PのSHAと構成は[#413報告](issue413_report.md)と同一。
- Python 3.12.15、NumPy 2.5.4、SciPy 1.18.1、OpenBLAS、WSL2共有host AMD Ryzen 7 PRO 4750G、子process affinity CPU 2、OPENBLAS/OMP/MKL各1 thread。core専有・温度や他負荷は制御していない。
- 本番は枝順/Q/接続のみbytes-backedの `[B,N²]` stampにして固定／可変を分けず、各forwardで6行Cとのmatmul。C/L/kのcacheや切替フラグはない。旧と新は別worktreeの**実本番経路**を実行し、試作同士の比較ではない。

## 数値・科学回帰

旧新の全100 vector×70点、S全4要素、IL/APL/入力RL/出力RL、worstILとmandatory_g全42要素を順序のまま比較。atol 1e−9 / rtol 1e−11でPASS、いずれもビット一致ではない。最大絶対差：S 1.951e−14、IL 9.326e−14、APL 3.642e−14、入力RL 7.674e−13、出力RL 3.020e−13、worstIL 1.688e−14、mandatory_g 9.237e−14。

代表vector 0/49/99の各全70点を旧新で独立branch-current MNA、外部S2P・複素負荷込みの受動性、枝損失、電力残差で照合。新の独立値との差は最大2.214e−12（絶対許容差1e−9）。代表サンプルに限る。

実行PASS：`test_issue413_c_stamps.py` 7件、`test_issue410_c_assembly.py` 5件、`test_issue309_rf_core.py` 7件、`test_issue389_minimal_worker.py` 4件、`test_phase2_branch_mna.py` 6件、`test_phase2_numeric_diagnostics.py` 3件、`test_issue415_production_stamps.py` 3件、`test_ci_test_selection.py` 16件。既存回帰はF003/T005/T006/T007/T008、T006追加帯域、0可変枝、GND・異Q並列、外部値／不正サンプリング、非SPD・悪条件、node/Schur/Y→S/wave/available-gain STOP、ゼロ透過と+Inf、不変応答を含む。新テストは0 C枝・stamp不変性・変更時再構築・node非有限の先頭異常sample index 1も確認。全可能入力のSTOP位置の同一性を証明するものではない。storage auditは正常終了したが既存EXP-058 running、EXP-116/117 preservation_incompleteを含み、全EXP完全性PASSではない。

## Plain性能（外れ値を含む）

各方式warmup各1子process後、10 pair、偶数pairは新→旧、奇数は旧→新。固定forwardは各子processで100 vector warmup後、全指標を生成する100 forward全体のみ計時。Solverは別processで同一start/seed 1002、評価100/restarts 0のplain `worker.solve()`のみを計時。setupは別計時。表の各セルは **wall / CPU / setup wall / setup CPU [ms]**、warmupは集計外。全runを表示し外れ値を除外していない。

| pair | fixed旧 | fixed新 | solve旧 | solve新 |
|---:|---|---|---|---|
| warmup | 60.704/60.704/163.260/155.929 | 51.334/51.333/163.661/158.761 | 77.625/77.627/229.847/225.157 | 149.803/149.481/243.994/238.877 |
| 0 | 58.447/57.923/157.549/151.980 | 51.267/51.266/164.230/159.016 | 74.522/73.820/237.514/232.699 | 63.382/63.381/237.773/232.966 |
| 1 | 58.309/58.309/177.392/172.744 | 51.541/51.542/162.114/157.107 | 72.303/72.303/226.924/222.114 | 65.421/65.105/236.519/231.620 |
| 2 | 58.822/58.820/156.041/151.299 | 50.724/50.725/161.565/157.037 | 78.394/78.395/228.364/223.361 | 63.576/63.576/234.626/229.777 |
| 3 | 59.885/59.863/156.256/151.552 | 50.847/50.847/161.007/156.242 | 75.881/75.798/232.746/227.967 | 115.112/114.732/237.414/232.262 |
| 4 | 57.641/57.640/172.581/167.762 | 50.988/50.986/161.349/156.762 | 72.594/72.595/274.657/267.759 | 62.993/62.995/236.876/231.780 |
| 5 | 58.752/58.751/153.004/148.307 | 51.252/51.254/159.308/154.573 | 73.285/73.284/233.560/228.725 | 63.358/62.936/273.522/264.919 |
| 6 | 61.146/60.605/156.641/151.832 | 50.998/50.997/160.897/156.258 | 71.321/70.466/228.736/223.349 | 63.257/63.257/240.427/235.650 |
| 7 | 57.658/57.658/155.060/150.383 | 50.775/50.775/162.053/157.259 | 73.263/73.263/228.615/223.614 | 63.649/63.229/236.518/231.852 |
| 8 | 72.307/72.307/159.976/155.359 | 49.837/49.817/162.203/157.421 | 72.717/72.236/228.116/223.417 | 64.752/64.753/240.308/235.588 |
| 9 | 59.499/59.498/156.399/151.624 | 51.780/51.780/161.665/156.733 | 71.962/71.961/224.168/219.457 | 91.390/91.393/234.259/228.867 |

固定forward wall中央値は旧58.787→新50.993 ms/100、対応差中央値−7.609 [−22.470, −6.653] ms、新が速い10/10。Solver wall中央値は旧72.990→新63.612 ms/100 nfev、対応差中央値−8.833 [−14.818, +39.231] ms、新が速い8/10。方向は#413と整合するが共有hostの外れ値の原因は未特定で、常に速い・一般的な改善率とはしない。

Solverは全22 run（warmup含む）nfev100、evaluation_budget_exhausted、未収束。旧新それぞれのrun内結果は一致するが、旧新のbest_x最大差約8.254e−4、best_fun差−0.004521675で軌道が変わり得る。固定候補比較とは区別し、RF適合や収束を主張しない。

計測消費：fixed 22子process×200＝4,400 forward、Solver 22×(100＋観測1)＝2,222 forward、同値性200 forward、計6,822 forward／477,540 requested samples。独立MNAは旧新各210 sampleで別。単体テストと事前Solver smokeは別。

## 再現・限界

```bash
uv sync --frozen
git worktree add --detach /tmp/rf-lpf-issue415-main c24c0c3b91ef78cbb7dcf72bf3c328387cca9d4f
uv run --frozen python project/diagnostics/issue415_compare.py \
  --old /tmp/rf-lpf-issue415-main --new "$PWD" --output /tmp/issue415-results.json --pairs 10
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  uv run --frozen python -m unittest discover -s tests -p 'test_issue415_production_stamps.py' -v
```

出力先は未存在にする。計測driver SHA `1c973e0bc4bf9f1504f092d0da1d9648884d0fbb5610ff93af62f79ca834e645`。今回の全run・Solver出力を含む一時JSON SHA `4d0b9fde9beed1c1c427e43ff934c5dd405d211bddaa8e1e40975af637e69213`、結果と外れ値は上表に保持。新たなEXP・正式Campaignはない。100 vector全ての独立MNA、極端overflowの全STOP同一性、別BLAS/CPU、連続周波数、EM/SRF/Q(f)/公差/測定は未検証。独立レビュー・CIは別ゲート。

# Issue #427 開発専用 Worker・限定検証

## 境界と再現

正式EXP・Campaignではない。main `f52742bdbed5731c2838d165a45c5cc67a9491f0` を基準とした開発差分で実施。正式Worker、Runner、G0〜G5、正式保存契約、RF Core、Optimizerは変更していない。`DevelopmentWorker`はPlanと明示完全vectorを取り、外部一時ディレクトリの新規checkpointを要する。復元・費用予約・正式入口ではない。`MinimalWorker`は既存の単独ベンチ基準として残すが、開発用の複数Solverは一経路。Formal Worker置換は別Issue。

```sh
uv sync --frozen
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 uv run --frozen python -m unittest discover -s tests -p 'test_issue427_development_worker.py' -v
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 uv run --frozen python project/diagnostics/issue427_benchmark.py
```

測定環境 Python 3.12.15 / NumPy 2.5.4 / SciPy 1.18.1、BLAS/OMP/MKL各1 thread。対象は明示trial `RF-T008`、effective SHA `e682165c72d3a8b9f1384a2529f71bacfebfc9d17164d4af5af879e4a138b532`、full_lpf。Plan SHA `8ac7bab9567918ae5c656fd449807ad2c38c1e1cad9e39c8ed217b95a569043e`、step grid SHA `6805740a36f6100d7dec3e7308924242e909255f1ea2d287b7c734c400f98f26`、全6設定28個別区間、通過域2点/区間・阻止域3点/区間、70 samples/forward。seed 1002、start vector SHA `6203467121a4e37baaa51c471aaecb3174f3374f9ab955d6fbf101f7b5ce935f`、入力は `issue377/baseline.yaml` と `issue401_starts_1002.json`。bands・入出力S2PのSHA、全grid、ファイルごとのsource SHA等は [最終測定raw](issue427_benchmark_final.json) に記録。実行時HEADは上記main、source identity SHA `84df4b853038d54166b766c86855128fcd738ce51a6e3c762c68565b151d69ac`（未commit追加ソースを含むファイル別SHAもrawに記載）。

## 実際の回帰

- `test_issue427_development_worker.py` 6件 PASS。実RF-T008で3 Solverを旧 `FixedStageEvaluation` + 同一Optimizerと比較し、完全Solver結果・停止理由・使用forward数が一致（各3回、限定budget）。保存bestの完全vectorから同条件で再評価し指標一致。複素S、IL/APL/両RL、ordered mandatory_gを旧経路と完全一致で比較。全6設定28区間、SPD異常STOP、既存 `rank_candidates` とのbest一致。Terminal両端2点の独立MNA・受動性・電力保存がPASS。複数step・異なるgridも確認。
- checkpoint初回、N未満、N到達時の未保存改善、改善なし、step終了時flush、grid切替、書込失敗STOP・再実行拒否を確認。保存頻度テストの制御済み評価値はmockでありRF結果ではない。
- `test_issue389_minimal_worker.py` 4件、`test_issue394_physical_path.py` 5件、`test_issue315_fixed_stage.py` 10件、`test_phase2_branch_mna.py` 6件、`test_issue311_performance.py` 10件、`test_issue317_fixed_worker.py` 30件 PASS。各コマンドは上記unittest discoverのパターン名を対応ファイルに変更。旧正式経路のテストPASSはG0〜G5通過や科学承認を意味しない。

## 短時間計測

Hybrid、評価上限100、restart 0、N=100。下表は [final raw](issue427_benchmark_final.json) のwarmup除外4 run、実行順 development/minimal/minimal/development。秒、solverはinclusive、I/Oはsolver内部のatomic write/fsyncのinclusive時間。Developmentはsolver以外にSelection/Terminalを実施するためtotalはMinimalと直接比較できない。Minimalのsolver区間はsolve後の出力物理検証を含み、Developmentのsolver区間はOptimizer本体であり、区間も厳密には同一でない。計時ラッパーもDevelopment側にのみ存在。

| 経路 | setup | solver | checkpoint I/O（回数） | total | search forward |
|---|---:|---:|---:|---:|---:|
| Development | .1394 | .0760 | .0147 (2) | .4732 | 100 |
| Minimal | .1168 | .0584 | 0 (0) | .1752 | 100 |
| Minimal | .1526 | .0596 | 0 (0) | .2121 | 100 |
| Development | .1232 | .0747 | .0165 (2) | .4560 | 100 |

全runのSolver best SHA `8600b8199f90cc0e9c60f397f45e2ca57b0fc08470a4bbbd95b2c9855b3d1203`、終了理由 `evaluation_budget_exhausted`、未収束。単純なsolver時間差は約15〜18msだがサンプルが少なく区間・計時負荷も異なるため一般的なオーバーヘッド率やNの最適値は断定しない。直前の探索的測定 [他テスト並行](issue427_benchmark_concurrent.json) と [単独](issue427_benchmark_early.json) は旧開発差分であり、ばらつきと並行負荷があるため最終比較に混ぜない。計測はwarmupを含め全runを保存し、成功runのみを選別していない。

## 残る制約

有限grid、短budgetの限定等価性であり、全連続周波数・全候補の受動性/電力保存・独立MNAを保証しない。Terminal以外の独立検査は明示依頼がなければ `not_run`。SRF、Q(f)、EM、公差、実測は未検証。Solverの収束とstrict RF適合は別。新規EXP・大規模探索・正式Runner接続は実施していない。checkpointは一時bestの保全であり再開可能性・コスト保証ではない。ChatGPT独立レビューおよびCIは別途必要。

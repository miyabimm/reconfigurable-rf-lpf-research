# Issue #427 開発専用 Worker・限定検証

## 境界と再現

正式EXP・Campaignではない。main `f52742bdbed5731c2838d165a45c5cc67a9491f0` を基準とした開発差分で実施。正式Worker、Runner、G0〜G5、正式保存契約、RF Core、Optimizerは変更していない。`DevelopmentWorker`はPlanと明示完全vectorを取り、system tmp内・checkout外の**未存在のcheckpointディレクトリ**を自ら新規作成する（親は既存であること）。復元・費用予約・正式入口ではない。`MinimalWorker`は既存の単独ベンチ基準として残すが、開発用の複数Solverは一経路。Formal Worker置換は別Issue。

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

## 短時間計測（追記型変更前）

以下は追記仕様適用前の旧実装の記録であり、新実装の速度とは扱わない。Hybrid、評価上限100、restart 0、N=100。下表は [final raw](issue427_benchmark_final.json) のwarmup除外4 run、実行順 development/minimal/minimal/development。秒、solverはinclusive、I/Oはsolver内部のatomic write/fsyncのinclusive時間。Developmentはsolver以外にSelection/Terminalを実施するためtotalはMinimalと直接比較できない。Minimalのsolver区間はsolve後の出力物理検証を含み、Developmentのsolver区間はOptimizer本体であり、区間も厳密には同一でない。計時ラッパーもDevelopment側にのみ存在。

| 経路 | setup | solver | checkpoint I/O（回数） | total | search forward |
|---|---:|---:|---:|---:|---:|
| Development | .1394 | .0760 | .0147 (2) | .4732 | 100 |
| Minimal | .1168 | .0584 | 0 (0) | .1752 | 100 |
| Minimal | .1526 | .0596 | 0 (0) | .2121 | 100 |
| Development | .1232 | .0747 | .0165 (2) | .4560 | 100 |

全runのSolver best SHA `8600b8199f90cc0e9c60f397f45e2ca57b0fc08470a4bbbd95b2c9855b3d1203`、終了理由 `evaluation_budget_exhausted`、未収束。単純なsolver時間差は約15〜18msだがサンプルが少なく区間・計時負荷も異なるため一般的なオーバーヘッド率やNの最適値は断定しない。直前の探索的測定 [他テスト並行](issue427_benchmark_concurrent.json) と [単独](issue427_benchmark_early.json) は旧開発差分であり、ばらつきと並行負荷があるため最終比較に混ぜない。計測はwarmupを含め全runを保存し、成功runのみを選別していない。

## 2026-11-15 追記仕様・再検証

Issue #427追記とPR #428レビューに従い、checkpointは同一ファイルの上書きを廃止し、新規専用ディレクトリ内の `000001.json`, `000002.json`, … に1イベントずつ保存する。全体通番はstep間で継続し、各recordにはstep内forward数と個別grid・Plan・RF・vector等を含む。履歴を全件メモリに保持しない。一時ファイルのfsync後、同一ファイルシステム上のhard linkで既存名を**置換せず**原子的に公開し、ディレクトリをfsyncする。未対応filesystemや書込・同期失敗はSTOP、再開不可。公開後にfsyncが失敗した場合はファイルが残っていても成功扱いしない。既存の`storage.atomic()`はreplace方式のため、保存済み名を絶対に上書きしないこの限定用途では使用しない。正式保存経路は不変。

Selectionは順位に必要なstatus・policy/mode/grid/requirements同一性・strict・IL・max/sum violationだけを保持し、`rows` / `samples` / `mandatory_g` / 詳細requirementsは蓄積しない。既存 `rank_candidates` とTerminal詳細・独立MNAは維持。Solver endpoint等以外のRF-bestを候補プールに加える変更は行っていない。

修正後、`test_issue427_development_worker.py` 9件 PASS。保存3件の古いバイト保持、step移行と通番・forward数、既存dir/ファイル衝突、2回目のI/O失敗時の先行記録保護、Selection上限付き3候補の旧詳細評価による順位・除外・上位Terminal詳細一致を追加。既存 `issue389` 4件、`issue394` 5件、`issue315` 10件、`phase2_branch_mna` 6件、`issue311` 10件、`issue317` 30件を再実行し全PASS。実行コマンドは上記と同じunittest discoverでファイルパターンを変更したもの。

修正後も同じ短時間RFベンチを単独実行した。基準HEAD `c7fdc0d237b8c8aa6ce3bc07d309453ffcd47c54` 上の未commit差分、source identity SHA `1bb5f85dc41df5ca101e9ed5289d380cff072c812ecb33d5b60a12496cffad78`、[全runとファイル別SHA](issue427_benchmark_append.json)。RF ID/effective SHA、Plan/grid、start/seed、環境は上記と同じ。warmup除外の順序はDevelopment/Minimal/Minimal/Development：solver各 `.0839 / .0670 / .0564 / .0809` 秒、setup `.1220 / .1134 / .1141 / .1254` 秒、total `.4529 / .1804 / .1705 / .5024` 秒。Developmentのcheckpoint I/Oは `.0171 / .0177` 秒・各2回。全run search 100 forward、solver best SHAと予算切れは変更前と一致。実行範囲・計時境界は上記同様に異なり少数測定なので、差やNの最適値の一般化はしない。

## 残る制約

有限grid、短budgetの限定等価性であり、全連続周波数・全候補の受動性/電力保存・独立MNAを保証しない。Terminal以外の独立検査は明示依頼がなければ `not_run`。SRF、Q(f)、EM、公差、実測は未検証。Solverの収束とstrict RF適合は別。新規EXP・大規模探索・正式Runner接続は実施していない。checkpointは一時bestの保全であり再開可能性・コスト保証ではない。ChatGPT独立レビューおよびCIは別途必要。

# Issue #429：単一Job DevelopmentWorker接続

## 範囲

開発専用、1 seed × 1 arm。Worker直接呼出しとの同値および保存／STOPを検査。既存正式runner、G0〜G5、親費用台帳、resume、RF条件／数式は変更しない。大規模探索・正式EXPは **not_run**。

## 短い実RF smoke

- 実行source HEAD `c408fecfd9ac148e44747be40cf368d7d6c276f5`、source identity SHA `8543a4c7e698a38d6b3779cfb9d203c1658d6b42e283913b0e74cc48ff8a642d`。Python 3.12.15 / NumPy 2.5.4 / SciPy 1.18.1、OPENBLAS/OMP/MKL各1 thread。実行時の完全sourceファイルSHAは一時出力のinputに記録。既存の無関係な未追跡`.issue361-definition.json`には触れていない。
- 入力 `project/diagnostics/issue377/baseline.yaml`、`project/diagnostics/issue401_starts_1002.json`、seed 1002 / arm hybrid、原本vector SHA `6203467121a4e37baaa51c471aaecb3174f3374f9ab955d6fbf101f7b5ce935f`。Plan SHA `8ac7bab9567918ae5c656fd449807ad2c38c1e1cad9e39c8ed217b95a569043e`。
- **trial RF-T008** 明示opt-in / full_lpf、effective SHA `e682165c72d3a8b9f1384a2529f71bacfebfc9d17164d4af5af879e4a138b532`。全6設定・28別区間、bands SHA `1b1182e4c947059cb263c1af52ddf64236bd1fd9e83770cc844126576c7865fe`、input/output S2P SHA `ad266111ba1dc2b92f235d39f4a647ff271050bc11941c217661dd299ee59945` / `b3cfc861bc0c8221f49328598c9d7d0766a6e94e42e990b6a50f6c90bf9a84da`。
- grid：coarse 70点 SHA `6805740a36f6100d7dec3e7308924242e909255f1ea2d287b7c734c400f98f26`、selection 84点 SHA `29e918981abda38c4becb14b1874bd7af5380b4ccaebecb5faafab6f9a51bfdb`、terminal 476点 SHA `28ee5b630e4842b183a7c36fd610cc32e2509c0044c6a5848ce2fbd147a22e29`。

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
uv run --frozen python scripts/run_development_worker.py \
  --config project/diagnostics/issue377/baseline.yaml \
  --starts project/diagnostics/issue401_starts_1002.json \
  --seed 1002 --arm hybrid --output /tmp/issue429-committed-smoke-AOPKwv/job \
  --spot-checks '{"terminal":[0,111]}'
```

終了コード4、`not_converged`、`evaluation_budget_exhausted`。step 100、selection 2、terminal 1、計103 forward。checkpoint 2件。terminal finite-grid strict **FAIL**、terminal独立MNA・受動性・電力保存は指定2 sampleのみPASS。全帯域MNA、連続周波数、Q(f)、SRF、EM、公差、実測は未検証。solverの収束、有限格子strict、独立検証、物理成立は別判定。

一時出力 `/tmp/issue429-committed-smoke-AOPKwv/job` を診断用に保持。実装コミット前にも同一条件で `/tmp/issue429-smoke-SBKyzW/job` を実行・保持（HEAD `0feea0866bf07e3598346020ca342e45f27985f1`、source SHA `9b14d60afbf3a1bee32b3d3520ca60565c2e81eed5b22e55460794be9af04d77`、同じ未収束）。一時出力は正式EXP証拠ではない。

## 検証

すべて `uv run --frozen`、テスト時も各thread=1。

- `python -m unittest discover -s tests -p 'test_issue429_development_runner.py' -v`：3 PASS。RF-T008の2 step別gridで直接Worker・CLI・Runner戻り値／保存結果を完全比較、selection/terminal・独立検証、checkpoint通番/grid/vector SHA・直接出力とのバイト一致、既存出力保護、seed/arm/SHA不一致、Git内拒否、Worker例外、input/result保存失敗・非再試行。
- `test_issue427_development_worker.py`：9 PASS。`test_issue389_minimal_worker.py`：4 PASS。`test_issue317_fixed_worker.py`：30 PASS。
- `python scripts/audit_new_experiment_storage.py audit`：終了0。監査出力の個別stage/validationはそれぞれの状態のままであり、一括で科学的PASSとはしない。
- GitHub CI：PR HEAD `ebafe7f3fd9ddceebe1951928518b3b9b3316bd6` の[Phase 2 smoke](https://github.com/miyabimm/reconfigurable-rf-lpf-research/actions/runs/43679303496) PASS（manual追加topology scienceは未実行）。この行を記録した後のHEADの状態はPR上で確認する。
- ChatGPT独立レビュー待ち。開発runnerには費用予約・G0〜G5・正式raw契約がなく本番入口ではない。

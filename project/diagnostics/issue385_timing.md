# Issue #385：実RF短時間Jobの内部タイマー

## 条件・事前照合

最新main `3e1fe8f56769a557eb84a4ab57301e6c1ca41806` を実行sourceとして、新規に `load_preflight` と `source_identity` を実行した。Plan canonical SHA `8ac7bab9567918ae5c656fd449807ad2c38c1e1cad9e39c8ed217b95a569043e` は同一設定のため#377と一致するが、今回新規にfreezeした。source SHA `33f822e15b4a54900f54d0576b2c765e42c88920c61c6866aafacdcd71004587`。RF-T008 rev3 trial明示opt-in、effective SHA `e682165c72d3a8b9f1384a2529f71bacfebfc9d17164d4af5af879e4a138b532`、full_lpf、6設定・28別区間・固定S2P。active formal RF-F003は変更なし。bands SHA `1b1182e4c947059cb263c1af52ddf64236bd1fd9e83770cc844126576c7865fe`、入力/出力S2P SHAはそれぞれ `ad266111ba1dc2b92f235d39f4a647ff271050bc11941c217661dd299ee59945` / `b3cfc861bc0c8221f49328598c9d7d0766a6e94e42e990b6a50f6c90bf9a84da`。

25変数seed1002のvector SHA `6203467121a4e37baaa51c471aaecb3174f3374f9ab955d6fbf101f7b5ce935f` を既存vector_shaで照合。search grid 70 samples、SHA `6805740a36f6100d7dec3e7308924242e909255f1ea2d287b7c734c400f98f26`、`max_evaluations=100`、`max_restarts=0`。事前Planのsearch上限7,000、selection最大336、terminal 476、合計上限7,812 samplesはJob cap 8,000内。anytimeなし、dense別枠でnot_run。#377累積枠は引き継がない。

Python 3.12.15 / NumPy 2.5.4 / SciPy 1.18.1、Linux 6.18.58.1 WSL2、Ryzen 7 PRO 4750G、OPENBLAS/OMP/MKL各1 thread。#377と記録された主要環境は同等、共有負荷とfilesystem cacheは非制御。計測は内部タイマーのみでcProfile・外部監視なし。

```sh
cd /home/user/src/reconfigurable-rf-lpf-issue385
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 PYTHONPATH=src \
 uv run --frozen python scripts/run_rf_search.py develop \
 --config project/diagnostics/issue377/baseline.yaml \
 --starts /home/user/issue377-rf-profile-20261110/inputs/starts-1002.json \
 --storage-mode window100 --output /home/user/issue385-raw \
 --timing-output /home/user/issue385-timing.json > /home/user/issue385-run.log 2>&1
```
出力先は未存在の別パスを要する。上記は実行記録であり再実行許可ではない。

## Job別包含wall（加算不可）

| region | count | wall s | mean ms | failed |
|---|---:|---:|---:|---:|
| total | 1 | 10.058 | 10057.960 | 未記録 |
| job_worker | 1 | 9.227 | 9226.609 | 0 |
| solver:coarse:hybrid | 1 | 2.313 | 2312.957 | 0 |
| solver_callback | 100 | 2.297 | 22.966 | 0 |
| evaluation | 103 | 3.290 | 31.942 | 0 |
| physical_validation | 103 | 0.061 | 0.587 | 0 |
| rf_forward | 103 | 0.109 | 1.056 | 0 |
| requirements | 103 | 0.126 | 1.227 | 0 |
| checkpoint | 9 | 2.937 | 326.297 | 0 |
| window_checkpoint_save | 20 | 6.297 | 314.835 | 0 |
| source_contract | 20 | 2.199 | 109.973 | 0 |
| evaluation_initialization | 1 | 0.160 | 159.627 | 0 |
| hybrid_local_run:coarse | 1 | 2.313 | 2312.678 | 1 |
| hybrid_restart_generation:coarse | 未観測 | 未観測 | 未観測 | 未観測 |

`total` のfailedはタイマー形式に存在しない。Hybrid eventは未検証で、local failed=1はrawの評価予算枯渇・未収束と整合するが、独立した例外分類ではない。領域は包含・重複し、window保存はsource契約を含む。window保存6.297秒はworker 9.227秒中の大きな候補で、RF forward 0.109秒より大きいが、plain/Python変換・SciPy差分・RF内部CPUや保存内の各処理は未分離。タイマーオーバーヘッドも未測定。

#377の別HEAD・cProfile＋外部監視の100-forward Job wall 19.200秒、`_save` 12.685秒、RF evaluator 0.134秒とは計測器・範囲・負荷が異なる。別Jobの3,000評価 local 77.445秒も粒度が異なり、直接速度比や60秒/20秒達成を認定できない。

## 科学rawとの突合・限界

終了コード4、parent flow completed、worker not_converged、stop `evaluation_budget_exhausted`。search 100 forwards / 7,000 samples、nfev 100、nit 1。selection 2 forwards / 168、anytime 0、terminal 1 / 476、計103 forwards / 7,644 samples。requested=completed=7,644、reserved=unknown=0、released=356。raw confirmed/uncertain upperは共に7,644・103 forwards、summaryと一致。selection・terminal完了、terminal 17点/区間で最悪IL 1.843110 dB、最大違反28.019859 dB、strict finite-grid FAIL。component policy PASS、L最小固有値 `3.9306819299763447e-10 H`。独立MNA・dense・連続周波数・Q(f)/SRF/EM・公差・実測・物理実装性は今回未検証。#377の別テスト6点MNAを今回の独立検証としない。新規EXP、本番、追加3,000評価、100 restartはnot_run。

## 原本・読戻しSHA256

Git外ローカル、外部バックアップ未確認。ファイルを実読戻ししてSHA256を取得。rawは変更していない。

| file | SHA256 |
|---|---|
| `/home/user/issue385-preflight.json`（新規Plan/source） | `657fafb9e1fadfd5d025b3dd983e8c7fd4c88e1911ad3fbaeb43dafd63362223` |
| `/home/user/issue385-timing.json` | `2eb3337ed3516d66d7d8518b28d00a112b469016a4d424bf8f5b23bf891a39f1` |
| `/home/user/issue385-run.log` | `3ea2d63cc93af3ec48cafb128adbe965e63cf185addd75e3d6e3ea239600b6db` |
| `/home/user/issue385-raw/run.json` | `090659d8cd674c9ddaa6ac687f971f9b0a08e7df4ae88256ef118c01f6ae21ef` |
| `/home/user/issue385-raw/development-hybrid-1002.json` | `9c071c05b68c7d9c7b2627bec801e91841baceb7134155e2aeed6114333182b5` |
| `/home/user/issue385-raw/summary.json` | `3ea2d63cc93af3ec48cafb128adbe965e63cf185addd75e3d6e3ea239600b6db` |
| `project/diagnostics/issue377/baseline.yaml` | `f45f2b853fdf43eb36579c5e2c6876124f7c006d6107d5e0910ee5ae921c812d` |
| `/home/user/issue377-rf-profile-20261110/inputs/starts-1002.json` | `63b671ea269656843df118230b7d920e91515188235809b6dd0efd667ac997ab` |
| `project/diagnostics/issue361/definition.json` | `e8ac857c063e0b9d2eb8eaf629c2e4b700a694e9241f3bbc596d99f6374487f6` |

# Issue #393：限定旧新A/B（非EXP）

**結論：同一応答系列の科学的同等性はこの1組で確認。性能のばらつき・一般化は未評価。既存Worker全経路の移行は未完了。** [事前にIssueへ記録した予算](https://github.com/miyabimm/reconfigurable-rf-lpf-research/issues/393#issuecomment-6797728032)に従い、旧詳細評価と新prepared評価のHybridを各1回、各100 RF forward（70 samples/forward）、計200 forward / 14,000 samples実行。追加の末尾RF forward、独立MNA、dense、EXP・正式Campaignは未実施。

- 実行HEAD `16a2fb91c7334d7df0342c4d58c1fbc3f0dac5cf`、実行対象source identity SHA `e0903c1c9a36dcf3125fa261222aca9b8767b45cae322adaf8855d30fb314e2f`（両経路一致、対象tracked patch空）。実行スクリプトSHA `bdbe2253c0a43d5512a764526d9b66c3b7e84cc888ba694bc7debed347fa14ab`。後続のコード変更はこの結果で計測していない。
- RF-T008 rev3 trial opt-in / full_lpf、effective SHA `e682165c72d3a8b9f1384a2529f71bacfebfc9d17164d4af5af879e4a138b532`、固定S2P・全6設定/28区間。Plan SHA `8ac7bab9567918ae5c656fd449807ad2c38c1e1cad9e39c8ed217b95a569043e`、grid SHA `6805740a36f6100d7dec3e7308924242e909255f1ea2d287b7c734c400f98f26`。bands/S2P fingerprintsと環境は[生JSON](issue393_ab.json)参照。
- 原本seed 1002 vector SHA `6203467121a4e37baaa51c471aaecb3174f3374f9ab955d6fbf101f7b5ce935f`、starts byte SHA `63b671ea269656843df118230b7d920e91515188235809b6dd0efd667ac997ab`。Hybrid sum、max_evaluations=100、max_restarts=0、BLAS/OMP/MKL各1 thread。
- 全100 forwardのvector、worst IL、mandatory gの全要素が完全一致。solver全出力も一致、nfev=100、`evaluation_budget_exhausted`（未収束）、best_fun `27088.776754855604`。連続周波数適合や物理実装の証明ではない。

| 経路 | setup (s) | solver (s) | total (s) |
|---|---:|---:|---:|
| 旧詳細評価 | 0.332778 | 0.384701 | 0.717479 |
| 新prepared評価 | 0.242711 | 0.150141 | 0.392852 |

同一プロセスで旧→新の順に1回ずつ実行、全forwardのvectorと結果を記録する計時オーバーヘッドを含む。キャッシュや実行順・システム負荷は制御していないため、比率を安定した改善率とは扱わない。現行Worker全体や保存処理の速度比較ではない。

再現コマンド（追加実RF予算の承認なしに再実行しない）：

```sh
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 PYTHONPATH=src \
  uv run --frozen python project/diagnostics/issue393_ab.py
```

生JSON SHA256 `0dbcfbe3de9c5a4e2fa357990ad55bdbdd37a277d1fd4a7fc1c78eccc3261185`。別のseed、反復によるばらつき、独立MNA/電力保存、EM・SRF・Q(f)・公差・実測は未検証。

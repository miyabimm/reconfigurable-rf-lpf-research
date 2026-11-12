# Issue #401: 固定source/load事前準備のplain A/B

## 変更と科学回帰

`RFEvaluator`の構築時に、承認済み不変policyから従来の `_fixed_port_impedance` でsource/loadを検証・複素数に変換し、その値を凍結する。forward毎のpolicy JSON再decodeと同変換を省く。`power_response`の式、参照面、S2P、SPD、6設定・28区間、solver/requirementsは変更しない。不正impedanceはevaluator構築時に明示拒否され得る（以前はforward中）。

5モデル各6設定で凍結値・複素S/IL/APL/RL等価、policy再decodeなし・不変性を確認。既存RF Core、SPD/有限異常、独立MNA、枝MNA、およびMinimalWorker/物理境界回帰を実行。さらに固定Planの3候補（原本、L座標と最後のCv座標を各1個ずつbox中央へ変更）を旧新で各3 forward、計6 forward／420 samples評価。各70点の複素S・IL/APL/input/output RL・mandatory g配列についてdtype・shape・raw bytesのSHA256、およびworst ILは旧新完全一致。[旧](issue401_ports_ab_repeat_raw/old-equivalence.json)／[新](issue401_ports_ab_repeat_raw/new-equivalence.json)。照合スクリプトSHA `31119dcbc491dda612f3738fe09d1d949730396300c63636aff590d429dc91c7`。これは全solver軌道・連続帯域の直接照合ではない。

## plain計測

固定科学条件はRF-T008 rev3 trial/full_lpf、seed1002、70 samples、100 nfev、Plan `8ac7bab9567918ae5c656fd449807ad2c38c1e1cad9e39c8ed217b95a569043e`、grid `6805740a36f6100d7dec3e7308924242e909255f1ea2d287b7c734c400f98f26`、vector `6203467121a4e37baaa51c471aaecb3174f3374f9ab955d6fbf101f7b5ce935f`、policy `e682165c72d3a8b9f1384a2529f71bacfebfc9d17164d4af5af879e4a138b532`、同S2P・環境、BLAS/OMP/MKL各1、affinity 0。旧HEAD `f5bd7dbb0d5ccc580999633b76116eb7356b80db`、新コードは初回 `5b36d134ccec4454dd136076c85a83e4602549f9`、反復 `88abc7a3624e7f7d9260112d5a929851d7977a74`（両新HEAD間は記録・診断driverのみ変更）。各比較で対象実行sourceは `src/lpf/rf_core/model.py` のみ異なり、source/script/input SHAは各freeze記録を参照。

初回と追加反復はそれぞれ旧新warmup各1＋測定各10、旧新新旧×5の別process。合計44 run／4,400 forward／308,000 samples（nfevから算出）、後段RF forwardなし。全44 runのsolver出力は各batchで完全一致し、各100 nfevで評価予算切れ・未収束。各開始予約・stdout/stderr/停止状態・solver結果は[初回](issue401_ports_ab_raw/)／[反復](issue401_ports_ab_repeat_raw/)に保持。

| solve wall | 旧 中央値 [範囲] ms | 新 中央値 [範囲] ms | 対応差中央値 [範囲] ms |
|---|---:|---:|---:|
| 初回 | 97.285 [90.429, 124.746] | 83.234 [78.643, 108.464] | −14.248 [−41.030, +11.622] |
| 反復 | 105.981 [95.017, 126.110] | 86.339 [78.717, 135.641] | −14.863 [−33.671, +32.507] |

初回10組の対応差中央値のbootstrap参考95%区間（10,000再標本、seed401）は −29.52〜+5.77 ms、反復も −24.48〜+7.65 ms。両群20組をまとめると −20.85〜−3.27 msだが、共有host・順序・外れ値に依存し、独立同分布や統計的確証は保証されない。方向は両batchで同じだが分布は重なり、汎用的な速度改善率ではない。setupも含む初回total中央値は旧352.692／新344.740 ms。`solve_wall`は`worker.solve()`全体でありHybrid単独ではない。timer無効のplain比較、測定器負荷は別途厳密に校正していない。

RF coreは共有されるが測定はMinimalWorkerのみ。window100・正式Campaignの実時間改善、未収束結果のRF性能適合、独立dense/連続周波数、Q(f)/SRF/EM、公差、実測、物理実装可能性を示すものではない。2,600 forwardの先行計測、3,300の詳細測定、2,200の不採用候補、上記4,400＋6はそれぞれ別の実施数量であり予算台帳付き正式EXPではない。

## main追従と現役入力

計測後にmainの#397 batch 3で元の `issue375/starts-1002.json` が削除されたため、当該入力のbyte-identicalな現役コピー `issue401_starts_1002.json` を作り、SHA照合は維持した。既存記録・当時のscript SHAは変更していない。main `246444b93fb6e6b082af6ece3c5bfc7bcaff05c9` のmerge後、`issue401_postmerge_smoke.json` に新しい入力経路によるplain 1 run（100 forward／7,000 samples）を記録。solver全出力はA/B旧版と一致し、予算切れ・未収束。旧新同一スクリプトによる今後の比較ではdriverが新しい入力の完全SHAを両者に適用する。

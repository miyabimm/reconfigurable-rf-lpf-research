# #487 追補：batch decode・matrices分解

[初回報告](report.md)・[その全測定](measurements.json)は変更せず保持。Issue追加スコープに基づき同一PRで`decode_lk`の内側に、batch一括decodeと実際のmatrices呼出のみのタイマーを追加し、全測定をやり直した。RF式・候補順・キャッシュ/失敗replay・予算・optimizerを変更していない。測定HEAD **`94f9d65f4f1e2a36fd2fa400644255463f8d1319`**、実行時clean、source identity SHA `63d2333f042b373571ad8a7561e03ac08a2e7c4f6a33815bdbcf2ee0aeebf091`。全環境・生測定行・timing snapshotは [decode_100k_measurements.json](decode_100k_measurements.json)、preflight全行・deepは [decode_preflight.json](decode_preflight.json)。旧測定と新測定はHEAD・時刻・計器が異なり、区間絶対値を同一視しない。

## 再現・条件

初回と同じRF-T010 trial effective SHA `d50e6c9fef3e41b8258c00cbd14436a3bcb1d84444d50cf4a445ccf5d288e417`、物理RF-T008 rev3、Plan SHA `0e2d62841f286281eb9b2c662382a50238f865193b16eafabf6aa3227ba18d90`、seed 1013、4L2C 25変数・6設定・28分離区間、Hybrid/L-BFGS-B sum・sigma 0.1、batch+partial FD、L/k、Search 70点・Terminal 476点・MNA `[0,111]`、checkpoint 1000、名目100000 Search forwards。S2P/bands/grid/startの指紋・詳細は[初回報告](report.md)と同一。

```sh
# 測定HEADで、各出力先は未存在のパスを指定
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
 uv run --frozen python project/diagnostics/issue487/measure.py /tmp/UNUSED-PREFLIGHT 312
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
 uv run --frozen python project/diagnostics/issue487/measure.py /tmp/UNUSED-100K
uv run --frozen python project/diagnostics/issue487/analyze.py /tmp/UNUSED-100K > summary.json
```

WSL2 Linux 6.18.58.1、Ryzen 7 PRO 4750G、affinity CPU 0、Python 3.12.15、NumPy 2.5.4、SciPy 1.18.1、OpenBLAS/OMP/MKL各1 threadを環境変数で指定。実thread数・周波数・ホスト負荷は未確認。独立プロセスの各モード312 forward warmupは集計外、その後 fresh出力で `plain,timed,deep` / `timed,deep,plain` / `deep,plain,timed`。別途plain/deep軌道replay。失敗・外れ値は恣意的に除外していない。完全raw、receipt、checkpoint等は `/tmp/rf-lpf-487-decode-100k-94f9d65f/`、preflightは `/tmp/rf-lpf-487-decode-preflight-94f9d65f/` に保持。system tmpで永続保証なし。

preflightの312 Search forwardsは12 scalar＋12 batch×25。各deepの`batch/decode` 12回、`batch/matrices` 84回＋逐次`rf/matrices` 12回＝L/k miss 96回、`decode_lk >= decode + matrices`、各failed 0。個別候補decode時計・matrices内の子時計は抑止。全3モードresult一致、別trace 312候補のハッシュ一致。preflight 2-deepのresidual約6.16msは1/3-deep約1.53/1.37msより大きいが除外せず、短時間・計器/スケジューリング等の原因未特定。正常・例外時復元およびhandled batch failureからの逐次replayはテストで確認。

## 100k 全9測定（秒、RSS KiB）

| set / mode | Runner wall | process wall | CPU | max RSS |
|---|---:|---:|---:|---:|
| 1 plain | 26.832159 | 27.234905 | 26.211467 | 93476 |
| 1 timed | 27.109195 | 27.511786 | 26.549674 | 93248 |
| 1 deep | 27.719810 | 28.127675 | 27.115240 | 93460 |
| 2 timed | 26.862265 | 27.335694 | 26.296131 | 93504 |
| 2 deep | 27.882724 | 28.338400 | 27.239331 | 93524 |
| 2 plain | 26.816119 | 27.238960 | 26.236622 | 93396 |
| 3 deep | 28.013078 | 28.449366 | 27.431849 | 93332 |
| 3 plain | 26.954059 | 27.405819 | 26.351773 | 93460 |
| 3 timed | 26.834125 | 27.243809 | 26.256053 | 93520 |

Runner中央値（最小–最大、標本SD）: plain **26.832159** (26.816119–26.954059, 0.075437)、timed **26.862265** (26.834125–27.109195, 0.151344)、deep **27.882724** (27.719810–28.013078, 0.146935)。plain中央値に対しtimed +0.11%、deep **+3.92%**。対応setのdeep−plainは0.8877、1.0666、1.0590秒。timed−plainは−0.1199〜+0.2770秒でゼロと区別できない。deep追加時計には約2.36万回のmatrices計時が含まれ、測定器負荷と小標本・OSばらつきを分離できない。deepの秒数をplainの絶対値とみなさない。

過去C plain中央値27.528678秒とは−0.696519秒（−2.53%）。初回#487 plain中央値26.417674秒とも異なるが、いずれも別HEAD・別時刻・少数runであり、この差から改善・回帰は断定できない。

## 同時測定の内訳

各deep runは3847 batch、96175 batch候補＋3847 scalar＝100022候補、実計算4308640 samples（論理要求7001540）。L/k lookup 100022、hit 73102、miss 26920。`batch/matrices` 23555回＋逐次`rf/matrices` 3365回＝全miss 26920。逐次matricesは別区間（1-deep 0.4110秒）で表のbatch内訳に含めない。1 batchのdecodeは全候補一括1回であり、matricesは実生成されたcache missのみ。

| deep run | decode_lk total s / 回 | batch decode s / 回 / 平均ms | batch matrices s / 回 / 平均ms | 残余 s / 平均ms per batch |
|---|---:|---:|---:|---:|
| 1 | 7.997199 / 3847 | 6.318579 / 3847 / 1.642469 | 1.377147 / 23555 / 0.058465 | 0.301472 / 0.078366 |
| 2 | 8.034544 / 3847 | 6.353410 / 3847 / 1.651523 | 1.377348 / 23555 / 0.058474 | 0.303786 / 0.078967 |
| 3 | 8.133750 / 3847 | 6.445815 / 3847 / 1.675543 | 1.385677 / 23555 / 0.058827 | 0.302258 / 0.078570 |

全行failed 0。`decode_lk`はinclusiveで、decodeとmatricesを内包する。表の残余は **同一runの`decode_lk − decode − matrices`** であり、キー生成・LRU操作・numerator格納・wrapper/時計負荷等を含む。純cache lookupではない。1-deepの内訳はdecode 79.0%、matrices 17.2%、残余 3.8%。これらの和と親を重ねてwallに加算しない。元の7区間・cascade/power・Search/solver/その他の包含関係は[初回報告](report.md)の説明を参照。今回1-deepのSearch 27.2151秒、solver 27.1940秒、RF評価19.9957秒、batch全体17.3046秒、mask 0.3548秒は[JSON](decode_100k_measurements.json)に全回記録。SciPy内部だけの時間は分離できず不明。

## 数値検証・結論

全9本および別trace 2本でresult・全checkpoint `(forward_count, observation)` 一致、全receipt/Plan SHAを照合。100022候補のplain/deep vector・目的値順序ハッシュは両方 `becf8d2705f0f2def10d356645dc4aa924401ef98f63c9dc29cff060be0cb448`。旧測定rawともPlan・initial vector・全step・costs・ledger・Terminal・grid SHAが一致。Search 100022 / requested 7001540、Terminal 1 / 476、MNA 2、forward予約100025・完了100023・解放2・unknown 0、checkpoint 99。Terminal全S/IL/APL/入出力RL・受動性・電力保存、成分条件/L行列SPD、独立MNA spotはresult検証の対象。予算停止・未収束であり、連続帯域・SRF・Q(f)・EM・公差・実測・RF適合は保証しない。

次の調査対象は**batch一括decode**。同時測定でmatricesの約4.6倍、decode_lkの約79%を占める。例えばbatch decode全体を理想的に10–50%短縮できた場合、deep Runner比の単純Amdahl参考は約2.3–11.4%、完全除去の非現実的上限約23%。matrices全体の完全除去上限は約5%、残余全体でも約1.1%。計器負荷・有限標本・他区間の相互作用を無視した仮定であり、plain A/Bなしに改善率は主張しない。decode内部の細分や高速化は本Issueでは実施していない。

## 検証

`OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 uv run --frozen python -m unittest discover -s tests -p '<pattern>' -v`: `test_issue468_timing.py` 11件（import fixture 5件含む）、`test_issue479_rf_batch.py` 5件、`test_issue482_batch_fd.py` 5件、`test_issue484_partial_fd.py` 9件、`test_issue487_batch_timing.py` 7件、すべてPASS。追加commitは先行レビューの対象外であり、CIと独立再レビューは別途。

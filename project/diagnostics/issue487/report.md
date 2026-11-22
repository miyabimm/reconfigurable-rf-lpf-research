# #487 Hybrid partial FD の deep 計測

正式EXPでなく、固定済み単一seed・試験条件の性能診断。測定HEAD **`882872506a50b1888a5436edcdd3ebc6c16e71ce`**、source identity `938e22c469f295b79ca7fd60c6d8fdbb4ceb7ca53e7d3e929067af91fbb00140`。実行時tracked差分なし、未追跡の本レポート草稿・集計器等4ファイルあり（測定コード/RF sourceへの差分なし）。測定後のレポート等のコミットは測定HEADではない。RF式・予算・探索方式は変更していない。試験RF-T010 effective SHA `d50e6c9fef3e41b8258c00cbd14436a3bcb1d84444d50cf4a445ccf5d288e417`、物理base RF-T008 rev3 `e682165c72d3a8b9f1384a2529f71bacfebfc9d17164d4af5af879e4a138b532`。formal RFの結果ではない。

## 再現・条件

[測定器](measure.py)、[検証・集計器](analyze.py)、[全run測定値と全timing行](measurements.json)、[preflight](preflight.json)。完全raw、receipt、checkpoint、diagnosticは `/tmp/rf-lpf-487-100k-88287250/`、preflightは `/tmp/rf-lpf-487-preflight-88287250/` に保持（system tmp、永続保証なし）。

先行測定HEAD `0a60a7c9` はbatch内の個別候補decodeを計時してIssueの計器負荷条件を満たさなかったため修正・全測定をやり直した。失敗・外れ値の選別ではなく計器実装が異なる測定であり、全測定数値・内訳は [superseded JSON](superseded_0a60a7c9.json)、rawは `/tmp/rf-lpf-487-100k-0a60a7c9/` に保持。先行preflightも `/tmp/rf-lpf-487-preflight-72437a9a/` と `/tmp/rf-lpf-487-preflight-0a60a7c9/` に保持。いずれも削除していない。

```sh
# 測定HEADで実行、出力先は新規パス
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  uv run --frozen python project/diagnostics/issue487/measure.py /tmp/UNUSED-PREFLIGHT 312
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  uv run --frozen python project/diagnostics/issue487/measure.py /tmp/UNUSED-100K
# analyze.py は測定後のreport commitに追加
uv run --frozen python project/diagnostics/issue487/analyze.py /tmp/UNUSED-100K > summary.json
```

seed 1013、`issue470/config.json` / `starts.json`、開始vector SHA `6e06d271e0ea54eecb547cfff045a6edda4850bfaa1f9c23bf9f3037ab867131`。4L2C・25変数・6設定・28分離区間、Hybrid/L-BFGS-B、sum、restart sigma 0.1、`batch_fd=true, partial_fd=true, rf_cache_mode=lk`。Search 70点、Terminal 476点、MNA `[0,111]`、checkpoint 1000、名目100000、バッチ境界の最大超過24。Plan SHA `0e2d62841f286281eb9b2c662382a50238f865193b16eafabf6aa3227ba18d90`、Search grid SHA `6805740a36f6100d7dec3e7308924242e909255f1ea2d287b7c734c400f98f26`、Terminal grid SHA `28ee5b630e4842b183a7c36fd610cc32e2509c0044c6a5848ce2fbd147a22e29`。bands SHA `1b1182e4c947059cb263c1af52ddf64236bd1fd9e83770cc844126576c7865fe`、入力S2P SHA `ad266111ba1dc2b92f235d39f4a647ff271050bc11941c217661dd299ee59945`、出力S2P SHA `b3cfc861bc0c8221f49328598c9d7d0766a6e94e42e990b6a50f6c90bf9a84da`。

WSL2 Linux 6.18.58.1、Ryzen 7 PRO 4750G、affinity CPU 0、Python 3.12.15、NumPy 2.5.4、SciPy 1.18.1、OpenBLAS/OMP/MKL各1 threadを環境変数で指定。実thread数・CPU周波数・ホスト負荷は未確認。各モード312 forwardの独立プロセスwarmupを集計外に実施し、その後 fresh出力で `plain,timed,deep` / `timed,deep,plain` / `deep,plain,timed` の順。別途両モードの軌道ハッシュreplayを実施。Runner wallは`runner.run`のみ、process wallは子プロセス生成〜終了、CPU/RSSはwait4。失敗・外れ値を恣意的に除外していない。

preflightは312 Search forward、12 batch（各25候補）、12 scalar、mask 12、各バッチ7区間12回/failed 0、cascade 48・power_response 24（scalarとbatchの合算）、個別decode計時はscalarの12回のみ。実計算13440 samples、L/k hit 216 / miss 96。3モードresult完全一致、plain/deep軌道312件のSHAも一致。312点では固定費・ノイズが大きく計器負荷は100kで評価。正常時・例外時復元、fallbackの多重記録防止、Schur失敗のfailedはユニットテストで検証。

## 100k 全9測定（秒、RSS KiB）

| set / mode | Runner wall | process wall | CPU | max RSS |
|---|---:|---:|---:|---:|
| 1 plain | 26.350463 | 26.783073 | 25.716449 | 93496 |
| 1 timed | 26.374054 | 26.803090 | 25.778095 | 93284 |
| 1 deep | 27.151696 | 27.569126 | 26.546080 | 93372 |
| 2 timed | 26.683899 | 27.112931 | 26.097347 | 93324 |
| 2 deep | 26.831547 | 27.273396 | 26.198832 | 93600 |
| 2 plain | 26.417674 | 26.846429 | 25.779447 | 93728 |
| 3 deep | 27.430931 | 27.872057 | 26.884073 | 93600 |
| 3 plain | 26.549618 | 26.955205 | 25.938650 | 93428 |
| 3 timed | 26.454858 | 26.901220 | 25.838251 | 93396 |

Runner median（min–max、標本SD）: plain **26.417674** (26.350463–26.549618, 0.101316)、timed **26.454858** (26.374054–26.683899, 0.160724)、deep **27.151696** (26.831547–27.430931, 0.299925)。plain中央値比のtimed/deep増加は各 **0.14% / 2.78%**、3組対応差はtimed −0.0948〜+0.2662秒、deep +0.4139〜+0.8813秒。小標本と順序・負荷差を含み、特にtimed負荷はゼロと区別できない。deep内訳は計器自体を含み、plainの絶対時間に転用しない。

過去Cのplain中央値27.528678秒（別HEAD `a7450555`、6回）との差は−1.111004秒（−4.04%）。ホスト・時刻・HEAD・回数が異なり対応比較ではないため、改善・回帰の証拠ではない。

## 包含関係と内訳（1-deep、他2回の全値はJSON）

区間はinclusive。`search` 26.6188 s は `solver` 26.5976 s、setup 0.0204 s等を含む。`solver` はRF評価19.5303 s、checkpoint 1.0473 s、mask 0.3537 sとその他を含み、その差 **5.6663 s** は目的関数・callback・SciPy・Python等の混合であってSciPy内部時間ではない。`job` 26.9740 s − `search` = 0.3552 s はTerminal・worker等、Runner − `job` = 0.1777 s はrunner側残余。区間境界の計器負荷を含む。Terminal RF自体0.0045 s。`rf_evaluate` 7694回はscalar 3847回とbatch入口3847回の合計。内側`rf/batch` 16.9288 sを差し引いた2.6015 sはscalar RF **とbatch入口の検証・wrapper等**を含み、純粋な逐次RF時間ではない。

`_compute_batch` 3847回、候補96175本（別途scalar 3847、総100022）。実計算sampleはscalar込み4308640で論理要求7001540とは異なる。L/k lookup 100022、hit 73102、miss/計算26920。下表はbatchの相互排他的な主要7区間で、平均は累積÷3847。batch内で候補ごとのdecode/matrices時計は動かさず、それらは`decode_lk`に包含する。

| batch区間 | 累積 s | 平均 ms | failed |
|---|---:|---:|---:|
| decode_lk | 7.5930 | 1.9737 | 0 |
| select | 0.0439 | 0.0114 | 0 |
| stamp | 1.4897 | 0.3872 | 0 |
| schur_solve | 1.6220 | 0.4216 | 0 |
| schur_update | 0.5410 | 0.1406 | 0 |
| y_to_s | 1.2697 | 0.3301 | 0 |
| output | 1.2790 | 0.3325 | 0 |

7区間の和をbatch全体から引いた **3.0906 s** は未分解残余であり、batch内cascade/power_response、配列添字、timer wrapper等を含む。既存`cascade` 0.7160 s / 15388回、`power_response` 2.6568 s / 7694回は **scalarとbatchの合算**で、batch残余に全量を加算・減算できない。powerの子区間はwave build 0.6409、solve 1.2346、dB 0.5270 sで親に包含される。`decode` 0.3277 s / 3847回と`matrices` 0.3954 s / 3365回は**scalarのみ**。結果からdecode/Lkが最大、続いてstamp・Schur solve・Y→S・outputが各1.27–1.62 s規模。maskは0.3537 sで比較的小さい。ただしdeep値には計器負荷を含む。

## 数値一致と限界

warmup群、100k 9本および別trace 2本について各群で `result.json` 全体および全checkpoint `(forward_count, observation)` が一致。全receiptファイルのサイズ/SHA、Plan raw SHAを検証。100k plain/deep replayの全100022候補のvector/目的値順序ハッシュは両方 `becf8d2705f0f2def10d356645dc4aa924401ef98f63c9dc29cff060be0cb448`。replayは計時対象外。最終solver objective `2.929380163370666`、vector SHA `8cfdf946543a7f56a50b346b219d06e4b56060c1d3d65dd568308e61ae0f982e`、Terminal J `0.747758285205661`。Search 100022 / 7001540 requested samples、Terminal 1 / 476、MNA 2；forward予約100025・完了100023・解放2・unknown 0、checkpoint 99。`evaluation_budget_exhausted`、未収束。

Terminalの全S/IL/APL/入出力RL、solver詳細、ledger、checkpointはresult完全一致に含まれる。Terminal有限grid受動性・電力保存、成分条件・L行列SPD、独立MNA spot `[0,111]` はpass。連続周波数、SRF、Q(f)、EM、公差、測定は未検証でありRF適合や物理実現性を保証しない。

## 次の候補（計測根拠に基づく仮説）

1. decode/Lk経路の重複validation・データ変換を同一結果・例外順序のまま削減する検討。deep batch 7.49–7.70 s / Runner 26.83–27.43 s ≈28%を完全除去できたという**非現実的上限**、当該区間を10–50%短縮できた仮定なら全体約2.8–14%。実際の利益は無計時A/Bで要確認。
2. stamp/Schur solve+update/Y→Sの配列演算を調査。4区間合計約4.88–4.95 s、deep Runnerの約18%が理想上限。仮に当該部分10–50%削減なら約1.8–9%。RF式・結果・失敗時の振る舞いを変えない別Issueと検証が必要。
3. output組立・凍結（約1.26–1.29 s、約4.7%上限）やmask（約0.35–0.36 s、約1.3%上限）は後順位。各区間完全除去という上限すら小さい。

上限・仮定はAmdahlの単純参考で独立・重複なしの理想化。deepで計測された比率をplainの確定時間とみなさず、実測速度向上や全体最適を主張しない。SciPy内部のみは分離されておらず**不明**。

## 実行した回帰

`OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 uv run --frozen python -m unittest discover -s tests -p '<pattern>' -v` で `test_issue468_timing.py` 11件（importされたfixture 5件含む）、`test_issue479_rf_batch.py` 5件、`test_issue482_batch_fd.py` 5件、`test_issue484_partial_fd.py` 9件、`test_issue487_batch_timing.py` 4件、すべてPASS。CI・ChatGPT独立レビューは別途。

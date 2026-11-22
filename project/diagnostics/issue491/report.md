# #491 Hybrid solver未分解時間の診断

**診断のみ。** 正式EXP・高速化実装ではない。測定HEAD `ad5eec5d0979b6d35af760b5afd6d2d3d34fe941`（実行時clean）、source identity `6a999abf47bdff1e3d5c9fa7597554024e7a15597551f6070ca2be6501376ceb`。コードとその条件での計測を保存し、#490の記録は変更していない。全run・全inclusive timing・receipt検証・cache・preflight・環境・sourceファイルSHAは[measurements.json](measurements.json)。実行時の診断scriptは既存 `issue487/measure.py` を使用し、本報告の集計scriptは測定後に作成した。後続commitは測定HEADではない。

## 固定条件と再現

RF-T010 **trial** effective SHA `d50e6c9fef3e41b8258c00cbd14436a3bcb1d84444d50cf4a445ccf5d288e417`、物理RF-T008 rev3 `e682165c72d3a8b9f1384a2529f71bacfebfc9d17164d4af5af879e4a138b532`。seed 1013、4L2C/25変数・6設定・28分離区間、Hybrid/L-BFGS-B sum、sigma 0.1、batch FD＋partial FD、L/k cache、checkpoint 1000、名目100000 Search forwards、Search 70点、Terminal 476点、独立MNA `[0,111]`。固定入力：

- Plan `0e2d62841f286281eb9b2c662382a50238f865193b16eafabf6aa3227ba18d90`、初期vector `6e06d271e0ea54eecb547cfff045a6edda4850bfaa1f9c23bf9f3037ab867131`。
- Search grid `6805740a36f6100d7dec3e7308924242e909255f1ea2d287b7c734c400f98f26`、Terminal `28ee5b630e4842b183a7c36fd610cc32e2509c0044c6a5848ce2fbd147a22e29`。
- bands `1b1182e4c947059cb263c1af52ddf64236bd1fd9e83770cc844126576c7865fe`、入力S2P `ad266111ba1dc2b92f235d39f4a647ff271050bc11941c217661dd299ee59945`、出力S2P `b3cfc861bc0c8221f49328598c9d7d0766a6e94e42e990b6a50f6c90bf9a84da`。

WSL2 Linux 6.18.58.1、Ryzen 7 PRO 4750G、affinity CPU 0、Python 3.12.15、NumPy 2.5.4、SciPy 1.18.1、OpenBLAS/OMP/MKL指定各1 thread。実thread数・周波数・ホスト負荷は未確認。独立プロセス312-forward warmupは集計除外、100k各3本を `plain,timed,deep` / `timed,deep,plain` / `deep,plain,timed` の順、別プロセスでplain/deep trace、さらにplain/deep cache replay。失敗や外れ値の選別なし。診断追記後に再現する場合も科学コードのHEAD/差分とsource identityを記録する。

```sh
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1
uv run --frozen python project/diagnostics/issue487/measure.py /tmp/UNUSED-preflight 312
uv run --frozen python project/diagnostics/issue487/measure.py /tmp/UNUSED-100k
for mode in plain deep; do
  taskset -c 0 uv run --frozen python project/diagnostics/issue491/cache_replay.py "$mode" "/tmp/UNUSED-cache-$mode" | tee "/tmp/UNUSED-cache-$mode.log"
done
uv run --frozen python project/diagnostics/issue491/analyze.py /tmp/UNUSED-preflight /tmp/UNUSED-100k /tmp/UNUSED-cache-plain /tmp/UNUSED-cache-deep > summary.json
taskset -c 0 uv run --frozen python project/diagnostics/issue491/clock_cost.py > clock.json
```

rawは `/tmp/lpf-issue491-preflight-ad5eec5d/`、`/tmp/lpf-issue491-100k-ad5eec5d/`、`/tmp/lpf-issue491-cache-replay-ad5eec5d-{plain,deep}` と対応ログ。初期計測実装のpreflight `/tmp/lpf-issue491-preflight-6276cd15/` も残る。system tmp上の大量rawに永続保証はない。キャッシュreplayは後から追加したscriptをuntrackedで実行し、result/source identityが本測定と一致したことを照合した。

## Preflightと時計負荷

312 forward（12 scalar＋12 batch×25）。A `batch/vectors` 12回、B `batch/consume` 300回、C `objective/value` 312回、D `objective/state` 312回、D内 `objective/group_callback` 12回、mask 12回、RF入口24回、checkpoint 1回。3 deepで全region `failed=0`。timedには新regionがない。plain/deep traceは312候補のSHA `7511cb0ba37b9fa347134a30c142e6dabef4a5c203e21a54a9a380ae9b80f454` で一致。3 deepにおけるA 2.368–4.896ms、B 1.732–2.004ms、C 3.771–3.846ms、D 0.464–0.531ms。短いrunは固定起動・checkpoint・OS変動が支配的で、overheadの定量には不足。generator停止中に模擬時計を100万ns進めるテストでもBは各処理1nsのみを計上する。

100k Runner中央値（範囲、標本SD）はplain **20.246秒**（20.195–20.553、0.194）、timed **20.200秒**（20.129–20.406、0.144）、deep **21.641秒**（21.496–21.792、0.148）。全9本のRunner/process/CPU/RSSはJSONのrowsに保存。deep中央値はplain比+6.89%だが、既存deep計器も含む差であり、新設時計だけの負荷ではない。順序・OS変動を分離できず、deepの秒数をplainの確定時間に転用しない。

同CPUで300000回×5の簡易マイクロ計測（[script](clock_cost.py)、[全値](clock_cost.json)）ではループ差分の時計2回が149–173ns/回、時計2回＋`TimerCollector.add` が499–513ns/回。条件分岐・f文字列・失敗処理・実RF内相互作用を表さず、差し引き補正には使えない。新regionは約30万回の集約addで、イベントは保存しない。

## 区間と重複

- A：SciPy提供 `zs` のphysical vector/copy構築だけ。`zs` list化・RF・objective・group callbackは外。
- B：正常batchでRF返却後の各候補のforward課金、identity、audit、signed margin、finite判定。**yieldの前に停止**。RFと重ならない。scalar `_forward` とbatch失敗時のscalar replayは含まれず、solver残余に残る。失敗時の候補順・例外伝播は変更しない。
- C：`raw` 取得**後**の検証・二乗・aggregate・finite判定。`next(pending)`（Bを実行）とRFは含まない。
- D：値確定後のobjective/progress callback、best/last更新とscalar group callback。batch終了時のgroup callbackはD外。`objective/group_callback` はD内のscalar callback全体で、checkpointが発火すればcheckpointを内包する。checkpointは別のinclusive region。solverは上記を全て内包する。

各100k deepの秒（括弧内はsolverに対するinclusive割合）。Dの内側callbackをDへ重ねて足してはいけない。

| 区間（回数/run） | 1-deep | 2-deep | 3-deep |
|---|---:|---:|---:|
| solver (1) | 20.9607 | 21.1247 | 21.2229 |
| RF入口 (7694) | 13.2478 | 13.3933 | 13.5454 |
| checkpoint (99) | 1.0525 | 1.0780 | 1.0072 |
| mask (3847) | 0.3586 | 0.3731 | 0.3613 |
| A vectors (3847) | 0.8302 (3.96%) | 0.8292 (3.93%) | 0.8362 (3.94%) |
| B consume (96175) | 0.6253 (2.98%) | 0.6183 (2.93%) | 0.6338 (2.99%) |
| C value (100022) | 1.2552 (5.99%) | 1.2292 (5.82%) | 1.2311 (5.80%) |
| D state (100022) | 0.1582 (0.75%) | 0.1569 (0.74%) | 0.1579 (0.74%) |
| D内 scalar group callback (3847) | 0.00437 | 0.00476 | 0.00543 |
| 元の未分解残余 | 6.3018 | 6.2803 | 6.3089 |
| 保守的な新未分解残余 | **3.4372** | **3.4515** | **3.4552** |

各行の失敗0。計算は**同じdeep run**ごとに：

```text
元の残余 = solver - RF入口 - checkpoint - mask
新残余   = 元の残余 - A - B - C - (D - D内scalar group callback)
```

後式はcheckpointを含み得るcallback全体を控除対象から外すため二重控除しない。callback内のcheckpoint以外も残余に戻るので、厳密な排他的分解ではなく保守的。今回のcheckpoint forward countはすべて26の倍数（最後は予算停止時のforce）、scalar callbackは26の倍数＋1であり、**今回のD↔checkpoint重複は0**。したがって今回に限りD全量を控除すれば3.4328/3.4467/3.4498秒だが、上の保守値を主値とする。batch_map内でB/C/Dは交錯するが、A/B/C/Dは互いに同時計測していない。RF外側にはscalar応答検証・audit等が残り、時計自体と辞書集計も残余/親に負荷を加える。新残余は候補変換のobjective側、予算・callback・Python・SciPy等の混合であり、**SciPy内部処理時間とは断定できない**。

## 一致・科学的限界

全100k実行のresult全体・checkpoint観測・各receiptファイルサイズ/SHAを比較して一致。別traceでplain/deep各100022候補のvector・目的値順序SHA `becf8d2705f0f2def10d356645dc4aa924401ef98f63c9dc29cff060be0cb448` 一致。plain/deep cache replayでも同じresultとtrace、L/k lookup 100022、hit 73102、miss/computation 26920、computed samples 4308640が一致。全timed/deep 100kのcacheカウンタも一致。Search 100022 forwards・requested 7001540、Terminal 1/476、MNA 2、checkpoint 99、`evaluation_budget_exhausted`・未収束。batch group完了により名目100000を22超過。

Terminal 476点の全S/IL/APL/入力・出力RLが有限で全run同一、component policy・全L行列SPD、格子上の受動性・電力保存、独立MNA 2 spotのS/IL/APL/RLを検証。有限格子の観測であり連続帯域、SRF、Q(f)、EM、公差、実測、RF適合・物理実装性、また最適性を保証しない。

## 次工程の候補

1. Cの約1.23秒：検証・二乗・集計を細分化し、同等性・異常分類を維持できる案を検討。Aの約0.83秒、Bの約0.62秒も次点。
2. 新残余約3.44–3.46秒：objective側のphysical変換・予算・callback等を必要に応じ分離する。ただし計器負荷に注意し、SciPy単体と決めつけない。
3. RF入口約13.2–13.5秒は最大だが既存deep子区間を参照し、他区間と重複して足さない。checkpointの頻度・耐久性は変更対象外。

いずれも現条件の候補で、改善率・一般性・採用を主張しない。変更する場合は別Issueで同一条件のplain A/Bと異常・科学的不変条件を検証する。

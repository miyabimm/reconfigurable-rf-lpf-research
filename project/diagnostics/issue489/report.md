# Issue #489: batch NumPy decode A/B

## 対象・再現

性能診断であり正式EXPではない。A = #488マージ済みmain `3d1cd68a121f6885f1c548cb22fe0d1420ed0600`、B = 実装測定HEAD `f325e2bebd41766e78798492e52328c5a33fa618`。B測定時に未追跡の本診断ディレクトリが存在（`environment.json`に記録）、実行対象のtracked sourceはclean、dirty patchは空。source identity A `039e1b76048b9a0f7c1ed234a801686f3aea77982b0ee83e25e6ab85e311d0b6`、B `37631e2406641238a37fa54c78da2d2641fed85f4fb06863444673b070f3f6a0`。後続commitはテスト・診断資料のみで測定対象コードを変更していない。

RF-T010 **trial** effective SHA `d50e6c9fef3e41b8258c00cbd14436a3bcb1d84444d50cf4a445ccf5d288e417`（物理RF-T008 rev3 SHA `e682165c72d3a8b9f1384a2529f71bacfebfc9d17164d4af5af879e4a138b532`）、4L2C/25変数、全6設定/28分離区間、seed 1013、Hybrid/L-BFGS-B sum、sigma 0.1、batch+partial FD、cache `lk`、Search 70点、Terminal 476点、独立MNA `[0,111]`、checkpoint 1000、名目100000 Search forwards。Plan `0e2d62841f286281eb9b2c662382a50238f865193b16eafabf6aa3227ba18d90`、initial vector `6e06d271e0ea54eecb547cfff045a6edda4850bfaa1f9c23bf9f3037ab867131`、Search grid `6805740a36f6100d7dec3e7308924242e909255f1ea2d287b7c734c400f98f26`、Terminal grid `28ee5b630e4842b183a7c36fd610cc32e2509c0044c6a5848ce2fbd147a22e29`。bands `1b1182e4c947059cb263c1af52ddf64236bd1fd9e83770cc844126576c7865fe`、入力S2P `ad266111ba1dc2b92f235d39f4a647ff271050bc11941c217661dd299ee59945`、出力S2P `b3cfc861bc0c8221f49328598c9d7d0766a6e94e42e990b6a50f6c90bf9a84da`。

WSL2 Linux 6.18.58.1、Ryzen 7 PRO 4750G、affinity CPU 0、Python 3.12.15、NumPy 2.5.4、SciPy 1.18.1、OpenBLAS/OMP/MKL各1 thread指定。実thread数・周波数・ホスト負荷は未確認。別プロセスで各312 forward warmup後、無計時plainを A B / B A / A B の順で各3回。全結果を掲載、除外なし。CPU割当を取得する最初のdeep実行コマンドはPIDを誤認しtaskset失敗、RF子プロセスは未起動。`os.sched_getaffinity`でCPU 0を取得して再実行した。

```sh
# A/Bそれぞれの完全なgit worktreeを指定。出力は未存在パス。
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
 uv run --frozen python project/diagnostics/issue489/measure_ab.py A_ROOT B_ROOT /tmp/UNUSED_AB
# 同じPython・thread・affinityで各ROOTの既存measure.pyを呼ぶ。
for TAG in A B; do
  ROOT=対応するworktree
  OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 taskset -c 0 \
   /path/to/.venv/bin/python "$ROOT/project/diagnostics/issue487/measure.py" \
   --child deep 100000 "/tmp/UNUSED_DEEP/$TAG" 1 > "/tmp/UNUSED_DEEP/$TAG.log"
done
uv run --frozen python project/diagnostics/issue489/analyze.py /tmp/UNUSED_AB /tmp/UNUSED_DEEP
# 固定25候補、同じaffinity/threadsで各worktreeにつき実行
uv run --frozen python project/diagnostics/issue489/micro_decode.py ROOT
```

## 無計時測定（秒）

| 順序 | run | Runner wall | process wall | CPU | max RSS KiB |
|---:|---|---:|---:|---:|---:|
| 1 | A1 | 29.485286 | 29.903445 | 26.288138 | 93428 |
| 2 | B1 | 22.449134 | 22.866407 | 19.734473 | 93548 |
| 3 | B2 | 22.032748 | 22.452472 | 19.559841 | 93336 |
| 4 | A2 | 28.844037 | 29.249126 | 26.102315 | 93368 |
| 5 | A3 | 28.341986 | 28.740676 | 26.056206 | 93344 |
| 6 | B3 | 21.449121 | 21.861641 | 19.470670 | 93260 |

Runner中央値 A 28.844037（範囲28.341986–29.485286、標本SD 0.573060）、B 22.032748（21.449121–22.449134、SD 0.502331）。この固定条件の中央値は **6.811290秒、23.61%短縮**。3組各々の差は6.81秒以上、観測範囲は重ならないが、少数回・単一環境の観測であり普遍的速度保証ではない。process wallとCPUも全行掲載、OS待ち・周波数等の寄与は未分離。

固定25候補のdecode＋配列構築2000回（各プロセス100回warmup、A B B A A B）ではA 3.265587/3.264512/3.229165秒、B 0.047899/0.049214/0.047443秒。入力SHA `90116987520221fd44d86c9ae5d3cc6634ae70c3e91f9e22189c66b86be3540a`、L/k/C出力bytes SHA `b73524a2b9bc8ddfdae16c9b72ecd4c37d5e2781406695903c667b55a882c910` 全回一致。Aは従来の個別decodeと後段の配列構築、Bは配列decodeを計時。短縮傾向は全体測定と整合するが、micro自体の比率を全体改善率とはしない。

## 等価性・deep

`analyze.py` は6 plain・2 deep全runのPlan/receipt/rawハッシュと、source identity以外の**結果JSON全体**および99 checkpoint全内容を照合し一致。Terminalの全S/IL/APL/両RL、mandatory margins、固定S2P cascade、成分条件・6設定・L SPD、Terminal格子受動性/電力保存、独立MNA spot、Search/Terminal/ledger/停止理由を含む。A/B deep別traceは各100022候補のvector・目的値順序SHA `becf8d2705f0f2def10d356645dc4aa924401ef98f63c9dc29cff060be0cb448` 一致。Search 100022 forwards、要求7001540 samples、計算4308640 samples、Terminal 1/476、MNA 2、forward予約100025・完了100023・解放2、unknown 0。予算停止 `evaluation_budget_exhausted`、未収束。Terminal signed max margin 0.7477582852 dBであり、RF適合の主張ではない。

各deepは3847 batch、decode 3847回、batch矩陣生成23555回＋scalar矩陣生成3365回＝cache miss 26920、hit 73102、lookup 100022。A/Bとも各タイマー失敗0。decode合計 A 6.290157秒、B 0.167941秒、batch matrices A 1.350637秒、B 1.284953秒。deepにtrace hookと計測器負荷があるため、この壁時計をplainの改善証拠にしない。deepトレースや矩陣回数を含む機械可読結果は [measurements.json](measurements.json)。実行rawは `/tmp/lpf-issue489-ab-f325e2be/` と `/tmp/lpf-issue489-deep-f325e2be/` に保持、system tmpのため永続保証なし。

## テスト・限界

`test_issue309_rf_core.py` 8、`test_issue468_timing.py` 11、`test_issue479_rf_batch.py` 5、`test_issue482_batch_fd.py` 5、`test_issue484_partial_fd.py` 9、`test_issue487_batch_timing.py` 7、`test_issue489_batch_decode.py` 4、`test_phase2_branch_mna.py` 6、すべてPASS（BLAS各1 thread）。固定入力の旧decode配列をoracleに`off/lk`、部分/全mask、全S/IL/APL/両RL、LRU順・統計のbit一致を検証。NaN/Inf、非正L、負C、極端k、shape/dtype、注入solve失敗、replay、deep復元も対象。全浮動小数入力・全回路の同等性を証明したものではない。連続周波数、SRF、Q(f)、EM、公差、実測、物理実装性、正式EXPは未検証。独立レビューとCIは別判定。

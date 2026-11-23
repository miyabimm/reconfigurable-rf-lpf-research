# Issue #495：batch physical 再利用（案Aのみ）

## 判定

**採用候補（暫定、独立レビュー待ち）**。候補の実行時一致確認とコピーのコスト込みで、plain Runner再測定ではA中央値21.594秒、B中央値20.526秒（差−1.068秒、約−4.9%）。ただし初回測定は約41〜43秒と再測定の約2倍で、3組目はBが遅い。外乱の原因・実CPU周波数・実BLASスレッド数は未確認であり、この割合を確定的な改善率としない。安全性・例外経路を含めDraft PRで独立レビューを受ける。案Bは未実装。

`batch_map` は候補ごとに正規化座標と物理座標を独立コピーし、SciPy提供 `fun(z)` 経由のobjectiveで座標一致・1回消費を検査、合致時のみ再利用。不一致・未消費は明示的に失敗しfinallyで一時状態を復元。batch consumerが入力を変更してもobjectiveとcallbackの座標を汚染しない。`np.clip`、残差順、予算・コールバック・deep regionは変更しない。確認とコピーの追加コストがある。

## 計測条件と再現

旧A `c3891f019898b203deee3050f2481c7cbd7655c9`、新B `d12ceafd6adf5eebe18168ab2daf31ea66f19cfe`（両clean、Bは案A実装と計測driverのみ、以降の変更はテスト・診断のみ）。RF-T010 **trial** effective SHA `d50e6c9fef3e41b8258c00cbd14436a3bcb1d84444d50cf4a445ccf5d288e417`、seed1013、4L2C/25変数、6設定・28区間、Hybrid L-BFGS-B(sum)、batch/partial FD、L/k cache、Search70、Terminal476、MNA [0,111]、checkpoint1000、名目100000。Plan `0e2d62841f286281eb9b2c662382a50238f865193b16eafabf6aa3227ba18d90`、初期vector `6e06d271e0ea54eecb547cfff045a6edda4850bfaa1f9c23bf9f3037ab867131`、Search grid `6805740a36f6100d7dec3e7308924242e909255f1ea2d287b7c734c400f98f26`、Terminal grid `28ee5b630e4842b183a7c36fd610cc32e2509c0044c6a5848ce2fbd147a22e29`。bands `1b1182e4c947059cb263c1af52ddf64236bd1fd9e83770cc844126576c7865fe`、S2P input `ad266111ba1dc2b92f235d39f4a647ff271050bc11941c217661dd299ee59945`、output `b3cfc861bc0c8221f49328598c9d7d0766a6e94e42e990b6a50f6c90bf9a84da`。

Linux WSL2 6.18.58.1、Ryzen 7 PRO 4750G、CPU affinity 0、Python 3.12.15、NumPy 2.5.4、SciPy 1.18.1、OPENBLAS/OMP/MKL 各1指定。独立プロセス、各312 warmup除外、A/B→B/A→A/Bを2セット。trace/cacheは別プロセス、plain採否時間に混入しない。環境・全値・プロセスwall・失敗は [measurements.json](measurements.json)。各rawのreceipt/ファイルhashは検査済み。

```sh
# A=clean base worktree, B=clean測定時HEADのworktree、出力先は未作成の空きパス
PY=/path/to/python3.12
$PY project/diagnostics/issue495/measure.py /path/to/A /path/to/B /tmp/issue495-run1
$PY project/diagnostics/issue495/measure.py /path/to/A /path/to/B /tmp/issue495-run2
$PY project/diagnostics/issue495/analyze.py /tmp/issue495-run1 /tmp/issue495-run2 > summary.json
CPU=$($PY -c 'import os; print(min(os.sched_getaffinity(0)))')
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 taskset -c "$CPU" $PY project/diagnostics/issue495/micro.py > micro.json
```

## 全plain測定（秒）

| セット | A1 | B1 | B2 | A2 | A3 | B3 | A中央値 (範囲、標本SD) | B中央値 (範囲、標本SD) |
|---|---:|---:|---:|---:|---:|---:|---|---|
| 初回 | 42.787 | 40.611 | 40.579 | 42.557 | 42.589 | 42.710 | 42.589 (42.557–42.787, 0.124) | 40.611 (40.579–42.710, 1.221) |
| 再測定 | 21.594 | 20.526 | 20.438 | 23.661 | 21.453 | 20.676 | 21.594 (21.453–23.661, 1.237) | 20.526 (20.438–20.676, 0.120) |

選別せず両セットを記録。初回は同一checkoutで別セッションの開発作業が並行していたが、それが原因とは確認できない。二重仮想化等の外乱は未確定。deep時間は取得していないためprepare内訳の削減量は未検証。

microは固定25候補、初期値一致1個を含む。各200 batch warmup除外、1000 batch×各6回交互、出力完全一致。旧中央値0.358269秒、新0.235147秒（全値は[micro.json](micro.json)）。これは候補準備・コピー・照合のみの合成測定でありRunner改善率ではない。

## 一致と限界

別trace再現でA/Bとも100022候補のvector・objective順序SHA `becf8d2705f0f2def10d356645dc4aa924401ef98f63c9dc29cff060be0cb448`、cache lookup 100022/hit 73102/miss 26920/computed samples 4308640。全100k runについてsource由来フィールドを除いたresultと99 checkpointsが完全一致。search 100022 forward/7001540 requested samples、terminal 1/476、独立MNA 2、予算group完了後 `evaluation_budget_exhausted`、非収束。2セット計20 runの内warmup 4・plain 12・trace 4は全成功。TerminalのS/IL/APL/両RL各476点の有限性、6設定、L最小固有値正、受動性・電力保存のチェック状態、独立MNA 2 spotとの差を確認。physical記録はdense RF/Q/SRF/EM等未確認・promotion blockedであり、spot照合が物理実装可能性や全帯域適合を意味しない。

実SciPy workersにおける順序・一致、batch input変異の独立性、連続batch・初期値・generator失敗後scalar・budget・不一致/未呼出時の復元を追加テスト。既存Hybrid/restart/batch FD/partial FD/runner回帰も実行。正式EXPでなく有限格子診断であり、連続周波数保証、SRF、Q(f)、EM、公差、実測、大域最適性は未検証。

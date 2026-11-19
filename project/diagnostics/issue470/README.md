# Issue #470: Search RF Core の L3 診断

## 条件・再現

開発性能診断、正式EXP・収束品質評価ではない。測定HEAD `6d992a1f502ec15971608d6ef0370a9640f3b844`（計測コードを含むクリーンcommit）、source SHA `afec6c554bcf2bb42d650a374b53c1b80a4aa1bbdd94a54a630c5297e8300e89`、Plan SHA `8c28bd63975133e731d266a395c9bdf9ec73d95be9dfd186e744049af2706f2e`。計測条件は同ディレクトリの `config.json`（byte SHA256 `db60096e07e4804b28497c3bd06509df56030e119787ba9996cb8ad1520dba20`）と `starts.json`（`9122b1b976ddbd53e0618f9f5c269d75bc2dd1b2f52fc64a2e6d1edb2dd84dac`）。

#468のseed 1013原raw `/tmp/issue468-diagnostics-uf83ft3k/run/job-0002/` のreceipt全103ファイルの長さ・SHAを照合し、inputの完全vectorと一致、vector SHA `6e06d271e0ea54eecb547cfff045a6edda4850bfaa1f9c23bf9f3037ab867131` を確認。RF-T010 effective SHA `d50e6c9fef3e41b8258c00cbd14436a3bcb1d84444d50cf4a445ccf5d288e417`、物理base RF-T008 rev3 `e682165c72d3a8b9f1384a2529f71bacfebfc9d17164d4af5af879e4a138b532`。25変数、全物理bounds、6設定/28区間、Hybrid sum、sigma 0.1、checkpoint 1000。Search 70点 grid SHA `6805740a36f6100d7dec3e7308924242e909255f1ea2d287b7c734c400f98f26`、Terminal 476点 `28ee5b630e4842b183a7c36fd610cc32e2509c0044c6a5848ce2fbd147a22e29`、独立MNA `[0,111]`。bands SHA `1b1182e4c947059cb263c1af52ddf64236bd1fd9e83770cc844126576c7865fe`、入力S2P `ad266111ba1dc2b92f235d39f4a647ff271050bc11941c217661dd299ee59945`、出力S2P `b3cfc861bc0c8221f49328598c9d7d0766a6e94e42e990b6a50f6c90bf9a84da`。

再実行例（freshなパスを使用、level/outputを省くとplain）：

```sh
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1
uv run --frozen python scripts/run_rf_search.py develop \
  --config project/diagnostics/issue470/config.json \
  --starts project/diagnostics/issue470/starts.json \
  --output /tmp/issue470-example-run --spot-checks '{"terminal":[0,111]}' \
  --timing-output /tmp/issue470-example-timing.json --timing-level deep
```

各モードwarmup 1回、実測3回。warmup順 plain/timed/deep、実測順 plain/timed/deep、deep/timed/plain、timed/plain/deep。12 Job全てSearch 1,000 forward、Terminal 1 forward、requested 70,476 RF samples、独立MNA 2 samples：合計12,000 Search + 12 Terminal forwards、845,712 RF samples、24 MNA samples。全runでexit 4・正常完了だが `evaluation_budget_exhausted`、未収束、異常STOPなし。各receiptの全ファイルbyte数とSHA、親台帳、全result JSON（S全要素/IL/APL/RL、Search/Terminal J、vector、cost/ledger等）を12 run間で完全一致照合。最終vector SHA `4f5274551d8336b02cccb23775afaa13f1710e401bf7565bfac80e3a658e2eb9`、Search objective 2599.687730726887、Terminal J 10.678979507384295 dB。Terminal gridの受動性・電力保存、2点の独立MNAはpass。詳細raw・receipt・JSON・stdout/stderrは `/tmp/issue470-rf-timing-mxfmRoOM/` に保持（system tmp、永続性保証なし）。

環境: WSL2 Linux x86_64、Ryzen 7 PRO 4750G、16論理CPU、Python 3.12.15、NumPy 2.5.4、SciPy 1.18.1、OPENBLAS/OMP/MKL各thread環境変数=1。実thread数・CPU周波数固定は未確認。

## 時間と限界

CLI全wall秒（プロセス起動・Terminal等を含む、warmup除外）。中央値差は目安でありばらつきと重なる。

| mode | 実測3回 [s] | 中央値 [s] | 範囲 [s] |
|---|---|---:|---|
| plain | 1.640, 1.713, 1.540 | 1.640 | 1.540–1.713 |
| timed | 1.742, 1.654, 1.591 | 1.654 | 1.591–1.742 |
| deep | 1.706, 1.763, 1.690 | 1.706 | 1.690–1.763 |

中央値のplain比 timed +0.8%、deep +4.1%。測定短時間で散布が大きく、精密な計器負荷・速度差とは解釈しない。warmup CLI wallは順に1.687、1.660、1.842秒。timed Search RF evaluator累積中央値481.758 ms（範囲468.391–523.736）、deepは558.020 ms（524.350–560.599）、どちらも1000回。deepの測定値をplain性能と混同しない。

Search RFのdeep L3（3実測の累積wall中央値と範囲、meanは中央値/回数、failedは全て0）：

| region | 回数 | 累積中央値 [ms] | 範囲 [ms] | 平均 [μs/回] |
|---|---:|---:|---:|---:|
| port_admittance | 1000 | 221.734 | 215.283–224.843 | 221.734 |
| node_admittance | 1000 | 154.574 | 151.674–156.371 | 154.574 |
| matrices | 1000 | 86.588 | 86.105–87.803 | 86.588 |
| power_response | 1000 | 122.009 | 112.912–123.808 | 122.009 |
| decode | 1000 | 74.782 | 71.418–76.354 | 74.782 |
| cascade | 2000 | 57.218 | 52.916–58.804 | 28.609 |

portはnodeを含みnodeはmatricesを含む。全regionはRF evaluatorに包含され、加算不可。各回の差を取ってもwrapper・タイマー負荷込みの残差であり未計測solve等の固有時間ではない。TerminalはL3対象外。計測値はこの入力・環境・有限格子でのみ有効。

次の調査候補（高速化を実装したという意味ではない）: 1. port/node/matricesの包含階層、特にmatricesとnodeの構築・線形代数。2. power_responseの変換・評価。3. decodeの検証と変換。いずれも科学結果・SPD・電力・独立MNAを維持した別Issueで検証する。連続周波数、EM、SRF、Q(f)、公差、実測は未検証。

## 回帰

`test_issue468_timing`, `test_issue448_common_runner`, `test_issue309_rf_core`, `test_issue311_performance`, `test_phase2_branch_mna`, `test_phase2_generic_coupled_lc`, `test_issue315_fixed_stage`, `test_issue419_power_probe` とstorage auditを実行しPASS。誤って追加実行した歴史専用 `test_r2_independent_validation` は、現行loaderが歴史専用RF-F001を拒否するためimport error（`scripts/select_ci_tests.py` の `MANUAL_HISTORICAL_NUMERIC` に明記、通常CI対象外）。この失敗を現行独立MNA回帰のPASSと混同しない。CIとChatGPT独立レビューは別途確認。

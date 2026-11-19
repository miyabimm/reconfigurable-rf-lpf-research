# Issue #473: Search RF の演算単位計時

開発診断であり正式EXP、収束品質評価、最適性・RF適合の証明ではない。測定コードHEAD `6a8438ca305a0118e486a0be41ca050de6787bd2`（clean）。固定入力・再現CLI・各入力のハッシュは [#470](../issue470/README.md) と同一。RF-T010 effective SHA `d50e6c9fef3e41b8258c00cbd14436a3bcb1d84444d50cf4a445ccf5d288e417`、base RF-T008 rev3 `e682165c72d3a8b9f1384a2529f71bacfebfc9d17164d4af5af879e4a138b532`、seed 1013、初期vector SHA `6e06d271e0ea54eecb547cfff045a6edda4850bfaa1f9c23bf9f3037ab867131`。25変数・全物理bounds、6設定28区間、外部S2P、Hybrid sum/sigma 0.1、Search 70点・1000 forwards、Terminal 476点・独立MNA `[0,111]`。Plan SHA `8c28bd63975133e731d266a395c9bdf9ec73d95be9dfd186e744049af2706f2e`。

WSL2 Linux x86_64、Ryzen 7 PRO 4750G、Python 3.12.15、NumPy 2.5.4、SciPy 1.18.1、OPENBLAS/OMP/MKL各thread環境変数=1。実thread数・CPU周波数固定は未確認。各モードwarmup 1回（plain/timed/deep）、実測3回（plain/timed/deep、deep/timed/plain、timed/plain/deep）。新CLIや専用ベンチスクリプトは使わず #470 のCLIで fresh output に実行。生データ・stdout/stderr・診断JSONは `/tmp/issue473-final-diagnostics-1795130803/` に保持（system tmp、永続性保証なし）。最初の試行 `/tmp/issue473-rf-diagnostics-1795130803/` は計測コード修正前の別HEADのため以下の解析に含めない。

12 Job全て exit 4、正常終了だが `evaluation_budget_exhausted`・未収束。各Job Search 1000 + Terminal 1 forwards、requested RF 70,476 samples、独立MNA 2 samples。各Jobのreceiptと親台帳の全rawファイル長・SHA、planを読み戻し照合し、12 runの全ledger/rawがbyte一致。Search objective 2599.687730726887、Terminal J 10.678979507384295 dB、最終vector SHA `4f5274551d8336b02cccb23775afaa13f1710e401bf7565bfac80e3a658e2eb9`、局所終了状態・予算も一致。Terminal格子で受動性・電力保存、2点独立MNAはpass。

さらに別途同HEADで各モード1 Jobを実行し、テスト用に `_forward` を一時的に包み、全1000 Searchおよび1 Terminalの入力vectorと全S/IL/APL/RLのバイト列を順番にハッシュしたところ、3モードとも `a2e8424a9292e4849e26375eefee16635b8a6cfa48292acf3bdb95cfe7447791` で一致。この追加captureは測定wallには含めない。Search objectiveとTerminal Jはrawから照合。ハッシュ比較はbyte同一性の証拠であり、連続帯域での保証ではない。

## wall と計器負荷

CLI wall秒（プロセス起動・Terminalを含む、warmup除外）。同一HEAD内の比較だが散布が大きい。

| mode | 3回 [s] | 中央値 [s] | 範囲 [s] |
|---|---|---:|---|
| plain | 1.974, 1.861, 2.046 | 1.974 | 1.861–2.046 |
| timed | 1.784, 1.965, 1.868 | 1.868 | 1.784–1.965 |
| deep | 1.866, 1.818, 1.900 | 1.866 | 1.818–1.900 |

中央値のplain比 timed -5.4%、deep -5.5%だが、明らかにノイズが計器負荷より大きく、負の負荷や高速化を意味しない。warmup wallは順に1.912、1.926、2.018秒。timedのSearch RF evaluator累積は538.05/624.01/587.62 ms、deepは631.27/642.91/668.32 ms（各1000回）。中央値差55.29 msには追加timer呼出し・記録、wrapperと環境変動が混在し、純粋なtimer一回のコストではない。plain/timedにもdisabled hook分岐があり、PR #472との異なるHEAD間で負荷を定量したとは言えない。

## deep内訳

3実測の累積中央値と範囲。1000回の区間では中央値msと平均μs/回の数値が同じ。全failed=0。`cascade` のみ2000回（平均29.019 μs/回）、`evaluator_setup`はSearchにつき1回でforward前のS2P準備を含む。

| region | 回数 | 累積中央値 [ms] | 範囲 [ms] |
|---|---:|---:|---:|
| evaluator_setup | 1 | 22.788 | 22.664–25.280 |
| rf_evaluate | 1000 | 642.908 | 631.269–668.321 |
| rf/port_admittance | 1000 | 279.096 | 271.965–291.180 |
| rf/node_admittance | 1000 | 200.849 | 195.186–211.753 |
| rf/matrices | 1000 | 114.021 | 112.917–122.250 |
| rf/matrices/build | 1000 | 14.656 | 13.926–15.854 |
| rf/matrices/build_h_incidence | 1000 | 18.123 | 17.744–20.204 |
| rf/matrices/spd_eigvalsh | 1000 | 41.456 | 40.187–43.472 |
| rf/matrices/inductor_solve | 1000 | 24.049 | 22.942–25.027 |
| rf/node/l_expand | 1000 | 28.602 | 27.708–31.099 |
| rf/node/c_stamping | 1000 | 25.358 | 23.265–25.806 |
| rf/port/reorder | 1000 | 11.591 | 11.036–11.656 |
| rf/port/schur_solve | 1000 | 40.437 | 39.215–40.518 |
| rf/port/schur_update | 1000 | 14.956 | 14.160–15.004 |
| rf/y_to_s_solve | 1000 | 36.571 | 35.508–37.420 |
| rf/response_build | 1000 | 17.592 | 16.824–18.222 |
| rf/power_response | 1000 | 135.741 | 134.941–141.770 |
| rf/power/wave_build | 1000 | 36.830 | 36.508–37.634 |
| rf/power/wave_solve | 1000 | 32.609 | 32.560–33.764 |
| rf/power/db_metrics | 1000 | 41.431 | 40.558–44.224 |
| rf/decode | 1000 | 79.608 | 79.399–82.426 |
| rf/cascade | 2000 | 58.038 | 56.535–59.081 |

区間はinclusive、port⊃node⊃matricesであり親子を合算しない。各runの親−直下子の残差範囲はport 11.748–12.314、node 31.295–33.046、matrices 16.849–17.693、power 24.944–26.148 ms。これらは未計時の検査・演算、timer呼出しや集計などを含み、特定演算の固有時間ではない。演算区間にもclock呼出し負荷があり、集計処理は親に含まれる。Searchは `check_power=False`、Terminalは `True` でL3対象外。

候補（高速化を実装したわけではない）: 1. SPD eigvalsh（41.456 ms、必ずSPD検査維持）、2. 周波数バッチSchur solve（40.437 ms、数値安定性維持）、3. power波構築/solve・dB評価（それぞれ36.830/32.609/41.431 ms、極端値と電力検査維持）。いずれもtimer負荷を含み、有限格子・単一入力の優先順位にすぎない。連続周波数、EM、SRF、Q(f)、公差、実測は未検証。

## 回帰

`test_issue468_timing`（計測区間の回数、同一結果、STOP/異常終了復元）、`test_issue448_common_runner`、`test_issue309_rf_core`、`test_issue311_performance`、`test_phase2_branch_mna`、`test_phase2_generic_coupled_lc`、`test_issue315_fixed_stage`、`test_issue419_power_probe`、`scripts/audit_new_experiment_storage.py audit` はPASS。途中の実装で歴史診断probeの文字列置換との互換性が壊れたが修正・再実行済み。CIとChatGPT独立レビューは別途。

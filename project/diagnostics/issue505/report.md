# Issue #505：同一 Search wall 時間の予備比較 A

正式 EXP ではなく開発診断。**RF-T010 trial**、seed 1013 のみ。同一初期 vector から Hybrid 3 run、TRF 3 run（H→T / T→H / H→T）。各 run は独立ディレクトリ。主表は Search 目的値が各時刻までに最小だった**観測候補**を固定し、探索終了後に Terminal 476 点で検証した結果。Terminal J を見て選択し直していない。J ≤ 0 は有限格子上のみの条件適合であり、今回の主表にはない。

## 保存形式（Issue #505 レビュー後の整理）

既存の開発診断に倣い、比較結果は `paired.csv`（各run×1/5/20秒の18行）、実行条件と選択候補は `summary.json`、科学的解釈は本 `report.md` に分離した。全450,369件の逐次観測・巨大raw・controls.tarはPR差分から削除。削除前にCI `45195260738` でgzip元データから18窓を再抽出し、選択sequence・vector SHA・選択規則を照合した。候補10種類の25次元完全vectorを`summary.json`に保存し再評価可能とした。今後の `compare.py` もファイル保存時に全観測を出力せず、窓選択のcompact値だけを保存する。

**証拠の限界：** 全イベント履歴は保持しないため、削除後に別の任意時点の順位を生データから再集計することはできない。既存の予備比較A（1/5/20秒）に必要な数値・選択候補・条件・科学的確認結果は保持する。正式EXPの原本ではない。

## 主結果：Terminal 最大 signed margin J [dB]（小さいほど良い）

| 時刻 | H1 | H2 | H3 | H 中央値 [範囲] | T1 | T2 | T3 | T 中央値 [範囲] |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 s | 9.7283 | 10.1842 | 9.8945 | 9.8945 [9.7283, 10.1842] | 7.3868 | 7.3868 | 7.3868 | 7.3868 [7.3868, 7.3868] |
| 5 s | 5.8247 | 5.8521 | 5.8517 | 5.8517 [5.8247, 5.8521] | 7.3868 | 7.3868 | 7.3868 | 7.3868 [7.3868, 7.3868] |
| 20 s | 0.9534 | 0.9218 | 0.8506 | 0.9218 [0.8506, 0.9534] | 7.3868 | 7.3868 | 7.3868 | 7.3868 [7.3868, 7.3868] |

H は全窓で探索中、T は **0.604–0.625 s で ftol 数値収束**後の既観測最良候補の hold。T が1/5/20秒まで探索を続けたという意味ではない。H は実行終了時には予算到達・未収束だが、20秒の窓は予算により打ち切られていない。比較は1 seed・同一 host の3反復だけで、solver全般の優劣を証明しない。

| run/窓 | Search最良目的値 [dB²] | 観測時刻 [s] | Terminal 最大pass IL [dB] | 最小H2/H3減衰 [dB] | Terminal J [dB] |
|---|---:|---:|---:|---:|---:|
| H1/1 | 1540.1608 | 0.941 | 6.4821 | 20.2717 | 9.7283 |
| H2/1 | 1504.6575 | 0.999 | 6.5047 | 19.8158 | 10.1842 |
| H3/1 | 1991.2374 | 0.999 | 7.5219 | 20.1055 | 9.8945 |
| H1/5 | 301.4157 | 4.994 | 4.3737 | 24.1753 | 5.8247 |
| H2/5 | 301.3170 | 4.999 | 4.3730 | 24.1479 | 5.8521 |
| H3/5 | 301.3161 | 4.997 | 4.3737 | 24.1483 | 5.8517 |
| H1/20 | 4.4260 | 19.999 | 1.7034 | 29.8219 | 0.9534 |
| H2/20 | 4.0606 | 19.997 | 1.6718 | 29.8296 | 0.9218 |
| H3/20 | 3.8226 | 19.999 | 1.6006 | 29.8048 | 0.8506 |
| T1–T3/全窓 | 449.3049 | 0.604–0.625 | 5.1247 | 22.6132 | 7.3868 |

初期 Search objective は H 28654.23931390905、T 28654.239313909056（丸め差）。実 run 終了までの観測最良 Search objective は H 1.6829086103、T 449.3048887828。H の実終了時 Terminal J 0.4550793985 は **20秒窓の値ではない**。H の全窓選択候補9点とTの各runで1点はSPD・物理box検査、Terminal格子上の外部受動性・電力保存検査、独立MNA spot [0,111] の照合が通過。選択された完全vector 10種類とそのSHA、各時間窓の目的値・時刻・Terminal指標は `summary.json` / `paired.csv` に保存した。物理box・SPD、指定MNA spot、Terminal受動性・電力保存のPASS状態を残したが、全spotの複素数行列や全観測時系列は保持しない。独立MNAは全帯域ではない。物理検査の `candidate_promotion_blocked` は解除されていない。

## 実行条件・計測

- 入力：`issue470/config.json`, `starts.json`、RF-T008 base、4L2C/25変数、6設定28独立区間。Search各pass 2/stop 3点で70、Terminal各区間17点で476。固定S2P付き外部port評価。
- RF-T010 effective SHA `d50e6c9fef3e41b8258c00cbd14436a3bcb1d84444d50cf4a445ccf5d288e417`、base `e682165c72d3a8b9f1384a2529f71bacfebfc9d17164d4af5af879e4a138b532`、bands `1b1182e4c947059cb263c1af52ddf64236bd1fd9e83770cc844126576c7865fe`。S2P input `ad266111ba1dc2b92f235d39f4a647ff271050bc11941c217661dd299ee59945`、output `b3cfc861bc0c8221f49328598c9d7d0766a6e94e42e990b6a50f6c90bf9a84da`。
- 初期 vector SHA `6e06d271e0ea54eecb547cfff045a6edda4850bfaa1f9c23bf9f3037ab867131`、物理 search bounds SHA `bf274caf1ff46fed4fead6af5dc2f151bdb7579f62117434c1507aed44aea521` は両 arm 一致。Search grid `6805740a36f6100d7dec3e7308924242e909255f1ea2d287b7c734c400f98f26`、Terminal grid `28ee5b630e4842b183a7c36fd610cc32e2509c0044c6a5848ce2fbd147a22e29` も一致。
- Plan SHA H `7dbe85f32e713a8b7ea7fd6acf502c26c1c076113617c818ee5d41cf836d8a94`、T `635d512e32e37897be4a844aaa6fb5bed14b7a4aa6956a4a3c4713ed30eeb6c4`。solver/options/budgetの差により一致を要求しない。Plan SHAは `summary.json` に保存。完全な凍結Planは同じ入力と `compare.py` で再生成できる。
- H: L-BFGS-B Hybrid、sum、batch/partial FD、lk cache、restart sigma 0.1、名目 max_search_forwards 150000。batch最後のgroup完了で各150020 Search forward。3 local runs、2回の local success と最後の予算中断、全体は `evaluation_budget_exhausted` / 非収束。T: TRF解析Jacobian、sum、cache off、restartなし、max_evaluations 5000。各103感度 forward、SciPy nfev=103/njev=96、status=2 ftol、`converged`。数値収束は RF 適合ではない。
- H Search requested 10501400 / computed 6462400 samples、T Search requested/computed 7210。Tの `search_cache_stats.computed_samples=0` は感度評価をそのcache統計が計上しないためで、正しい値は `trf_details.computed_samples`。Runner自身のTerminalは各1 forward/476 samples/独立MNA2点。これに加えて事後検証はH各3 forward/1428 samples/MNA6、T各1/476/MNA2。Search時間・Runner予算とは別。H実行終了後の別途Terminalと切出し点のTerminalを混同しない。
- Solver wall/CPU [s]: H1 37.965/33.616、H2 37.976/33.623、H3 37.408/32.949；T1 0.625/0.625、T2 0.604/0.604、T3 0.615/0.615。Hはwall−CPUが約4.3–4.5秒で外乱・待機等があるが原因未特定。load averageの始終、全run時間は `summary.json` に保存（post処理時間は保存対象外）。計測中の並列診断は行っていない。
- source HEAD `252ec531f3ef280a65c32fbe25a8bf859df85efe`、Runner source identity `632aad1c003b26066ec7763f99385bccaab9d0bde22039dfdae5110f58219965`、対象src等のdirty patch SHA は空の `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`。診断script自体のSHA `8c1c033f8c068ea5e0d2063adc3a629f175c49006dac649b02879789bf90432f`。Python 3.12.15、NumPy 2.5.4、SciPy 1.18.1、Linux WSL2 x86_64、OPENBLAS/OMP/MKL各1、ホスト・affinity・NumPy BLAS設定はraw。深い計測ではない。

`compare.py` は診断プロセス内のみ既存 solver callback を包む。原点は evaluator setup後、solver呼出直前。目的値確定後の callback で時刻/vector/forwardをメモリに保持し、SHA/JSONは探索後に計算する。Hybrid batchは結果が消費され目的値が確定した後、TRFはfun/jac共用cacheの新規評価だけを記録。Search外のTerminal評価時間を窓に入れない。選択は `elapsed <= window`、同値は先着。checkpoint時刻ではない。Solver/Runnerの規定動作・停止・ledger・RF Coreは変更していない。

## 校正、control、異常および証拠

短い初期校正ではH名目1000→1014 forward・0.221秒、T上限100→100 forward・0.597秒でいずれも20秒未満の **budget_censored**。続くH名目100000→100022 forward・24.290秒、T上限5000→103 forward・0.705秒でftol収束。Hの余裕を見て本測定は150000に増やし、回数一致を要求しない。校正のH 100000/T 5000は本測定とsource HEADが異なり、主表には混ぜない。

計測対象外のwarmup（H1000/T28）後、短いcontrol/観測ありをそれぞれ実施。H 5018 forward: control wall/CPU 1.171/1.030秒、観測あり1.155/1.068秒；T 28: 0.168/0.168秒、観測あり0.161/0.161秒。各ペアの最終objective/vector SHAは一致。各1回の短時間比較であり、負荷がゼロと証明するものではない。なおcontrolの窓候補は観測を無効にしたので欠測であり、品質比較には使わない。

初回H校正はRunner自体は完了したが、診断側で独立MNAのcomplex値をJSON化できず保存に失敗。修正後にH1000校正をやり直した。失敗した元Runner記録・部分JSONは `/tmp/issue505-calibration-dObiw7ah/h` と `h.json` に保持し、成功と数えない。以後の6本・control/warmupにRF STOPや欠測はない。選択した18窓レコードは `paired.csv`、10種類の完全候補vectorと各runの計測条件・実消費・停止理由は `summary.json` に保存。校正・control・warmupの重要数値と失敗履歴は本レポートに残す。全イベントraw、controlアーカイブ、元Runnerのraw/checkpoint/receiptはGitに保存しない。元の測定実施時に用いた一時ディレクトリへの依存も設けない。各runの必要な実行結果・指紋・時間窓の選択候補は `summary.json` と `paired.csv` に抽出済み。全イベント・Runnerの大きなrawやcheckpointはGitに含めない。

再現は空のsystem temp配下の未存在pathと未存在recordを指定：

```sh
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  uv run --frozen python project/diagnostics/issue505/compare.py \
  hybrid 150000 /tmp/<fresh-run> /tmp/<fresh-record>.json.gz
# trf 5000 に置換、control は --control
```

## 解釈と次の判断

このseedではTRFは1秒窓で良いが、早期停滞後は改善せず、Hは5/20秒窓でより小さいJに達した。TRF restartの有無が重要な仮説だが、この比較は単一TRFとrestart付きHybridの比較であって、restart自体の因果効果は未検証。実装や本比較への追加は別判断とする。

比較Bへの提案（未承認・未着手）：同じ1/5/20秒窓、事前凍結した20 seedと同一開始・物理条件、少なくとも各3反復で順序交互化。各方式独立に校正して20秒を十分超える予算を確保し、早期収束holdと予算censorを区別する。TRF restartの必要性は別armとその予算・公平性・実装仕様を先に決める。1 seed結果から予算や普遍的勝敗を確定しない。

有限格子・モデルの結果であり、連続周波数、SRF、Q(f)、EM、製造公差、実測、物理実装可能性、大域最適性はいずれも未保証。

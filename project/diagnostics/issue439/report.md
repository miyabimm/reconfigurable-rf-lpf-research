# Issue #439 — 4L2C full-physical random starts × weighted Hybrid

**判定:** 開発限定の20 seedを全件実行。Hybrid数値収束は19/20、17点Terminalのstrict H2/H3 ≥30.00 dBは1/20。strict候補は既知良好解の+0.02 dB／+0.05 dB IL範囲には入らず、条件同時達成は0/20。有限探索の観測であり、大域最適性・連続帯域適合・物理実装を証明しない。

## 実施条件と固定証拠

- Issue: [#439](https://github.com/miyabimm/reconfigurable-rf-lpf-research/issues/439)。同Issue内のユーザー承認範囲によるPhase 2 **開発限定実験**。正式EXPではなく、EXP番号・`data/experiment_index.csv`・中央予約台帳を変更していない。
- 実行コードHEAD: `79789f2f3a4b8a9feece9a4cc9a212b4c086f1ed`（PR #438 merge後main）。[PR #438のpostmerge smoke](https://github.com/miyabimm/reconfigurable-rf-lpf-research/actions/runs/43723263182) はSUCCESS。対象checkoutは完全履歴化済み（shallow=false）。
- RF: trial **RF-T008 opt-in / `full_lpf`**、effective SHA `e682165c72d3a8b9f1384a2529f71bacfebfc9d17164d4af5af879e4a138b532`。bands SHA `1b1182e4c947059cb263c1af52ddf64236bd1fd9e83770cc844126576c7865fe`。固定input/output S2P SHAは `ad266111ba1dc2b92f235d39f4a647ff271050bc11941c217661dd299ee59945` / `b3cfc861bc0c8221f49328598c9d7d0766a6e94e42e990b6a50f6c90bf9a84da`。正式active RF-F003は変更なし。
- Circuit: `project/diagnostics/issue361/definition.json`（byte SHA `e8ac857c063e0b9d2eb8eaf629c2e4b700a694e9241f3bbc596d99f6374487f6`、canonical SHA `bc50042a1b0b1ebf19c0272fb2ee944b52cd76e14eb8d44673bfa57f6033c068`）、既知EXP-062 A6と同じ4L2C/25成分/全6設定。基準ベクトルは初期値生成へ注入していない。
- 評価は6設定・28の別々のUL/DL/H2/H3区間。H2/H3 strict閾値30.00 dB。Hybridの固定目的は `max(0, worst_pass_IL−0.30)^2 + 100 × mean(max(0,30.01−H2/H3 attenuation)^2)`。30.01は探索マージン、35 dB nominalは別の情報指標で、いずれもstrict30判定と混同しない。
- Solver: Hybrid, `sum`, `maxiter=max_evaluations=150000`, `max_restarts=0`, `restart_sigma=0.1`。Search 70 samples/forward（pass 2点、H2/H3各3点）、Selection 84、Terminal 476（17点/区間）、best-J 1候補。各Terminalで独立branch-current MNA spot `[0,111]`。
- Starts: seed 1001〜1020、全20件を探索前にscrambled Sobol 1点ずつ/seedで生成。完全25変数のphysical hard bounds、clip/repair/retryなし。20/20が物理閉区間・部品・結線role・全L行列SPDを通過し、無効seedの置換なし。開始時最小L固有値は `5.204340157276986e−10 H`。全vectorとSHA、生成方式、物理bounds matrix、各Plan/config/starts fingerprintは[`preflight.json`](preflight.json)／[`generated/`](generated/)／[`inputs/`](inputs/)に保存。
- 初期点20件とbest-J候補20件は同じ70点格子でread-only評価・照合。Search rawのbest/solver endpoint/Terminalを区別し、全checkpoint SHA・各input/result SHAを保存。strict候補のみIL昇順・同値vector SHAでdense/MNA選抜。追加seed/retry/resumeなし。

## 20 seedの結果

`J(start) → best J` は同一70点格子。ILとΔIL、H2/H3最小値は476点Terminal。ΔIL基準は既存#437/EXP-062既知解の17点IL `0.8278411484628502 dB`。IL基準+0.02/+0.05は厳密に元値へ加算（丸めでPASS化しない）。CPUはuser+system、RSSはGNU time最大値。wallはseed 1001〜1003でGNU time、1004〜1020でPython monotonic計測を使用したため時間値は厳密な同一計測器比較ではない。

| Seed | Hybrid | Search nfev | J(start) → best J | Terminal strict30 | Terminal IL dB | min H2 / H3 dB | ΔIL dB | wall s | CPU s | max RSS KiB |
|---:|---|---:|---:|---|---:|---:|---:|---:|---:|---:|
| 1001 | 収束 | 7,020 | 54,194.558 → 5,774.358 | FAIL | 8.582769 | 22.5016 / 18.6474 | +7.754928 | 11.85 | 10.32 | 123,144 |
| 1002 | 収束 | 3,588 | 76,911.022 → 4,506.022 | FAIL | 7.649546 | 22.3477 / 19.4663 | +6.821704 | 3.97 | 5.12 | 112,844 |
| 1003 | 収束 | 78 | 75,849.043 → 73,403.858 | FAIL | 1.521407 | 2.1473 / 3.0634 | +0.693566 | 2.59 | 1.98 | 111,956 |
| 1004 | 収束 | 1,456 | 77,921.482 → 31,618.721 | FAIL | 1.848901 | 5.1566 / 5.1969 | +1.021060 | 3.42 | 3.09 | 112,316 |
| 1005 | 収束 | 1,430 | 66,325.925 → 31,618.721 | FAIL | 1.848901 | 5.1566 / 5.1969 | +1.021060 | 3.20 | 2.85 | 112,748 |
| 1006 | 収束 | 4,550 | 78,029.734 → 2,332.534 | FAIL | 49.893468 | 27.2762 / 27.2823 | +49.065627 | 6.24 | 5.45 | 113,720 |
| 1007 | 収束 | 17,836 | 56,330.011 → 20.780966 | FAIL | 4.705317 | 29.8469 / 29.3934 | +3.877476 | 19.85 | 17.50 | 113,016 |
| 1008 | **未収束** | 12,532 | 32,549.864 → 22.838548 | FAIL | 4.997191 | 29.6235 / 29.8736 | +4.169350 | 13.88 | 12.34 | 112,800 |
| 1009 | 収束 | 2,808 | 73,474.915 → 25,351.819 | FAIL | 24.527384 | 6.4464 / 7.0128 | +23.699543 | 4.51 | 4.03 | 111,152 |
| 1010 | 収束 | 5,720 | 68,428.467 → 226.975286 | FAIL | 7.511415 | 25.6567 / 26.2591 | +6.683573 | 7.66 | 6.79 | 113,164 |
| 1011 | 収束 | 9,230 | 79,645.117 → 41.588078 | FAIL | 6.621250 | 29.5333 / 29.5416 | +5.793409 | 11.87 | 10.48 | 112,424 |
| 1012 | 収束 | 30,134 | 37,243.138 → 0.886783 | **PASS** | **1.241676** | **30.0070 / 30.0098** | **+0.413835** | 35.91 | 31.52 | 113,220 |
| 1013 | 収束 | 3,276 | 64,140.636 → 127.433482 | FAIL | 11.151027 | 28.1504 / 29.4805 | +10.323186 | 4.88 | 4.39 | 113,628 |
| 1014 | 収束 | 35,516 | 71,695.392 → 33.397135 | FAIL | 5.885952 | 29.4801 / 29.3083 | +5.058111 | 38.15 | 33.60 | 111,580 |
| 1015 | 収束 | 78 | 74,398.460 → 73,403.858 | FAIL | 1.521407 | 2.1473 / 3.0634 | +0.693566 | 1.83 | 1.67 | 111,344 |
| 1016 | 収束 | 78 | 74,223.834 → 73,403.858 | FAIL | 1.521407 | 2.1473 / 3.0634 | +0.693566 | 1.88 | 1.72 | 112,060 |
| 1017 | 収束 | 37,492 | 72,949.829 → 438.012635 | FAIL | 8.036110 | 28.1463 / 23.2189 | +7.208269 | 40.43 | 35.55 | 114,136 |
| 1018 | 収束 | 18,772 | 76,712.861 → 24.584748 | FAIL | 5.249290 | 29.8836 / 29.9364 | +4.421449 | 21.24 | 18.73 | 112,796 |
| 1019 | 収束 | 1,430 | 71,343.157 → 31,618.721 | FAIL | 1.848901 | 5.1566 / 5.1969 | +1.021060 | 3.24 | 2.88 | 111,956 |
| 1020 | 収束 | 4,446 | 72,335.314 → 11,830.246 | FAIL | 25.339238 | 14.4707 / 12.6746 | +24.511397 | 6.50 | 5.70 | 112,632 |

Seed 1008はL-BFGS-B `success=false`, status 2, message `ABNORMAL`, 166 iterations/12,532 evaluationsで未収束。これはsolver失敗観測であり、物理/RF異常や失敗の証明ではない。収束判定とRF strict適合は独立に集計。

## 候補と独立検証

- 20/20が合法で実行、19/20（95%）がHybrid収束。Search forwardは合計197,470 / 3,000,000、seed当たり78〜37,492、中央値4,498。1 Job上限150,000は超過なし。
- 17点Terminal strict30 PASSはseed 1012のみ：`min H2=30.0069741341`, `min H3=30.0097857234 dB`。**30.01 dB search marginは未達**、H2/H3の35 dB nominalも未達。全20 seedで30.01 targetおよび35 dB nominal H2/H3は0件。
- seed 1012は同じ70点格子でstart J `37,243.138163` → search best J `0.886783301`。既知解の70点J `0.2792115161`より大きく、既知性能には再到達していない。17点ILは基準より+0.4138346568 dB。strict30 PASSかつ+0.02 dB以内は0/20、+0.05 dB以内も0/20、収束∧strict30∧+0.02 dB以内も0/20。
- search best-J とSolver endpointはSHA一致3/20のみ。端点をbest候補やTerminal結果へ読み替えず、全best/endpoint vector・Jを[`results.json`](results.json)に分けて記録。
- 17点strict PASS候補は1件だけだったためseed 1012をdense選抜。1001点/区間（28,028点）でもstrict30 PASS、worst IL `1.2416758053 dB`、min H2/H3は同値。84点独立branch-current MNAはS/IL/APL/RL比較、受動性・電力収支をPASS、最大絶対誤差 `7.32e−13`（許容`1e−9`）。これは1候補・有限格子の検証であり、連続周波数保証ではない。
- 各Terminalで独立MNA spot `[0,111]` は20×2=40 sample PASS。密候補MNA84を合わせ独立MNA total 124 / 460 sample上限。全28区間/6設定のTerminal要件ごとの要約は`results.json`にあり、strict候補のinterval詳細も保持。

## 実費用・保存・再現性

| 項目 | 実消費 | Issue上限 |
|---|---:|---:|
| Search forwards | 197,470 | 3,000,000 |
| Search RF samples（70/forward） | 13,822,900 | — |
| 全20 Jobのsearch + selection + terminal | 13,834,100 | — |
| 初期点read-only 20×70 | 1,400 | — |
| best-J 20件の同一70点 readback | 1,400 | — |
| dense 28,028 + MNA比較84 primary samples | 28,112 | — |
| **Primary RF samples total** | **13,865,012** | **211,000,000** |
| Independent MNA samples | 124 | 460 |

環境: Python 3.12.15, NumPy 2.5.4, SciPy 1.18.1、OPENBLAS/OMP/MKL各1。`uv.lock` SHA `52144cfd0dfc7249e78c24942bac69fddc8dc3ae088799d9cf31d0d90e824e0b`。実Worker source identity SHA `8a2ada9533414b186569f9870df628907b4974d4daa580cccf79fde46e442f12`。Generic source helperにWorker CLI scriptのSHAを足した実体は[`source_provenance.json`](source_provenance.json)に固定。

- Seed 1001 Worker自体はexit 0で完了。最初の薄い記録wrapperが、完了後のsample集計で空summaryを処理できず例外となった。入力/result/checkpoint実byteを再読込して検証し、execution recordを修復した。再実行・retry・resumeはしていない。Seed 1002〜1020は更新後の記録手順で順次実施。
- Seed 1015のGNU timeは負のelapsed `−1.88 s`を出したためwall統計に使用しない。Seed 1001〜1003の外側monotonic値はwrapper例外時に保存されなかったのでGNU time値を記録し、1004〜1020は外側`time.monotonic()`を採用。全raw time logとSHAを`execution.json`で保持する。wall/CPUの集計は参考情報で、性能比較の断定には使わない。
- Raw input/result/checkpoints/stdout/time はsystem tmpに保持され、寿命は保証されない。Gitの診断記録に完全初期vector、候補vector、全checkpoint SHA、各結果/input SHA、全サンプル費用、28区間サマリー、検証結果をcurate。Issue #397の方針に従い、未収束seedも残す。新規EXP manifest/index/registryは作成・変更していない。
- RF入力、formal constraints、共通Solver/Worker/Runnerの変更なし。試験条件・モデル意味・評価格子の変更なし。

## 限界・結論

この有限20点Sobol/Hybrid試験では、全20の合法startから19がSolver収束し、1件がstrict30を達成した。一方、その候補は既知good解よりILが約0.414 dB悪く、探索目標30.01およびnominal35にも届かず、既知性能への再到達は確認できなかった。よってこの結果は「ランダム初期値で収束することは多かったが、指定予算内で既知良好性能に近づく成功率は0/20」という限定観測である。探索空間全体の不可能性や大域最適性を示さない。

未検証: continuous-frequency guarantee、EM/layout、Q(f)/SRF、tolerance、実測、実装可能性。Draft PRでChatGPT独立レビュー待ち。Issue #439範囲内の結果提出であり、Formal RFへの昇格・Phase移行・追加探索の承認を意味しない。

## Evidence index

- [`preflight.json`](preflight.json), [`initial_evaluations.json`](initial_evaluations.json), [`source_provenance.json`](source_provenance.json), [`execution.json`](execution.json), [`results.json`](results.json)
- Generator/curator/wrapper: [`prepare.py`](prepare.py), [`evaluate.py`](evaluate.py), [`run_job.py`](run_job.py), [`summarize.py`](summarize.py)
- Preflight SHA `c6c5d7d476e5ad2306309f0323c8bf93a0f379a4300637c0857227143e804879`
- Initial evaluations SHA `83d15ad8649b23c025da3765485c7f4275b8787062cc3731f9a3305a148116f7`
- Source provenance SHA `96b78427989426bc50f200cf2bd6803d516a14b947991db4e67e93591e67aaa8`
- Execution SHA `b0d6acc26302891d437361e596385fd1acbe24d618786c6c97cd0dd7b1591105`
- Results SHA `bf541021a52376986d7d92b08434f4b8a019d1d1b5c839b043bde5021f2defac`

# Issue #437：既知4L2C近傍 weighted_violation の開発評価

## 範囲・結論

[Issue #437](https://github.com/miyabimm/reconfigurable-rf-lpf-research/issues/437) で指定された A→B→C の3 Jobだけを実行。正式EXPではない。基準main `6037ba0e20d98a1dfa222ffe745c1e8ae644273c` と [postmerge smoke PASS](https://github.com/miyabimm/reconfigurable-rf-lpf-research/actions/runs/43722165304) を開始前に確認した。探索コードのHEADも同じで、対象ソースの tracked dirty patch は空。Aは収束、B/Cは20,000 search forward上限で未収束。3候補とも開始点から70点Jが改善し、17点strict30 PASS。**30.01 dB目標は3候補とも17点で未達成**。選抜A/Bは1001点strict30と84点独立MNA PASS。Cの密格子・84点MNAは選抜対象外。これは1 seedの限定観測であり、大域最適・連続周波数・物理実装・実測の保証ではない。

## 固定条件と基準

- RF-T008 trial opt-in / full_lpf、effective SHA `e682165c72d3a8b9f1384a2529f71bacfebfc9d17164d4af5af879e4a138b532`。正式RF-F003は変更なし。6設定・28の別区間、外部2 S2P込み。bands SHA `1b1182e4c947059cb263c1af52ddf64236bd1fd9e83770cc844126576c7865fe`、S2P input/output SHA `ad266111ba1dc2b92f235d39f4a647ff271050bc11941c217661dd299ee59945` / `b3cfc861bc0c8221f49328598c9d7d0766a6e94e42e990b6a50f6c90bf9a84da` を実バイトとPlanで照合。
- #433のbox/startsを無変更で使用。12/19/25自由座標とbox内start・閉区間・SPD・接続役割を確認。ファイルbyte/canonical SHA・全ベクトル・各チェックは [`preflight.json`](preflight.json) と元 [`issue433/`](../issue433/) に記録。元EXP-062 checkpoint byte SHA `4fbd86e8b46ad7bcb550ba327672b0983e8b58e9ce4b2a9364f8c6557a812b4b`、vector SHA `4131fa4e677afd364c8e448325d2971f05214284047c349bf2f794585668313c`。definition byte/canonical SHA `e8ac857c063e0b9d2eb8eaf629c2e4b700a694e9241f3bbc596d99f6374487f6` / `bc50042a1b0b1ebf19c0272fb2ee944b52cd76e14eb8d44673bfa57f6033c068`。原本は変更していない。
- 基準解の現HEAD再評価：70点 J **0.2792115161039812**（IL項 0.2786162780105807、H項 0.0005952380934005133）、strict PASS・30.01目標FAIL。17点 IL **0.8278411484628502 dB**、最小H2/H3 **30.004999999866513 / 30.004999999930703 dB**、strict PASSで #433保存値と一致。#433の基準denseはstrict PASS、IL 0.8278411484628502、H3最小30.004736913098142 dB。今回は基準denseを再計算していない。
- Plan SHA `c72c912436d5d61d7ca9fa07112840faadff59a9880ff6a3950d2570b40ca114`。1 Job静的予約 search 1,400,000、selection 84、terminal 476、計1,400,560 samples。searchはpass 2点/区間、H2/H3 3点/区間の70点、selectionは84点、terminalは17点/区間476点。seed 1001、Hybrid、maxiter=max_evaluations=20,000、restart 0、best-J 1件のみ選抜。terminal spot `[0,111]`、checkpoint interval 100。
- J = max(0, IL−0.30)² + 100×mean(max(0,30.01−H2/H3 attenuation)²)。重みと30.01の探索余裕は未検証。mandatory 30 dBは不変、35 dB nominalを目的に含めない。J=0では0.30以下のIL改善を追わない。70点、84点、476点のJは各格子の平均で、異なる格子の値を直接優劣比較しない。

## Job結果：search、selection、solver

| Job | 開始J → best 70点J | IL項 / H項（best 70点） | 84点J | solver / exit / stop | nfev / nit | wall / user+sys 秒 / max RSS KiB |
|---|---:|---:|---:|---|---:|---:|
| A | 67.8348772013 → 0.278994549713 | 0.278629305424 / 0.000365244288 | 0.278994549713 | converged / 0 / restarts_exhausted | 2,054 / 87 | 4.13 / 3.64 / 111100 |
| B | 284.997650719 → 0.278717823714 | 0.278704928119 / 0.000012895595 | 0.278717823714 | not_converged / 4 / evaluation_budget_exhausted | 20,000 / 585 | 24.01 / 21.14 / 111268 |
| C | 714.371015497 → 0.279362711229 | 0.279355644389 / 0.000007066840 | 0.279362711229 | not_converged / 4 / evaluation_budget_exhausted | 20,000 / 360 | 21.04 / 20.24 / 113392 |

全Jobは70点strict30 PASS・30.01目標FAIL。best-J vector完全値、solver出力、入力/結果/全checkpoint SHA、計測、各格子のJ内訳と物理検査は [`results.json`](results.json)。最終保存bestはsearch best・selection・terminalとvector SHA一致、独立再評価70/84のJも一致。exit 0/4はsolver状態でありRF strictとは別。探索中のbest-Jとsolver endpointは同一とは限らず、best-Jのみを選抜した。A/B/Cのbest vector SHAは `a3a8c962a4835a5704e3e7fda8c5265cf5f3b1788a2d7df64e2e742d462aee3f` / `fbb9f6207f187dec5889e3f794d8f68ac0dcc02ab2978af4325a193cc5728aca` / `64a8a4af4290ac6af42f7581ead554f750ab4dfa2ea30e637caae7cbb0bafc1f`。

## 17点共通格子・追加検証

ΔILは上記基準解の17点に対する差。strict30と探索目標30.01は別判定。全候補の17点H2/H3最小はいずれも35 dB未満で、35 nominalも未達。

| 候補 | strict30 | IL dB / ΔIL dB | 最小H2 / H3 dB | 30.01目標 |
|---|---|---:|---:|---|
| A weighted terminal | PASS | 0.827853488597 / +0.000012340134 | 30.0042707315 / 30.0025540084 | FAIL |
| B weighted terminal | PASS | 0.827925116015 / +0.000083967552 | 30.0091213155 / 30.0083960366 | FAIL |
| C weighted terminal | PASS | 0.828541052700 / +0.000699904237 | 30.0089808518 / 30.0071698285 | FAIL |
| A #433 Hybrid terminal | PASS | 0.827841148463 / 0 | 30.0000188870 / 30.0049999999 | FAIL |
| A #433 Hybrid RF-best | PASS | 0.827841148463 / 0 | 30.0000188870 / 30.0049999999 | FAIL |
| B #433 Hybrid terminal | FAIL | 0.827780632443 / −0.000060516020 | 29.9989107038 / 29.9849290336 | FAIL |
| B #433 Hybrid RF-best | PASS | 0.837398490654 / +0.009557342191 | 30.0044366289 / 30.0049925681 | FAIL |
| C #433 Hybrid terminal | FAIL | 0.828153212523 / +0.000312064060 | 29.9988352800 / 29.9971887941 | FAIL |
| C #433 Hybrid RF-best | PASS | 0.836024624042 / +0.008183475579 | 30.0014333892 / 30.0021035691 | FAIL |

旧候補6件を現HEADで同じ476点に再評価。旧Hybridの旧目的値と新Jは比較しない。上記の新旧は同じ近傍・開始点・格子・forward上限だが、#433旧Hybridはmaxiter 350、新modeは明示仕様どおりmaxiter 20,000なので反復上限は同一ではない。

17点strict PASSの新terminalをIL昇順・同値時vector SHA順に選別し **A/B** を1001点/区間へ：Aはstrict PASS、IL 0.827853488597、H2/H3最小 30.0042707315 / 30.0022967482 dB；Bはstrict PASS、IL 0.827925116015、H2/H3最小 30.0091213155 / 30.0083960366 dB。両者とも30.01未達。各候補の84点独立branch-current MNAはS・IL・APL・RL比較、受動性・電力収支 PASS、最大誤差とも **1.059e−12**（許容1e−9）。全3 terminalの指定2点spotもPASS。Cはdense/MNA84 **not_run**、2点spotのみ。これは連続帯域やEM/SRF/Q(f)/公差/実測を検証しない。

## 消費・再現性・保存

- Primary実費：search **2,943,780**（42,054 forwards）、Job selection **252**、terminal **1,428**、基準70/476と開始点70×3 **756**、best別再評価70/84/476×3 **1,890**、旧候補476×6 **2,856**、dense 28,028×2と独立比較用primary 84×2 **56,224**。合計 **3,007,186 / 4,400,000**。独立MNAは別途 terminal 2×3 + 選抜84×2 = **174 samples**。#433の費用は含まない。要求値＝正常完了値。追加seed、resume、自動再実行、条件調整なし。
- 環境：Python 3.12.15、NumPy 2.5.4、SciPy 1.18.1、OPENBLAS/OMP/MKL各1、uv.lock SHA `52144cfd0dfc7249e78c24942bac69fddc8dc3ae088799d9cf31d0d90e824e0b`。全Job source identity SHA `179dfdf370718403e294dfecb3000941972ed3902c091a7ed8b63699c887bbea`。実行前の独立評価スクリプトは新規未追跡、既存 `.issue361-definition.json` も未追跡・原本と同byteで、探索ソースは変更なし。
- Job CLIは `OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 uv run --frozen python scripts/run_development_worker.py --objective-mode weighted_violation --max-search-forwards 20000 --search-bounds project/diagnostics/issue433/<A|B|C>-box.json --config project/diagnostics/issue433/hybrid.json --starts project/diagnostics/issue433/<A|B|C>-starts.json --seed 1001 --arm hybrid --checkpoint-interval 100 --spot-checks '{"terminal":[0,111]}' --output <各jobの新規system-tmpパス>`。この記録は再実行の承認ではない。
- [`evaluate.py`](evaluate.py) は限定されたread-only評価用でsolverを起動しない。再実行はRF samplesを消費する。preflight初回は `PYTHONPATH` 未設定でimport時に終了し、RF forward消費なし。その後 `PYTHONPATH=src` で完了。Jobを再試行していない。
- Raw system tmp（寿命保証なし）：`/tmp/issue437-preflight-B1D4OZiQ`、`/tmp/issue437-A-laUUTaYs`、`/tmp/issue437-B-kefHSPBD`、`/tmp/issue437-C-FR8dmGdT`。作業後も保持。Gitに完全vector・入力/結果/checkpoint SHA・検証要約を保存するが、tmp raw全体の永続性は保証しない。
- 自己検証：postmerge smoke、指紋/基準/Plan照合、best・selection・terminal再評価、指定spot、選抜dense/MNA、費用再集計、`test_issue435_weighted_development.py` 7件 PASS。独立レビュー待ち。物理的実現性、連続周波数、広域探索成功率、科学的認定は未証明。

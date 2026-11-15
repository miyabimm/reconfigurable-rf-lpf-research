# Issue #433：既知4L2C近傍の開発限定比較

## 範囲と結論

[Issue #433](https://github.com/miyabimm/reconfigurable-rf-lpf-research/issues/433) の6 Jobのみ実行。最新main `b876667c8af5f6467bcbb951ea62780d94c90ccb` の[postmerge smoke](https://github.com/miyabimm/reconfigurable-rf-lpf-research/actions/runs/43702229600) PASSを確認。探索ソース・凍結入力のHEADは `38736b563e652a910c3263c38dbfe7590a6d44bf`（RF Core/optimizer/worker/runnerの変更なし）。これは**正式EXPでもG0–G5でもなく、1 seedだけの開発評価**。大域最適・連続帯域・実装可能性は主張しない。

基準解に対し、A/HybridのterminalとRF-bestは17点・1001点ともstrict PASS、IL差は表示精度上0。B/CでもHybrid RF-bestは17点strict PASS、基準比IL +0.00956/+0.00818 dBだが、**solver endpointのterminalは両方FAIL**。SLSQPのsolver収束3件は全て17点strict FAIL（Aは約1e-12 dB、B/Cは約0.0155 dB）。70点searchと476点terminalの格子差、RF-bestとsolver endpoint、solver収束とstrict判定は別。下記は有限数値サンプルの観測であり、strict閾値を緩和しない。

## 再現性・基準

- RF-T008 trialを明示opt-in、effective SHA `e682165c72d3a8b9f1384a2529f71bacfebfc9d17164d4af5af879e4a138b532`、`full_lpf`、6設定・28個別区間、外部2 S2P込み。active formal RF-F003は未変更。bands SHA `1b1182e4c947059cb263c1af52ddf64236bd1fd9e83770cc844126576c7865fe`。input/output S2P SHAはそれぞれ `ad266111ba1dc2b92f235d39f4a647ff271050bc11941c217661dd299ee59945` / `b3cfc861bc0c8221f49328598c9d7d0766a6e94e42e990b6a50f6c90bf9a84da`、preflightで実バイト照合。
- 元 `experiments/chatgpt_topology_search/runs/EXP-062/checkpoints/a6_best.json` byte SHA `4fbd86e8b46ad7bcb550ba327672b0983e8b58e9ce4b2a9364f8c6557a812b4b`、元の25要素 canonical vector SHA `4131fa4e677afd364c8e448325d2971f05214284047c349bf2f794585668313c`。元vectorと同ファイル内固定値・全設定、結線・部品・順序・公称Qを照合。definition byte SHA `e8ac857c063e0b9d2eb8eaf629c2e4b700a694e9241f3bbc596d99f6374487f6`、canonical SHA `bc50042a1b0b1ebf19c0272fb2ee944b52cd76e14eb8d44673bfa57f6033c068`。元checkpoint/manifest/indexは未変更。
- 基準の閉区間部品・役割・SPD PASS、最小L固有値 2.3262911741 nH。17点/区間では IL **0.8278411484628502 dB**、最小H2 **30.004999999866513 dB**、H3 **30.004999999930703 dB**、strict PASS。#361参考と一致。
- 現行1001点/区間（28,028 samples）は IL **0.8278411484628502 dB**、H2 **30.004999999866513 dB**、H3 **30.004736913098142 dB**、strict PASS。旧保存IL 0.8278411484628513との差は約 −1.1e−15 dB。17点と密格子は別検証深度。
- 独立branch-current MNAは選択84点すべてでS・IL・APL・RLを既存実装に照合、受動性/電力収支 PASS、最大誤差 1.11e−12（比較許容値1e−9）。これは84点限定。6設定別の基準性能は [`baseline.json`](baseline.json)。
- Python 3.12.15、NumPy 2.5.4、SciPy 1.18.1、OPENBLAS/OMP/MKL各1。uv.lock SHA `52144cfd0dfc7249e78c24942bac69fddc8dc3ae088799d9cf31d0d90e824e0b`。Job共通source identity SHA `4efb2463e3ee1ef17f04b62753f72506960a59c1161a603b7f87a93f7dda91bd`、tracked dirty patchは空。ファイル別source SHAと環境は [`results.json`](results.json)。基準評価時は同じRF/source treeで、入力生成スクリプトは未追跡だった。

## 凍結入力・評価条件

完全box・x0・canonical SHAは [`A.json`](A.json)、[`B.json`](B.json)、[`C.json`](C.json)、実CLI入力はそれぞれ `*-box.json` / `*-starts.json`。A/B/C各12/19/25自由座標。候補boxとphysical hardの交差をbinary64で一度作成し、各座標の**凍結されたbinary64端点から計算した**上下余裕を比較、大きい側へ25%、等しければ＋。理論上対称な幅でも端点の丸めにより実数値の余裕は微小に非対称になり、例えばAのindex 19は−側となる。これはclip/再抽選ではなく凍結入力そのもの。開始3点はphysical/role/SPD PASS。開始17点の(IL, max/sum violation dB)は A (0.83738714, 3.118678/12.238159)、B (0.85461508, 4.498316/29.773234)、C (0.85927835, 7.551644/48.264939)、いずれもstrict FAIL。

SLSQP/Hybrid共通 seed 1001、sum、max evaluations 20,000、350反復、各1-step、Hybrid再開0、検索70・選抜84・terminal476 samples。Planは [`slsqp.json`](slsqp.json)、[`hybrid.json`](hybrid.json)；各stage静的予約1,400,000、単一Job cap 1,400,812 samples。Plan SHAは `fca4239ea0a7f86da12d312b09994355d9d17d23f4724d555691ec60ad3f3b0f` / `2b04f8aaa657233f8d769b020b25ae83daa5fa86bda537e77b438cbaaea98b80`。選抜max 4 / top 1、terminal 2点の独立spot、checkpoint interval 100。preflightは予約計算であって実時間台帳ではない。HybridとSLSQPの目的式は異なるためobjective値を直接比較しない。

## Job観測（同じ17点格子）

以下のRF-bestはsearch上で選ばれたcheckpointを別途476 samplesで再評価。ΔILは現行基準17点との差。max/sumはmandatory violation dB、±0を合格と丸めない。時間はプロセス全体のwallでありforward専用計時ではない。

| box/solver | solver / exit | search forward (nfev,ncev,nit) | wall s / wall÷search forward s | RF-best strict | max / sum | IL / ΔIL dB | terminal strict, max/sum dB |
|---|---|---:|---:|---|---:|---:|---|
| A/SLSQP | converged / 0 | 196 (94,102,7) | 0.35 / 0.001786 | FAIL | 9.59e−13 / 9.59e−13 | 0.82784115 / 0 | FAIL, 9.59e−13 / 9.59e−13 |
| A/Hybrid | converged / 0 | 1,313 (1313,–,63) | 2.78 / 0.002117 | PASS | 0 / 0 | 0.82784115 / 0 | PASS, 0 / 0 |
| B/SLSQP | converged / 0 | 870 (424,446,21) | 2.46 / 0.002828 | FAIL | 0.01553055 / 0.01553055 | 0.82776943 / −0.00007171 | FAIL, 0.01553055 / 0.01553055 |
| B/Hybrid | 350反復未収束 / 4 | 13,360 (13360,–,350) | 11.88 / 0.000889 | PASS | 0 / 0 | 0.83739849 / +0.00955734 | FAIL, 0.01507097 / 0.01894314 |
| C/SLSQP | converged / 0 | 8,865 (4360,4505,145) | 8.64 / 0.000975 | FAIL | 0.01554458 / 0.01554458 | 0.82776657 / −0.00007457 | FAIL, 0.01554458 / 0.01554458 |
| C/Hybrid | converged / 0 | 17,290 (17290,–,314) | 14.99 / 0.000867 | PASS | 0 / 0 | 0.83602462 / +0.00818348 | FAIL, 0.00281121 / 0.00608500 |

terminalのILは順に0.82784115、0.82784115、0.82776943、0.82778063、0.82776657、0.82815321 dB。全terminalの指定2独立spotはPASS、全周波数MNAではない。各JobのCPU user+systemは順に1.97、2.54、2.22、10.99、7.89、13.77秒、max RSSは約108–110 MiB。A/SLSQPでは集計CPUがwallを超えたためCPU/wallを単一threadの整合したタイミングと見なさない。全wall合計41.10秒は起動等込みで環境依存。

厳密な「初回17点strict forward」は、全callbackを17点で検査していないので**unknown**。17点でPASSと再評価したRF-bestがcheckpointに記録されたforwardはA/Hybrid 1313、B/Hybrid 3361、C/Hybrid 4677（候補自体の評価はそれ以前の可能性）。70点でcheckpoint上に初めてstrictが見えたのはそれぞれ1115、3261、3641だが、17点の初回時刻や最初の到達forwardではない。各checkpointの保存回数・best完全vector・指標・SHAの系列、全Job input/result SHA、solver message、各terminal vectorは [`results.json`](results.json)。strict・物理適合が前提のΔIL≤+0.02参考目標は17点RF-bestの上記Hybrid 3件のみ該当し、密格子適合とは区別する。

## 限定追加検証と予算

17点strict候補をIL昇順、同値ならvector SHAで2件選択した結果、A/HybridのRF-best `02db9aaee47a18c9feec4cb4f8e5f43f84237c8c799d3e564eb04302594dffa0` とterminal `ffd93a82e577aad1c912b3a906556551b29a75f1ca5555803285013454e0b5ea`。両vectorは異なるが結果はほぼ同一で、**異なる独立seedの再現ではない**。両方1001点/区間 strict PASS、IL 0.8278411484628502、最小H2 30.000018886995342、H3 30.004999999938356 dB。各候補の84点独立MNA/受動性/電力収支PASS、最大比較誤差1.08e−12。B/C RF-bestの密格子は予算上の選抜対象外で未実施。

search callback合計 **41,894**、search **2,932,580 samples**。選抜・terminalを含む6 Job **2,936,108 samples**、基準と3開始点30,016（独立比較用のprimary 84含む）、6 RF-best再評価2,856、追加密格子2本＋その独立MNA比較用primary 84×2が56,224、primary requested/completed合計 **3,025,204 / 8,600,000**。独立MNAは別枠 **264 sample**（基準84、terminal 12、追加候補168）。異常STOP、外部強制停止、追加seed、resume、探索幅の事後調整なし。

## 第2段階への暫定提案・制限

次段階に向けた**未承認・未実行の案**：近傍保持とstrict checkpointの利用を前提にHybridを先に評価、各ランダム合法seedからC相当の局所幅（L/fixed C/IC-fixed ±10%、k ±0.02、Cv ±0.2 pFをhardと交差）を事前凍結し、1 seed当たり最大20,000 search forward・350反復・再開0を初期上限候補とする。C/Hybridは17,290 forward・14.99秒でsolver終了したが、Bは13,360 forward・350反復で未収束。20,000回は収束保証ではない。1 seedのwall予算目安は少なくとも **1分程度**を暫定計画値とし、起動/機械差・異常負荷で大きく変動し得るため時間で強制停止しない。ランダムseedでの到達率・局所boxの妥当性は未測定で、1件ずつの合法性/SPD、実際の費用・厳密17点評価、候補保存を別Issueで事前規定し、ownerの実施判断後にのみ開始する。今回の結果だけでランダム探索優位、予算十分、広域探索性能を断定できない。

`prepare.py`と`analyze.py`は今回の限定評価記録であり再実行は新たなRF samplesを消費する。実験rawは下記system tmpに残存し永続性はない。Gitに残すのは凍結入力、SHA、ベストvector、checkpoint系列、評価要約であり、全rawの永続再現性は保証しない。SRF、Q(f)、EM、物理結合、レイアウト、公差、実測、連続周波数、および大域最適性は未検証。ChatGPT独立レビュー待ち。

- `/tmp/issue433-A-slsqp-VeSI4end`, `/tmp/issue433-A-hybrid-eiK70sY4`
- `/tmp/issue433-B-slsqp-SwLXLelq`, `/tmp/issue433-B-hybrid-5PzsWpGE`
- `/tmp/issue433-C-slsqp-EykH3UuS`, `/tmp/issue433-C-hybrid-K4uiXLRY`

自己検証：main postmerge smoke PASS、元回路/部品/順序/Q照合 PASS、基準17点/密格子・84点独立検証、6 Job読戻しとcallback/sample再集計、`test_issue427_development_worker.py` 11件、`test_issue429_development_runner.py` 5件 PASS。これらは科学的認定ではない。

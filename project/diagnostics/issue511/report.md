# Issue #511 — TRF restartのftol paired開発比較

## 新5,000 forward比較：結果と判断材料

2026-11-24承認のRF-T010 **trial** 開発比較であり正式EXPではない。同一seed・同一初期25変数の4 arm、20 seed、各Search上限5,000 forward。選択は全局所runを通じたSearch目的最良vectorで行い、外部portのTerminal 476点で `J=max(signed margin)` を評価。小さいほどよい。

| arm | ftol | Terminal J 中央値 | 最良 / 最悪 | J≤0 | A比改善/悪化/同値 | A比ΔJ中央値 | Job wall中央値(s) | restart中央値 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| A | 1e-8 | 4.522170 | 0.293800 / 21.804255 | 0/20 | — | — | 31.153 | 5 |
| B | 1e-7 | 0.880034 | 0.264425 / 17.927016 | 0/20 | 14 / 4 / 2 | -3.442815 | 31.461 | 7 |
| C | 1e-6 | 0.675567 | 0.105919 / 11.867147 | 0/20 | 14 / 6 / 0 | -3.630267 | 31.147 | 11.5 |
| D | 1e-5 | 0.559049 | 0.322862 / 4.592820 | 0/20 | 15 / 5 / 0 | -3.686779 | 31.196 | 35.5 |

今回の20 seed・5,000 forwardという条件では、**Dを中央値・最悪値・A比改善数とwallを考えた暫定候補**とする。一方、最良単一解はCのseed 1016（J=0.105919）で、D対Cのpaired差中央値は -0.093966 dB、改善10・悪化10。B対Dも一方的ではない。いずれも0/20 finite-grid PASSであり、Dの普遍的優越性やRF適合を意味しない。計測時wallはほぼ同程度だが、同一wall時刻のTerminal Jの時系列は取得していないため、その優劣を厳密には立証できない。既定値変更、追加seedや正式EXPは行わない。

全80 JobはSearch 5,000 forwardで `evaluation_budget_exhausted` / `not_converged`、CLI exit 4は正常な未収束として区別。例外やscientific STOPなし。各armの局所run総数はA/B/C/D=131/176/267/730、restart総数111/156/247/710。局所終了のstatus 2（ftol）は107/149/247/710、status 3（xtol）は4/6/0/0、status 4（ftol+xtol）は0/1/0/0、status 0（評価上限）は各20。各局所runのstatus/message/optimality/nfev/njev・感度forward・wall/CPUは `summary.json`。Job全体CPUは未計測でありsolver CPU合計と混同しない。各armのworst pass IL中央値は3.765249/1.630034/1.425567/1.309049 dB、min H2/H3中央値は25.641575/29.548744/29.928805/29.897993 dB。Search最良目的中央値は122.265268/8.080964/3.195520/2.559530 dB²。

## 条件・監査・計算費用

- 計算HEAD `e16f9f9c25c81eb73e2eddd57e9cecd3fa9e1b43`、main基点 `22ddd2f7f90ce4e933f1d1c63bbed74baf997066`、source identity SHA `7f34898ac8bcfb64e87b7c8132fd6be1598f3883d915232616020a893799ab8f`、source dirty patch SHAは空patch `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`。RF-T010 trial effective SHA `d50e6c9fef3e41b8258c00cbd14436a3bcb1d84444d50cf4a445ccf5d288e417`、RF-T008 base `e682165c72d3a8b9f1384a2529f71bacfebfc9d17164d4af5af879e4a138b532`。definition canonical SHA `bc50042a1b0b1ebf19c0272fb2ee944b52cd76e14eb8d44673bfa57f6033c068`。bands SHA `1b1182e4c947059cb263c1af52ddf64236bd1fd9e83770cc844126576c7865fe`、input/output S2P SHAは `ad266111ba1dc2b92f235d39f4a647ff271050bc11941c217661dd299ee59945` / `b3cfc861bc0c8221f49328598c9d7d0766a6e94e42e990b6a50f6c90bf9a84da`。
- 4L2C、物理box全域、6設定・28独立UL/DL/H2/H3区間、source 50+j0Ω/load 60−j40Ω、固定S2P外部port cascade。1段Search 70点、Terminal 17点/区間＝476点。解析Jacobian、TRF `restart_sigma=0.1`、`x_scale=1.0`、SciPy既定 `xtol=gtol=1e-8`、`signed_margin_db` / sum、checkpoint 1000 Search forward、独立MNA spot `[0,111]`。初期vectorはseedごとにscrambled Sobolの1点で、20件全て#465の `new_initial_sha` と一致。各Plan・config/starts原byte SHA、全初期vector、全選択vector・SHA、bounds、Job別数値は `summary.json`、20×4のpaired J等は `paired.csv`。
- Run 1〜4のPlan canonical SHAは順に `69e61776b84563b38a89c36b73092a74ff7e251be5474d36a8c92b1a9a3e1026`、`4c8672b0699b3f5b1facadd9a85ed1b82cf72ef5e2f75447dc493dd73edcbdda`、`7ed0a8600be82297f00ab7c86e8e9c8dee7e2e177fb49c9f7d8e2930d5973dda`、`23fc98a744e4d6664e23612ad98d2bce778152eea21f8e37c3b16944f09fd905`。各Run Search 100,000、総RF 100,020、requested samples 7,009,520、MNA 40を予約・実消費し、解放0・不明0。合計Search **400,000**、総RF **400,080**、samples **28,038,080**、独立MNA **160**。旧100k中断の観測済400万と未知上限200万は下記に別記し、新比較の消費で上書きしない。
- 事前照合はRF forward 0。各Run後、20 JobのPlan・台帳・全receiptとcheckpoint原byte SHA・消費/解放・選択vector・科学条件を検査。さらに4 Runを全件再読込し、80 Jobの保存済summary/CSVと照合（RF forward 0）。全候補のcomponent box/SPD、外部受動性・電力保存はTerminal格子上、独立MNAは各2 spotで80/80記録PASS。最小L固有値は3.9184e-10 H。checkpointは計464件。科学audit PASSはRF閾値達成を意味しない。
- 同一ホスト・逐次、AMD Ryzen 7 PRO 4750G / WSL2、Python 3.12.15、NumPy 2.5.4、SciPy 1.18.1、BLAS/OMP/MKL各1 thread。CPU/BLAS構成・負荷・source・Plan/入力SHAはsummary。Runner `--timing-level timed` はJob wallに計測負荷を含み、plainとの差は未校正。Run wallは634.74/622.94/631.12/620.57秒、user CPUは510.33/501.90/510.75/501.62秒、system CPUは120.12/118.58/118.46/117.01秒。時間区間はinclusiveで合算分解しない。4 Run raw/receipt/checkpoints、凍結入力とtimingの一時原本は `/tmp/issue511-5k-1795529307/` に保持、system tmpであり耐再起動保存ではない。rawはGitに入れていない。
- 有限格子の評価であり、連続周波数・dense 1001点/区間、SRF、Q(f)、EM、公差、測定、物理実装可能性、大域最適は未保証。Hybrid #465は異なるHEAD・計算費用等の履歴値であり、同一wallの優劣を主張しない。

以下は旧100,000 forward比較の記録。2026-11-24承認の新5,000比較とは混同しない。

## 旧100,000 forward比較の中断記録

旧比較は未完了であり、以下の消費・証拠喪失は保持する。

**正式EXPではない。旧4 Run / 80 Jobの比較は未完了。** Windows更新後に環境が再起動し、Runnerのsystem tmp出力が消失した。再実行・救済retry・未完了Jobの再開はしていない。旧比較のRF品質の集計結果、最良ftolや完全vectorは復元できず、旧比較の `paired.csv` / `summary.json` は作成していない（現存する2ファイルは新5k比較のみ）。

## 実行状況と消費

以下は再起動前にPiのツール出力で確認した内容であり、元の台帳・raw・抽出JSONは現在存在しない。第三者による原byteの再照合はできない。

| Run | 対象 | 中断前の観測 | 消費（Runner実績として観測した値） |
|---|---|---|---|
| 1 | 1001〜1005、A→B→C→D | 20 Job completed、CLI exit 4、全Job `evaluation_budget_exhausted`。receipt/checkpoint・物理/SPD・外部受動性/電力保存・独立MNA spotの抽出監査PASS | Search 2,000,000、総RF 2,000,020 forward、RF samples 140,009,520、MNA 40、解放0 |
| 2 | 1006〜1010、B→C→D→A | 同上、20 Job completed、CLI exit 4、全Job `evaluation_budget_exhausted`、抽出監査PASS | Search 2,000,000、総RF 2,000,020 forward、RF samples 140,009,520、MNA 40、解放0 |
| 3 | 1011〜1015、C→D→A→B | CLIを開始後、ツール呼出しが `No result provided` で中断。終了、完了Job数、科学監査および実消費は**不明** | 0〜予約上限 Search 2,000,000、総RF 2,000,020、RF samples 140,009,520、MNA 40。**未消費とはみなさない** |
| 4 | 1016〜1020、D→A→B→C | 当セッションでは開始操作なし | 0 |

確実に観測した Run 1+2 合計は Search **4,000,000**、総RF **4,000,040**、RF requested samples **280,019,040**、独立MNA **80**。Run 3の未知消費を足した比較全体は、それぞれ最大 Search 6,000,000、総RF 6,000,060、samples 420,028,560、MNA 120。Run 4は未実行。Run 3が中断前にどこまで実行されたか、計算の成否や実消費を推測しない。

Run 1の `/usr/bin/time` は elapsed 10,780.34秒、user 8,763.60秒、system 1,990.79秒を観測。Run 2の正確なRun全体時間・両RunのJob別wallおよび局所solver CPUは保存出力喪失により再確認できない。Job全体CPUはもともと未計測。有限格子PASS数、J、選択vector・SHA、個別停止詳細なども失われ、4 armのpaired品質や効率の比較はできない。終了code 4は数値未収束とRF適合を区別するもので、科学的適合を意味しない。

## 原本・監査・中断

- 元出力は `/tmp/issue511-execution-fixed-1795453585/`。再起動後にディレクトリ自体が存在しないことを確認。Run 1/2の `audit-*.json`、Plan、run台帳、入力、result、receipt、checkpoint、timing、host環境・実行ログは同一tmp配下にあったため、現在は再監査できない。旧preflight tmpも存在しない。意図的な削除ではない。Run 3の `run.json` / failure状態も確認不能で、復旧を主張しない。
- Run 1/2は消失**前**に `analyze.py` で20 Job分のPlan、台帳、全receipt/checkpoint原byte SHA、box/SPD、Terminal 476点の受動性・電力保存、独立MNA `[0,111]` 等を照合し、ツール出力で各PASSと予算値を観測した。これは現在の証拠に基づく独立再監査PASSではない。
- 起動時のHEAD `e57a64e80a81d86787db89ae0954a038fe8ff895`、main基点 `22ddd2f7f90ce4e933f1d1c63bbed74baf997066`。Run 1/2 source identity SHAは両方 `2b3b1f07c02ebe1705d62f96654c5f67dc934de8ef48f7ca8fbce8d3f178d874` と観測。実行は単一ホストで逐次、OPENBLAS/OMP/MKL各1 thread、既存CLI `develop` / `--timing-level timed`。計測オーバーヘッドは未校正。ホスト・負荷等の詳細原記録は消失。
- 最初のRun 1起動は、準備スクリプトが出力したJSONの `1e-08` をCLIのYAMLローダーが文字列として解釈し、`ftol must be None or finite and positive` でPlan作成前にexit 2。Job・RF消費は0。YAML出力とCLIと同じローダーによる事前照合を追加し、**Job実行前の入力不備**を修正した後、別のfresh tmpでRun 1を開始した。初回tmpも再起動で消失。

## RF forward 0 の事前準備

RF-T010 trial effective SHA `d50e6c9fef3e41b8258c00cbd14436a3bcb1d84444d50cf4a445ccf5d288e417`、物理base RF-T008 `e682165c72d3a8b9f1384a2529f71bacfebfc9d17164d4af5af879e4a138b532`。25変数Sobol初期点20件のSHAを `issue465/paired.csv` と照合し一致。4 Planについて全物理bounds、6設定28区間、Search 70 / Terminal 476点、S2P原byte、MNA spot、3費目予約、seed→arm順を確認。Plan canonical SHA（Run 1〜4順）は以下。

1. `78a1fafb12cbcf79d7892d699703254876910901f643dd18b106bfd4f55faa57`
2. `3b86e689ea4efba2870f0848f1be1f2a4f1a071d298b71b867fe81d947ccde01`
3. `32328472cfa28977c4052c8dffd04af98de66bf2d413b18b48261def37c9ee5b`
4. `a49df24ef8be3c5a2489a204654b45ef14d462fbbb1de536adb6dfac920b88be`

`prepare.py` はRF評価を行わず入力とPlanをfresh system tmpに生成する。再起動後に再生成・照合を実施し、20件の初期SHA・上記4 Plan SHAの一致を確認した。新規の入力確認用tmpは `/tmp/issue511-handoff-preflight-1795528122/` に残しており、以前のRun原本ではない。当時の `analyze.py` は完了Runの抽出監査用であり、旧100k比較の80 Job集計は完成していない。Run 1/2の原本が失われている以上、再生成のみで当時の計時や実行証拠を再現したとは扱えない。

## レビューに基づく判断と今後の判断事項

先行PRで `solver_failure` の後にRunnerが継続することをブロッカーとした判断は過剰だった。PR #512独立レビューに従い、有限・整合した負statusは数値未収束として記録し、実際のRF/数値例外や科学監査異常はSTOPする。既存test 14件PASS、合成statusの決定的2 Jobテストは比較とは別にSearch 2 / Terminal 2 forward、MNA 4を使用。

旧100kの救済retry/resume/再計算は行わない。ユーザーは別の新比較として5,000 forward/Jobを承認し、保存方針は変更しないと指定した。新比較の結果は本PRで別途記録し、旧比較の消費や証拠喪失をゼロに戻さない。

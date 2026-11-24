# Issue #511 — 実行途中で中断、証拠喪失（未完了）

**正式EXPではない。4 Run / 80 Jobの比較は未完了。現状マージ不可。** Windows更新後に環境が再起動し、Runnerのsystem tmp出力が消失した。再実行・救済retry・未完了Jobの再開はしていない。RF品質の集計結果、最良ftolや完全vectorは復元できず、`paired.csv` / `summary.json` は作成していない。

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

`prepare.py` はRF評価を行わず入力とPlanをfresh system tmpに生成する。再起動後に再生成・照合を実施し、20件の初期SHA・上記4 Plan SHAの一致を確認した。新規の入力確認用tmpは `/tmp/issue511-handoff-preflight-1795528122/` に残しており、以前のRun原本ではない。`analyze.py` は完了Runの抽出監査用であり、今回の80 Job集計を完成させるスクリプトではない。Run 1/2の原本が失われている以上、再生成のみで当時の計時や実行証拠を再現したとは扱えない。

## レビューに基づく判断と今後の判断事項

先行PRで `solver_failure` の後にRunnerが継続することをブロッカーとした判断は過剰だった。PR #512独立レビューに従い、有限・整合した負statusは数値未収束として記録し、実際のRF/数値例外や科学監査異常はSTOPする。既存test 14件PASS、合成statusの決定的2 Jobテストは比較とは別にSearch 2 / Terminal 2 forward、MNA 4を使用。

Issueの原本に指定された「再試行しない」と比較予算を尊重し、Run 3の未知消費やRun 1/2証拠喪失を無視した再実行は行わない。**必要な次の判断は、証拠を復旧できるかの確認と、復旧不能なら比較の再設計・予算・証拠の耐再起動保存についてのユーザー／研究PMの指示**。本PRは途中記録であり、統計・科学的結論・DoD達成を主張しない。

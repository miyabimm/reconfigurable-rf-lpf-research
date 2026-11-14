# Issue #413 — 枝スタンプ前計算＋3縮約方式の開発診断

## 結論／採否

**A six-matmulを独立レビューへの第一候補とする。本番採用はまだ行わない。**
B direct-matmulも同程度の改善候補だが、A/B間の速度順位は認定しない。
C six-einsum-no-optも固定RF forwardは改善したが上位2案より中央値が約1ms遅く、Solver比較へは進めなかった。
`src/`、RF入力・モデル／指標の意味、Solver、保存契約に変更なし。正式EXP・本番探索・Phase移行ではない。

数学的な固定／可変分離より、**枝Qとincidence外積の前計算＋小行列縮約の処理負荷削減**が有効だった。
#410のsix（毎回Q/incidenceを構築しoptimize=True）と異なる。#410旧six/splitの新HEADでの速度再測定はしない。
今回の旧新plainでは固定100 vector forwardとSolverの両方で改善方向が2batch継続した。
ただし共有hostの長い外れ値があり、全runで速い／一般的な改善率／Aが唯一最速とは主張しない。

## 測定rawの現役tree整理（PR #414）

固定forward初回・再測定、Solver初回・再測定、計測内訳の**5件の大容量raw JSON**は、内容・SHA256を変更せず[測定原本を含む固定commit](https://github.com/miyabimm/reconfigurable-rf-lpf-research/blob/19a86a30ac15b1de1255af8e67a89ed85d652448/project/diagnostics/issue413_forward.json)（`19a86a30ac15b1de1255af8e67a89ed85d652448`）に残し、現役treeからは除外する。本PRは**通常のmerge commit方式でマージしてこの原本commitをmainの履歴に残す**。以下の各rawリンクは削除前の固定commitを直接参照する。

現役treeには本レポート（条件・代表値・分布・全消費・再現コマンド・原raw SHA256）、現役KBへの要約、比較driver・試作・回帰テスト、比較的小さい`issue413_equivalence.json`（数値同値性・独立検証結果）を保持する。削除は現役参照のみであり、原記録の破棄・測定の再実行・科学的数値の変更ではない。詳細な全run値と外れ値を再集計するときは固定commitのrawを使用する。

## 基準・科学入力・再現性

- main `b97f0fa2`（#412マージ済み）から分岐。最新instructions、registry active、bands、#401/#410/#413、#412報告、roadmap/KBを確認。
- **全記録の計測HEAD `fd0f420c7c0323f3745f1411bd59399b202f7386`**。試作・計測器・共通テストの初回実装をcommitしてから計測。RF/source tracked差分なし。後の変更は追加STOPテストと本報告／KB／測定記録のみ。
- source identity SHA（全計測共通）`c9ed984add03182768099fad69609e739154558fcd8366b460ff5b9ab6730e41`。各記録にsource全ファイルSHA・dirty patch・スクリプトSHA・HEAD・status・環境・実引数を保持。未追跡 `.issue361-definition.json` は既存のまま、不使用・未変更。生成中の診断JSONはstatusに現れるがRF入力ではない。
- **RF-T008 rev3 trial opt-in** / full_lpf、effective SHA `e682165c72d3a8b9f1384a2529f71bacfebfc9d17164d4af5af879e4a138b532`。active formal RF-F003へ速度結果を一般化しない。
- #410と同じ25変数／4L／9 C枝／5ノード、seed1002、6設定・28不連続区間、70 samples/forward、mandatory_g全42点。
- Plan `8ac7bab9567918ae5c656fd449807ad2c38c1e1cad9e39c8ed217b95a569043e`、grid `6805740a36f6100d7dec3e7308924242e909255f1ea2d287b7c734c400f98f26`。
- start vector `6203467121a4e37baaa51c471aaecb3174f3374f9ab955d6fbf101f7b5ce935f`、starts bytes `63b671ea269656843df118230b7d920e91515188235809b6dd0efd667ac997ab`。
- 固定候補列は[issue410_equivalence.json](issue410_equivalence.json)の100 vectorを順序固定・全vector SHA再照合して使用（新しいSolver軌道のcaptureではない）。原本SHA `e87355eb364073a5743062e8e4ee7c90c3012cbfb5e38bef6283860381736ba0`。
- bands SHA `1b1182e4c947059cb263c1af52ddf64236bd1fd9e83770cc844126576c7865fe`、input S2P `ad266111ba1dc2b92f235d39f4a647ff271050bc11941c217661dd299ee59945`、output S2P `b3cfc861bc0c8221f49328598c9d7d0766a6e94e42e990b6a50f6c90bf9a84da`。logical dataパスをloaderが同一byteのrf実体へ解決。
- Python 3.12.15 / NumPy 2.5.4 / SciPy 1.18.1 / OpenBLAS 0.3.34.106.0 ILP64。WSL2共有host、AMD Ryzen 7 PRO 4750G、各子process affinity `[2]`、OPENBLAS/OMP/MKL各1 thread。物理core専有、温度・電源・他負荷制御なし。

## 実装と計測前の処理内訳

[issue413_probe.py](issue413_probe.py)のみで明示opt-in。
初期化時に `T[b,i,j] = 1e-12/(1/Q[b]-j) * B[i,b]*B[j,b]` とその `[B,N²]` viewを作る。
トポロジー／Qだけをcacheし、C/L/kは各候補で再計算。枝順 `[fixed,variable,IC_fixed,constant]`、ground、同一端子のQ35/Q60並列枝を維持する。stamp配列はbytes backingで不変。

- **A six-matmul**: `C[6,B] @ T_flat` → `[6,N,N]` → `D[setting]`。
- **B direct-matmul**: `C[setting,B] @ T_flat` → `[70,N,N]`（D gatherなし）。
- **C six-einsum-no-opt**: `einsum('sb,bij->sij', C, T, optimize=False)` → `D[setting]`。
- 全案で `Y=K/(ω 1e-9)+ωD`。完全L行列SPD・Q、Schur、Y→S、固定S2P cascade、power_response、全S／IL/APL／両RL、不変公開配列はそのまま。

[detail原記録](https://github.com/miyabimm/reconfigurable-rf-lpf-research/blob/19a86a30ac15b1de1255af8e67a89ed85d652448/project/diagnostics/issue413_detail.json)：各方式別processで3回、各100 vector。以下は区間合計の中央値ms/100 vector（setupはµs）。**計器付きの算術内訳でありplain RF速度ではない**。baselineも70点を一括einsumで処理し、70回のPythonループではない。

| 方式 | C変換 | C gather | branch Q＋incidence | 縮約 | D gather | Y合成 | probe setup µs |
|---|---:|---:|---:|---:|---:|---:|---:|
| baseline | 0.413 | 0.529 | 2.009 | 7.057 | — | 0.486 | 2.0（no-op） |
| A | 0.378 | — | setupへ | 0.483 | 0.496 | 0.621 | 151.4 |
| B | 0.375 | 0.451 | setupへ | 0.900 | — | 0.661 | 167.1 |
| C | 0.376 | — | setupへ | 1.037 | 0.464 | 0.645 | 144.6 |

setupは追加トポロジー構築／検査も含む。固定S2P・evaluator等の全setupは別途rawに記録。
新案のY合成は周波数乗算込み、baselineはbranch段階で乗算済みのため、Y合成だけを同じ演算量として比較しない。
100,000 noop領域の合成校正：空ループ2,197,307ns、measure付き124,335,127ns、追加約1,221ns/領域（記録された領域内平均155ns）。単回・affinity未固定の校正で、内訳から一律に差し引かない。
初回の校正コマンドはPYTHONPATH不足でimport失敗し、`PYTHONPATH=src`を付けて再実行した。RF run失敗ではない。

## 固定100 vectorの実RF forward plain

[初回raw](https://github.com/miyabimm/reconfigurable-rf-lpf-research/blob/19a86a30ac15b1de1255af8e67a89ed85d652448/project/diagnostics/issue413_forward.json)／[再測定raw](https://github.com/miyabimm/reconfigurable-rf-lpf-research/blob/19a86a30ac15b1de1255af8e67a89ed85d652448/project/diagnostics/issue413_forward_repeat.json)。各候補につき旧新各warmup1子process後、旧新新旧の釣り合った順序で各10子process。各子processでも同じ100 vectorをwarmup評価後に100 vectorを固定順で再評価。
タイミング区間は完全`evaluator.evaluate`ループのみ。requirements、同値性比較、digest、タイマーwrapperは含まない。CPU・wallを区間全体で測り、全sample・全公開指標を生成する。
外れ値除外なし。表はms/100 forward、CPU欄は旧→新の中央値（CPUの範囲・全個別値もrawに保持）。

| batch | 案 | 旧wall 中央値[min,max] | 新wall 中央値[min,max] | pair新−旧 中央値[min,max] | 新が速いpair | CPU旧→新 |
|---|---|---|---|---|---:|---|
| 初回 | A | 57.999 [57.240,62.835] | 51.072 [50.147,57.137] | −6.910 [−11.767,−0.771] | 10/10 | 57.991→51.071 |
| 初回 | B | 60.602 [58.774,71.715] | 51.069 [49.509,104.925] | −9.347 [−20.605,+44.464] | 9/10 | 60.321→50.981 |
| 初回 | C | 60.346 [58.128,69.929] | 52.167 [50.457,55.940] | −7.451 [−17.787,−5.805] | 10/10 | 60.062→51.985 |
| 再測定 | A | 60.460 [58.827,164.020] | 51.352 [49.762,103.397] | −8.547 [−112.989,+43.746] | 9/10 | 60.308→51.347 |
| 再測定 | B | 59.488 [57.137,62.351] | 51.366 [50.145,105.765] | −7.868 [−11.842,+43.902] | 8/10 | 59.503→51.108 |
| 再測定 | C | 60.090 [59.229,105.115] | 52.291 [50.459,64.761] | −8.078 [−53.525,+5.532] | 9/10 | 59.946→52.292 |

初回の上位A/BをSolverへ進めた。A/Bの固定forward中央値はほぼ同値で、縮約単独のA優位をRF全体の順位とはしない。
再測定でも改善方向は維持したが、共有hostの外れ値の原因を温度／他負荷等へ特定はできない。外れ値ではCPUも増えるためwall−CPUだけで完全説明できない。

## Solver plain（同じ軌道ではない）

[初回raw](https://github.com/miyabimm/reconfigurable-rf-lpf-research/blob/19a86a30ac15b1de1255af8e67a89ed85d652448/project/diagnostics/issue413_solver.json)／[再測定raw](https://github.com/miyabimm/reconfigurable-rf-lpf-research/blob/19a86a30ac15b1de1255af8e67a89ed85d652448/project/diagnostics/issue413_solver_repeat.json)。上位A/Bのみ、各batch旧新warmup各1＋各10run、新process・交互順。`benchmark_minimal_worker.py`の無計器`worker.solve()`をそのまま使用。
単位ms/100 nfev。後段観察（best_xの追加1 forward）は時間・消費とも別。setupをsolveへ混ぜない。

| batch | 案 | 旧solve 中央値[min,max] | 新solve 中央値[min,max] | pair新−旧 中央値[min,max] | 新が速いpair | CPU旧→新 | setup旧→新 |
|---|---|---|---|---|---:|---|---|
| 初回 | A | 73.931 [71.390,78.812] | 66.354 [63.401,184.813] | −8.605 [−12.117,+112.554] | 8/10 | 73.931→66.333 | 248.164→251.572 |
| 初回 | B | 73.772 [71.446,149.560] | 65.514 [63.869,124.131] | −9.014 [−28.280,−3.867] | 10/10 | 73.615→65.515 | 261.784→244.971 |
| 再測定 | A | 73.600 [69.927,80.531] | 65.014 [62.732,119.080] | −8.899 [−14.986,+46.536] | 8/10 | 73.586→64.778 | 244.973→243.674 |
| 再測定 | B | 74.006 [71.332,155.829] | 63.997 [62.424,67.420] | −10.719 [−92.800,−4.122] | 10/10 | 73.961→63.998 | 245.578→244.845 |

全88runはnfev100/restarts0、evaluation_budget_exhausted、**未収束**。RF異常終了なし。
全runでvariant内のsolver出力は完全一致、AとBのsolver出力も一致。
ただしbaselineとのbest_x最大差約8.254e−4、best_fun差−0.004521675。
丸め差が有限差分経路へ伝播するため、Solver A/Bを固定100 vector比較とは呼ばない。旧新の評価候補列全体の一致や全軌道captureも主張しない。

固定forwardに同じ方向の改善があるので、Solverの時間差を軌道変化だけで説明しない。
一方、今回の実測のみでSolver加速分をすべてC縮約へ定量帰属しない。
**Aを第一候補とする理由は、Bと同程度のend-to-end観測で積和量が少なく、実装も小さいこと**。
Bのsolve中央値は低いが、別batch・共有負荷・約1ms差であり直接A対Bの優位認定には不足する。
本番への小さな採用差分は独立レビュー後の別判断とし、診断試作を恒久fast-pathへ自動昇格しない。

## 科学同値性・STOP・検証深度

[数値同値性raw](issue413_equivalence.json)。固定100 vector×70点×3案で全複素S・IL/APL/両RL・worstIL・mandatory_g全42要素の順序を同じprepared requirementsで比較。
全案で**ビット非一致**、atol1e−9 / rtol1e−11内。

| 最大絶対差 | A | B | C |
|---|---:|---:|---:|
| 複素S全4要素 | 1.951e−14 | 1.951e−14 | 1.975e−14 |
| IL dB | 9.326e−14 | 9.326e−14 | 9.326e−14 |
| APL dB | 3.642e−14 | 3.642e−14 | 3.997e−14 |
| 入力RL dB | 7.674e−13 | 7.674e−13 | 7.887e−13 |
| 出力RL dB | 3.020e−13 | 3.020e−13 | 3.126e−13 |
| mandatory_g | 9.237e−14 | 9.237e−14 | 9.237e−14 |
| worstIL dB | 1.688e−14 | 1.688e−14 | 1.688e−14 |

代表vector index 0/49/99を全案で**全70点**独立branch-current MNA／外部S2Pを含む受動性・枝損失非負・電力残差検証。9応答630点、独立応答との差の最大2.214e−12（atol1e−9）。
unit testではstartとL/固定C/IC固定C＋全6可変C行を変えたvector、0可変枝でも独立MNAを実施し、独立検証時に試作forwardが呼ばれたら失敗させる。

回帰：RF-F003/T005/T006/T007/T008（T006追加区間含む）、0可変枝、ground、異Q並列、固定C設定差の拒否、サンプル形状／NaN／非整数、非SPD／悪条件閾値、node非有限コードとsample index、zero-transmissionのIL/APL +Inf、不変応答。
追加テストで全案のSchur特異／非有限、Y→S特異、実power_responseのavailable_gain_undefined／wave_singular／wave_nonfiniteがplain Solverから伝播しSTOPすることを確認。既存複素負荷・subnormal／ゼロ電力・S2P SHA／範囲・独立MNA・MinimalWorker保存経路との同等性も回帰。

**未検証／限界：** 100 vectorすべての独立MNA、あらゆるoverflowでの旧新STOP発生位置の一致、全トポロジー／別BLAS・CPUでの速度、正式RF-F003の速度、連続周波数保証、EM/SRF/Q(f)/公差/実測。浮動小数の再結合は極端値のoverflow順序を変え得る。代表境界回帰を任意入力の契約同一性証明としない。

## 実行済みチェック・消費・workspace

- `uv sync --frozen` PASS。
- `test_issue413_c_stamps.py` **7件**、`test_issue410_c_assembly.py` **5件**、`test_issue309_rf_core.py` **7件**、`test_issue389_minimal_worker.py` **4件**、`test_phase2_branch_mna.py` **6件**、`test_phase2_numeric_diagnostics.py` **3件**：計32件PASS（初期6件実行後、STOP追加版7件を再実行）。CI／独立レビューは別判定。
- storage audit正常終了。既存EXP-058 running、EXP-116/117 preservation_incomplete等を保持。全EXP完全性PASSとは呼ばない。新規EXPなし。
- fixed-forward 132子process×(warmup100＋measured100)＝26,400 RF forward。
- Solver 88run×(solve100＋observation1)＝8,888 RF forward。
- 数値同値性600 RF forward。上記合計 **35,888 forward／2,512,160 requested samples**。独立MNAは別途630 sample検証。unit/regressionの呼出数はこのベンチ集計の外。
- detail 12子process×100 vector×(内訳組立て＋一致assert用組立て)＝2,400 node組立て／168,000 sample、RF forwardではない。commit前のdetail smokeはさらに200 node組立て／14,000 sample。単一node microのみの採否ではない。
- 追加checkout/worktree／永続project directoryなし。通常checkoutを使用。参照取得用`/tmp/issue413-401.json`・`/tmp/issue413-410.json`と、commit前smoke `/tmp/issue413-detail-smoke.json` は残存（正式EXP／checkpointではない）。測定rawは本ディレクトリに保持し、過去#410記録は変更しない。

## 再現コマンド／原記録

```bash
uv sync --frozen
# --outputは毎回未存在のパス。全子processをaffinity2 / BLAS各1threadで実行する。
uv run --frozen python project/diagnostics/issue413_benchmark.py --suite detail --output <new-detail.json>
uv run --frozen python project/diagnostics/issue413_benchmark.py --suite forward --output <new-forward.json>
uv run --frozen python project/diagnostics/issue413_benchmark.py --suite equivalence --output <new-equivalence.json>
uv run --frozen python project/diagnostics/issue413_benchmark.py --suite solver \
  --candidates six-matmul direct-matmul --output <new-solver.json>
# forwardとsolverをもう1batch、別outputで反復。--pairs default10。
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  uv run --frozen python -m unittest discover -s tests -p 'test_issue413_c_stamps.py' -v
```

生記録は全run（warmup・外れ値含む）、CPU/wall、setup、終了状態、Solver全出力を保持。driverは失敗時もstderr/returncodeを書いて停止する。今回の正式計測子process失敗は0。
原記録SHA256：

| ファイル | SHA256 |
|---|---|
| issue413_detail.json | ad664db32aa355b690b38e25158f05b9a5158570954c84524fc5af806c95f451 |
| issue413_forward.json | c0649335eec5136b8edb674787443f472bd9e9937fcec05efa12042fd84f63a9 |
| issue413_forward_repeat.json | 73f7c57a95fc4a7858f6d98154f1408b9a29fb3e9f285dd1f276f07fd39cb17c |
| issue413_equivalence.json | 9038e0b825f24ebe09a36e958742506914240f43b0be3c9cad4425ebd550b6ff |
| issue413_solver.json | cfebe3c1824fe9001508752fcf53fc414072bdf11f4356e692f67a71a9ce32b1 |
| issue413_solver_repeat.json | 4f71301666d68aa232a5203f3c1f2666d78508132a9518c5743651927704fb3f |

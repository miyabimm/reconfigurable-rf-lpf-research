# Issue #417 — six-matmul採用後mainのRF forward関数別時間

## 結論と範囲

- PR #416反映後のmain HEAD **`523f3ab8d0d89323fd521c9b6738728f8babc54b`** で、固定100vectorの実RF forwardだけをfresh processで測定した。無計器plain 12run、deep 12run（隣接12組、順序を交互）を完了。**solver性能・旧実装との新しいA/B・RF改善の主張ではない。**
- plain 100 forwardのwall中央値は **49.140 ms**（48.167–51.819）、CPU中央値 **49.145 ms**（48.170–51.761）。約0.491 ms/forward。warmup・外れ値を除外していない。
- deepでは`power_response`、portのうちSchur側、`decode`が測定上の有力な次候補。**首位はpower_response、Schurとdecodeの2/3位差は不確か**。matrices/node残余も近い候補。今回のIssueでは高速化実装をしていない。
- inclusive timer付きdeepはwall中央値55.020 ms/100（53.294–71.004）で、plainとの対応差中央値 **+5.955 ms**（+1.474～+20.298）。計器負荷が大きくrun間で変動するため、deepの全体時間をplain性能や速度比に使わない。関数別値は詳細化のためのinclusive観測に限る。
- RF/TOP/S2P・Solver・モデルには変更なし。正式EXP・本番Campaign・RF-F003測定ではない。全100候補の独立MNA、連続周波数、EM/SRF/Q(f)/公差/実測は実施していない。

## 固定条件と識別子

- 計測HEAD：`523f3ab8d0d89323fd521c9b6738728f8babc54b`（#416 merge）。source identity SHA **`b701aee50fa2a506eaef942109fb93a96fe8405e7c0b1e7715b539f6293e467e`**、計測driver SHA **`bb861deeeea169cdd8f5dc0a3409725adf3c6652bf1d1cea4a21ab16c57ee3cc`**。RF実装のtracked差分なし。1回目は未追跡driverのみ、再測定ではdriverと最初のraw記録がworking treeに見えていた。source identityは全24測定で一致。
- 固定入力：`project/diagnostics/issue410_equivalence.json` SHA `e87355eb364073a5743062e8e4ee7c90c3012cbfb5e38bef6283860381736ba0`。既存`vector_sha256`列と100 vectorすべてを再計算照合（vector列fingerprint `3e3adfc5c2b3f0c18c04cffd447fa64734dca7154a325c31261b6968a9fac693`）。vector順序固定。初期設定はseed1002、`issue401_starts_1002.json` SHA `63b671ea269656843df118230b7d920e91515188235809b6dd0efd667ac997ab`。
- RF-T008 rev3 **trial opt-in**、`full_lpf`、effective SHA `e682165c72d3a8b9f1384a2529f71bacfebfc9d17164d4af5af879e4a138b532`。RF-F003はregistry active formalだが今回の計測条件ではない（formal effective SHA `e12c42b11d12db7f20983c48cfa441ea96e362e533450d5862aa8a271c82af86`）。trial結果をformal性能へ一般化しない。
- Plan `8ac7bab9567918ae5c656fd449807ad2c38c1e1cad9e39c8ed217b95a569043e`、grid `6805740a36f6100d7dec3e7308924242e909255f1ea2d287b7c734c400f98f26`。全6設定、28別interval、70 samples/forward、mandatory g 42値/候補。固定S2Pを含む通常`RFEvaluator.evaluate()`本番経路。
- bands SHA `1b1182e4c947059cb263c1af52ddf64236bd1fd9e83770cc844126576c7865fe`、input S2P `ad266111ba1dc2b92f235d39f4a647ff271050bc11941c217661dd299ee59945`、output S2P `b3cfc861bc0c8221f49328598c9d7d0766a6e94e42e990b6a50f6c90bf9a84da`。
- Python 3.12.15／NumPy 2.5.4／SciPy 1.18.1、WSL2共有host AMD Ryzen 7 PRO 4750G、子process affinity `[2]`、OPENBLAS/OMP/MKL各1 thread。CPU affinityは物理core専有ではなく、温度・電源・他負荷は制御していない。

## plain測定とdeep計器負荷

各runは別process。各processで同じ100 vector順序の100-forward warmupを1回実施し、測定はその後の`RFEvaluator.evaluate()` 100回だけ。S全4要素・IL/APL/両RLの完全応答を作る。grid/固定S2P準備・warmup・digest・要求計算は測定外。deepでは既存`instrument(..., deep=True)`と`TimerCollector`だけを使用し、solverは呼ばない。plain/deep順序は6組ずつ`plain→deep`／`deep→plain`を交互にした2スイート。

下表は各runの **wall/CPU ms/100 forward**。省略・外れ値除外なし。

| suite | pair | 順序 | plain wall/CPU | deep wall/CPU | deep−plain wall |
|---:|---:|---|---:|---:|---:|
| 1 | 0 | plain→deep | 51.244 / 51.248 | 53.960 / 53.966 | +2.716 |
| 1 | 1 | deep→plain | 50.849 / 50.853 | 55.378 / 55.384 | +4.529 |
| 1 | 2 | plain→deep | 48.756 / 48.735 | 54.662 / 54.668 | +5.906 |
| 1 | 3 | deep→plain | 49.202 / 49.207 | 59.762 / 59.727 | +10.561 |
| 1 | 4 | plain→deep | 51.161 / 51.170 | 54.593 / 54.599 | +3.432 |
| 1 | 5 | deep→plain | 48.447 / 48.454 | 60.030 / 60.035 | +11.583 |
| 2 | 0 | plain→deep | 48.584 / 48.587 | 55.718 / 55.723 | +7.134 |
| 2 | 1 | deep→plain | 50.707 / 50.710 | 71.004 / 71.007 | +20.298 |
| 2 | 2 | plain→deep | 49.001 / 49.006 | 53.865 / 53.868 | +4.864 |
| 2 | 3 | deep→plain | 48.167 / 48.170 | 54.170 / 54.203 | +6.003 |
| 2 | 4 | plain→deep | 51.819 / 51.761 | 53.294 / 53.297 | +1.474 |
| 2 | 5 | deep→plain | 49.079 / 49.083 | 58.337 / 58.344 | +9.259 |

plain/deepのpaired差は12/12でdeep側が長いが、その差は大きく変動。deep wrapperは100 forwardあたりおよそ1,000 region計時を追加する。差中央値5.955msを純粋なTimerCollector校正値とはみなさない。特に71.004msのdeep runも保持し、測定負荷／共有CPUの揺れの原因は特定できていない。Timer付き値を実RF plain時間として報告しない。

## deep関数別inclusive時間

TimerCollectorの1run集計から、ms/100 forwardの中央値と全12runの[最小,最大]を表示。ここでいう`inclusive`領域は包含関係があり、**合算不可**。

| 関数 | 呼出回数/100 forward | inclusive ms/100 [min,max] |
|---|---:|---:|
| `rf_forward` (`RFEvaluator.evaluate`) | 100 | 54.392 [52.716, 70.213] |
| `l3_port_admittance` | 100 | 21.084 [20.417, 26.938] |
| `l3_node_admittance` | 100 | 12.566 [12.103, 16.735] |
| `l3_matrices` | 100 | 6.338 [6.001, 8.748] |
| `l3_power_response` | 100 | 12.705 [12.376, 18.100] |
| `l3_decode` | 100 | 7.186 [6.794, 8.454] |
| `l3_encode` | 100 | 0.799 [0.725, 1.487] |
| `l3_cascade`（2回/forwardの合計） | 200 | 5.130 [4.910, 5.964] |
| `l3_y_to_s_solve`（port/power内solveは除外） | 100 | 2.523 [2.399, 2.853] |

同一run内の差を計算してから得た残差の中央値と[最小,最大]：

| run内差 | median [min,max] ms/100 | 解釈／境界 |
|---|---:|---|
| `node_admittance − matrices` | 6.228 [6.102, 7.987] | nodeのC stamping、broadcast/add等と内側timer境界の残り。`matrices`単独やC縮約単独ではない |
| `port_admittance − node_admittance` | 8.590 [8.153, 10.203] | Schur側のindex抽出・配列copy・solve・検査等を含む。Schur solveだけの計時ではない |
| `rf_forward − (decode + encode + port + power + cascade×2 + Y→S solve)` | 5.121 [4.764, 6.417] | RFResponse配列freeze/copy・応答生成・未計時処理と**timer/wrapper負荷**の残り。純粋なRFResponse構築時間ではない |

各差の分布から先にrun単位で減算しており、中央値同士の引き算ではない。`port`は`node`を包含し、`node`は`matrices`を包含する。`rf_forward`はport、power、cascade等を包含する。全inclusive値を足し合わせない。

## 次の候補（このIssueでは未実装）

1. **`power_response`** — inclusive中央値12.705ms/100で、独立に計時した関数群の中で最大。source/load power-wave renormalization、batched solve、dB応答生成を保持したまま、どの内処理が支配的かを小さく分ける候補。今回の12runでも他と差が見えるため第一候補。ただしdeep計器下の値。
2. **Schur/port側** — `port−node`中央値8.590ms/100。固定トポロジーでもSchur用indexing/copy/solve等のどこが支配するかを局所診断する候補。source/load順序、middle nodes、接続・特異STOPを保つ必要がある。
3. **`decode`** — inclusive中央値7.186ms/100。設定6行の構築とPython値検査が含まれる。入力有限性、型・schema、固定C/可変Cの不変条件を落とさずに短縮できるかを調べる候補。

**2位Schurと3位decodeは区間が重なり、決定的な相対順位ではない**。`matrices`6.338msと`node−matrices`6.228msも近い測定対象である。次回はまず1位の内訳を絞り、Schur/decode/matrices/nodeの順位は局所計測のtimer overheadを再確認してから決める。高速化コードの変更、RF意味の緩和、正式条件への一般化は本Issueに含まれない。

## 同値性・STOP・独立検証と消費

- 全24測定runで応答配列digestが完全一致：`f4fc7c5d02eca231999210ad1987245f39196f20c34f2dcd6311293b52e2bc07`。複素S全4要素、IL/APL/両RL、100 vector順序を含む。mandatory g全42要素/vector digestも全run一致：`f74012842588209da721ab387e1c0b30ea74dd16fddec8ed9c6aed690853da33`。plainとdeepの配列digest・mandatory_g digestは一致。ビット一致するのは**同じHEADで計器を付け外ししたこの比較**であり、旧mainとの比較や全候補の独立MNAではない。
- 全24runで100/100 forward完了、計測中RF STOP/例外0。timer wrapperがRF例外を握りつぶす経路はなく、既存`test_issue401_timing.py` failure propagationを実行。
- 検証PASS：`uv sync --frozen`、`test_issue401_timing.py` 7件、`test_issue415_production_stamps.py` 3件、`test_issue309_rf_core.py` 7件、`test_phase2_branch_mna.py` 6件、`test_phase2_numeric_diagnostics.py` 3件、`git diff --check`。これらは独立MNA／科学回帰を確認するが、100候補すべてのMNAを意味しない。CIは未実行。
- 12 plain + 12 deep process、それぞれwarmup 100 + measured 100。**測定forward 2,400／168,000 requested samples**、warmup 2,400／168,000 samples。Solver runは0。RF応答digestとmandatory_g集計は計測区間の外。
- 初回driver bring-upでpolicy辞書の直接SHA fieldを読む誤りによりsetupで停止したが、RF forwardは0件。`constraint_fingerprint()`照合に修正してから本計測し、未計測失敗をraw run数へ混ぜていない。

## 原記録・再現

全run、warmup外のwall/CPU、計時領域/count、STOP状態、SHA・環境は[コンパクトraw JSON](issue417_forward_timing.json)に保存。最終JSON SHA256：**`6d431c5e163def021e607687d23c421b37d545512915bbd4113bae29e36d9b88`**。同ファイルは全24runを含む。第1 raw suite SHA `2cb177f2129993748cc52bf80236f8abc80eebe8431c654a5211ebd557b5c024`、別processで行った再測定suite SHA `55f520dae6aa55a0f9b5799d92066a6abf3570ebd21d83a45ba8d6a082da6c60`を、merge前fingerprintとして記録。

再現（出力先は未存在であること）：

```bash
uv sync --frozen
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 taskset -c 2 \
  uv run --frozen python project/diagnostics/issue417_forward_timing.py \
  --suite --pairs 6 --output <未存在の出力.json>
# 同じコマンドを別の未存在出力先で再測定する。
```

両run suiteの出力は測定完了まで一時記録として保存し、全runを単一raw JSONへ統合した。再測定用`/tmp/issue417-forward-repeat.json`は統合とSHA記録後に削除済み。別worktree `/home/user/src/reconfigurable-rf-lpf-issue417` を作成し、Draft PR作業用として維持する。

# Issue #410 — 完全RFResponseを維持したC行列組立て診断

## 結論と範囲

**固定C／可変C分離は不採用。全6設定先行組立ても効果未確定につき本番不採用。**
初回の診断・仮説比較として完了し、`src/`、RF入力、requirements、Solver、保存契約は変更しない。
[issue410_probe.py](issue410_probe.py)だけで明示選択する開発用試作を残す。正式採用には独立レビューが必要。
IL-only案、incidenceのみの事前準備、公開RFResponseのコピー除去は実装していない。
正式EXP、新トポロジー研究、RF-F003への昇格、Phase移行ではない。

## 固定入力と出典

- 最新main確認時 `3000a6fac0f7165173f19a1fea38f5d8e380b1f8`。#393/#394/#401/#408、正本instructions、registry、bands、results/KB、roadmapを確認。
- 全測定HEAD **`9e9c3f13ef0fe0dca218ef0d7b3bdd1bc9c42415`**。試作もこのcommitに含む。RF/source tracked差分なし。既存未追跡 `.issue361-definition.json` は不使用・未変更。
- RF-T008 rev3 **trial明示opt-in**、effective SHA `e682165c72d3a8b9f1384a2529f71bacfebfc9d17164d4af5af879e4a138b532`、full_lpf。
- [baseline.yaml](issue377/baseline.yaml)、[starts原本](issue401_starts_1002.json)。seed1002、25変数、4L、C9枝（設定共通7・可変2）、5ノード。6設定・28不連続区間、70 samples/forward（pass 2点／stop 3点）、全mandatory 42点。
- Plan `8ac7bab9567918ae5c656fd449807ad2c38c1e1cad9e39c8ed217b95a569043e`、grid `6805740a36f6100d7dec3e7308924242e909255f1ea2d287b7c734c400f98f26`。
- start vector `6203467121a4e37baaa51c471aaecb3174f3374f9ab955d6fbf101f7b5ce935f`、starts bytes `63b671ea269656843df118230b7d920e91515188235809b6dd0efd667ac997ab`。
- 全77runのsource identity SHAは同一 `6f8f5112537a5a30877fae780b037abe9e6e8675fd2be34340b955ab2c3949fb`。probe SHA `3bcd07b49d2917f0ddafedc62425a08ea11e67f6982b0b93fdf79b4be711c12d`、共通bench SHA `32b29c4059b452c26eb89d5dcf42f09293dbf134dae176e2512ddccf289e358d`。
- bands、両固定S2PのSHA・source全ファイルSHA・実引数・環境・全solver出力は[原記録](issue410_ab.json)に保持。旧logical `data/...` をloaderでbyte同一の `rf/...` に解決し、固定S2Pを含む外部ポート評価を維持。
- Python 3.12.15 / NumPy 2.5.4 / SciPy 1.18.1、NumPy buildのOpenBLAS 0.3.34.106.0（ILP64）、WSL2共有host AMD Ryzen 7 PRO 4750G。各run別process、affinity `[2]`、OPENBLAS/OMP/MKL各1 thread。仮想CPU固定であり物理coreの専有・温度・電源・他負荷制御ではない。

## 4関数の比較と優先順位

F=70 samples、S=6設定、B=9 C枝、N=5ノード。以下のC計算量はdense einsumの概算で、70回のPythonループを6回にしたという意味ではない。

| 対象／候補 | 減らせる処理・計算量 | リスク・今回の実施状態 |
|---|---|---|
| decode直後のencode逆変換除去 | schema既知の数値入力だけ逆変換・固定C全6行比較・vector配列生成 O(SB) を省ける | 外部CircuitValuesではschema／設定不変検査が必要。**未試作**。baseline deep encode中央値0.854ms/100 forwardで、単独効果は小さい見込み |
| decode内のPython変換重複 | takeのfloat tuple生成後、CircuitValues.__post_init__でL/k/C全行のfloat変換・有限／符号検査を再実行。decode全体 O(SB) | 検査を無条件削除すると直接CircuitValues構築の契約を壊す。decode deep中央値7.471ms/100、内部分離は未計時。**未試作** |
| node C：全6設定Dを先行（six） | O(FBN²)からO(SBN²+FN²)、周波数係数・branch中間配列を70行→6行 | 再結合により丸め・overflowの発生位置が変わり得る。**実測済み** |
| node C：固定共通＋可変設定別（split、最優先仮説） | O((Bfixed+S Bvar)N²+FN²)、ただし今回coeff変換は6行のまま。einsum2回・fixed抽出・共通加算が増える | 各forwardで更新、候補間cacheなし。Cfix Q60とCvar Q35は並列でも別枝。**実測済み、遅いため不採用** |
| einsum optimize=False／固定path／小行列積 | 小行列ではpath探索費用を減らせる可能性 | 縮約順序・中間配列・メモリ配置依存。今回の2案ではoptimize=Trueを維持し独立変数化。**他方式は未測定** |
| port Schur抽出 | 現状ports/middle tuple再生成と4組の二段advanced-indexコピー。index事前準備／単一並べ替えで O(FN²) コピー定数を削減し得る | source/load順序・middle空・任意treeを保持する必要。Schur solve O(F(N−2)³)は残る。**未試作** |

baseline deep 10回（warmup別1回）の中央値ms/100 forward：RF 66.653、port 31.307、node 22.110、matrices 7.250、power 13.531、cascade2段計5.528、Y→S solve 2.467。
包含時間は加算不可。runごとに差し引いた node−matrices 中央値14.872ms、port−node 9.160msは検査・配列変換も含み、C stamping／Schur solve単独時間ではない。
`_frozen`は5配列をbytes backingへコピーして公開不変性を保証する。直接配列を返す変更はcallerの書換えやwriteable再設定を許し得るため未試作。gridのω事前準備も未試作。

## 試作の意味

`Y_f = K/(ω_f 10^-9) + ω_f D_setting(f)`。sixは9枝を6設定で縮約。splitはschemaのstamping順 `[fixed, variable, IC_fixed, constant]` から共通枝／可変枝を分け、共通Dを1回・可変Dを6行で縮約後に加算する。
固定C・L/kは**設定間だけ共通**。毎forwardにK・C係数・全Dを作り直す。Qは枝ごとに保持し、0可変枝も空の縮約で処理する。
入力検査、完全L行列SPDと悪条件閾値、Schur、Y→S、固定S2P cascade、複素load power_response、S全4要素／IL/APL／両RL生成・immutableコピーは保持。
ProbeTopologyのnode overrideを既存deepのbase-class probeが捕捉しないため、試作側のdeepは明示拒否する。deep実測はbaselineのみ。plain/timedは利用可、今回はtimedは未測定。

## plain A/B（ms、warmup除外、外れ値除外なし）

各batchはbaseline／候補を各warmup1回の後、`旧→新→新→旧`の釣り合った順序で各10回。隣接2runを1pairとする。再測定batch2も全件保持。

| batch | 候補 | solve旧 中央値[最小,最大] | solve新 中央値[最小,最大] | pair新−旧 中央値[最小,最大] | 新が速いpair |
|---|---|---|---|---|---|
| 0 | split | 73.254 [70.930,82.103] | 80.615 [78.965,93.071] | +8.244 [−2.217,+17.919] | 1/10 |
| 1 | six | 73.381 [70.677,86.270] | 71.281 [69.162,111.971] | −2.040 [−16.400,+39.957] | 6/10 |
| 2 | six再測定 | 73.506 [71.397,89.818] | 72.370 [69.492,156.670] | +0.865 [−18.952,+77.950] | 4/10 |

setup旧→新の中央値：batch0 237.856→237.500、batch1 239.277→239.637、batch2 241.436→238.390ms。
total（setup+solve）中央値：311.174→318.136、318.740→315.429、318.517→316.437ms。
solver CPU中央値：72.969→80.364、73.303→70.974、73.506→72.048ms。observationは全て計測外（中央値約1.1–1.2ms）、追加1 forward。
solveは`worker.solve()`でありHybrid単体ではない。setupには入力検査・source記録・固定S2P準備も含む。

同一start値のnode-only micro（1000呼出×10巡、初巡除外、順序反転）はbaseline 174.769、six 156.084、split 242.321ms中央値。
これはRF forward全体やSolverの速度比ではない。splitの抽出・2縮約等の追加費用がこの小回路では勝る。sixの局所改善はplainの小差・符号反転・共有負荷と区別できず、**改善率は認定しない**。

全77runはnfev100、restarts0、evaluation_budget_exhausted／**未収束**、RF異常失敗runなし。同一variant内のsolver出力は全件完全一致。
一方、variant間は一致しない。baseline→splitのbest_x最大差2.911e−8、best_fun差+1.599e−5。sixはbest_x最大差8.253e−4、best_fun差−0.00452144。
有限差分がRFの丸め差を増幅して経路を変えるため、同じ100候補の時間比較とは主張しない（同じstart/seed/条件/nfevの比較）。

## 固定100候補の数値同値性

baseline Solverから得た100 vectorを固定し、旧・six・splitでそれぞれ同じvectorを再評価。
[ベクトル原本・各vector SHA・全誤差・node micro原記録](issue410_equivalence.json)。同じimmutable grid/prepared requirementsを共有して全mandatory_g **42点の順序込み**で比較した。

| 最大絶対差（100 vector・70点） | six | split |
|---|---:|---:|
| 複素S全4要素 | 1.870e−14 | 1.870e−14 |
| IL dB／mandatory_g | 8.172e−14 | 8.172e−14 |
| APL dB | 4.219e−14 | 4.219e−14 |
| 入力RL dB | 4.406e−13 | 7.284e−13 |
| 出力RL dB | 3.553e−13 | 3.482e−13 |

**ビット一致ではない**。テスト許容差atol1e−9/rtol1e−11内の一致であり、許容差を理由にsolver出力完全一致とは記載しない。
固定2候補（start、L/固定C/IC固定C変更＋全6可変C行を0..3へ変更）を各試作で全70点独立branch-current MNA・受動性・電力保存検証。さらに0可変枝のRF-T008で独立MNAを実施。
RF-F003/T005/T006/T007/T008の現行モデル比較（T006追加区間含む）、外部CircuitValuesの固定C設定差拒否、NaN/形状/不正sampling、非SPD／悪条件閾値、node非有限STOPとsample index、zero transmissionの+Inf、Y→S特異例外、不変配列を回帰。
既存独立MNA・複素負荷・透過ゼロ／subnormal・S2P SHA／範囲・Worker異常STOP/保存回帰も実行。
**未検証**：100候補すべての独立MNA、あらゆるoverflow条件での旧新STOP発生位置同一性、連続周波数保証、EM/SRF/Q(f)/公差/実測。試作は本番契約の代替ではない。

## 消費と検証

- A/B 66run＋baseline deep11run＝77run：Solver **7,700 forward**、後段観察77、計7,777 forward／544,390 requested samples。
- trajectory capture100＋固定再評価300＝400 forward／28,000 samples（上記とは別）。
- node-only micro 30,000呼出／2,100,000 sample組立て。S/cascade/metricsを通らないためRF forward数には加算しない。unit/regressionのRF呼出はこの計測合計の外。
- `uv sync --frozen` PASS。新規同値性テスト最終5件、既存9モジュール64件 PASS（importによる2件重複実行を含む）。新規テスト開発時のcomplex isposinf／T006追加格子不足／overflow fixture不足を修正して再実行した。RF診断runの失敗ではない。
- 保存audit正常終了。既存EXP-058 running、EXP-116/117 preservation_incomplete等を出力どおり保持し、全EXP完全性PASSへ読み替えない。
- ローカル集計でTimerCollectorのキーをwall_sと誤記したKeyErrorはwall_nsで再集計済み。原記録・計測を改変／再解釈していない。
- Draft PR独立レビュー・CIは別判定。追加checkout/worktree/永続tmpディレクトリは作成していない。

## 再現

```bash
uv sync --frozen
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 taskset -c 2 \
  uv run --frozen python project/diagnostics/issue410_probe.py --variant split \
  --config project/diagnostics/issue377/baseline.yaml \
  --starts project/diagnostics/issue401_starts_1002.json --arm hybrid --seed 1002 --mode plain
# variantをbaseline/sixに替え、上記順序・warmupで別process反復。結果JSONのsource/SHAを再照合。
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  uv run --frozen python -m unittest discover -s tests -p 'test_issue410_c_assembly.py' -v
```

原記録のHEADで実行すれば当時のソース、別HEADなら新sourceとして区別する。各runの完全なcommandはrawにある。
固定replayは新規testが保存100vectorを再評価する。microは同JSONのvector[0]をdecodeし、各variantの`topology.node_admittance(values, 2π*grid.frequency_hz, grid.setting)`を1000回、10巡の正逆順に実行（初巡除外）。SPD検査を含み、固定Dを呼出間でcacheしない。

原記録SHA256：ab `2583c5f4b9301698dfa6d3027197e5e47403a764b3297be9498d11d5cbe534de`、equivalence `e87355eb364073a5743062e8e4ee7c90c3012cbfb5e38bef6283860381736ba0`。

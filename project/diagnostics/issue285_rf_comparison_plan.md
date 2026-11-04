# Issue #285 — 同一RF費用によるSLSQP v2 / Hybrid / SLP比較案

**計画のみ・未承認・未実行。** 基点main `8de28ad51de9377bc62080c2b097e26b0c79213c`。#284 / [PR #297](https://github.com/miyabimm/reconfigurable-rf-lpf-research/pull/297) は独立再レビューPASS・CI PASS後にmain統合済み。ただし実RFは2点×28区間のforwardを同一点で2回（112 samples）確認しただけで、粗2→精3 pipelineはmock、実RF最適化・17/1001点・独立検証は未実施。**統合は比較実行可能の証明ではない。** 下記の実行配線・合法性・保存・anytimeが未実装/未検証のためG2は禁止。#284の[APIと限界](issue284_rf_pipeline_adapter.md)も参照。

## 共通条件と接続

- 明示opt-in **RF-T008 rev3 / full_lpf**、effective SHA `7de08611f8dd15b40fdfb7946e8c93de5796d026641bdca0f12e992962d05fd4`。active正式RF-F003 / `f85710200ccda5b72ab32f943540fbfd7a8abb3137c5f4e6e5ba7a6d7b3da2ba`は不変。`build_nominal_circuit()`はF003/T006未対応でT008へ代用しない。bands SHA `1b1182e4c947059cb263c1af52ddf64236bd1fd9e83770cc844126576c7865fe`、6設定の28個別UL/DL/H2/H3区間、ギャップを結合しない。外部50Ω源・60−j40Ω負荷、固定S2P `circuit1_ant_coupler_0_6ghz.s2p` SHA `ad266111ba1dc2b92f235d39f4a647ff271050bc11941c217661dd299ee59945` と `circuit2_poc_through_0_6ghz.s2p` SHA `b3cfc861bc0c8221f49328598c9d7d0766a6e94e42e990b6a50f6c90bf9a84da` をG1でpolicyと照合する。
- 固定対象案は[#250](https://github.com/miyabimm/reconfigurable-rf-lpf-research/issues/250)のEXP-062由来4L/3GJM/1 PCB-C/2複合Cv、面積6、definition SHA `bc50042a1b0b1ebf19c0272fb2ee944b52cd76e14eb8d44673bfa57f6033c068`。枝・chip row・signed k順まで原checkpoint/manifestと照合し、再現できなければSTOP。固定Cと6設定Cvは別Qの別部品。面積は固定群間では同じだが成績表に記す。sparse checkoutでは原証拠のbyte監査は未実施。
- 固定`CircuitDefinition`＋解決済みpolicy → `build_nominal_circuit()` → `circuit.schema`と`circuit_box(circuit)` → 物理 `x=[L, fixed C, signed k, IC fixed C, 6設定のvariable C]` → `circuit.forward_evaluator(n).il(x)` → 薄い `RFPipelineAdapter` → 汎用solver。`il`は固定S2Pを含む**外部ポートIL配列**であり複素S全体ではない。boundsは物理部分のみ、SLSQP内部の無界epigraph `t`をHybrid/SLPへ渡さない。既存solver・回路・S2P・sample生成を複製しない。
- 閉boxは開境界の緩和にすぎず、SPDも非凸。`validate_components()`/`PhysicalComparison.validate_vector`で部品、接続role、開端、全L行列SPDを厳格に別検査し、物理不正の修復・clip・有限ペナルティは禁止（既存generic solverの正規化座標からの浮動小数点再構成時のbox保護clipは別であり、物理/SPD修復ではない）。`for_exploration=True`による探索上の緩和は厳格適合ではない。現solverは非法点や例外で中断し得て、自動回復・stage永続化はない。

## 数学と格子（提案、RF仕様の変更ではない）

ILはdB、尺度1 dB、mandatoryはpolicyの30 dB。各sampleについて
`r_pass=IL_pass/1dB`, `r_stop=max(0,30−IL_stop)/1dB`、
`e_pass=IL_pass/1dB`, `g_stop=(IL_stop−30)/1dB >= 0`。
Hybridは `sum_i w_i r_i²`、本案は全 `w=1`。SLPは `min max_i e_i`（**signed max**、二乗max/絶対値maxではない）、`g>=0`、weightsを渡さない。例えば通過0.4、阻止29.9 dBでは `r=(0.4,0.1), e=0.4, g=-0.1`。目的とhard制約は別でありHybridはboxのみ、罰則ゼロやsolver成功でもRF可行とは限らない。sample数により二乗和の実効重みが変わる。1 dB尺度・等重みは探索例であり承認済みRF重みではない。35 dB公称・0.30 dB目標・30.005 guardを新hard制約にしない。既存`SampledEpigraph.residuals(x,t)`は符号/意味が異なりそのまま`e`にしない。

RF側wrapperで粗2点/区間（56 samples/forward）のHybridと、精3点/区間（84）のSLP・pipeline候補選別を別adapterとして構成し、meterを共有する。Aも既存粗2→精3。全群の中間/最終評価は別の17点（476）、選抜後dense1001点（28,028）。各区間の端点を含み、setting/role/周波数/S2Pを固定する。`minimize_pipeline`, `hybrid_minimize`, `slp_minimize`にRF周波数制御や再試行を追加しない。

## 4群・同じ開始点

| 群 | 提案する探索 | 意味と差 |
|---|---|---|
| A | 既存 `run_c1_staged` + physical SLSQP v2 | epigraph `min t`、各格子でpass `t−IL>=0`、stop strict30。粗240/精120、既存のstatus依存warm/rescue（最大粗500/精280、最大4 stages）を変更しない |
| B | `hybrid_minimize(..., aggregation='sum')`、粗2 | rの二乗和、boxのみ。選別前に別途精3評価 |
| C | `slp_minimize(..., aggregation='signed_max', constraints=fine.constraints)`、精3 | signed最大pass IL、精格子stop制約。数値許容とstrict判定は別 |
| D | `minimize_pipeline(coarse.residuals, fine.errors, bounds, constraints=fine.constraints, ...)` | Hybrid→精3候補選別→SLP。選別はsolver許容の可行性→違反→signed max、以降多様性。未収束候補を含み得る |

4群とも同一物理box・同一開始**物理vector**・同一seedを対応させ、Aの`t`だけ同じxから既存C1で再seedし再生費用を課金する。Aは`search_guard=False`、AFEなし。Dのgeneric pipelineは内部で必ず `2**sobol_m` 個生成するため、**sobol_m=0、starts空**とし1 scrambled Sobol点/seedだけを用いる案。A/B/Cにもその物理vectorをそのまま渡し、完全vector/SHAと生成規則をG1で凍結。`generate_starts`の16点blockやnominalを暗黙に混ぜない。生成された点が非法なら全群に同じ事前固定のfail-closedを適用し、後知恵の置換やseed追加はしない。AのC1 seed/replayがxを変えないことを検証できなければ比較実施前にSTOP。Dの内部Sobol/変換と保存vectorの完全一致も試験必須。

実装上の内部評価・選別は群で異なり、数値的feasibleやsuccessはRF厳格判定ではない。最終順位は同じ17/1001格子・同じ深度の共通RF指標のみ。既往checkpointは固定definitionの出典/同条件・同深度の外部参照に限る。最良vectorを初期値に注入しない。既往結果はRF ID/SHA・参照面・格子・validation・sourceが全一致しない限り比較順位に入れない。

## 有限予算案と計上

以下は**根拠付きの未測定提案値であり実行承認・自動確定ではない**。pilot seed 23,24、remaining seed 25,26、各seed×4群=16 actual（pilot 8、remaining 8）、各actual 750,000 **requested frequency samples**、全体上限12,000,000。1 seedあたり1 start、欠損を補充しない。既往[#263](https://github.com/miyabimm/reconfigurable-rf-lpf-research/issues/263)は同4Lの異なる保存startによるAFE対照で750,000/start、#250は1,500,000/startと粗2で最大952の初期選別費用、#245は17 forward/952 samplesの限定実測、#239は56/84/476計測、#284は実forward 112 samplesのみ。これらは**本4群の必要量・収束時間の実測ではない**。過去のnfevからsamplesを推測しない。#250のseed 23〜34とpilot 23/24は出典であって、同じ開始vectorだったとは主張しない。#263のguard/AFEと本案のunguarded条件は混同しない。pilot後にseed/上限/目的を変更して続行しない。

初期生成/検査、Aのt seed/replay、有限差分、再始動、Dの精密選別・errorとconstraint各forward、stage観測、後述17点のanytime観測・終端検査まで**同じ750,000枠**に算入。共有前処理は物理実消費を別記し、比較上は各群へ同じ全額を配賦、二重実行したと偽らない。batch全体が残枠に入らなければ入口前に`budget_exhausted`、失敗forwardはrequested全額・completedは正常return分のみ。候補RF cacheは全群なし（固定S2P等の既存cacheは別）。同一xでもadapterのerrors/constraintsは各1 forward。`nfev/counts`はcallback数でRF費用ではない。粗/精/17別のrequested/completed・calls・失敗・cache・初期化・差分・選別・restart・CPU/wallを保存。CPU/wallはsolver全体も外側で別計測し、meterの入れ子時間を合算しない。requestedは実FLOPsそのものではない。

追加のsolver安全上限案：B/D Hybrid `maxiter=240`, `max_restarts=0`, `max_evaluations=6000`, `restart_sigma=0.1`；C/D SLP `max_iterations=120`, `max_evaluations=8000`, `constraint_tolerance=1e-7`；D `max_evaluations=14000`, `max_slp_candidates=1`。これらはcallback上限でsample上限の代替ではなく、Dは粗Hybridと精SLPの合計に同一meterを適用する。SLPの初期step等は既存API既定をG1に明示固定。固定値が実装上不適合ならSTOPし、別決定なしに増額しない。B/C/Dの例外伝播では現pipelineは部分結果を返さない。外側で事前marker、観測済vector/費用/例外の原子保存が必要であり、**現在その本番接続はない**。合法点観測がない場合は候補ゼロ、途中停止と未収束を区別する。

Anytimeは事前固定sample milestones 150k, 300k, 450k, 600kと終端で、その時点までの最後の合法観測vectorを17点で同一規則で評価（存在しなければnot_run）。各scanの476も上記総枠内、最終scan分を事前予約し、途中scanは予約分を侵さない。first feasible/bestは**検査された観測点に限る**、scanの完了時累計samplesで記録し、見逃した途中可行点の最初の到達とは主張しない。各群で同じ観測・測定方式と保存順が必要だが、現solverの全callback観測・安全なmilestone scan・最終予約は未接続。変更の独立レビューとmock予算/例外試験が実行前の必須ゲート。時間/提案数の有限安全上限もG1で環境実測を根拠に固定し、試験中の強制killは中断・raw保持、勝手に再試行しない。

## 成績表・検証

各seed/群に start SHA、終了/未開始、solver status・成功/非収束/予算停止/例外、forward数、粗/精/17別requested/completed、CPU/wall、最初の検査済strict17可行まで/最良候補までの累積samples（なければnull、観測規則を明記）を記す。未丸め `F=max(pass IL)`、`d2=max(0,30−min H2)`、`d3=max(0,30−min H3)`、`V=max(d2,d3)`、`d2+d3`、最悪setting/区間/周波数、部品/box/role/SPDと面積を保存。物理不正はRFスコアと混ぜず理由付き拒否。strict可行同士はF、不適合RF点はV→d2+d3→Fで並べ、可行ゼロなら最小違反・件数を表示。異なる深度やHybrid二乗和とSLP signed maxは直接順位比較しない。

17点strict30（丸めなし）かつ物理/role/SPD PASSの候補から群ごとF上位最大1件を事前規則で選び、dense1001を最大4件＝112,112 samplesの**別枠検証費**で行う。重複vectorも群別の計上規則をG1固定し物理実消費を別記。dense strict PASSだけに既存`evaluate_independent_sample()`による全28区間×3点=84点の独立branch MNA、電力収支・受動性・独立SPDを実施、既存`validate_post_search`の適用条件/予算を事前照合する。独立MNAの演算費用・CPU/wallはforward samplesとは別記。候補なし、選抜外、未開始は`not_run`と理由を保存し、失敗と混同しない。solver収束、17点/1001点有限格子PASS、独立検証PASS、正式RF適合は別。trial結果は正式F003認定ではない。連続周波数、Q(f)、SRF、EM、公差、実測、実装可能性は未保証。best-foundは大域最適の証明ではない。

## 後続の本番実行Issue案（1件・未起票）

**題案：RF-T008固定4LのSLSQP v2 / Hybrid / SLP / Pipeline同requested-sample対照pilot**。範囲は上記4 seed・16 actual・各750,000・検証最大112,112とし、先に必要最小の共通入口/計測・保存配線を別途レビュー、mockで同一Sobol/x、C1 replay、格子、sample上限、17予約、例外時部分証拠と既存v2非回帰を確認。既存共通CLI/YAML・`SampleBudgetCost`・post-search/storageを再利用し、未対応を隠して実行しない。格子・重み・seed・予算・検証方式を変更する場合は別決定。

- **G0** 完全evidence checkoutで最新main中央台帳へ新番号を予約・remoteで照合。番号推測禁止。Issue起票だけで実行せず、具体的実行Issueのユーザー起動が必要。
- **G1** RF ID/effective SHA、bands/両S2P SHA、definition/完全x・seed/C1、commit/dirty patch・uv.lock・環境・single-thread、配賦、全上限・milestone・停止・選抜・最大保存byteをmanifest/storage plannedへ凍結しremote byte readback。10,000,000 bytes/EXP等の保存規則と例外承認を遵守。原checkpointはread-only。G1整合できなければSTOP。
- **G2** pilot 23/24の8 actualを順次実行しrawを原子的に記録。予算停止・非法・非収束は区別し、provenance/保存障害・不明な中断は全体STOP、残りnot_started、無断再試行禁止。pilot保全・費用・配線監査PASS後にのみ固定remaining 25/26へ進む。pilotは最終集計に含め、予算拡大・再選別が必要なら停止し別判断。
- **G3** 固定選抜と17/dense/独立gate、候補ゼロ・未実施を含むsummary、完全checkpointと失敗診断・検証overlayをA/Bに分類。rawは`results/`、保存不完全なら保持。既存証拠を改変しない。Git HEADからbyte読戻し、finalize監査。
- **G4** 全試行・容量・出典・保存監査/CIと結果Draft PR、ChatGPT独立レビュー。正式RF適合認定/候補昇格は該当条件の独立ゲート後の別判断。
- **G5** finalize PASS、再開不要、A/B保全確認後のみ対象EXPの一時Cを個別整理。未完了なら保持。

今回、実RF本番計算、新EXP予約、結果生成、17/1001点や新候補独立検証は**すべて未実施**。Phase 2のまま。

# Issue #284：RF-T008 薄型アダプタ（限定開発検証）

基点 main `8f1029a5033ab96824f74397ef3ac08b83c1d65d`、#283/PR #296 は独立レビュー後にmain統合済み。対象は明示 opt-in **RF-T008 rev3 / full_lpf**、実効SHA `7de08611f8dd15b40fdfb7946e8c93de5796d026641bdca0f12e992962d05fd4`。active正式 **RF-F003** / `f85710200ccda5b72ab32f943540fbfd7a8abb3137c5f4e6e5ba7a6d7b3da2ba` は不変、現 `build_nominal_circuit` はF003/T006未対応で代用しない。bands SHA `1b1182e4c947059cb263c1af52ddf64236bd1fd9e83770cc844126576c7865fe`。これは実験runner・性能比較・候補昇格APIではない。

## 接続と意味

固定 `CircuitDefinition` と `load_constraint('RF-T008', allow_trial=True)` → `build_nominal_circuit` → `RFPipelineAdapter(circuit, points_per_interval, cost_meter=...)`。`bounds` は `circuit_box` の**物理部分のみ**、`x` の順序は `circuit.schema` のL、固定C、signed k、IC固定C、6設定の可変C。既存SLSQPの最後のepigraph `t` は含まない。固定S2Pを含む既存 `forward_evaluator(...).il(x)` のIL配列を使用し、複素S全体は返さない。既存のgridは6設定・28区間を別々に扱う。

各sampleのILをdBとし、尺度は**1 dB**、mandatoryをpolicyから読む：

- `residuals(x)`：全通過sampleの `IL / 1 dB` と全阻止sampleの `max(0, mandatory - IL) / 1 dB` を連結。Hybrid `sum` は既定重み1の二乗和。これは探索用の例示的ペナルティであり、新RF重みの承認・RF可行性ではない。点数で実効重みは変わる。Hybridはbox以外を制約として扱わない。
- `errors(x)`：通過sampleの `IL / 1 dB`。SLP `signed_max` は**符号付き最大**を最小化し、二乗max・絶対値maxではない。
- `constraints(x)`：阻止sampleの `(IL - mandatory) / 1 dB >= 0`。H2/H3 mandatoryは現trialで30 dB。SLPにweightsを渡さない。例：pass IL=0.4、stop IL=29.9なら `e=0.4, g=-0.1, r=(0.4, 0.1)`。名目35 dBや目標ILをhard constraintにしない。

`minimize_pipeline(adapter.residuals, adapter.errors, adapter.bounds, constraints=adapter.constraints, ...)` に既存generic solverの必須seed・有限予算・restart設定を呼出側が与える。評価器の粗/精密切替は異なるadapterを作るRF側の責務であり、generic solverにはRF固有処理を追加しない。pipelineの開始点・候補・各stage状態・nfevをそのまま記録すること。`result['best']['success']` や `feasible` は数値上の判定であり、RF判定ではない。`assess(x)` は別forwardで物理・未丸めstrict finite-gridを再評価し、常に `candidate_promotion_blocked=True`、dense/MNA/power/passivityを `not_run` とする。独立検証は既存 `evaluate_independent_sample` / post-search validation等の別工程。

物理box・開端・接続role・部品・全L行列SPDは既存 `PhysicalComparison.validate_vector` / `validate_components` を再利用。非有限、非法、未証明role、SPD不正、forward失敗は例外として伝播、clip・修復・有限ペナルティで隠さない。`for_exploration=True` はRF-T008のGJM=0や未証明roleを探索上だけ許容し、その場合はstrict物理適合・昇格にしない。閉boxを使うgeneric solverは開端・SPD不正点を生成しうるため、**例外でpipeline全体が停止し得る**。未対応の非凸可行域を自動回復する仕組みはなく、実験利用可能とは判断しない。

`EvaluationCost`または`SampleBudgetCost`を外部から渡せる。各callbackは共有cacheなしで毎回1 forwardを行い、2点では56 samples。有限差分・選別・`assess`・失敗batchも実際のrequestedに課金し、completedは正常returnのみ。`nfev`はcallback数でありrequested samplesではない。`SampleBudgetCost`は次のbatch全体が上限を超える前に例外停止する。ソルバーに例外が伝播した場合はpipeline結果自体は返らないため、外部meterは確認できるが、途中stageの永続化・自動再開・EXP保存は提供しない。呼出側がseed・例外とmeterを保全しなければならない。

## 実施・未実施

- fixture `tests/test_phase2_problem_seed.py::make('RF-T008', 4)`、2点×28区間。実forward配線テストは同一物理xを直接1回・adapter経由1回の計2回（112 requested samples相当）だけで、solverによる実RF探索ではない。solver接続は実generic pipeline＋**mock IL**・固定box・seed 23。mockによる30 dB直下はsolver許容内でもstrict FAIL、30ちょうどは有限格子上PASSだが昇格blocked。部品/box/SPD/role違反、失敗forward、予算停止、例外後meterもテスト。
- 2点のみの開発fixture動作確認。17点、dense1001点、実候補の独立branch MNA・電力収支・受動性・独立SPDは **not_run**。既存branch MNAユニットテスト等はソフトウェア回帰であり、このfixtureの独立RF検証ではない。
- 実RF SciPy最適化・本番探索、新EXP/番号予約、結果や既存checkpoint変更、候補認定・Phase 3は行っていない。Q(f)、SRF、EM、公差、実測、連続周波数、物理実装は未検証。有限格子・solver収束はこれらの保証ではない。
- #285は独立レビュー・main統合前は本アダプタを比較実行可能と扱わない。RF条件・モデル・SLSQP v2の240/120と回復規則は不変更。

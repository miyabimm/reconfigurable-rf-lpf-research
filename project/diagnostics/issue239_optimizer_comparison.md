# Issue #239 / 9B-2：非凸最適値へのRF計算効率（設計・ソフトウェア検査のみ）

## 判断と確認範囲

優先順位は **計測の整合 → 共通strict評価 → SciPy-DEの小規模対照案 → 必要なら最小L-SHADE**。
SLSQP status0件数を研究目的にしない。L-SHADEの優位性は未実証、採用は未決定。
新EXP予約・実RF最適化・新予算・Phase 3はない。基点mainは
`e6586398ff9c4a39f2c6f8fca1d58e7e3a283c76`。

- 最新mainの運用指示・SLSQP v2・保存規則・registry・bands・RF-F003/T008を確認。
  active正式 RF-F003 / `f85710200ccda5b72ab32f943540fbfd7a8abb3137c5f4e6e5ba7a6d7b3da2ba`。
  比較候補だけが明示opt-in **RF-T008 rev3 / full_lpf /
  `7de08611f8dd15b40fdfb7946e8c93de5796d026641bdca0f12e992962d05fd4`**。
  loaderで両実効SHAを再確認。bands SHAは
  `1b1182e4c947059cb263c1af52ddf64236bd1fd9e83770cc844126576c7865fe`、6設定/28個別区間。
- 観測の出典：[Issue #237](https://github.com/miyabimm/reconfigurable-rf-lpf-research/issues/237) /
  [PR #238](https://github.com/miyabimm/reconfigurable-rf-lpf-research/pull/238) は収束7/9対8/9、
  17点strict30適合はいずれも0/9と報告。これは今回の再実験・履歴証拠の完全監査ではない。
  sparse環境では元EXP/全9seedの独立byte監査は未実施。
- 仮説：局所法は初期値・尺度・境界残差に敏感で、大域的な探索と局所polishの分担に余地がある。
  非凸性だけから特定手法の優越性・大域最適性・実装可能性は導かない。

## 1. 比較の共通契約

探索する物理変数 `x` は既存schemaの全L/C/signed k/共通IC固定C/6設定Cvのみ。
**DE/L-SHADEに無界epigraph tを渡さない**。SLSQP内部の既存epigraphは維持するが、
報告ILはtではなく同じforwardから求める。固定kは固定座標のまま、box開端をepsilonで閉じない。
外部固定S2Pの完全cascade、50Ω源・60−j40Ω負荷、Q・部品・接続・全L行列SPDを維持。
IC Cfix(Q60)とCvar(Q35)を合算せず、Cvar=0でもCfixを残す。

同一の不連続28区間を個別にサンプルし（ギャップを橋渡ししない）、

- `F(x) = max(passband IL)`：全6設定のUL/DL。
- `d2 = max(0, 30 − minH2)`、`d3 = max(0, 30 − minH3)`、`V=max(d2,d3)`。
  比較用sumは **d2+d3**（サンプル別和ではない）と固定する。
- strict feasibleは**未丸めV==0、部品/box/SPD/接続role適合**の全て。
  可行点同士はIL、不適合RF点はmax違反→sum違反→ILの辞書式で順位付け。
  物理不正・forward失敗はRFスコアを作らず、理由付き拒否/失敗として保持する。
  それらを可行点・通常のRF不適合点に混ぜず、修復/clip/有限penaltyで隠さない。
- 30.005guard、四捨五入、ソルバー許容差、nominal35、IL目標0.3を新hard制約にしない。
  探索2/3点でのVと、17点/1001点のstrict判定は別列・別評価。
  収束と可行性も別列。共通RFスコアは数値収束を可行性の代用にしない。

`optimizer_comparison.PhysicalComparison(circuit, points).evaluate(x)` が最小forward-only API案。
既存policy-bound builder/validator/evaluatorを再利用し、tを拒否し、適合物理点だけに
`SampledScore(F, minH2, minH3, V, sum, strict_feasible)` と `rank_key()` を返す。
`sampled_score`単体はRF-only helperであり、物理適合の証明には使わない。
条件/参照面/格子/検証深度の異なるインスタンスの値は順位付けしない。
runner、EXP export、グローバル探索器、昇格APIではない。

## 2. 計測：nfev≠RF forward

根拠は既存 `sampled_epigraph.py` / `staged_optimization.py`：objectiveはtを読むだけ、
重いIL計算はresiduals内。SciPy DEも不適合個体ではobjectiveを呼ばず制約を評価する。
両nfevをFEとして並べる比較は不正確。

`evaluation_cost.EvaluationCost` はオプトインのin-process計測（単一thread用）。
`scipy_slsqp_stage(..., cost_meter=meter)` でobjective/constraintと実際のil入口を数える。
既定引数なしの挙動・状態形式、forwardの数学/出力・SLSQP予算/ftol/差分設定は不変更。

|記録|意味|
|---|---|
|`RF_forward_calls`|`evaluator.il`に入った回数、失敗も含む。キャッシュhit/事前拒否は含まない|
|`frequency_samples_requested`|入口で課金した周波数sample総数。2点=56、3点=84、17点=476/回|
|`frequency_samples_completed`|正常returnしたbatchのsample数。途中失敗の実solve数は未計測|
|`forward_failures`|例外・中断で完了しなかったforward batch|
|`component_checks/rejections`, `spd_rejections`|既存component検査の回数/失敗と、componentまたはforwardで判明したSPD失敗。SPDはcomponent失敗の内数になり得る|
|`box_rejections`, `role_rejections`|物理APIの明示事前拒否（修復なし）|
|`cache_hits`|物理APIの明示opt-in exact cacheでforwardを省略した回数|
|`solver_objective_calls/solver_constraint_calls`|ソルバーが要求した各callback数。SciPyのnfevも別途そのまま保存|
|`cpu_seconds/wall_seconds`|process_time/perf_counter。ソルバー全体または物理evaluate全体の累計、RFだけの時間ではない|

同じ点への複数検査は複数event。unique物理点数とは呼ばない。物理SLSQPには内部部品検査を
新設しないためcomponent_checks=0も正常。正規化経路に元々ある検査は計測する。
SLSQP計測の時間は座標変換・ソルバー・最終変換まで。C2の `_observe`、seed生成、17点再評価、
dense/独立検証は**別メーター/別フェーズ**で課金する。過去のnfevからRF回数を復元しない。

```python
# 既存C2 callbackへの接続案（本番実行許可・新runnerではない）
def measured_stage(problem, vector, maxiter, target):
    meter = EvaluationCost()  # stageごとに新規
    try:
        return scipy_slsqp_stage(problem, vector, maxiter, target, cost_meter=meter)
    finally:
        # 呼出し元の既存record sink等でsnapshotを保存する必要がある。
        # 例外時もmeter.snapshot()を失わず保存。自動再試行しない。
        pass
```

成功時はstatus.evaluation_costにsnapshot。外部meterは例外時にも読める。
メーターの再利用なら累計になるので、stage単位と混同しない。
新しいwrapperを既存driverへ本番接続する実装・出典分類・例外保存は後続Issueの作業。
今回既存driverの認可経路や候補記録/索引schemaは変更しない。

公平な一次比較案は全方式**cacheなし**（SLSQPと物理APIの既定）。
`PhysicalComparison(..., cache=True)` の1件exact cacheはAPI検査用opt-inであり、
SLSQPに未接続のままDEだけ有効にする比較は禁止。将来共通cacheを採用する場合は
全方式で同じ物理x/条件/格子identity、失敗非cache、hit別計上を事前固定する。
固定S2P/grid cacheは既存のまま、候補RF cacheとは別。

## 3. 実装根拠と保守コスト

SAWのmainを確認（Issue記載SHAと一致）：
[`1f7da215fd2cd1b1901192b93e16ae0feb11d4f3`](https://github.com/miyabimm/saw-com-optimizer/tree/1f7da215fd2cd1b1901192b93e16ae0feb11d4f3)。
同SHAの `src/sawopt/optimization/` にある
[lshade.py](https://github.com/miyabimm/saw-com-optimizer/blob/1f7da215fd2cd1b1901192b93e16ae0feb11d4f3/src/sawopt/optimization/lshade.py)、
[selection.py](https://github.com/miyabimm/saw-com-optimizer/blob/1f7da215fd2cd1b1901192b93e16ae0feb11d4f3/src/sawopt/optimization/selection.py)、
[adaptive_frequency.py](https://github.com/miyabimm/saw-com-optimizer/blob/1f7da215fd2cd1b1901192b93e16ae0feb11d4f3/src/sawopt/optimization/adaptive_frequency.py)、
[polish.py](https://github.com/miyabimm/saw-com-optimizer/blob/1f7da215fd2cd1b1901192b93e16ae0feb11d4f3/src/sawopt/optimization/polish.py) を参照。

|手法|実装上の事実・LPFへの差分|保守判断|
|---|---|---|
|既存SLSQP|epigraph t＋各sample残差、v2粗240/精120と条件付き回復。任意のstrict30達成を保証しない|既存経路を維持し計測だけ追加。局所polishを再利用可能|
|SciPy-DE 1.18.1|公開NonlinearConstraint対応、finite bounds、既定polishは制約付きならtrust-constr。制約はobjectiveとは別評価|まず公開API＋明示polish=Falseで基準案。新依存不要、最小保守費|
|SAW LShadeBackend|[0,1]、current-to-pbest/1、archive、成功履歴F/CR、線形人口削減、feasibility-first、trace/cache/RNG checkpoint|約千行のmixed integer/continuous backendを移植しない。LPFの固定幅0/open bounds・無修復・RFコスト停止は別設計が必要|
|最小LPF L-SHADE案|連続物理x、pbest/archive/F/CR履歴/固定horizon人口削減＋共通比較/計測のみ|Cを実装するならこの範囲を別Issueで承認。式・RNG・選択・人口削減・予算中断の小fixtureが必要。現時点未実装|
|L-SHADE→SLSQP|global出力の物理xから同格子Fを使いt初期化、既存局所法を明示呼出し|既存polishを再利用。ただし残予算内停止・例外保存の接続は未実装|

重要な相違：SAW comparatorはfeasible省略時に1e-10許容のfallbackがあり、LPFには持ち込まない。
SAWは境界midpoint修復・integer canonicalize/clip、unique-design予算、周波数version付きcache、
履歴再評価を持つ。LPFでは物理不正を隠さず、同点の新格子RF計算も実コストに数える。
SAWの `shade_success_memory` はFのweighted Lehmer mean、CRのweighted arithmetic mean。
原典の全詳細との一致を今回認定していないため、名前だけで標準L-SHADEと同一視しない。
SAW polishはmixed-coordinate/Powellで、LPF既存SLSQPそのものではない。
READMEはreal-SAW統合runner未提供と明示。SAWでのソフトウェア実装はLPFでの有効性の証拠ではない。
adaptive_frequencyは参考確認のみで、**9B-3適応格子を同時に変更しない**。

SciPyの内部選択はLampinen（両不適合なら全制約の非悪化）で、max→sum→ILの辞書式とは違う。
共通契約は**観測候補の集計・最終比較**に適用し、Bは標準DEの内部選択を保持したbaselineと明記する。
private `_accept_trial` をpatchして同一アルゴリズムと偽装しない。
ソース：[`scipy v1.18.1 _differentialevolution.py`](https://github.com/scipy/scipy/blob/v1.18.1/scipy/optimize/_differentialevolution.py)
の `_accept_trial`、`_calculate_population_feasibilities` と
[公開API](https://docs.scipy.org/doc/scipy/reference/generated/scipy.optimize.differential_evolution.html)。
実環境1.18.1のsignature/実装と、合成非線形制約で確認した。

文献：[Tanabe/Fukunaga CEC2014](https://doi.org/10.1109/CEC.2014.6900380)。
[2026年32変種比較](https://doi.org/10.1016/j.swevo.2026.102286) はIssueの調査参照であり、
本文の独立精査/再現は未実施。bound-constrained benchmarkの報告をRF制約問題の結論に外挿しない。
COBYQA/CMA-ESは補欠、同時実装しない。

## 4. 未実行ベンチマーク計画（数値予算は未決定）

- 対象：既存3L0GJM/3L1GJM/4L0GJM、同じ9保存初期値（EXP-086〜094由来）。
  順序・ベクトル/definition SHAは [issue235_scaling.json](issue235_scaling.json) の `starts` を参照し、
  本番前に完全checkoutの元seed/manifestと照合する。新しい初期値を今回生成しない。
- A=既存物理SLSQP、B=SciPy-DE、C=最小L-SHADE、D=C→既存SLSQP。
  正規化SLSQP既往結果は外部参考。A/B/C/Dの実装・実行済みを意味しない。
- 固定seed集合はこの9件の保存seed provenanceに束縛し、B/C/Dの対応する乱数streamも同じ
  保存seedを使用する案。具体的stream/RNG state・各方式の設定は実行前manifestに固定する。
  比較の反復数はこのIssueでは決定しない（9由来初期化は新たな9×4試行の承認ではない）。
- B/C/Dは同一の明示人口行列を共有し、各対応保存xを同じslotへ注入。残りは同seedの
  同一boxサンプル生成規則。既存良好seed注入は**追加なし**を一次案とする。
  注入を採用するなら同接続/同条件の同一リスト・同slot・課金を全global方式に適用し、
  Aへの追加start配分も含めて別途固定する。事後に一方式だけ良いseedを追加しない。
- 人口数/生成法の詳細、RFコスト上限、coarse/fine配分、Dのpolish取分、試行数、
  proposal/wall上限は**未決定**。後続Issueで事前承認されるまでRF探索しない。
  SAWの18D人口などをLPFの既定に流用しない。
- 全方式で固定粗2点→精3点（56/84 sample）、同じ遷移規則・予算配分。
  Aのv2通常240/120・回復条件・絶対上限は維持し、RF上限到達なら
  `budget_exhausted` として既存status9とは区別する停止接続を別途実装する必要がある。
  Dのglobal＋局所＋t初期化forwardも同じ総枠内。CとDは共通global prefixを比較可能に保存。
- 一次コスト軸案：`frequency_samples_requested / 56` を粗2点forward換算FEとし、
  `RF_forward_calls`・completed samples・CPU/wallも併記。失敗batchは全sampleを保守的に課金し、
  実FLOPsと同一とは主張しない。境界で次batch分を予約して上限を超えない仕様が必要。
  世代callbackだけでは途中超過を防げず、public DEにはこのRF上限引数がない。
  事前拒否でRFゼロでもwall/proposal上限で停止し、無限無料探索を許さない。
- anytime traceは各観測候補の物理vector/SHA、格子、strict flag/F/V/sum、累計RF/sample/時間、
  solver callback数/状態を保持。初期人口/seed確認/最終F再計算も課金。
  first strict可行解までのコスト、予算内best feasible IL（ゼロならnull）、可行ゼロ時の最小V、
  最終物理vectorを報告。DEが最後に返す一点だけでなく観測したbest-foundを使う。
- 17点read-only再評価は探索予算と別の共通評価枠で、同じ選別規則に基づき実施。
  17点strict30＋部品/role/box/SPDを満たすものだけ同じ1001点・独立MNA84・
  passivity/power gateへ。収束要件等の既存昇格ゲートも緩和せず、候補ゼロならnot_run。
  全帯域評価・固定S2P SHA・検証深度は維持し、最終RF認定とは区別する。
- 新EXP G0/G1、環境/ソース/seed/完全vector/予算/容量/選別規則、失敗・中断保存とG2〜G4を
  後続Issueで固定。歴史的manifest/索引/結果は遡及変更しない。

## 5. 今回実施した検査と未確認事項

新規テスト `test_phase2_optimizer_comparison.py` は契約7件：
mock SLSQPのobjective2回/constraint3回→RF3回（物理/正規化とも出力同一）、
2/3/17点forward-onlyの56/84/476 sample、無cache/明示exact cache、open端/t拒否、
SPD/role/forward例外と外部meter保持、nextafter(30,0)のstrict FAILとmax/sum/IL順、
**解析的mockのみ**のSciPy-DE非線形制約（1世代、テストfixture予算）を検査した。
新規常時CIへの追加理由はnfev誤用・境界strict誤判定・計測による既存forward変更を防ぐ恒久契約。
汎用optimizer frameworkやアルゴリズム性能テストではない。

`uv sync --frozen`、既存staged 11件・normalized 4件を含むsparse CI相当14モジュール
計103件（102 PASS/既存opt-in real-SciPy smoke 1 SKIP）、synthetic mock CLI、
`git diff --check` PASS。最初の一括コマンドはツール120秒制限でsynthetic_runner中に中断され、
未完了の末尾3モジュールを300秒枠で再実行して全件完了した。環境はPython3.12/frozen uv/
SciPy1.18.1、BLAS/OMP/MKL各1thread。full歴史保存監査はsparse環境のため未実施。
実RF SLSQP/DE/L-SHADE最適化、新EXP、1001点・独立MNA/powerによる新候補検証は未実行。
SRF/Q(f)/EM/公差/実測・signed k実現性・IC/PCB実面積・連続帯域保証は未確認。
Draft PRで独立レビューを待ち、性能改善の判断と実RF対照実験は別Issue/ユーザー判断に分離する。

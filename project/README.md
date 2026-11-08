# Pi Codeの通常作業範囲

Piの通常作業は必要なファイルを取得した完全checkoutで行う。過去EXPの監査や新規EXPの予約では、対象の原本・台帳と必要なGit履歴が実際に揃っていることを確認する。追加checkoutが必要な場合は作成前に承認を得る。

- 現行の正式・試験RF入力は `rf/constraints/`、全28区間は `rf/bands.csv`、固定S2Pは `rf/parasitics/`。
- `rf/constraints/registry.json` の `active_formal_id` が現行正式版。原則として承認済みJSONは**上書きしない**。新正式条件は所有者承認後に新IDとして追加し、active指定を変更する。trialは自動昇格させない。
  - #307 / #306 v1.0の承認済み例外として、現役F003/T005〜T008は同一IDでschema 2・閉区間へ移行（GJM01/PCB_L下限変更を含む）。旧版・旧registry・SHA・親子関係を`rf/constraints/history/pre-issue-307/`に先行保存。新旧SHA対応は`rf/constraints/history/issue307-migration.json`。旧EXPや凍結済み計画のSHAは書換えず、現役条件として再実行しない。
- 不変の旧RF JSON内の `data/...` は**保存時の論理パス**であり、`src/lpf/constraint_versions.py` が新 `rf/` 実体へ解決する。履歴JSON内容・旧実効SHA・S2P SHAは維持する。現役JSONの#307移行後実効SHAは旧版と区別する。ファイル欠落やSHA不一致時は失敗させる。
- 各EXPの原manifest、重要証拠、番号台帳は従来の `experiments/`・`data/` に保全する。番号予約・保存監査の前にcheckoutの完全性を確認する。着手は[運用正本](instructions.md)のIssueスコープとユーザーのPi Code起動指示に従い、完全checkoutでG0/G1を満たす（追加の二重承認は不要）。
- CIは `.github/workflows/audit.yml` で通常の回帰テストと保存監査を実行する。CI PASSは新RF性能の科学的保証ではない。

## 現行フローと資料の入口

- **[Campaign操作ガイド](campaign_workflow.md)**：研究側PlanとAIのdata-only構造提案、明示Controller→JobSpec→Worker、開発/正式EXP、G0〜G5の順序を一か所で確認する。
- [ロードマップ](roadmap.md)：mainの実装実績と未検証ゲート。
- [解析手法・理論](methods.md)：共通モデル、T/π磁気結合と零点の統合知識、BSF文献の出典。
- [保存結果](results.md)：代表結果から条件・格子・検証深度を区別して元EXPへ戻る。
- [データ保全の役割](../data/README.md)：完全treeでの台帳・validation・Pareto・復元証拠の入口（通常sparseでは非取得）。
- [診断・歴史資料索引](diagnostics/README.md)：旧Stageごとの説明、限定実証・レビュー証拠、整理候補。古い「未接続」「レビュー待ち」は当時の範囲であり現況の正本ではない。
- 固定step Worker／逐次親Runnerの詳細は [#317](diagnostics/issue317_fixed_worker.md)／[#319](diagnostics/issue319_parent_runner.md)。
- 旧schema1の `preflight`／`run` は撤去済み。旧EXP変換・互換保証は提供しない（経緯は[#302](diagnostics/issue302_sequential_search.md)）。

### 開発用固定definition CLI

`run_rf_search.py develop --config <schema2.yaml> --starts <starts.json>
--output <未存在のcheckout外system tmpディレクトリ>` が既存の逐次親Runnerを呼び、
親・Job rawの最終実ファイル読戻し後に `summary.json` を原子的に保存する。
任意の `--spot-checks '{"terminal":[0]}'` は格子内sample indexを明示する。
`--starts` はseed文字列→完全vector/SHAのJSONで、生成・clip・補充はしない。
終了コード0=開発完走＋solver収束、4=照合済み予算切れ／solver未収束、
2=unknown/入力不正/保存障害STOP、3=production未認可。
いずれも正式RF認定ではなく、G0–G5未承認・dense/全帯域独立MNA/保存監査は未実施。
[契約・再現コマンド・限定証拠](diagnostics/issue321_development_cli.md)を参照。

開発専用 `--storage-mode window100` は別形式の100 forward予約・チェックポイントを明示opt-inする。
出力は既存ディレクトリの下の**未存在・Git管理外・永続**パスを指定し、system tmpやcheckoutは拒否する。
中断時は未確定枠の結果が失われ得るため、親のunknown予約を保持し、自動再開しない。
通常は全search履歴を保存せず、科学順位bestと候補・検証証拠を保存する。各forwardのcompact履歴は
`--debug-forward-history` を併用した場合のみ保存し、JobSpecに凍結する。失われた履歴は復元できない。
旧raw・formal Campaignとは互換ではなく、EXPやRF認定ではない。
[保存・費用・readback契約と模擬計測](diagnostics/issue369_forward_window.md)を参照。

## 廃止済み旧探索入口

Issue #343 D2で `run_phase2_shared.py` / `run_phase2_one_start.py`、旧実験runner・
旧prepare/診断入口を撤去した。過去の診断記録やEXP原本に残るコマンドは歴史的記述で、
現行の実行手順ではない。旧schema計画とIssue #250準備の元commit・元パスは
[履歴索引](../archive/issue343/README.md)を参照し、`git show <元commit>:<元パス>`で取得する。
旧Pythonコピーは現行treeにない。現役の実行・保存は
[Campaign操作ガイド](campaign_workflow.md)を使用する。

以下のIssue別API・探索案は当時の限定記録であり、旧探索実行入口は廃止済み。
Issue #343 D3で `multistart`、`SampledEpigraph`、旧SLSQP・候補・post-searchの
APIも撤去した。以下の旧API呼出例は歴史的記述であり実行できない。
現役Campaignの実行契約や本番実行許可を意味しない。

## Issue #245 A：Sobol RF選別（明示opt-in）

`generate_starts(..., selection='rf_pareto', max_initial_samples=952)` は
RF-T008/coarse2で既存16点blockを評価し、nominal/検証済warm＋F/V非劣性・正規化vector多様性で2本を選ぶ。
既定出力は不変更。全候補/例外/費用を `selection_report`、途中停止を
`StartSelectionError.report` に保持する。[API・限定診断・未実施事項](diagnostics/issue245_start_selection.md)参照。
本番探索、17点/1001点適合の代用は提供しない。
Stage Bの `candidate_pool='design_prototype'` は純直列L＋port-shunt IC 1組だけの限定仮説。
実固定S2Pでは適用不能で停止したため、有効性未確認のprototypeで止めている。
[API・仮定・mockと実診断の区別](diagnostics/issue245_designed_starts.md)参照。Stage Cは未実装。

## Issue #241：SciPy-DE最小接続（履歴）

[当時の診断](diagnostics/issue241_scipy_de_preview.md)はmock限定の履歴記録。
Issue #343 D3で旧 `scipy_de_preview` を撤去したため、記載のAPIは現役ではない。

## Issue #285：SLSQP v2 / Hybrid / SLP 同費用比較（計画のみ）

[4群の比較案・sample予算・実行前ブロッカー・G0〜G5](diagnostics/issue285_rf_comparison_plan.md)を参照。
未承認の計画であり、本番RF探索・EXP予約・科学的結果はない。

## Issue #284：RF-T008 → Hybrid/SLP 薄型接続（履歴）

[当時の診断](diagnostics/issue284_rf_pipeline_adapter.md)は開発fixtureとmock中心の履歴記録。
Issue #343 D3で旧 `rf_pipeline_adapter` を撤去したため、記載のAPIは現役ではない。

## Issue #239：optimizer比較契約・RFコスト計測（本番EXPなし）

[診断と未実行比較計画](diagnostics/issue239_optimizer_comparison.md)を参照。
`scipy_slsqp_stage(..., cost_meter=EvaluationCost())` はopt-inで実forward/sample数と
solver callback数・CPU/wallを分離し、既定探索・RF計算・v2予算は変えない。
`lpf.phase2_models.optimizer_comparison.PhysicalComparison` は物理xだけのforward-only API案。
strict30、max/sum違反とILの比較、部品/box/SPD/role拒否を軽量検査する。
DE/L-SHADE本番runner・L-SHADE本体・新EXP/数値予算の承認は含まない。

## Issue #235：SLSQP座標正規化（明示opt-in、本番EXPなし）

[診断・実装差分・9B-2提案](diagnostics/issue235_scaling.md)を参照。
`partial(scipy_slsqp_stage, coordinates="normalized")` は既存C1/C2のstage内だけで
有限boxを正規化する。完全物理vector・tのdB・RF制約・v2予算・検証ゲートは維持し、
従来の既定経路は変更しない。差分幅は比較用に明示指定可能だが、新標準の採用や
実験で未実証の収束改善を意味しない。保存済み9初期値の診断再現には完全evidence checkoutが必要。

## Issue #231：多start準備・mock比較（本番EXPなし）

`lpf.phase2_models.multistart` は既存1-start driverとは別の**synthetic専用**経路。
`generate_starts(SampledEpigraph(circuit, 2), nominal_vector, seed=23)` で、
同一schema/接続の設計値1本＋scrambled Sobol 2本を順序固定で返す。
Sobolは16点の固定blockを一度だけ検査し、合法な異なる3本を確保できなければ理由付き停止。
open lower boundにepsilonを足すことも、設計値の自動clipも行わない。
Q・全6設定Cv・IC固定C併設・signed k・全L行列SPD・接続roleは既存policy/APIで検査する。
各startは完全vector、seed、生成法、Sobol index、RF/definition/schema/vector SHA、C1記録を保持。
互換warm startは `warm_checkpoint` と期待するファイル `warm_sha256` を両方指定した場合だけ
設計値を置換する。JSONの `policy_id/policy_sha256/definition_sha256/parameter_schema/vector/vector_sha256`
を照合する（既存 `CandidateRecord` の対応列を利用可能）。別接続の単純射影は行わない。
歴史的checkpointをこの形式へ遡及書換えしない。

`run_multistart_preview(circuit, generated, temp_checkpoint, optimize_stage=mock,
historical_benchmarks=benchmarks, max_new_starts=None)` は既存 `run_synthetic` と
`run_c1_staged` を使用し、coarse2/fine3点・v2予算を不変更でdispatchする。
checkpointはリポジトリ外のsystem temp限定。既存rawの読戻し、中断marker、callback失敗後の
後続start停止を維持し、自動再試行しない。`max_new_starts` は正常なstart境界での停止のみ。
中断結果不明は例外とmarkerで保持し、成功・未開始へ丸めない。実SciPy接続・EXP exportは提供しない。

`unique_topologies` は構成リストのexact key重複だけを除去する（同一構成のstart/vectorは消さない）。
`two_axis_report` は既存CandidateRecordの再検査/厳密30dB判定/Pareto群を流用し、収束・部品/box/role/SPD・
IL/H2/H3・面積fraction・実効SHA・格子・検証深度を別列で保持する。
`finite_grid_eligible` は有限格子適合の意味のみ。境界直下値も丸めや許容誤差でPASSにしない。
syntheticと実SLSQPの比較群は混在しない。診断候補の理由・値も残し、RF認定・正式Paretoへ昇格しない。
`historical_benchmarks` は必須で、source、policy_id/SHA、objective、reference_planes、grid、validationと
保存済み数値を渡す。同一条件以外は拒否し、歴史的1001点値は常時**外部参照**として表示するだけで粗格子と順位付けしない。
完全checkoutでは `data/pareto_snapshots/rf_t008_exp062_exp063_exp064_cross_pr_20261020.json` の
`observed_nondominated` を出典SHA・manifest条件/格子/深度とともに使えるが、snapshot中の過去のDraft状態は
当時の記録であり現在の状態へ書き換えない。必要な履歴を確認せず比較PASSを主張しない。

`intermediate_scan(circuit, vector)` は既存forward evaluatorによる6設定/28個別区間×17点のread-only診断。
構成/値/入力/ソースSHAを保持し、CandidateRecordの1/2/3点制約は変更しない。
SPD/部品検査と、未実施の最終1001点・独立MNA84点・電力収支/受動性の `not_run` は別。
同じ端点で歴史値と一致してもdense再実行や連続帯域保証を意味しない。

### 次回本番の予算案（未承認・未実行）

RF-T008 rev3 / full_lpf、面積<=4の3L0GJM・3L1GJM・4L0GJMを提案対象とし、
Piの回路理論案＋既存TopologySpaceで多様性を確保する。20構成の固定列挙を要求しない。
Stage A 20構成×3start=60 → Stage B 上位5構成×**追加**5=25 →
Stage C 上位2構成×**追加**8=16、最大101start・各最大4stage、総最大404stage。
各stage粗500/精280を絶対上限とする現行v2回復規則以外は増額しない。
選別は厳密適合→面積/ILの同条件非劣性、構造多様性、異なるstartでの再現性を重視し、ILだけで選ばない。
実際の予算・選定規則・停止条件は**別Issueでユーザー意思決定後**に固定する。

本番への接続にはG0最新main事前予約、G1完全checkout/remote main SHA・科学入力・ソース/環境・
start別完全vector/seed/格子/選別/予測容量の照合、G2各start原子的raw/中断保存、
G3/G4候補ゼロ・失敗・未開始も含む証拠のGit byte読戻し/遠隔照合/保存監査が必要。
これらを省く本番multistart driverは本Issueに存在しない。kill/STOP/timeout/不一致/保存失敗で停止し、
rawを保持。新EXP・実探索・独立MNA大規模再実行・Phase 3は未実施。

数値余裕の調査：`SampledEpigraph.mandatory_stop_db` はpolicyの正式30dBを直接読み、
`residuals` は `IL - mandatory_stop_db`、`scipy_slsqp_stage` はこの残差を直接制約化している。
内部30.005dBは境界直下のstrict FAILを減らす可能性があるが探索条件変更であり、ここでは不変更。
別Issue案：評価用30dBと探索用guardを明示分離し、owner判断後、同一予算・同一初期値で
strict適合率/ILの影響を比較する（歴史的guard使用値と無guard値を混同しない）。

### 複数回路研究の次回Issueで固定するもの

1. ChatGPT回路案＋有限列挙から候補を提案し、事前selectionと条件を固定する。
   候補総数・条件別件数、各stage予算（標準v2）、seed、完全vector、格子、容量、停止条件、
   比較可能な証拠深度を次回実EXP Issueに記載する。この実装自体は実験実行許可ではない。
2. **1回路・1 start・1 EXP**。完全checkoutの最新mainで候補ごとにG0正式予約を確定し、
   G1 planned manifest/storageをmainへ統合する。実行ソース・環境・入力SHAの一致を確認してから、
   Issueスコープとユーザー起動指示に従ってG2実SciPyを呼ぶ。バッチ／自動次候補実行は提供しない。
3. G3/G4で候補ゼロ・失敗・未収束も含めGitHubへ証拠保存する。既存raw、入力／環境／ソース不一致、
   非法構造、STOP、timeout、例外、容量／readback／audit失敗時は停止・証拠保持し、自動再試行しない。
4. 保存済みIL/H2/H3、部品／box違反、数値失敗、面積、回路多様性からPi Codeが次の構成を提案できる。
   **次EXPは別途定義・条件を固定してから起動**し、実験途中のdefinition／制約／生rawを書き換えない。
   比較は同一条件ID・実効SHA・参照面・格子・検証深度内だけとし、T005群とT008群を混合しない。

# Pi Codeの通常作業範囲

Piの通常作業は `project/`・`rf/`・`src/`・`scripts/`・`tests/`・`.github/` とリポジトリ直下ファイルで行う。
`docs/`・`data/`・`experiments/` は通常ローカルに取得しない。過去のEXP再検証・全研究証拠の監査は、これらを明示的に取得した**別の完全検証環境**で行う。

```bash
git clone --filter=blob:none --depth=1 --sparse https://github.com/miyabimm/reconfigurable-rf-lpf-research.git
cd reconfigurable-rf-lpf-research
git sparse-checkout set --cone project rf src scripts tests .github
```

- 現行の正式・試験RF入力は `rf/constraints/`、全28区間は `rf/bands.csv`、固定S2Pは `rf/parasitics/`。
- `rf/constraints/registry.json` の `active_formal_id` が現行正式版。承認済みJSONは**上書きしない**。新正式条件は所有者承認後に新IDとして追加し、active指定を変更する。trialは自動昇格させない。
- 不変の旧RF JSON内の `data/...` は**保存時の論理パス**であり、`src/lpf/constraint_versions.py` が新 `rf/` 実体へ解決する。JSON内容・実効SHA・S2P SHAは維持する。ファイル欠落やSHA不一致時は失敗させる。
- 各EXPの原manifest、重要証拠、番号台帳は従来の `experiments/`・`data/` に保全する。通常のPi sparse環境で新EXPの番号予約・保存監査が可能とはみなさない。着手は[運用正本](instructions.md)のIssueスコープとユーザーのPi Code起動指示に従い、完全checkoutでG0/G1を満たす（追加の二重承認は不要）。
- Piの最低限の作業ツリーテストは `.github/workflows/pi-sparse-rf.yml`、全履歴・保存監査は通常の完全CI／個別実行とする。CI PASSは新RF性能の科学的保証ではない。

## 共通YAML CLI（コード検証と本番実験は別）

`scripts/run_phase2_shared.py` の既存4モードは維持し、次を明示的に追加する。

```bash
uv run --frozen python scripts/run_phase2_shared.py plan --config project/experiments/issue250.yaml
# 以下は別工程のG0/G1と実験Issueの起動指示が必要。コードレビューでは実行しない。
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1
uv run --frozen python scripts/run_phase2_shared.py run --config project/experiments/issue250.yaml --experiment-id EXP-NNN --phase pilot
uv run --frozen python scripts/run_phase2_shared.py run --config project/experiments/issue250.yaml --experiment-id EXP-NNN --phase remaining
# 実験Issueで予定した検証証拠も揃え、curated diff確認後にGit保存を確定（push/削除なし）。
uv run --frozen python scripts/run_phase2_shared.py finalize --experiment-id EXP-NNN
```

- `plan` はread-only。SafeLoaderで未知・重複キー、未対応schema、RF/definition/vector/SHA、
  box/role/SPD、seed/比較群・logical→actual・予算を照合し、既存manifestの
  `search_scope.input_source` / `input_source_sha256` に入れる凍結対象を標準出力へ返す。
  `plan.sha256` はprepared JSONの `input_source` から `wall_seconds` / `cpu_seconds` だけを
  再帰除外したcanonical SHA。YAML自体のcanonical SHA、完全実行vector/C1 SHA、群別screen費用も凍結する。
  YAMLに部品bounds、S2P、solver maxiterを重複定義しない。
- Issue250例はPR #251で取得済みのローカルprepared入力を、**追加RF計算なし**で時間非依存に
  正規化した `results/issue250/frozen-plan.json`（SHAはYAMLに固定）を参照する。
  このファイルはG1前のread-only `plan` に必要（欠落時は停止）。完全環境で準備入力を確保し、
  再計算時のSHA差をレビューしてからG1へ進む。既存準備原本とplan SHAは書換えない。
  G1 manifestには完全vector・完全C1 seed_recordとそのSHA・比較群・screen費用を保存する。
  G1後の `run` はYAMLとGit保存済み実行入力だけを読み、ローカル準備planを一切開かない。
  新しい完全checkoutでもpilot/remainingの入力を復元でき、既存C1 APIの実行前replayで
  seed_recordの数値も照合する。未確定の実行結果までG1から復元できるという意味ではなく、
  結果rawの喪失や途中不明は引き続きfail-closedで自動再計算しない。
  全poolの候補・除外理由などの詳細screen診断はG1ではSHA参照のみで、完全保全済みとはしない。
  必要なscreen診断のA/B分類・保全と容量確認は#250のG1工程で行い、無条件に1.8MBを複製しない。
  保存容量例外や証拠分類が必要なら既存ポリシーでSTOPする。
- `run` は完全checkout・最新remote mainのG0、main上planned manifest/storageの実byte読戻し、
  実行ソース/環境/全入力の一致を必須とする。storage選別はYAMLのtop Kと `retain=["pareto"]`、
  ruleに全除外・失敗診断保持を明記し、容量を事前見積もりする。追加owner認証は要求しない。
- 同一EXPの固有startを既存v2へ一度ずつ渡す。pilotに共通nominalと対象seedが参照する固有startを含め、
  remainingとの重複は計算しない。pilot終了時にも既存manifest/storage/summaryへ保存・監査する。
  remainingは明示的な別呼出しとpilot保存監査PASSを要し、自動で次phaseへ進まない。
  保存完了済みphaseの再指定はG1/raw/保存監査の静的照合後にno-opで返し、RF forward・費用加算・
  raw/summary/manifest/storage/checkpointの書換えをしない。RF再検査はphase保存処理の計画内費用であり、
  操作上の再読込では実施しない。
- start前markerとstage snapshotは原子的な `results/EXP-NNN/run.json` に保存。
  確定結果だけskipし、途中不明・STOP・システム中断・保存/provenance障害は全体STOP、raw保持。
  status4/8、数値例外、`budget_exhausted` は個別結果。v2以外の救済はしない。
  操作はWSL/Linuxの単一プロセス・直列のみ（EXP単位の排他lock、並列workerなし）。
  pilot〜remaining中は実行checkoutのHEAD/ソース/環境を保持し、Git確定は別のfinalize工程で行う。
  確定済みGit証拠はrunで再更新しない。
- optimization（seed replay/solver/stage観測を同一sample上限へ算入）、screen、候補再検査の
  forward/sample費用を分離する。73論理参照を58固有試行へ水増ししない。
  各方式/seedの論理IDと共有actual結果参照を保存し、A/B paired解析に使える。
- 17点/dense1001/独立MNA・power・独立SPDは別証拠で `not_run`。このCLIはそれらを起動しない。
  自動候補昇格、Git push、raw削除はない。Issue #250では予定した17点/1001点/MNA等の最終検証証拠を
  保存する前にfinalizeしない。finalize PASSはGit証拠保全だけであり、科学的検証PASSとは別判定。
  Issue #252のコードCIはIssue #250の本番実行やRF改善の証拠ではない。

### 探索ガードと探索後検証の開発中 API（Issue #267）

`run_c1_staged(..., search_guard=True)` と `run_c1_frequency_exchange(...,
search_guard=True)` は、policy必須値に0.005 dBを加えた探索目標をcoarse/fineと
周波数交換に渡す。guard有効時は `source_provenance` に `kind`、`git_head`、
`dirty_patch_sha256`、`input_source_sha256` が必要（型・形式を検査、自己申告の認証ではない）。
既定は旧条件のまま。必須30 dBと探索目標は別であり、探索ガードは最終PASS閾値や許容差ではない。

`post_search_validation.validate_post_search` は明示的な候補・予算・sinkに対する
17点→選別された1001点→独立MNAの開発中入口。rawを先にsinkへ渡し、policy・
トポロジー・vector・出典・帯域・部品・role・SPDを照合する。MNAサイズは
回路に依存する（4Lでは9×9）。有限格子や独立84点は連続帯域・物理実装の保証ではない。
`experiment_post_search` は、完全checkoutで既存G0/G1と候補checkpointを照合し、
G1の `post_search_validation` 計画によりguard・選別上限・各費用上限を固定する試作API。
検証前に選別集合とvector/SHAを凍結し、候補を明示的に一件ずつ実行、独立MNAの
途中点もrawへ原子的に保存する。中断・保存障害時はmarkerを残し、自動再試行しない。
候補別overlayと独立したnumerical/independent集約値を既存manifest/index/storageへ
接続し、既存の明示的finalize・Git byte読戻し・監査を別途必要とする。
対象は現在の共通実行経路で保存された候補に限る。コードレビューとCIによる共通実装の
検証は、実EXPにおけるG0〜G4運用・RF適合・実装可能性の検証とは独立である。
実EXP・本番探索・実回路dense1001・科学適合の検証は未実施であり、コードレビューや
sink・一時checkoutのテストは、実験実行の許可、実EXP保存監査、科学的PASSの代わりではない。

### 周波数交換の固定start対照（schema 3、Issue #263）

`project/experiments/issue263.yaml` は共通CLIの明示opt-in。2 source × baseline/exchangeを
`RF-T008 rev3/full_lpf`・物理座標・同一sample上限で凍結する。元vectorはEXP-114の17点記録、
raw最終stage、curatedの3者とSHAで照合するため、`plan` と `run` は完全evidence checkoutが必要。
`project/experiments/issue263-starts.json` は元物理vectorからcoarse2でtを再seedした準備入力で、
準備時の112 samplesは探索・最終検証ではない。`plan` はread-only、G1後の `run` はG1入力を使い、
準備planを再読込せず元証拠を静的照合する。baselineにも同じ17点開始・終端scanを課金する。

```bash
uv run --frozen python scripts/run_phase2_shared.py plan --config project/experiments/issue263.yaml
```

exchangeは各周で既存v2を使い、coarse/fineの両方に同じ追加点を反映する。内部scanと最終独立
17点判定は別であり、CLIはdense1001・独立MNA・電力・受動性を実行しない。低IL維持は同じ17点
開始値比+0.05dB以下の実験ラベルで、最適化制約ではない。失敗・中断はmarkerとrawを保持し再試行しない。
**コードDraft PRの独立レビュー・CI・main統合前にEXP予約や実SLSQPを開始しない。** その後もG0/G1、
pilot保存監査、remaining、最終独立検証、証拠保全は別工程。有限格子は連続周波数・実装保証ではない。

### 明示source × 座標対照（schema 2、Issue #259）

`project/experiments/issue259.yaml` は同じ共通CLIの明示opt-in入力。schema 1と既定solverは不変更。
`issue259-starts.json` はGit原本の最終物理vectorから現行 `SampledEpigraph.seed` で
再初期化した完全C1記録を保持し、負の旧tを継承しない。schema 2では各actualに
`source_ref: {path, sha256, vector_sha256}` と `coordinates: physical|normalized` を要求し、
同じseedの2 armはsource参照とC1記録が完全一致しなければ拒否する。
固有start identityは `(vector SHA, coordinates)`。common nominalや他armへの計算共有はない。
G1には完全vector・source参照・座標モードを保存し、G1以後はprepared planを開かず、
参照原本のSHAも静的照合する（完全checkout必須）。pilot/remaining・原子保存・費用上限は既存経路を再利用する。
例外はschema 2ではmarkerを保持して全体STOP（sample capの `budget_exhausted` は区別）。

```bash
uv run --frozen python scripts/run_phase2_shared.py plan --config project/experiments/issue259.yaml
```

元2候補のread-only dense診断は `project/diagnostics/issue259-source-dense1001.json`。
これは新EXPのG0/G1・最適化・最終独立検証の証拠ではない。コードの独立レビューとmain統合、
新EXPのmain予約・G1保存/遠隔読戻し後にだけ4 armを開始する。正規化は物理的な差分幅も変えるため、
純粋な座標変換だけの因果効果とは解釈しない。17点/1001点/独立MNAは本番後の別工程のまま。

## 限定1-start driver（RF-T005 / RF-T008 rev3・合法3L/4L）

`scripts/run_phase2_shared.py` の `prepare_one_start` / `one_start_gate` は引き続きread-only。
実験Issueの具体的スコープとユーザーの起動指示があるときだけ、別関数
`scripts.run_phase2_one_start.run_one_start(root, experiment_id, **one_start_args)` を明示的に呼ぶ。
`one_start_args` は `prepare_one_start` と同一のG0/G1・回路・完全vector・seed・v2予算・格子引数。
全検査後に既存 `run_c1_staged(..., optimize_stage=scipy_slsqp_stage)` を1 startだけ実行する。
回路は既存 `TopologySpace` / `enumerate_topologies` の候補または明示的な
`CircuitDefinition` を使い、条件別 `build_nominal_circuit` の合法性検査と完全なplanned入力照合を通す。
RF-T005とRF-T008 rev3だけを実driverで許可し、T007（共通モデルには残す）・未知trial・F003/T006、
異なるdefinition/vector/policy SHAの混同、一般multistart、独自予算は拒否する。
T008のIC固定Cは設定共通・Q60、可変Cは6設定・Q35の別部品として同端子に保持する。
Cvar=0でも固定Cは残り、容量合算や単一Qへの置換はしない。

- 完全checkoutの予約済みplanned manifestと、既存保存形式のplanned storage recordが必要。
  選別は事前に `top_k=0, retain=["pareto"]` とし、ruleでchecked Pareto選別と全除外診断の保持を明記し、容量を見積もる。
- 格子は各不連続区間の1/2/3点**診断限定**。研究上の評価条件と主張の範囲は後続実験Issueで固定する。
- 任意の `timeout_seconds` はstage境界での協調停止でありSciPy内部を強制停止しない。
  `results/EXP-NNN/STOP`、例外、KeyboardInterruptでも別startへ自動再試行しない。
  外部killでは直前の原子的raw snapshotを残す。既存rawがあれば再実行を拒否し、人手で調査する。
- rawと各stage記録はGit管理外 `results/EXP-NNN/run.json` に、選別候補／全除外理由は既存EXP形式へ保存する。
  保存diff確認後、`finalize_one_start(root, experiment_id)` を**別途明示的に**呼ぶと、そのEXPのみをcommit、
  実HEAD byte読戻し、storage record確定commit、既存finalize/auditを行う。pushやraw削除は行わない。
  未開始・未分類partial・読戻し／容量監査失敗は `preservation_incomplete` のままrawを保持する。
- Git保存PASSはRF科学PASSではない。独立MNA/power/dense/物理/連続帯域は `not_run`、候補昇格は禁止。
  `optimize_stage` の注入は隔離テスト用で、実SciPyとは異なる実行種別を記録する。実験実行はコードレビューとは別判断。

## Issue #250：D/A/B比較の実行前準備（独立レビュー待ち）

`scripts/prepare_issue250_comparison.py --output results/issue250/preparation.json` は
完全checkout・最新remote mainを検査し、EXP-062面積6の固定4L/3GJM回路を枝順・signed k順まで
保持して構築する。過去checkpoint/manifest/MNA原本SHAを照合し、1001点forwardの互換性と
84点独立branch-current MNA・電力・受動性をread-onlyで確認してから、bounds中点＋k=0の
共通nominalとseed 23〜34のD/A/B開始点を生成する。nominalはcheckpoint値を使わない。
出力は候補pool/選別理由・全vector/SHA・実消費費用・論理73件と重複除外後の計算対応表を含む。
`results/`内の新規ファイルだけに原子的に保存する。過去EXPは変更しない。

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  uv run --frozen python scripts/prepare_issue250_comparison.py \
  --output results/issue250/preparation.json
```

`run_c1_staged(..., cost_meter=SampleBudgetCost(1_500_000))` は1 startのseed replay、
ソルバー、段階後のforward観測、v2回復の全てを共通sample上限へ算入する。
次のforward全体が入らない場合は入口前に停止し、`budget_exhausted`、消費費用、既存段階の
入出力/statusを保存する。solver nfevによる代用や新しいRF guardはない。
既定のmeterなし経路は不変更。stage別費用は差分、start費用はreplayを含む累積であり、
SciPy status内のmeter snapshot（累積）を合算しない。

**これは実行前の独立PR範囲でありIssue #250全体の完了ではない。** EXP番号予約、厳格manifest/
storage plannedのGit保存と遠隔readback、独立レビュー、再開可能な本番反復配線、pilot監査、
17点→上位dense→独立検証・比較表・G3/G4は未実施。準備ファイルはG0/G1 PASSではなく、
既存one-start driverへmulti-startと偽装して渡してはならない。本番計算は開始しない。

## Issue #245 A：Sobol RF選別（明示opt-in）

`generate_starts(..., selection='rf_pareto', max_initial_samples=952)` は
RF-T008/coarse2で既存16点blockを評価し、nominal/検証済warm＋F/V非劣性・正規化vector多様性で2本を選ぶ。
既定出力は不変更。全候補/例外/費用を `selection_report`、途中停止を
`StartSelectionError.report` に保持する。[API・限定診断・未実施事項](diagnostics/issue245_start_selection.md)参照。
本番探索、17点/1001点適合の代用は提供しない。
Stage Bの `candidate_pool='design_prototype'` は純直列L＋port-shunt IC 1組だけの限定仮説。
実固定S2Pでは適用不能で停止したため、有効性未確認のprototypeで止めている。
[API・仮定・mockと実診断の区別](diagnostics/issue245_designed_starts.md)参照。Stage Cは未実装。

## Issue #241：SciPy-DE最小接続（mockのみ）

[API・計測・本番接続ブロッカー](diagnostics/issue241_scipy_de_preview.md)を参照。
`generate_starts(..., count=N, cost_meter=meter)` は既存16点Sobol blockを再利用し、
既定3-startを維持する。`scipy_de_preview.run_de_preview` は公開SciPy制約APIを
mock forwardで検査する小さなadapter。初期化も含むsample予算・中断時メーター/bestを保持し、
物理不正proposalはRFスコアを作らずfail-closed停止する。本番runner/実RF探索は未提供。

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
当時の記録であり現在の状態へ書き換えない。Pi sparse環境では履歴取得なしに比較PASSを主張しない。

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

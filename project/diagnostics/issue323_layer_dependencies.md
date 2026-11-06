# Issue #323 — 現役3層への依存収束（PR #324）

## 現在の判定と範囲

起点main: `81442ab9416d7cfe3e06c5a6c58587cab813c935`。
ブランチ: `issue-323-layer-dependencies`。
2026-11-06更新のIssue #323／PR追加指示に従い、**旧API互換・返却dict同値はDoDから除外**。
A/B/C-1/C-3を維持し、C-2は旧API修理でなく**現役schema2からの隔離**として実装した。
最終HEAD・同一HEADでの実測・CI・source SHAは[Draft PR #324](https://github.com/miyabimm/reconfigurable-rf-lpf-research/pull/324)の最新記録を参照。
独立再レビュー待ち。マージ・Issue close・次工程移行は実施しない。

## 変更

|対象|実装|
|---|---|
|A: 型・構造・role|`topology_management`が唯一の実体。現役CLI、search、rf_core、共通kernel/MNAから直接参照|
|B: 設計合法性|`search.component_constraints.validate_values`が唯一の現役厳密値域・role/Q・設計SPD窓口。`build_rf_model`のschema/topologyで構造を検査し、追加RF forwardなし|
|C-1: 宣言|`policy_schema`に純粋JSON宣言検査。性能コンパイル・区間採点はsearch|
|C-2: 旧API隔離|`search.problem.build`を削除し、旧schema1 builderを`search._legacy_schema1`へ移設。旧loader/run/execute_jobの関数内からのみimport。schema2 developは旧API/adapter/旧型re-exportをimportも呼出もしない|
|C-3: 独立MNA|`branch_mna`はtopology/schemaのみを検査し、具体的RFModel/NominalCircuit非依存。数値stamp不変|

旧API維持のための新value_constraints、Protocol、DI、共有boxは追加していない。
L/C枝順序・向き、符号付きk、全6設定、定数寄生/IC-fixed区別、外部S2P、数値kernelは変更していない。

## 利用元の棚卸しと残存理由

`src/`、`scripts/`、`tests/`、`.github/workflows/{audit,pi-sparse-rf}.yml`を検索して分類した。
旧コードの全面削除を目的化せず、次の明示的な非現役集合を残す。科学検査を旧APIと一緒に削除していない。

|対象|現役schema2／共通kernelからの利用|残るcaller・扱い|
|---|---|---|
|`NominalCircuit` / `build_nominal_circuit`|なし（実CLIの禁止importテストで確認）|`phase2_models/{sampled_epigraph,experiment_config,candidate_records,limited_candidate_evidence,topology_enumeration,vector_migration}`、`scripts/{run_phase2_shared,run_phase2_one_start,prepare_issue250_comparison}`、旧API/探索の専用tests。後続削除対象|
|`PolicyBoundRFT005T007Circuit` / `PolicyBoundRFT008Circuit`|なし|旧`api`と各wrapper専用tests。許容差を修理せず隔離|
|`phase2_models.problem_seed` / `circuit_box`|なし|旧sampled_epigraph、multistart、staged/normalized_epigraph、candidate_records、synthetic/experiment/post_search系、旧CLIと`diagnose_phase2_scaling`、`prepare_issue250_comparison`、旧tests。旧探索一式の削除時に整理|
|旧`search.problem.build`|削除|移設先`_legacy_schema1.build`を旧`plan.load`、`runner.run`、`worker.execute_job`と`test_rf_search`のみ使用|
|schema1 fixture/command|developから利用なし|`plan.load` / `runner.run` / `worker.execute_job`、CLI `preflight/run`、`project/experiments/rf_search_fixture.yaml`等の旧fixtureを明示的に非現役として保持。将来互換は保証しない|
|旧型re-export `phase2_models/{api,circuit_layout,role_audit}`|現役から利用なし|多数の旧tests・旧探索が利用。共通kernelの`coupled_lc`、`rft008_layout`、`branch_mna`、`independent_rf`は正本へ直接importに変更。re-export自体は後続削除対象で、型重複なし|
|`CoupledLCTopology` / `ParameterVectorSchema` / `nominal_inductors` / `branch_mna` / S2P|**現役**|削除不可。既存場所から再利用。共通kernelという分類であって旧APIではない|

両CIは旧API回帰をまだ含む（通常: public API、policy wrappers、problem_seed等／sparse: issue307、issue309、pi_sparse等の旧比較・fixture）。
そのため今回は旧APIメソッドや大量の専用testを一括削除しない。これらのPASSは旧互換を新たに約束するものではない。
新合法性の主検証`test_issue323_dependencies`は旧oracleを廃止し、RFModelのみの完全xから作る独立fixtureへ置換。
既存`test_issue309_rf_core`の旧数値比較は追加の科学回帰として残す（旧solver/順位/返却辞書の同値DoDではない）。

## 現役の実import/call図

```text
scripts/run_rf_search.py develop
  → schema2 load_preflight → Plan
  → run_development → freeze_development_job / execute_development_job
  → search.validate_values → rf_core.build_rf_model
  → FixedJobEvaluation / FixedStageEvaluation → rf_core RF forward
                                         └→ rf_core.independent → branch_mna

search ──→ rf_core ──→ 共通数値kernel (coupled_lc, nominal_parts,
  │            │                         nominal_inductors, rft008_layout,
  │            │                         _grid, independent_rf, branch_mna)
  └────────────┴──────────────→ topology_management
                                  （上位への依存ゼロ）
constraint_versions / nominal_inductors / search → policy_schema
search → optimizers （solverからRF層への参照なし）
```

`policy_schema.validate_performance`の`constraint_versions._validate_trial_additional_stopband`への既存遅延参照は純粋JSON検査で、import-time cycle/実行loopはない。

**非現役専用矢印（全リポジトリが非循環とは主張しない）**:

```text
schema1 plan.load / runner.run / worker.execute_job
  -- 関数内importのみ → search._legacy_schema1 → phase2_models.api
旧 phase2_models.api.validate_components → search.validate_values
旧 phase2_models.problem_seed.circuit_box → search.physical_bounds/validate_search_box
旧 phase2_models.api → PolicyBound wrappers / topology_management
旧 phase2_models.{circuit_layout,role_audit} → topology_management (同一型re-export)
```

AST検査は関数内importも含め、topology上向きゼロ、constraint_versions→searchゼロ、branch_mna→rf_coreゼロ、現役search/rf_core/CLI→旧api/wrapper/seedゼロを確認。
schema1への関数内参照は明示した例外。動的な実CLIテストはこれら旧facade・re-export・schema1 moduleのimportを禁止したfresh interpreterで**全schema2 developを完走**させる。

## RED → GREENと検証契約

実CLIの禁止import回帰を先に追加したところ、旧HEADで
`plan → problem → phase2_models.api`を検出してRED。
旧builder隔離とCLIの正本型参照後にGREEN（既存実RF 392 requested/completed、独立MNA 1 spot）。
共通kernelの旧re-export経由も禁止対象に追加した。

`test_issue323_dependencies`は次を新APIで検査:

- F003/T005/T006/T007/T008の全L/C/k座標上下端を受理、全座標の`np.nextafter`直外側を拒否。
  **5条件×4 k座標×上下=40拒否**を明示カウント。clip/許容差緩和なし。
- 完全vector・固定値の6設定不変、T007定数寄生、T008 IC-fixed、role/Q/count、設計SPD、RF SHA。
- 旧builder・NominalCircuit検査・両adapter検査・RF forwardをspyで禁止して新検査を実施。
- 旧型re-exportが同一実体であることと、残る非現役逆向きimport集合を明示。

既存RF coreテストは外部S2P込みS real/imag、IL/APL/InRL/OutRL、独立branch-current MNA、受動性/電力保存、6設定×28不連続区間を既存許容誤差で回帰。
T006追加18,006点は実施しない。既存端点spotのみ。
CLI回帰は親raw読戻し、requested/completed、unknown/予約・cap保持、未収束exit4、未認可production exit3を維持。

再現コマンド（結果はPRの同一HEAD実測参照）:

```bash
uv sync --frozen
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1
PYTHONPATH=tests uv run --frozen python -m unittest -v \
  test_issue323_dependencies test_issue309_rf_core test_issue321_development_cli
# 通常smoke: .github/workflows/audit.yml
# sparse: .github/workflows/pi-sparse-rf.yml の同一リスト、PI_SPARSE_RF=1。
# docs/data/experimentsが存在しない別worktreeで実行する。
```

## RF不変性・限界

RF JSON/bands/S2P/historyおよび実験原本に変更なし。現役effective SHA:

|ID|effective SHA256|
|---|---|
|RF-F003|`e12c42b11d12db7f20983c48cfa441ea96e362e533450d5862aa8a271c82af86`|
|RF-T005|`413c1f2979926dd8bc56fe6730603864f6c582e2a72ec3f7bb0ab1ba81a7becd`|
|RF-T006|`1d22e01d6da243bed24970de90a496e8f2d38b11bd5a5fae78e001398f647e1c`|
|RF-T007|`5452690de1c8590f1f7c306f76e41692e1885ac190da3cef050f1d926145c944`|
|RF-T008|`e682165c72d3a8b9f1384a2529f71bacfebfc9d17164d4af5af879e4a138b532`|

trial opt-in/approved fingerprint gate不変。ソースfingerprintは変更を反映する。
新EXP、本番/dense、大規模solver、T006追加18,006点、並列化は未実施。
G0–G5、全歴史監査、科学的RF合格、探索収束、連続周波数保証、EM/SRF/Q(f)/公差/実測の証明は主張しない。

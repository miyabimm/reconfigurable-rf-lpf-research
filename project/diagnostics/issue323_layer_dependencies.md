# Issue #323 — 依存整理の実装・未解消点

## 判定

**A/B実装済み、Cは部分実装。Issue全体の解消判定は保留。**
起点main: `81442ab9416d7cfe3e06c5a6c58587cab813c935`。
ブランチ: `issue-323-layer-dependencies`。最終HEAD・CI・PR URLはPRの実測記録を参照。
本番EXP、dense、T006追加18,006点、並列化、RF条件変更は実施していない。

## before → after

|対象|before|after|
|---|---|---|
|A: 型・構造・role実体|`phase2_models/{api,circuit_layout,role_audit}`|`topology_management/{definition,circuit_layout,role_audit}` が唯一の実体。旧pathは同一オブジェクトのre-export|
|B: `search.validate_values`|`build_nominal_circuit`→RF別adapter|`build_rf_model`の凍結schema/topology。値域/SPD設計判定は従来どおりsearch側。evaluator/forwardを呼ばない|
|C-1: JSON宣言検査|`constraint_versions`/`nominal_inductors`→search|`policy_schema.interval` / `validate_performance`を共有。既存のscalar宣言参照も同helperへ移動し、性能コンパイル・格子・区間採点はsearchに残す|
|C-2: 旧公開値検査|`NominalCircuit.validate_components`→search|**維持・未解消**。adapter委譲の差分検証がREDとなり置換を撤回|
|C-3: 独立MNA入力|`NominalCircuit` / `RFModel`具象型を参照|`CoupledLCTopology`と`ParameterVectorSchema`だけを検査。schemaでdecode/encode後、既存数値stampをそのまま使用|

L枝向き、符号付きk slot、dataclassフィールド順、端子/ノード、C枝順序、定数寄生/IC-fixed区別を変更していない。数値kernelの移動・複製なし。

## C-2 STOPの再現根拠

既存adapter `validate_candidate()` に単純委譲し、返却dictのrole/未検証状態を補完する案を試したところ、閉区間の直外側を受理した。
`test_issue307_constraints.make` の各条件で、k座標index 10/11/12/13それぞれの上下端直外側 (`np.nextafter`) が対象。
5条件×4座標×上下=**40件**。これは結合検査の既存許容差と、searchの厳密閉区間判定の差。
RF科学条件・既存許容差を独断で変更せず、旧公開APIから厳密検査への参照を残した。
`test_legacy_adapter_cannot_replace_exact_closed_box` が各条件の上端直外側を固定回帰として保持する。
新経路Bについては旧値検査との判定・返却dict同値が成立し、緩和していない。

C-2を解消するには、厳密部品合法性の単一所有を維持したまま旧APIをどう整理するか、独立レビューで決定が必要。
同じバリデータの複製、値域検査のRF coreへの逆流、adapterの無断の科学的意味変更では回避しない。

## 実import表（関数内遅延importも含む）

|import元|import先 / 名前|区分|
|---|---|---|
|`topology_management/*`|stdlib、numpy、同層のみ|search/rf_core/phase2_modelsへの依存ゼロ|
|`phase2_models/api`|`topology_management` CircuitDefinition/InductorTree/CapacitorPlacement|旧互換path|
|`phase2_models/{circuit_layout,role_audit}`|対応する`topology_management`モジュール|単純re-export|
|`rf_core/model`|`topology_management` CircuitDefinition/audit_variable_connection_roles|現役|
|`rf_core/independent`|`topology_management` audit_variable_connection_roles|現役|
|`search/{problem,worker}`|`topology_management` CircuitDefinition/InductorTree/CapacitorPlacement|schema1/2共通型|
|`search/component_constraints`|`rf_core.build_rf_model`、`policy_schema.interval`、既存coupled_lc/nominal_inductors|現役値検査|
|`constraint_versions`|`policy_schema.interval/validate_performance`|JSON宣言のみ|
|`phase2_models/nominal_inductors`|`policy_schema.interval`|逆参照除去|
|`search/performance`|`policy_schema.validate_performance/limit_db/harmonic_limit_db/additional_stopband`|旧公開名re-export|
|`phase2_models/{independent_scan,post_search_evidence,staged_optimization,post_search_validation,frequency_exchange_c1,sampled_epigraph,experiment_post_search,candidate_records}`|`policy_schema`のscalar宣言参照|searchへの参照除去|
|`policy_schema.validate_performance`|`constraint_versions._validate_trial_additional_stopband`|既存の純粋宣言検査への遅延参照。import-time cycle/実行loopなし|
|`phase2_models/branch_mna`|`coupled_lc` CircuitValues/CoupledLCTopology/ParameterVectorSchema|上位RFModel参照なし|
|**`phase2_models/api.validate_components`**|**`search.component_constraints.validate_values`**|**残存legacy互換矢印、C-2未解消**|
|**`phase2_models/problem_seed.circuit_box`**|**`search.component_constraints.physical_bounds/validate_search_box`**|**残存legacy探索box facade。二重bounds実装を避け維持**|
|`search/problem.build`|`phase2_models.api.build_nominal_circuit`|既存schema1 fixture互換。schema2現役経路からは呼ばない|

`test_import_boundaries_and_explicit_legacy_exception` はASTで上記legacy→search残存集合が `api.py` / `problem_seed.py` のみであることを検査する。残存を隠して全面PASSとはしない。

```text
現役schema2 search ──→ rf_core ──→ 既存数値kernel
          │                │              │
          └──────────→ topology_management ←┘
                  （値なし構造/role）
constraint_versions / nominal_inductors / search ──→ policy_schema

legacy例外（未解消）:
phase2_models.api ──→ search.validate_values
phase2_models.problem_seed ──→ search.physical_bounds/validate_search_box
schema1 search.problem.build ──→ legacy NominalCircuit
```

## 検証

段階A: layout/role/public API/RF core 24 tests PASS。
段階B: 新差分/closed bounds/RF core 14 tests PASS。
段階C（不適切なadapter置換撤回後）: 33 tests PASS。
通常smoke（audit.ymlの最初の9モジュール）: 45 tests PASS。
Pi sparse RF workflow相当: **歴史ディレクトリを含まない別worktree**で86 tests PASS。
最終HEADについては同じコマンド群を再実行し、実測をPRに記録する。

```bash
uv sync --frozen
# OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1
PYTHONPATH=tests uv run --frozen python -m unittest -v \
  test_circuit test_evaluate test_rf_f003_t005 \
  test_trial_pcb_pattern_c_t008 test_trial_ic_fixed_c_t008 test_trial_shunt_dtc \
  test_phase2_candidate_catalog test_exp047_legacy_manifest_adapter test_github_actions_yaml_keys
# Pi sparse側の全moduleリストは .github/workflows/pi-sparse-rf.yml と同一。
# PI_SPARSE_RF=1 を設定し、docs/data/experimentsが無いworktreeで実行する。
```

新差分テストは旧フローをテスト限定oracleとして保持し、F003/T005/T006/T007/T008の各座標上下端・直外側、完全vector、固定値不変、T007定数寄生、T008 IC-fixed不変、role、Q/count変更、SPD拒否を確認する。
旧builderへのspyとforwardへのspyで新値検査の独立性を確認する。
既存RF core回帰は外部S2P込みS実虚部・IL/APL/InRL/OutRLと独立branch-current MNA、受動性/電力収支、全28区間/6設定を含む。
T006の追加高密度検証は実施せず、matching_only小格子の開発契約を既存suiteで維持する。
`test_issue321_development_cli` は実RF **392 requested / 392 completed、独立MNA 1 spot** の小格子E2E、親raw照合、unknown/予約保持、exit4/production exit3を実測再確認する。
旧schema1 fixtureもPi sparse suite中の既存回帰に含む。

初回ローカル全suiteでは既存のsrc名前空間import回帰で1件REDとなり、`search.performance`のhelper importを相対importに修正した。
また通常作業treeにはdocs/data/experimentsが存在したため、`PI_SPARSE_RF=1`による不存在検査はそこで失敗した。これをPASSとせず、別sparse worktreeで再実行して確認した。

## RF不変性・限界

RF JSON/bands/S2P/historyバイトは変更なし。現役effective SHA:

|ID|effective SHA256|
|---|---|
|RF-F003|`e12c42b11d12db7f20983c48cfa441ea96e362e533450d5862aa8a271c82af86`|
|RF-T005|`413c1f2979926dd8bc56fe6730603864f6c582e2a72ec3f7bb0ab1ba81a7becd`|
|RF-T006|`1d22e01d6da243bed24970de90a496e8f2d38b11bd5a5fae78e001398f647e1c`|
|RF-T007|`5452690de1c8590f1f7c306f76e41692e1885ac190da3cef050f1d926145c944`|
|RF-T008|`e682165c72d3a8b9f1384a2529f71bacfebfc9d17164d4af5af879e4a138b532`|

trial opt-in/approved fingerprintは既存fail-closed contractを維持。ソースfingerprintは変更されるので旧値への一致を要求しない。
試験PASSは科学的RF合格、探索収束、G0–G5、本番実行承認、連続周波数保証、EM/SRF/Q(f)/公差/実測の証明ではない。
**独立レビューとC-2/legacy例外の方針確定までは、#323完了・次工程への移行を主張しない。**

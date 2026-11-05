# Issue #307 — Stage 1 RF制約移行・閉区間の共通化

対象Issue: https://github.com/miyabimm/reconfigurable-rf-lpf-research/issues/307  
Draft PR: https://github.com/miyabimm/reconfigurable-rf-lpf-research/pull/308  
作業開始時に確認したmain: `e1a1c883d449a9378eb9bf2e20c01d5e972afadd`  
実装commit: `0687814`、冗長なGJM限定判定の除去: `80599be8f126ae78a11e3aed76d614b9686186fe`。
最終handoff HEADはPR本文に記録する。

## 範囲とデータ保全

- #306 v1.0／#307で承認済みの同一ID移行。新EXP・本番探索・過去EXPの書換えは行っていない。Phase 2のまま。
- 先行commit `3b593ee` で旧formal/trial全JSONとregistryを原byteで保存済み。
  `rf/constraints/history/pre-issue-307/provenance.json` は元main SHA、ファイルSHA、全旧実効SHA、trial親子関係を保持する。
- 現役は正式 **RF-F003** と明示opt-inの **RF-T005/T006/T007/T008**。
  F001/F002/T001〜T004は履歴専用とし現役registry/loaderから退役。旧solverや旧IDの再実行互換は実装しない。
- 不変原則の一回限りの例外を `project/instructions.md`、`project/README.md`、`AGENTS.md`、registryに明記。
- 旧→新effective SHAの全桁対応は `rf/constraints/history/issue307-migration.json`。

| ID | 旧effective SHA（先頭12桁） | 新effective SHA（先頭12桁） |
|---|---|---|
| RF-F003 | f85710200ccd | e12c42b11d12 |
| RF-T005 | 59a451775ab4 | 413c1f297992 |
| RF-T006 | 54e86864b32b | 1d22e01d6da2 |
| RF-T007 | c6f0fc685464 | 5452690de1c8 |
| RF-T008 | 7de08611f8dd | e682165c72d3 |

## 実装

### JSON / loader

- 現役JSONは `schema_version: 2`。registry自体の構造はschema 1を継続。
- `evaluation.full_phase2` / `matching_only_phase2` を削除し、`evaluation.performance` の
  `objective`、`modes`、`limits.defaults/overrides`、`margins`、`additional_stopbands` に統一。
- F003のfull_lpf/matching_only、必須30 dB・公称35 dB・IL公称0.3 dBを区別。
  T006追加stopbandはperformance内へ移し、3–6 GHz、6設定、両端を含む1 MHz grid、20 dBを保存。
- 全探索対象L/C/kは `min/max/unit` の閉区間。GJM01下限0.1 pF、PCB_L下限0.01 nHのみ科学的数値変更。
  T007定数0.5 pF/Q40とT008設定共通IC固定C/Q60・可変C/Q35・接続別PCB-Cは別モデルのまま。
- 旧形式の互換パーサーや移行コンバーターを現役に残さない。旧形式・未知フィールド／性能規則・重複JSON key・不正SHAを拒否。
  trialの実効SHAもregistryで固定・検証する。
- 結合上限の既存scalarフィールドは独立SI検査用に残すが、新boundsとの一致をloaderが検査する。異なる値域を黙って使い分けない。

### 部品値検査 / 呼び出し元

- `src/lpf/search/component_constraints.py`:
  `physical_bounds(definition, schema, policy)`、`validate_values(definition, schema, x, policy)`、探索sub-box検査。
- 同じJSON由来boundsで完全x・finite・6設定・固定/IC/定数不変性、型/接続別容量を検査。
  既存の構造/Q/本数/配置builderと全L行列SPD検査を再利用する。LQP01/LQW04の未確定範囲を推測しない。
- `search/starts`と公開`NominalCircuit.validate_components`は共通値検査へ接続。
  新search経路の`open_lower`データを撤去。既存C1 boxは同じphysical boundsを用い、古いbox型のopen_lower属性は常に空。
- 旧seed入口も範囲外のclipを停止。明示jitterは別の操作であり、その記録は維持する。
  GJM=0のexploration例外や未立証series roleを部品PASSにする抜け道は設けない。
- `search/performance.py`は新宣言の検査と既存scalar呼び出し元用の要求値取得のみ。
  旧JSONを模したruntime policyや旧solver互換wrapperは作っていない。結果記録中のthreshold scalarは新performanceから導出する。
- 新RF forward、区間×指標compiler/順位、YAML可変grid/予算、全旧探索撤去は後続Issue。
  Stage 1では非空override/marginを**未対応として拒否**し、黙って無視しない。

## 実行した検査

`uv sync --frozen` 成功。Python 3.12 / frozen lock環境。
以下は通常の決定的software検査であり、新科学EXPではない。

### 主要回帰: 190件、189 PASS / 1 skip

環境: `OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 PYTHONPATH=src:tests`。
`uv run --frozen python -m unittest -v` に以下のmodulesを渡して実行（86.311秒）。

```text
test_issue307_history test_issue307_snapshot_equivalence test_issue307_constraints
test_constraint_versioning test_rf_f003_t005 test_rf_search test_pi_sparse_rf
test_phase2_branch_mna test_phase2_s2p_grid_cache test_phase2_independent_rf
test_phase2_rft005_t007_policy_circuit test_phase2_rft008_policy_circuit
test_trial_shunt_dtc test_trial_pcb_pattern_c_t008 test_trial_ic_fixed_c_t008
test_phase2_sampled_epigraph test_phase2_problem_seed test_phase2_circuit_layout
test_phase2_rft008_layout test_phase2_generic_coupled_lc test_phase2_public_circuit_api
test_phase2_connection_roles test_phase2_numeric_diagnostics test_phase2_zero_branch_projection
test_phase2_candidate_records test_phase2_normalized_epigraph test_phase2_generic_starts
test_lqp02_series test_lqp02_series_policy test_circuit test_evaluate
```

- 全現役ID・各座標の上下端と`nextafter`外側、GJM/PCB-L/HV/HQ/PCB-C/IC固定/6設定可変C/kの整合。
- 旧→新snapshot全内容の照合（許可された表現移行と2下限以外の脱落・変更を検出）。
- 全28不連続区間・6設定、両固定S2PのSHA/受動性、独立branch-current MNA・電力保存。
- 独立RF検査の観測最大IL差 `4.476419235288631e-13 dB`、電力残差 `5.833007687972014e-17`。
  これらは小規模既存fixtureの数値一致であり、新候補の科学的認定ではない。
- skipはローカル作業treeが非sparseのためのsparse専用テスト。下記の別sparse checkoutで実行した。

### 追加統合回帰

次の5 modules（62件）と`test_phase2_problem_seed`（14件）を同時再実行し、**76件PASS**（64.871秒）。

```text
test_phase2_staged_optimization test_phase2_frequency_exchange
test_phase2_post_search_validation test_phase2_rf_pipeline_adapter test_phase2_topology_enumeration
```

追加の冗長GJM判定除去後、`test_phase2_rft008_layout`と`test_phase2_rft008_policy_circuit`を再実行し、**17件PASS**。

### 実sparse checkout

実装commit `0687814`から別のローカルcloneを作り、cone sparseを
`project rf src scripts tests .github` に限定、`docs/data/experiments`不在で実行。
`PI_SPARSE_RF=1 PYTHONPATH=tests`でCI sparse指定の6 modules/test選択を実行し、**15件PASS、skipなし**（6.336秒）。
ソースの最終差分は上記GJM冗長判定の除去のみで、該当layout検査は別途再実行済み。

### Read-only preflight / 静的検査

```bash
uv run --frozen python scripts/run_rf_search.py preflight --config project/experiments/rf_search_fixture.yaml
git diff --check
```

両方PASS。preflight前後の`git status --porcelain=v1`を比較して変更なし。
plan SHA: `0f8ea261835139154cf145c93ef3c9d362599d18ae402f65471b56b0b8380fbd`。
`execution_authorized=false`。これは本番実行許可ではない。

## テスト変更の理由 / 未実施

- 旧開端・clip・GJMゼロexplorationを前提とする期待値を閉区間／範囲外拒否へ変更。
  未立証seriesを部品PASSとして残す期待は共通gateでの拒否へ変更し、独立MNA/RF/受動性検査は削除していない。
- 旧SHAを固定していた現役fixtureと決定的Sobol期待値は新bounds/新policy SHAへ更新。
  過去EXPのvector/manifest/順位/検証statusは更新しない。
- 全リポジトリdiscover、完全な研究証拠監査、全CI、旧ID/旧API/全歴史solverの回帰は**未実施**。
  歴史用scripts/testsの現役loaderによる旧ID再実行は互換保証しない。
- 実回路dense認定、新RFコアのS/APL/RL、EM、SRF、Q(f)、ばらつき・測定は未実施。
- Draft PRを維持し、全DoD・全回帰PASSやマージ承認とは扱わない。ChatGPT独立レビューとCI確認が必要。

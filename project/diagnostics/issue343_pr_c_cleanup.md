# Issue #343 PR-C — 構造正本・現役保存ゲートの旧caller分離

## 基点と範囲

引継ぎブランチ `issue-343-pr-c`、引継ぎHEAD `30b6bc1`。
着手時のremote mainはPR-B統合後 `f8481925c050d269370a2a2259c70c8baf0b2f09`。
mainの運用指示、#323依存棚卸し、#336統合差分（#338）、#341（#342）を再確認した。
新EXP、本番Campaign、予約、dense/大規模solver、RF条件・評価意味の変更は行わない。

本PRは**参照ゼロと確認できたre-exportだけを撤去**し、現役ゲートの旧runner依存を切る。
旧wrapper/旧optimizer一式の消滅、旧APIの再実行互換、Issue全体の最終DoD達成は主張しない。
下記の科学検査・保存/歴史callerが残る閉包を、テストごと削除して見かけ上参照ゼロにしない。

## 移動・削除

- `lpf/topology.py` → `topology_management/bridge.py`（構造検査、数値条件不変）。
- `phase2_models/topology_enumeration.py` の `labelled_trees` / `capacitor_choices`
  → `topology_management/enumeration.py`。旧nominal builder、Q、bounds、SPDは移管しない。
- `phase2_models/{circuit_layout,role_audit}.py` の純re-exportを削除。
  source/scripts/testsのcallerを既存の `topology_management` 正本へ変更。
- `run_phase2_shared.py` の `_complete_checkout` / `_fresh_main`
  → `search/checkout.py`。G0/G1とG5、残存旧callerは同一定義を使用。
- `run_phase2_one_start.py` の明示2-commit保存・post-search readback guard、
  `post_search_journal.py` の純粋な固定集合validation集約
  → `lpf/experiment_preservation.py`。Campaign G3/G4から旧runnerへのimportを除去。
  残存旧runnerは同じ保存実装を使用し、数値探索機能を新モジュールに持ち込まない。
- CI selectorの移動済みkernel/削除re-exportに対する古いpath登録を整理。
  共有保存はFULL、未登録の構造/kernelはFULL、delete/rename不明時FULLを維持。
  両workflowはこの単一selectorを使うため、workflow側の重複テストリストは追加しない。

## 現役依存図

```text
schema2 CLI → search Plan/Runner/Worker → search.validate_values → rf_core
                   │                                  │          │
Campaign G0/G1 → search.checkout                       └────┬─────┘
Campaign G3/G4 → experiment_preservation                    ↓
Campaign G5 → search.checkout                      topology_management
rf_core forward / 独立branch-current MNA ───────────────────┘
search → optimizers（solverからRFへ逆依存なし）
```

`experiment_preservation` はCampaign guardのため `search.preservation` を遅延参照する。
RF kernel・構造層への逆向き依存ではなく、保存層内の既存callback関係を維持する移動である。
旧post-search結果の集約も旧sampled_epigraph/APIをimportせず利用できる。

## 残存ファイルと理由（削除対象の依存閉包確認）

|残存集合|確認したcaller・理由|
|---|---|
|`phase2_models/api.py`, `rft005_t007_policy_circuit.py`, `rft008_policy_circuit.py`, `coupled_lc_evaluator.py`|科学検査 `test_issue307_constraints`、`test_issue309_rf_core` の旧forwardとの比較、role/Q/寄生/固定値/独立MNA回帰、および下記旧callerが参照。現役schema2/Campaignの実import経路から隔離。旧oracleを除くには、科学検査を別途移す必要があるため保持。|
|`problem_seed`, `sampled_epigraph`, `normalized_epigraph`, `staged_optimization`, `frequency_exchange*`, `optimizer_comparison`, `rf_pipeline_adapter`, `scipy_de_preview`|旧SLSQP・cost・epigraph/adapter回帰、旧post-searchの入力検査が参照。新solverとして移設・復元しない。|
|`candidate_records`, `candidate_audit`, `limited_candidate_evidence`, `post_search_{validation,evidence,journal}`, `experiment_post_search`|旧候補・保存済みsource照合・post-search証拠検査の閉包。validation集約のみを保存の単一正本へ移す。科学検査/保存機能を一緒に削除しない。|
|`experiment_{config,run}`, `synthetic_{plan,runner}`, `multistart`, `generic_starts`, `start_selection`, `designed_starts`, `evaluation_cost`|旧CLI/runnerと専用回帰の閉包。現役schema2 APIに昇格させない。|
|`phase2_models/topology_enumeration.py`, `vector_migration`|旧nominal生成・旧候補投影のcallerと専用検査。純構造ヘルパーだけを移管。|
|`phase2_models/{_grid,exp042,exp055,exp058_area3,exp058_area4,exp058_area4l_gjm,independent_scan}.py`|歴史モデル・保存source参照と科学的比較テスト。現役kernelの二重正本とは扱わない。|
|`lpf/variable_c_layouts.py`|保存済み `experiments/matching_limit/search_space.py` が現パスをimport。移設すると既存科学回帰がModuleNotFoundErrorとなることを確認し、移設案を取り消した。過去EXPファイルを書換えず、bridge検査のみ新正本を直接使用。|
|`lpf/coupling_layout.py`|旧matching/graph検査の値域・SPD・公差付き数値検査を含む。現役searchの厳密SPD/boundsとは異なり、topology層へ移すと数値責務が混入するため保持。新たな複製なし。|
|`scripts/{run_phase2_shared,run_phase2_one_start,prepare_issue250_comparison,diagnose_phase2_scaling}.py` 等の診断・歴史script|上記旧closureのcallerと、旧候補/保存source照合を保持。現役G0/G1/G3/G4はこれらをimportしない。過去EXPを一括削除/改変しない。|

通常CIの旧科学回帰登録は上記callerが実在するため維持する。削除済みschema1テストは復活しない。
完全な旧wrapper廃止は**未完**であり、この残存表を独立レビュー対象とする。

## 検証と再現

- RED: pure re-export不在およびCampaign保存の旧runner import禁止の2検査が失敗。
- GREEN: 同検査、fresh interpreterで旧 `phase2_models` / `scripts.run_phase2_*`
  を禁止する保存import検査を含め、短い回帰32件PASS。
- 実行中/最終実測とCI URLはDraft PR本文に記録する。途中timeoutはPASSに数えない。

```bash
uv sync --frozen
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1
PYTHONPATH=tests uv run --frozen python -m unittest \
  test_issue323_dependencies test_phase2_topology_enumeration \
  test_shared_variable_c_layouts test_ci_test_selection -q
uv run --frozen python scripts/audit_new_experiment_storage.py audit
CI_FULL=true uv run --frozen python scripts/select_ci_tests.py
# docs/data/experimentsのないsparse worktreeで:
CI_FULL=true uv run --frozen python scripts/select_ci_tests.py --sparse
```

正式RF-F003と明示opt-in RF-T005/T006/T007/T008を区別。
RF入力・registry・bands・S2P・history・過去EXP原本は差分なし。
effective SHAはmainの#323棚卸しに記載した値から不変で、PRで実読込確認する。
ソースfingerprintは新HEADから再計算し、旧fingerprintへ合わせない。
検証はソフトウェア回帰であり、RF合格・solver収束・連続帯域保証・物理実現性の認定ではない。

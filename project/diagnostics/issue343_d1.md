# Issue #343 D1 — 科学回帰・保存依存の現役API化

## 範囲

基点main `3df84132cb8f21ec97411a143d56f9272810faf4`、branch `issue-343-d1`。
Issue #343 の追加計画 D1 のみ。運用正本、#323依存棚卸し、#336/#338の
import-originゲートと#341/#342の選択CI、PR-C残存表を確認した。
本変更はテスト・固定期待値・説明のみ。production数値kernel/保存コードは変更しない。
D2〜D4の旧モジュール・入口削除、archive作成はまだ行わない。

## 置換と検査の対応

|対象|旧依存|置換・保持するアサーション|
|---|---|---|
|`test_issue307_constraints.make`|`phase2_models.api`/builder|構造正本と`rf_core.build_rf_model`。F003/明示trial T005〜T008の同一definition・中点完全vectorを保持|
|同閉区間テスト|旧`problem_seed.circuit_box`/`validate_components`|現役`physical_bounds`/`validate_search_box`/`validate_values`。全L/C/k上下端、nextafter直外拒否、縮小box・逆転box拒否。旧epigraphのt座標・旧wrapperへの二重委譲は新契約に含めない|
|`test_issue309_rf_core`|実行時の旧ABCD forward比較|変更前mainから凍結した旧ABCD IL、および現役S real/imag・IL/APL/InRL/OutRLの固定値と比較（絶対許容差1e-9、rtol=0）。schema/topology同一実装同士の比較は廃止し、入力definition/vector/格子/制約・入力SHAを照合|
|同独立MNA|旧fixtureによる間接import|現役モデルから独立branch-current MNA。forward stamp/cascade再使用禁止spyを保持。全6設定×全28個別区間の端点検証をT008だけから全5条件に拡張（各336点）。T006追加帯域は既存3/6 GHz端点のみ|
|`test_issue315_fixed_stage`|旧メソッドをpatchするためのimport|現役実評価・raw/予約/費用/selection/spot/読戻しをそのまま検査し、モジュール全体を旧import禁止下でも実行|
|`test_issue323_dependencies`|旧builder/adapter spy、旧script import|fresh interpreterで旧パッケージと旧scriptをimport禁止。307/309/311/315全体と現役合法性テスト（計31件）を実行。40 k直外拒否、6設定固定C/IC-fixed/定数寄生不変、role/Q/count/SPDは保持|
|現役Campaign保存|PR-Cで既に独立化済み|G0/G1/G5は`search.checkout`単一定義、G3/G4は`experiment_preservation`。既存の空集合not_run集約・旧import禁止を維持。G0〜G5・source/import-origin・Git byte読戻し・unknown/raw保持は`test_issue325_campaign_gates`既存17件で回帰|

旧scriptとcheckoutが同じ関数をre-exportすることは旧入口専用契約のため現役テストから除外した。
現役gatesとcheckoutの関数同一性は引き続き検査する。旧re-exportファイル不在はimportせずpathで検査。
現役依存図はPR-Cから不変:

```text
schema2 CLI → Plan → Runner/Worker → search.validate_values → rf_core
Campaign G0/G1/G5 → search.checkout                         ↓
Campaign G3/G4 → experiment_preservation       topology_management
rf_core forward / 独立branch-current MNA ──────────────────┘
```

## 固定期待値の出典・再現

`tests/fixtures/issue343_d1_rf_baseline.json` は変更前main上の
`test_issue307_constraints.make`（旧NominalCircuit）、`test_issue309_rf_core.grid`と
現役`build_rf_model`を使い、**編集前に取得**した。baseline commit、全definition、
全vector、frequency/setting/segment、effective SHA、bands/両S2P SHAを各caseへ保存。
生成後SHA256: `4df87e287fe1a7711b1ee159e79d385a5b9c4d6f3366956573122af9f252b059`。

再取得する場合は元commitの隔離worktreeで、5条件ごとに以下を実施する（通常CIで自動再生成しない）:

```python
p, d, old, _, x = make(cid)
x[10], x[13] = .03, -.04
x[-6*old.schema.n_variable:] = np.linspace(.2, 2.8, 6*old.schema.n_variable)
g = grid(p)
r = build_rf_model(d, p).evaluator(g).evaluate(x)
legacy_il = old.forward_evaluator(2).il(x)
np.testing.assert_allclose(r.il_db, legacy_il, atol=1e-9, rtol=0)
```

固定値は回帰用であり独立oracleではない。独立性の根拠は別stamp/枝電流MNAと解析既知値
（through/直列R/複素電力参照）で、既存の受動性・電力保存・零伝送検査も保持する。
有限端点格子のみで、RF合格・連続周波数保証・EM/SRF/Q(f)/公差/実測は認定しない。

## 実検証

```bash
uv sync --frozen
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1
PYTHONPATH=tests uv run --frozen python -m unittest \
  test_issue307_constraints test_issue309_rf_core \
  test_issue315_fixed_stage test_issue323_dependencies -q
CI_FULL=true uv run --frozen python scripts/select_ci_tests.py
# docs/data/experimentsが存在しない一時sparse worktreeで:
CI_FULL=true uv run --frozen python scripts/select_ci_tests.py --sparse
uv run --frozen python scripts/audit_new_experiment_storage.py audit
```

- RED: 元mainの307テストを旧import禁止finder下で読み込み、`lpf.phase2_models`で期待通り失敗。
- GREEN: 対象27件＋fresh interpreter内31件PASS。
- 通常FULL: PASS、既定opt-in実SciPy smoke 1件skip。選択CIは323経由で新しい307科学検査も実行。
- sparse: 完全checkoutでの試行は`docs/`存在の前提検査でFAIL（PASS扱いしない）。
  `/tmp/issue343-d1-sparse-worktree`（一時sparse worktree）のFULLはPASS。
  同一最終HEADの両GitHub CI URLはDraft PRへ記録する。
- 初回GitHub通常FULLは新診断文書の索引漏れでFAIL。`diagnostics/README.md`へ登録して修正。
  RF科学回帰の失敗ではないが、初回CI全体のPASSは主張しない。
- 保存audit: 既存checkoutでexit 0。これは本変更でEXPの科学結果・全歴史ソースを再監査した意味ではない。
- 最初のsparse試行は120秒timeoutで中断。残留した一時テストdefinition/planだけを確認して削除した。

## 残件・不変性

RF ID/effective SHAは`issue323_layer_dependencies.md`掲載の5値から不変。
registry/制約JSON/bands/S2P/history/data/experimentsの差分なし。
新EXP・正式Campaign・G0予約・dense/大規模探索は行わない。Git保存のテストは隔離fixtureのみ。

旧専用`test_phase2_*`/歴史callerはD2〜D4で整理するまで保持し、今回一括削除しない。
旧SHA固定の`FrozenConfigTests` 3件（20 dB診断、continuation構造参照、continuation dispatch）は
現行RF-T008と非同値であり、新条件に読み替えない。既存の歴史SHA skipを維持する。
通常FULLのboundary選択ではこの3件は対象外で、別途明示実行の結果をPRに記録する。
手動integration・過去EXP/source復元は未実施。Issue全体の最終DoDは未達、独立レビュー前にマージしない。

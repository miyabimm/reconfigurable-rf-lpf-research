# Issue #343 E1 — 旧matching専用テストの整理

基点 main `718c894a3c162130cdf1339d81dbbfcaec97e6b7`。E1はテストとCI選択のみ。旧root 2モジュールと履歴sourceは変更しない。

## 依存と処置

- `experiments/matching_limit/search_space.py` → `lpf.variable_c_layouts`、`coupling_layout.py` → `lpf.coupling_layout`。`enumerate_grounded`/`coverage_sampler`は前者、`p4_batch`は両facadeをimportし、`full_lpf`等も間接依存する。現役`run_rf_search.py`、`search`、`rf_core`、`topology_management`からの参照は見当たらない。全callerがゼロとは主張しない。
- 旧layout同一性・列挙・旧結合専用の `test_shared_variable_c_layouts.py`、`test_coupling_layout.py`、`test_p4_layout_pilot.py` を削除。selectorの前二者の登録を除去。削除・不明差分は引き続きFULL fallback。
- 混在 `test_shared_graph_core.py` の旧結合同一性と旧nominal結合だけを削除し、独立のgraph選別を保持。`test_search_space_extensions.py` の旧layout列挙・旧結合検査を除き、現役RF `build_rf_model`/`physical_bounds`、graph、旧設定構築と三手法検証を保持。`test_rf_f002_search.py` の列挙・coupling layout専用部分を除き、旧条件の設定構築・独立計算・boundsのテストコードを保持するが、RF-F002/T004は実行用loaderから撤退済みのため理由付きskip（以前も実行すると拒否される）。
- `test_p4_resume_integration.py`、`test_grounded_enumeration.py`、`test_coverage_sampler.py`、`test_node_area_selection.py`、`test_full_lpf.py`、`test_full_lpf_checkpoint_import.py`等はfacadeへ間接依存するが、再開・graph・checkpoint等の別契約があるため保持。旧matching専用コードの実行互換保証を追加したわけではない。

## 科学・保存の境界

現役の閉区間/直外・SPD・Q・6設定は `test_issue307_constraints.py`、`test_issue343_d3_science.py` 等、5条件×6設定×28個別区間端点、固定S2Pと独立branch-current MNAは `test_issue309_rf_core.py`、保存とG0–G5は `test_issue343_d2_preservation.py`、`test_issue325_campaign*.py` に残る。旧matchingのnominal/感度モードや列挙意味と現役の科学検証は同値ではなく、旧保証の撤去を新APIでの再現と呼ばない。

RF入力・履歴EXP原本を変更せず、E2のroot本体処置は未着手。テストの整理はRF合格、歴史EXP再現、連続周波数・物理実現性の保証ではない。

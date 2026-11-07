# Issue #343 D3 — 旧探索閉包の整理（作業中）

基点 main `0698a87925b30ccaf11531a5197a5dc611d3f681`。**D3は未完了**。
旧candidate_records、synthetic、epigraph、SLSQP、frequency exchange、multistart、
旧adapter/DEとその専用testを撤去。旧post-search evidence/validationは
[履歴資料](../../archive/issue343/README.md)へバイト不変で移動した。
旧候補再評価・旧solver順位互換は提供しない。

現役経路は `run_rf_search.py develop → search Plan/Runner/Worker →
search.component_constraints → rf_core → 独立branch-current MNA`、Campaignの
G0/G1/source origin及びG2–G5は `search` と `experiment_preservation` が所有する。
`test_issue323_dependencies` の旧import禁止検査、`test_issue343_d2_preservation` の
候補集合・overlay SHA・失敗/not_run分類、現役Worker/親Runner/Campaignのraw・停止・
readback検査、D1の5条件×6設定×28区間独立MNAと固定期待値は保持する。
旧post-searchの17/84/dense段階・再計算形式と、現役保存の状態集計は同値ではない。

## 残作業

`candidate_audit.py`、`limited_candidate_evidence.py`、`problem_seed.py`、
`topology_enumeration.py` は旧の独立scan・科学/構造testsから呼ばれるため未撤去。
既存の独立scan・実験vectorに対する検査と現役D1回帰の対応を明示し、必要な科学的
アサーションを現役APIへ移してから閉包を除去する。履歴証拠として必要な旧手法は
元blob・SHA・条件・対象と復元手順を記録して非import資料に隔離する。
`vector_migration.py` と旧RF wrapper・履歴modelはD4対象。Phase 2のまま。

RF条件・bands・S2P・history/EXP原本は変更しない。新EXP、本番Campaign、denseや
大規模solverは実行しない。ソフトウェアテストのPASSはRF合格や物理実現性を意味しない。

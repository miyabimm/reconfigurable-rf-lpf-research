# Issue #343 D2 — 旧実験入口の撤去

基点 `681dabee30a7804d63bacc3afa5932e320c1d11a`（D1統合main）。
#336のG1 import-origin／Worker前STOP（#338）と#341のCI selector（#342）を保持。
この変更はD2のみであり、D3/D4・Issue全体完了ではない。

後続の#362で隔離Pythonコピーは現行treeから削除。[履歴索引](../../archive/issue343/README.md)の元commit・元パスを `git show` で取得する。以下はD2当時の記録。

## 削除・隔離と現役依存

- 削除：`scripts/run_phase2_{shared,one_start}.py`、
  `phase2_models/{experiment_run,experiment_post_search}.py`。旧互換shimなし。
- 旧`experiment_config.py`、`prepare_issue250_comparison.py`、
  `diagnose_phase2_scaling.py`は履歴資料として
  `archive/issue343/`へ内容不変で移設。元blob、SHA-256、旧RF SHA、対象と復元方法は同README。
  archiveを現役APIやCIのimport元にしない。
- 現役依存は schema2 CLI → `search` Plan/Runner/Worker → `component_constraints` →
  `rf_core` → 構造正本；Campaign G0/G1/G5 → `search.checkout`、G3/G4 →
  `search.preservation` / `experiment_preservation`。旧runnerをimportしないことを
  fresh interpreterの旧import禁止科学・保存回帰とAST検査で保持。
- `phase2_models`の候補・最適化・post-search等はD3、旧RF wrapper・歴史モデル／
  root layoutはD4の残件。旧`project/diagnostics/`のコマンド記述は当時の記録。

## テストの対応

旧runner専用 `test_phase2_shared_entry.py` と旧SHA固定の手動
`test_phase2_continuation_integration.py` を撤去。旧packaging/dispatch固有の3件、
旧Issue250 plan identity 1件、旧continuation初期化1件をそれぞれの残存テストから除去。
科学的回帰はD1の `test_issue307_constraints` / `test_issue309_rf_core` / `test_issue311_performance`
（5条件・6設定・28区間・独立MNA等）と既存科学検査を維持。旧post-searchの格子、
独立検証、failed/not_run、固定集合aggregateのテストも維持する。

削除した旧runner包装テストの代わりに `test_issue343_d2_preservation.py` で現役
`experiment_preservation` の固定候補集合、overlayのSHA、未完了、manifest不一致、
index不整合、failed/not_runを直接検査する。現役Campaignの隔離Git fixture
`test_issue325_campaign_gates` はG0/G1、G2、G3/G4のraw保持・Git readback失敗、
unknown、G5拒否を検査する。旧post-search包装形式とschema2 Campaignが同義と主張しない。
`test_new_experiment_storage`は保存監査・byte readbackを保持。
CI selectorは削除testへの登録を外し、新guard検査をSTORE通常/sparseに登録。
削除・renameや未知のdiffは引き続きFULLへfail closed。

## 境界

RF/帯域/S2P/history/実験原本の差分なし。新EXP・予約・本番Campaign・dense/大規模探索なし。
旧SHA固定の手動integrationおよび旧EXP再実行は未実施。現役回帰PASSはRF適合、
連続帯域・SRF・Q(f)・EM・公差・実測・物理成立やsolver収束を意味しない。
実際のHEAD、実行コマンド、FULL結果、skipおよびCI URLはDraft PRを参照。

# Issue #343 D4 — 旧RF wrapperの撤去と検証対応

基点main `d3616b8b832c9f44fe7811d459d59664e3db8a0b`。履歴や実験原本、RF入力・kernelは変更しない。これはソフトウェア整理でありRF性能の認定ではない。

後続の#362で隔離Pythonコピーは現行treeから削除。[履歴索引](../../archive/issue343/README.md)の元commit・元パスを `git show` で取得する。以下はD4当時の記録。

## 処置

- `src/lpf/phase2_models/` の `api`、T005–T007/T008 policy wrapper、`vector_migration`、`__init__`を削除。旧zero-placeholder射影は現役schema2では使わず、互換shimを作らない。7件の旧`_grid`/ABCD evaluator/EXP固有モデルは非import対象の `archive/issue343/` にバイト不変隔離した。
- 旧EXP vectorや旧API/ABCD固有テスト12件も元blobのまま履歴に保存。うち6件は現役テストに置換し、残り6件は旧API専用なので通常CI対象外。保存対象、blob、SHA256、EXP、旧effective SHAと復元方法は[archive index](../../archive/issue343/README.md)。コピー単体の実行は保証しない。
- 旧matching専用 `src/lpf/variable_c_layouts.py` と `src/lpf/coupling_layout.py` は**残存**。immutable `experiments/matching_limit/{search_space,coupling_layout}.py` が直接importし、独立のmatching科学・検索空間検査（`test_shared_variable_c_layouts`、`test_coupling_layout`、`test_shared_graph_core`、`test_search_space_extensions`ほか）の依存。schema2 3層から利用されない。これらを現役`rf_core`に移すと旧matching物理検査と新kernelを混同する一方、単純撤去は歴史sourceと現行matching検査を壊すため、Issue全体の最終整理判断は独立レビューに残す。これら残存を全旧layout撤去と報告しない。
- 旧`run_phase2_*`と診断/prepare実行入口はD2で撤去済み。現役CLI/runnerは`phase2_models`・archiveをimportしない。AST境界検査、fresh interpreterで旧import禁止の科学回帰、CLI実行、G1 import-originテストを保持。

## 検査の対応・非同値

|旧検査|現役検査／限界|
|---|---|
|旧wrapperのF003/T005〜T008部品・role・Q・SPD・固定C|`test_issue307_constraints`, `test_issue323_dependencies`, `test_issue343_d3_science`, `test_phase2_rft008_layout`。全L/C/k端点と直外、40 k拒否、6設定、T007/T008を検査。|
|旧ABCD複素数値・EXPモデルとの比較|`test_issue309_rf_core`はD1固定入力のS実虚数・IL/APL/InRL/OutRLと旧ABCD IL固定値を検査。これは同じ実装の回帰基準で独立oracleではない。保存EXP固有vectorの新旧同値や旧solverは未再実行。|
|独立MNA・固定S2P・受動性/電力|`test_issue309_rf_core`の5条件×6設定×28個別区間×端点、およびforward stamp/cascade禁止spy、`test_phase2_branch_mna`の符号付き結合・明示KCL/KVL、`test_issue343_d3_science`の異常拒否。|
|旧MHz配列hash、ABCD cacheとSchur/transfer固有エラー|旧意味でarchiveに保存。現役Hz格子の区間/端点とS2P cacheは`test_phase2_s2p_grid_cache`、現役のゼロ伝送・数値拒否は`test_issue309_rf_core`。旧エラーコードやhashの同値は主張しない。|
|旧EXP配置注入・zero-placeholder射影|歴史テストを原文隔離。現役純構造、role、MNAおよび3L/4L合法性で代替可能な契約を維持するが、旧EXP vectorの再評価・投影互換は主張しない。|
|現役実行・保存|`test_issue321_development_cli`, `test_issue325_campaign[_gates]`, `test_issue343_d2_preservation`のraw/unknown/停止・G0〜G5・読戻しおよびsource/import-originを保持。|

現役呼出: `run_rf_search.py develop` → `search` Plan/Runner/Worker → `search.validate_values` → `rf_core.build_rf_model` → forward / 独立branch-current MNA。`topology_management`は構造正本、`optimizers`はRF非依存。歴史archiveからの現役importは禁止。

RF-F003 formal / T005〜T008 trialのeffective SHAはD1文書と同じ（試験条件は明示opt-in）。旧RF条件、実EXP、全履歴の完全再現・dense・新EXP・本番探索は実施しない。有限格子は連続帯域・EM/SRF/Q(f)/公差/実測を保証しない。

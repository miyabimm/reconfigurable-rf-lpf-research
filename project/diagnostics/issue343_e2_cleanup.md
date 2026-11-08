# Issue #343 E2 — 旧matching layoutの退役

基点main `f5141a12f2600e6332cb6a9ba528dd2995879192`。現役の構造/RF/search/保存の数値実装・RF入力・過去EXP/historyは変更しない。

後続の#362で隔離Pythonコピーは現行treeから削除。[履歴索引](../../archive/issue343/README.md)の元commit・元パスを `git show` で取得する。以下はE2当時の記録。

## 依存と処置

現役 `run_rf_search.py develop → search → rf_core` と `topology_management` に旧2モジュールのcallerはない。`src/lpf/{variable_c_layouts,coupling_layout}.py` は現役APIから撤去し、旧bounded列挙と旧nominal/感度・物理隣接検査は現役と非同値のため[archive](../../archive/issue343/README.md)へ元blobのまま隔離した。旧検査を `rf_core` に移さない。

`experiments/matching_limit/{search_space,coupling_layout}.py` は歴史原本として変更しないが、旧root importは**現checkoutでは解決しない**。これらをimportする `coverage_sampler`、`enumerate_grounded`、`p4_batch`、`full_lpf`、および `scripts/{full_lpf_checkpoint_import,reopt_lpf007_rf_f002,reopt_rft003_5l_rf_f002,reopt_rft004_seed_rf_f002}.py` は現checkoutで実行できない。互換shimは追加せず、必要な歴史再現は対象source/条件/環境の元Git commitで行う。E2は旧runner再実行保証ではない。

## テストの対応と失われる旧保証

|対象|処置・現役で残るもの|旧検査の限界|
|---|---|---|
|`test_search_space_extensions.py`|現役RF `build_rf_model`/`physical_bounds` のHV/HQ・3可変C境界は維持。旧原文はarchive。|旧sampler、matching settings、旧3形式比較とinstantiated edge照合は現役では実行しない。現役独立branch-current MNA・接続合法性は`test_issue309_rf_core.py`、`test_phase2_branch_mna.py`、`test_issue343_d3_science.py`等だが旧3形式や旧graphとの同値ではない。|
|`test_grounded_enumeration.py`|旧enumeratorに依存しないgrounded回路のMNA・電力検査は保持。元文はarchive。|旧graph canonical/列挙budget/area coverageは実行しない。|
|`test_node_area_selection.py`|独立のinvalid-budget検査は保持。元文はarchive。|旧samplerの15セルcoverageは実行しない。|
|`test_coverage_sampler.py`, `test_p4_resume_integration.py`|非同値の旧sampler・旧P4中断/resume検査を元blobのままarchive。|旧runnerと旧checkpoint互換は現役CI対象外。`test_p4_sharding.py`の単独checkpoint検査と現役Campaign G0–G5/raw/停止/readbackは維持するが、旧P4のresume実行を代替しない。|
|`test_full_lpf.py`, `test_full_lpf_checkpoint_import.py`, `test_rf_f002_search.py`|旧F002最適化・EXP-017/023 checkpoint固定再現、F002/T004設定検査を元blobのままarchive。|現役loaderはF002/T004を許可せず、E1末尾の2件は既にskip。旧EXP数値再現・旧目的関数を現役RFの合格に読み替えない。|

現役の5条件×6設定×28個別区間端点、固定S2P、独立MNA、閉区間・SPD・受動性/電力、G0–G5の検査を削除しない。旧matchingの保証縮小を隠さず、`test_issue323_dependencies.py`で旧2ファイルの不存在と現役経路からのimport禁止を検査する。履歴testのarchiveコピーは現役CIのimport対象ではない。

RF-F003 formalおよび明示opt-in T005〜T008 trialの実効SHAは既存条件と区別する。旧RF条件、旧EXP再実行、歴史全監査、denseや新規EXP/本番探索は実施しない。有限格子ソフトウェア回帰はRF適合・連続帯域・物理実現性を保証しない。

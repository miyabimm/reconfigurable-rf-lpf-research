# Issue #343 D3 — 旧候補・最適化閉包の撤去

起点は最新main `a86f47b6bf6fe3b722195167c88a6fbb07e220d6`。
D2 main `0698a87925b30ccaf11531a5197a5dc611d3f681` 以降の #350 は
歴史sparse CI参照の明確化で、D3は現行 `.github/workflows/audit.yml` を使用する。
最終HEAD・同一HEADでのCI実ログ・検証結果はDraft PRを正本とする。
Issue全体はD4まで未完了、研究はPhase 2のまま。

## 処置と現役依存

|処置|対象（`src/lpf/phase2_models/`）|理由|
|---|---|---|
|削除|`candidate_records`, `candidate_audit`, `post_search_journal`|旧候補形式・順位・昇格判定の互換は不要。保存検査は現役側で維持。|
|削除|`designed_starts`, `generic_starts`, `multistart`, `start_selection`|旧start生成・選別専用。現役Planの完全vectorに生成・clipを追加しない。|
|削除|`evaluation_cost`, `frequency_exchange`, `frequency_exchange_c1`, `normalized_epigraph`, `optimizer_comparison`, `rf_pipeline_adapter`, `sampled_epigraph`, `scipy_de_preview`, `staged_optimization`, `synthetic_plan`, `synthetic_runner`|旧solver/epigraph/予算・checkpoint閉包。現役solverへ移植しない。|
|削除|`topology_enumeration`|旧NominalCircuitの列挙・identity・area。純構造の`labelled_trees`/`capacitor_choices`は既存正本を維持。|
|履歴隔離|`post_search_evidence`, `post_search_validation`, `independent_scan`, `limited_candidate_evidence`, `problem_seed`|現役APIとは非同値の検証段階・区間内spot探索・識別/seed。バイト不変、元blob/SHA/復元手順は[履歴索引](../../archive/issue343/README.md)。|

旧候補・seed・optimizer専用testを撤去。旧独立scanの科学的手法とEXP vector参照を
持つ`test_phase2_independent_rf.py`はバイト不変の非実行資料として同索引に保存。
旧候補順位一致・旧solver再実行・旧候補形式の再認証は提供しない。

```text
run_rf_search.py develop / Campaign
  → search Plan / Runner / Worker
  → search.component_constraints → rf_core forward / 独立branch-current MNA
  → search.checkout / gates / preservation → experiment_preservation
                          （archive・phase2_modelsへの依存なし）
topology_management → 純構造型 / role / enumeration（上位層への依存なし）
```

`test_issue323_dependencies`のAST境界・fresh interpreter禁止import検査、
`test_issue321_development_cli`の実CLI禁止import完走を維持する。
`archive/`はsrc/package/現役CI実行経路ではない。D4まで旧`api`等のtestは残る。

## 削除・隔離した検査と保持する保証

|旧検査・意味|現役の保証・test|差分・未代替|
|---|---|---|
|候補auditの部品/role/Q/SPD・未検証をPASSにしない|`test_issue323_dependencies`, `test_issue307_constraints`, 新`test_issue343_d3_science`|旧audit返却dict・owner昇格判定は廃止。component PASSはRF認定でない。|
|旧固定vectorのforward/MNA・電力|D1固定期待値5条件/56点と全6設定×28個別区間×2端点の`test_issue309_rf_core`、forward stamp/cascade禁止spy|D1は現役条件の別入力回帰。EXP-042/043/055/058のvector再実行と同一とは主張しない。歴史oracleはarchiveに保持。|
|非受動/非有限電力・残差過大を拒否|新`test_issue343_d3_science`が実独立sampleを改変し、負S2P損失/NaN/電力残差を拒否。既存`test_issue309_rf_core`も維持|forward値は合っていても電力検証が失敗することを確認。|
|旧evidenceのSHA/回路/環境結合と再計算|`test_issue325_campaign_gates`のsource/input/environment/import-origin、`test_issue343_d2_preservation`の候補集合/overlay SHA/manifest-index/readback|旧形式の署名や互換読み戻しは提供しない。新testで異なるvector/偽policy SHAに対する独立照合失敗も確認。|
|旧post-searchのfailed/not_run/未完了・候補ゼロ|`test_issue343_d2_preservation`, `test_issue325_campaign_gates`, `test_issue319_parent_runner`|17/84/denseの旧段階を現役G3/G4保存集計と同値扱いしない。|
|旧frequency-exchange/費用・synthetic停止/中断保存|`test_issue315_fixed_stage`, `test_issue317_fixed_worker`, `test_issue319_parent_runner`, `test_issue321_development_cli`|requested/completed・cap・他Job予約・unknown/partial raw・保存失敗・未収束exit4/未認可exit3を現役経路で保持。旧budget/solver比較契約は廃止。|
|旧topology列挙の部品/3L4L/Q/寄生・構造helper|新`test_issue343_d3_science`が5条件×3L/4L、6設定、定数/IC固定C、role/k拒否と純構造helperを検査|旧exact candidate key・列挙counts/順位・面積reportの互換は不要。現役面積目的は`test_issue311_performance`、構造identityは現役Plan/Job testsで維持。|
|独立scanの区間内`minimize_scalar`・極値失敗oracle|非実行archiveに方法と元testを保持|固定格子は連続区間の極値探索の代替ではない。連続帯域保証・dense再実行は未実施。|

新科学testは通常RF/FULLとローカルsparse RF/FULLに登録。旧source/testの削除・renameは
セレクタがFULLへfallbackする。通常RF/OPT/RUN/GATEの境界検査も新testに接続。
旧手動topology integration入口は現役科学testを指す（FULLでも実行済みになる重複検査）。

## 検証の読み方

- RED: 追加した撤去guardが残存`candidate_audit.py`を検出して失敗。
- GREEN: 閉包の削除/隔離後、撤去guard・現役科学検査を実行。実コマンド・件数・CIはPR記録参照。
- 通常FULLと保存auditを実行する。sparse検査は廃止済みGitHub workflowの存続を仮定せず、
  `docs/data/experiments`のない隔離Git worktreeで現行selectorの`--sparse`を実行する。
- 完全EXP監査/歴史EXP再現、dense、実SciPy opt-in、本番Campaignは実施しない。
  通常保存auditのexit 0は全歴史EXPの科学的再認定ではない。

RF effective SHA（今回不変更）:

|ID|effective SHA|
|---|---|
|RF-F003 (formal)|`e12c42b11d12db7f20983c48cfa441ea96e362e533450d5862aa8a271c82af86`|
|RF-T005 (opt-in trial)|`413c1f2979926dd8bc56fe6730603864f6c582e2a72ec3f7bb0ab1ba81a7becd`|
|RF-T006 (opt-in trial)|`1d22e01d6da243bed24970de90a496e8f2d38b11bd5a5fae78e001398f647e1c`|
|RF-T007 (opt-in trial)|`5452690de1c8590f1f7c306f76e41692e1885ac190da3cef050f1d926145c944`|
|RF-T008 (opt-in trial)|`e682165c72d3a8b9f1384a2529f71bacfebfc9d17164d4af5af879e4a138b532`|

RF JSON/registry/bands/S2P/history/EXP原本への差分なし。source fingerprintは新HEADで再計算し、
過去SHAへ合わせない。ソフトウェア回帰PASSとRF適合・物理実現性は別判定。

## D4に残すもの

`phase2_models/`は`__init__.py`, `_grid`, `api`, `coupled_lc_evaluator`,
`exp042`, `exp055`, `exp058_area3`, `exp058_area4`, `exp058_area4l_gjm`,
`rft005_t007_policy_circuit`, `rft008_policy_circuit`, `vector_migration`の12 Pythonファイル。
旧RF wrapper・歴史モデル・vector投影の専用testsとroot layoutの最終処置はD4対象。
本D3をもってIssue全体の全撤去DoD達成とはしない。

# 歴史資料・研究記録の案内 — 2026-10-17（Phase 2）

> **非破壊の仮想フォルダ索引。** 旧文書の本体を本ディレクトリに移動していない。元の相対パス／Git blob SHAを保存し、条件・作成日・出典を確認して読む。現行正式制約は [RF-F003](../../data/constraints/formal/RF-F003.json)。参照する際は制約レジストリ上のactive IDを優先する。

**2026-10-17 W3追補：** D-001～D-004の旧二次文書は所有者承認で現行treeから削除し、[固有情報と元blob出典](w3_consolidated_documents_20261017.md)に統合。下の4件の旧題名リンクは統合資料に対応し、固定Gitコミットの元全文はそこから復元できる。D-005～D-007は原位置保持。

**最新の正式仕様を確認する場合：** [制約台帳](../../data/constraints/registry.json)、[現行仕様要約](../specification.md)、[保存パレート](../pareto_rf_t005_rf_f003_20261017.md)。旧RF-F002、RF-T004、RF-T003の成果をRF-F003へ置き換えない。

監査基準main: `bdb39904379637aeca5cf56ec3096e9e1b15f62a`。元`docs/`配下は**56件**。以下は実ファイルの所在を提示する索引であり、移動・改名済みの意味ではない。

## 現行の正本・結果（履歴として移動しない）（4件）

これらは現行の入口・正本に関係する文書。**archiveへ移動する候補ではない**。

- [ChatGPT「LPF設計」プロジェクト運用指示（GitHub正本）](../chatgpt_project_instructions.md) — `docs/chatgpt_project_instructions.md`
- [2026-10-17 RF-T005 / RF-F003 面積–挿入損失パレート解（保存スナップショット）](../pareto_rf_t005_rf_f003_20261017.md) — `docs/pareto_rf_t005_rf_f003_20261017.md`
- [Phase 2 現行状況 — RF-F003正式採用・RF-T005追加（2026-10-16 JST）](../roadmap.md) — `docs/roadmap.md`
- [設計仕様 / Specification — RF-F003（2026-10-16正式承認）](../specification.md) — `docs/specification.md`

## 旧RF-T003 系列（当時の計算・試験条件）（12件）

- [RF-T003 Phase 2：25nH上限の物理結合列再合成と30.35dB公称余裕（2026-10-13）](../rft003_25nH_new_row_margin_20261013.md) — `docs/rft003_25nH_new_row_margin_20261013.md`
- [RF-T003 / EXP-017：2可変C＋30dB数値探索（Phase 2、2026-10-12）](../rft003_30db_study.md) — `docs/rft003_30db_study.md`
- [RF-T003 Phase 2：5L・チップコスト6⅓・IL≤0.30dB達成（2026-10-13）](../rft003_5l_cost6p33_study_20261013.md) — `docs/rft003_5l_cost6p33_study_20261013.md`
- [RF-T003：5L・チップ面積6⅓未満への追加探索（2026-10-13、Phase 2）](../rft003_5l_further_cost_reduction_20261013.md) — `docs/rft003_5l_further_cost_reduction_20261013.md`
- [RF-T003 Phase 2：L3損失分解を起点にした5L新トポロジー探索（2026-10-13）](../rft003_5l_low_loss_study_20261013.md) — `docs/rft003_5l_low_loss_study_20261013.md`
- [RF-T003 Phase 2 継続：6L・面積6⅔のL値上限縮小と更なる縮約探索（2026-10-13）](../rft003_6l_inductor_cap_cost_followup_20261013.md) — `docs/rft003_6l_inductor_cap_cost_followup_20261013.md`
- [RF-T003 Phase 2：隣接強結合を全て利用する7L低損失回路（2026-10-13）](../rft003_7l_030_trial_20261013.md) — `docs/rft003_7l_030_trial_20261013.md`
- [RF-T003：7L目標達成候補からのチップ面積コスト削減検討（2026-10-13）](../rft003_7l_cost_reduction_study_20261013.md) — `docs/rft003_7l_cost_reduction_study_20261013.md`
- [RF-T003：6Lによるチップ面積削減の追加探索（2026-10-13、Phase 2）](../rft003_cost_down_continuation_20261013.md) — `docs/rft003_cost_down_continuation_20261013.md`
- [RF-T003：結合配列変更による5L損失改善（2026-10-13、Phase 2）](../rft003_coupling_row_improvement_20261013.md) — `docs/rft003_coupling_row_improvement_20261013.md`
- [RF-T003損失分解と3可変C比較（2026-10-12、Phase 2）](../rft003_loss_analysis_20261012.md) — `docs/rft003_loss_analysis_20261012.md`
- [RF-T003 Phase 2：6L・固定GJM1個・チップコスト6⅔への縮約（2026-10-13）](../rft003_six_L_one_GJM_cost_6p67_20261013.md) — `docs/rft003_six_L_one_GJM_cost_6p67_20261013.md`

## 旧RF-F001 / RF-F002 / RF-T004・EXP研究の記録（9件）

- [EXP-016 初回探索チェックポイント — 2対GND可変C / RF-F001](../exp016_initial_screening.md) — `docs/exp016_initial_screening.md`
- [EXP-016：PCB-Cの正式Q40モデルによる継続探索（2026-10-12、Phase 2）](../exp016_pcb_followup.md) — `docs/exp016_pcb_followup.md`
- [EXP-017 — 3可変Cから2可変Cへ：対GNDシャント共通化と非GNDブリッジ維持（Phase 2）](../exp017_two_varc_merge_study.md) — `docs/exp017_two_varc_merge_study.md`
- [Phase 2 / EXP-017 30dB近接報告点の原ソース追跡（2026-10-15）](../phase2_exp017_checkpoint_provenance_review_20261015.md) — `docs/phase2_exp017_checkpoint_provenance_review_20261015.md`
- [BSF合成理論・Cameron結合行列法 文献調査（2026-10-14）](../research/bsf_cameron_synthesis_literature_2026-10-14.md) — `docs/research/bsf_cameron_synthesis_literature_2026-10-14.md`
- [EXP-021の二重BSF的解釈と新合成探索仮説（2026-10-14）](../research/exp021_dual_bandstop_review_2026-10-14.md) — `docs/research/exp021_dual_bandstop_review_2026-10-14.md`
- [RF-T004 / EXP-022：面積6新トポロジー探索の索引（Phase 2）](../research/rf_t004_exp022_area6_discovery_index.md) — `docs/research/rf_t004_exp022_area6_discovery_index.md`
- [RF-T004 文献調査とトポロジー探索仮説（2026-10-14）](../research/rf_t004_literature_survey_2026-10-14.md) — `docs/research/rf_t004_literature_survey_2026-10-14.md`
- [RF-F002 Phase 2：P4-A ベンチマークと Full-LPF 再合成の中間報告](../rf_f002_full_lpf_phase2_20261013.md) — `docs/rf_f002_full_lpf_phase2_20261013.md`

## 研究方法・基礎理論（実装・物理検証との区別を要する）（13件）

理論・方法・実装計画の出典。計算実行と物理検証の有無は各原文で確認。

- [LQP02HV/HQインダクタシリーズ別の新しいPhase 2設計方針](../inductor_series_policy.md) — `docs/inductor_series_policy.md`
- [Phase 2 基礎研究：π型2組結合の伝送零点再配置（2026-10-16）](../phase2_pi_notch_retarget_20261016.md) — `docs/phase2_pi_notch_retarget_20261016.md`
- [Phase 2 基礎研究追補：π型の中央シリーズLと左右シャントLの2組結合](../phase2_pi_two_pair_coupling_20261016.md) — `docs/phase2_pi_two_pair_coupling_20261016.md`
- [Phase 2理論追補 — 3コイル平面配置から（＋,＋,−）磁気結合を合成（2026-10-16）](../phase2_t_coupled_inductor_planar_geometry_20261016.md) — `docs/phase2_t_coupled_inductor_planar_geometry_20261016.md`
- [Phase 2 独立基礎研究：T型3インダクタの磁気結合とモード実効Q](../phase2_t_coupled_inductor_q_foundations_20261016.md) — `docs/phase2_t_coupled_inductor_q_foundations_20261016.md`
- [Phase 2理論追補 — T型3Lの結合極性、全モードQ保証、同一リアクタンス比較（2026-10-16）](../phase2_t_coupled_inductor_uniform_mode_20261016.md) — `docs/phase2_t_coupled_inductor_uniform_mode_20261016.md`
- [Phase 2独立基礎研究 — T型とπ型3L・2組結合の等条件低損失比較（2026-10-16）](../phase2_t_pi_common_conditions_loss_comparison_20261016.md) — `docs/phase2_t_pi_common_conditions_loss_comparison_20261016.md`
- [Phase 2 基礎理論追補：T型シャントL大電流を通過帯域で許容する整合位相設計（2026-10-16）](../phase2_t_shunt_current_matched_passband_20261016.md) — `docs/phase2_t_shunt_current_matched_passband_20261016.md`
- [Phase 2 基礎研究追補：T型シャントLに大電流を流し、2組磁気結合で等価Qを高める（2026-10-16）](../phase2_t_shunt_high_current_modes_20261016.md) — `docs/phase2_t_shunt_high_current_modes_20261016.md`
- [Phase 2 基礎理論追補 — 3L-Tのうち2組だけを結合させるときの選択的Q改善（2026-10-16）](../phase2_t_two_pair_coupling_20261016.md) — `docs/phase2_t_two_pair_coupling_20261016.md`
- [EXP015_COMMON_MODEL_AUDIT.json (JSON source)](../r2/EXP015_COMMON_MODEL_AUDIT.json) — `docs/r2/EXP015_COMMON_MODEL_AUDIT.json`
- [R2 共通回路モデル・探索器：残作業の実装状況](../r2_handoff.md) — `docs/r2_handoff.md`
- [Phase 2 topology search lessons: EXP-011 compact-LPF discovery](../topology_search_lessons.md) — `docs/topology_search_lessons.md`

## 保全・出典・管理・旧計画（当時の状態）（12件）

過去の提案、PR状態、旧条件を含む。すべてが導入済みとは限らない。

- [Phase 2 実験マニフェストと索引](../experiment_manifests.md) — `docs/experiment_manifests.md`
- [Phase 2：EXP実験番号の中央予約規則（2026-10-15・提案）](../experiment_number_reservation_policy_20261015.md) — `docs/experiment_number_reservation_policy_20261015.md`
- [Phase 2：GitHubのみで管理する実験結果保存方針（2026-10-15、提案）](../experiment_result_storage_policy_proposal_20261015.md) — `docs/experiment_result_storage_policy_proposal_20261015.md`
- [GitHub不要ブランチ監査・削除記録（2026-10-14）](../maintenance/branch_cleanup_20261014.md) — `docs/maintenance/branch_cleanup_20261014.md`
- [Phase 2 GitHub Actions CI repair — 2026-10-17](w3_consolidated_documents_20261017.md#d-003) — `docs/phase2_actions_ci_repair_20261017.md`
- [Phase 2：46ファイルの出典・内容レビュー（2026-10-15）](../phase2_evidence_triage_20261015.md) — `docs/phase2_evidence_triage_20261015.md`
- [Phase 2：リポジトリ保存最適化レビュー（GitHub-only、2026-10-15）](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/blob/12b1dfd7a91ab466a6cfbbb8b4db968715e91d5f/docs/phase2_repository_optimization_review_20261015.md) — `docs/phase2_repository_optimization_review_20261015.md`
- [Phase 2：証拠逆引き・保管区分・条件別Pareto（2026-10-15）](../phase2_storage_pareto_review_20261015.md) — `docs/phase2_storage_pareto_review_20261015.md`
- [リポジトリ整理・引き継ぎ計画（Phase 2 / 2026-10-12）](w3_consolidated_documents_20261017.md#d-001) — `docs/repository_reorganization_plan.md`
- [Phase 2 Git保管構造の非破壊監査（2026-10-14）](w3_consolidated_documents_20261017.md#d-004) — `docs/repository_storage_audit_20261014.md`
- [Phase 2：実験成果の統合台帳と保全規則（初版、2026-10-14）](w3_consolidated_documents_20261017.md#d-002) — `docs/research_result_governance.md`
- [Phase 2 証拠の整合性調査と時点訂正（2026-10-14）](../result_record_corrections_20261014.md) — `docs/result_record_corrections_20261014.md`

## その他の時点付き研究・計画（3件）

- [Phase 2 制約群ごとの現行LPF候補と損失分解（2026-10-12）](../constraint_group_loss_summary.md) — `docs/constraint_group_loss_summary.md`
- [Historical research index (Phase 2)](../historical_results.md) — `docs/historical_results.md`
- [RF-F003 Phase 2 再ベースライン・実装・探索計画（2026-10-16）](../rf_f003_phase2_rebaseline_plan_20261016.md) — `docs/rf_f003_phase2_rebaseline_plan_20261016.md`

## 個別証拠の追跡と履歴復旧

- [56件の文書分類台帳](../../data/repository_reviews/step4_historical_documents_20261017.csv) は元path、Git blob SHAと仮分類を保持する。
- [同一内容34グループ](../../data/repository_reviews/step4_identical_blob_groups_20261017.csv) および [要レビュー46件](../../data/repository_reviews/step4_retention_46_20261017.csv) は削除の候補リストではなく、重複の意味を明示する保全台帳。
- [Step 4保全評価報告](../phase2_repository_step4_review_20261017.md) に条件別の保持判断と検証の限界をまとめた。
- [旧Gitコミットからの復旧手順](../historical_results.md) と [2026-10-14ブランチ整理記録](../maintenance/branch_cleanup_20261014.md) は当時の出典に基づく。2026-10-17時点で新たなbranch削除はしていない。

**Phase 2を継続。Phase 3へは所有者の明示承認まで移行しない。**

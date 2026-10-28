# RF-LPFの保存結果と検証証拠

このページは閲覧用です。数値原本は[実験索引](../data/experiment_index.csv)と各EXPのmanifest・候補・検証記録です。有限格子のbest-foundを大域最適性や実装性能の保証とは扱いません。

| RF条件 | 代表的な出典 | 判定時の注意 |
|---|---|---|
| **RF-F003（正式）** | [EXP-047](../experiments/chatgpt_topology_search/runs/EXP-047/README.md) | 正式2可変C。2026-10-17に固定したパレート4件は当時の記録 |
| **RF-T005（試験）** | [EXP-042](../experiments/chatgpt_topology_search/runs/EXP-042/README.md)、[EXP-043](../experiments/chatgpt_topology_search/runs/EXP-043/README.md)、[EXP-045](../experiments/chatgpt_topology_search/runs/EXP-045/README.md) | 最大3可変C。固定パレート6件 |
| **RF-T006/T007（試験）** | [実験索引](../data/experiment_index.csv)／[EXP-048](../experiments/chatgpt_topology_search/runs/EXP-048/README.md)／[EXP-049](../experiments/chatgpt_topology_search/runs/EXP-049/README.md) | 追加阻止帯域／固定寄生モデルの条件差がある。EXP-048/049の数値と実行範囲は旧試験時点の記録 |
| **RF-T008 v3（試験）** | [EXP-058](../experiments/chatgpt_topology_search/runs/EXP-058/manifest.json)／[EXP-062～068の索引](../data/experiment_index.csv) | IC固定Cと最大2可変Cのモデル。各EXPの数値・独立MNA・収束状態を個別に確認 |

[旧固定パレートJSON](../data/pareto_snapshots/rf_t005_rf_f003_20261017.json)と[2026-10-17保存候補24件CSV](../data/catalog/phase2_candidate_catalog_20261017.csv)は**歴史的スナップショット**であり、後続の探索を反映した現行最良一覧ではありません。[当時の説明](pareto_rf_t005_rf_f003_20261017.md)と元EXPで出典・訂正を確認します。

正式／試験／旧条件を混ぜてパレートを計算しません。目的関数、実効制約SHA、周波数格子、検証水準が等しい候補だけを比較します。H2/H3最低必須30dBと公称35dB、IL目標0.30dBは別判定です。固定S2Pはモデル由来であり、Q(f)・SRF・EM・公差・実測は未保証です。

[ロードマップ](roadmap.md) ／ [実験入口](../experiments/README.md)

EXP-048/049の当時の要約は[固定履歴版のステータス記録](https://github.com/miyabimm/reconfigurable-rf-lpf-research/blob/0bf0e3a41e2ed2a5ae4e734ccec71bc530c19a53/docs/current/phase2_status.md)から確認できます。後続の正式条件で検証済みの結果として再分類しません。

旧条件の数値記録や当時の未実行提案については[固定履歴版の研究索引](https://github.com/miyabimm/reconfigurable-rf-lpf-research/blob/0bf0e3a41e2ed2a5ae4e734ccec71bc530c19a53/docs/historical_results.md)を参照してください。現行RF制約への性能適合とは区別します。

## RF-T008 v3の保存済み比較（2026-10-20時点の履歴）

2026-10-20のEXP-062～065の横断レビューでは、**RF-T008試験条件**、全6設定・28区間×1,001点（有限格子）に対する以下のbest-foundが記録されています。後続EXP-066～068を含む最新値への更新や正式RF-F003への昇格ではありません。

| chip面積 | worst IL [dB] | 保存時点の出典・条件 |
|---:|---:|---|
| 3 / 3⅔ / 4⅓ | 1.010350255 / 0.934027580 / 0.928118761 | EXP-058。EXP-063（24/24両段階収束）は3Lの固定配置で記録更新なし |
| 4 | 0.929126781 | EXP-064、4L/0GJMの追加PCB-C配置 |
| 5⅓ | 0.829711540 | EXP-065で更新（EXP-062時点は0.833505430） |
| 6 | 0.827841148 | EXP-062、4L/3GJMの保存記録 |

[EXP-062～065の独立クロスレビュー](results/rf_t008_pr148_151_independent_review_20261020.md)では合計264試行のうち249収束・15非収束を記録し、選別10解の部品・SPD・既存MNA記録との照合を実施しています。**全28区間の独立RF解法でこのPRから再計算したものではなく、連続帯域・EM・実測は未検証**です。元の試行条件と個別結果は[実験索引](../data/experiment_index.csv)、[当時の統合スナップショット](../data/pareto_snapshots/rf_t008_exp062_065_integrated_20261020.json)から追跡してください。各段階の元文書も[Issue #170](https://github.com/miyabimm/reconfigurable-rf-lpf-research/issues/170)に固定Git blob付きで記録します。

## 旧条件・原本復元・訂正の証拠入口（Issue #170）

以下は**履歴監査の出典索引**であり、2026-10-28現在のRF-F003達成値や元の最適化を再実行した結果ではありません。原EXPのmanifest・checkpoint・原ソースの版と、後から作成された索引・復元コピー・監査報告を区別します。

| 対象 | 元証拠と監査 | 保全・解釈上の注意 |
|---|---|---|
| **EXP-017（旧RF-F002）** | [回収候補](../experiments/chatgpt_topology_search/runs/EXP-017/EXP017-LQW4-H30-NEAR.recovered.json)／[独立MNA追試の保存値](../data/validation/exp017_rf_f002_recovered_20261015/summary.json)／[回収経緯](phase2_exp017_checkpoint_provenance_review_20261015.md)／[訂正記録](result_record_corrections_20261014.md) | 元ZIPのSHA・内部member SHAを記録。**元ZIP自体はGitに収録されていない**。Gitの正規化コピーは元ZIPとバイト同一ではない。旧30dB試験点のIL 0.301248245dBは0.30dB目標未達であり、35dB公称達成でもRF-F003成果でもない。 |
| **EXP-042（RF-T005）** | [元ZIP保存](../data/repository_reviews/w4_exp042_actions_original_zip_b64_20261018.json)／[元ZIPの保全方法](phase2_w4_exp042_artifact_preservation_20261018.md)／[ZIP・checkpoint対応](phase2_w4_exp042_artifact_checkpoint_crosswalk_20261018.md)／[対応判定JSON](../data/repository_reviews/w4_exp042_crosswalk_summary_20261018.json) | 元ZIP10件・19 member。既存Gitファイルと**バイト同一だったmemberは1件**。値・ベクトルの一致だけで残りを重複原本として削除しない。 |
| **EXP-042 未選別3変種** | [6件の元member復元結果](../data/repository_reviews/w4_exp042_missing_variant_source_review_20261018.json)／[復元監査](phase2_w4_exp042_missing_variant_recovery_20261018.md)／[実行スクリプト](../scripts/audit_w4_exp042_missing_variants.py) | 復元したJSONは元Actionsの原文コピー。選別済みcheckpointを新規に作った、または新たな独立RF計算をしたとは扱わない。 |
| **EXP-046/047（試験／正式を分離）** | [131ファイル対応CSV](../data/repository_reviews/w4_exp046_exp047_131_20261018.csv)／[監査JSON](../data/repository_reviews/w4_exp046_exp047_summary_20261018.json)／[原典レビュー](phase2_w4_exp046_exp047_source_review_20261018.md) | 35件（EXP-046、RF-T005）と96件（EXP-047、RF-F003）。EXP-047のQ割当訂正前5ファイルを正式性能順位へ昇格しない。[旧manifestの索引用adapter](../data/validation/exp047_legacy_manifest_adapter_20261017.json)は実行の完全再現ではない。 |
| **EXP-046の旧バッチ原文** | [元バイト可逆アーカイブ](../data/repository_reviews/phase2_bc_exp046_bridge_lossless_archive_20261018.json)／[統合監査](phase2_bc_wave1_consolidation_20261018.md)／[バイト復旧検証器](../scripts/verify_phase2_bc_exp046_lossless.py) | 圧縮表現は元3 JSONの置換承認ではない。元ファイルを残し、出典SHAと復元互換を守る。 |
| **W4/W5の履歴監査** | [W4原本・削除ゲート](phase2_cleanup_w4_evidence_workflow_review_20261017.md)／[225原本の再実行依存](phase2_cleanup_w4_replay_dependencies_20261018.md)／[W5監査記録](phase2_w5_readonly_closure_20261018.md)／[W5保存JSON](../data/repository_reviews/w5_phase2_readonly_closure_20261018.json) | W4/W5のworkflow件数・削除未承認は**当時の監査状態**。監査成功はEXP原本削除や現行CIの完全代替を認めるものではない。 |
| **R2 / EXP-015（旧RF-F001）** | [保存済み独立モデル監査JSON](r2/EXP015_COMMON_MODEL_AUDIT.json)／[当時の実装引継ぎ](r2_handoff.md) | 当時のQ・k・可変C接続・旧正式版での追試結果であり、現行RF-F003への合格や再最適化を意味しない。 |

### 旧条件の候補報告（C群、出典へ戻るための導線）

- **RF-F001 / RF-T003の有限探索:** [2可変C・30dBの実行報告](rft003_30db_study.md)、[損失分解と電力収支](rft003_loss_analysis_20261012.md)、[7L初回成立点](rft003_7l_030_trial_20261013.md)、[5L面積6⅓](rft003_5l_cost6p33_study_20261013.md)、[6L面積6⅔](rft003_six_L_one_GJM_cost_6p67_20261013.md)。残る日付別RF-T003報告も独自の探索数・未収束・パレートを含むため、**計12件を一括退出させず**、出典コード・全ベクトル・独立検証・旧制約の一致を個別に調べる。
- **EXP-016/017とRF-F002の履歴:** [EXP-016初期探索](exp016_initial_screening.md)、[PCB-CのQ区分を修正した追試](exp016_pcb_followup.md)、[EXP-017初期2可変C仮説](exp017_two_varc_merge_study.md)、[RF-F002のFull-LPF長形式報告](rf_f002_full_lpf_phase2_20261013.md)、[RF制約群別の損失分解](constraint_group_loss_summary.md)。各文書の元試行条件・承認時点・結果訂正と別途保全したEXP-017 RF-F002の復元結果を混同しない。旧時点の公称35dB・30dB、Q・k・S2Pの条件差を現在の達成状況へ繰り上げない。
- **日付固定の結果表示:** [2026-10-17 RF-T005/RF-F003パレート](pareto_rf_t005_rf_f003_20261017.md)、[当時の24件カタログ](results/phase2_candidate_catalog_20261017.md)／[結合符号索引](results/phase2_topology_search_20261017.md)、[EXP-062～065独立クロスレビュー](results/rf_t008_pr148_151_independent_review_20261020.md)。表示用派生物と凍結した数値証拠は分けて扱う。


- **古い証拠管理・Pareto分類:** [2026-10-15の保管・証拠逆引き監査](phase2_storage_pareto_review_20261015.md)は、当時の13登録候補・8条件群の暫定Pareto、過去のGit追跡ファイルの分類、旧CI Artifactを記した**保存時点の監査原典**です。退役した旧索引生成コードを現在の実行入口と誤解せず、[固定原文ソース](https://github.com/miyabimm/reconfigurable-rf-lpf-research/blob/f0337963688d2a7155b8e28488d6723f2578e73e/scripts/build_reference_inventory.py)から復元可能であることと、現在の検証コードが別物であることを区別する。

原本を動かす前に、各pathのGit blob SHA、出典EXPと実効制約、コード／テスト／workflow／manifestからの参照、ZIP/member SHA・CRC、動的読込、必要なら元環境からの復元を調べます。特に[現存データの位置付け](../data/README.md)にある `validation/` の266件と `repository_reviews/` の29件は、ファイル件数だけで再生成可能と判断しません。**この索引はData削除・移動・元実験の書換えを承認するものではありません。**

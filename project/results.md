# RF-LPFの保存結果と検証証拠

このページは閲覧用です。数値原本は[実験索引](https://github.com/miyabimm/reconfigurable-rf-lpf-research/blob/main/data/experiment_index.csv)と各EXPのmanifest・候補・検証記録です。有限格子のbest-foundを大域最適性や実装性能の保証とは扱いません。

| RF条件 | 代表的な出典 | 判定時の注意 |
|---|---|---|
| **RF-F003（正式）** | [EXP-047](https://github.com/miyabimm/reconfigurable-rf-lpf-research/blob/main/experiments/chatgpt_topology_search/runs/EXP-047/README.md) | 正式2可変C。2026-10-17に固定したパレート4件は当時の記録 |
| **RF-T005（試験）** | [EXP-042](https://github.com/miyabimm/reconfigurable-rf-lpf-research/blob/main/experiments/chatgpt_topology_search/runs/EXP-042/README.md)、[EXP-043](https://github.com/miyabimm/reconfigurable-rf-lpf-research/blob/main/experiments/chatgpt_topology_search/runs/EXP-043/README.md)、[EXP-045](https://github.com/miyabimm/reconfigurable-rf-lpf-research/blob/main/experiments/chatgpt_topology_search/runs/EXP-045/README.md) | 最大3可変C。固定パレート6件 |
| **RF-T006/T007（試験）** | [実験索引](https://github.com/miyabimm/reconfigurable-rf-lpf-research/blob/main/data/experiment_index.csv)／[EXP-048](https://github.com/miyabimm/reconfigurable-rf-lpf-research/blob/main/experiments/chatgpt_topology_search/runs/EXP-048/README.md)／[EXP-049](https://github.com/miyabimm/reconfigurable-rf-lpf-research/blob/main/experiments/chatgpt_topology_search/runs/EXP-049/README.md) | 追加阻止帯域／固定寄生モデルの条件差がある。EXP-048/049の数値と実行範囲は旧試験時点の記録 |
| **RF-T008 v3（試験）** | [EXP-058](https://github.com/miyabimm/reconfigurable-rf-lpf-research/blob/main/experiments/chatgpt_topology_search/runs/EXP-058/manifest.json)／[EXP-062～068の索引](https://github.com/miyabimm/reconfigurable-rf-lpf-research/blob/main/data/experiment_index.csv) | IC固定Cと最大2可変Cのモデル。各EXPの数値・独立MNA・収束状態を個別に確認 |

[旧固定パレートJSON](https://github.com/miyabimm/reconfigurable-rf-lpf-research/blob/main/data/pareto_snapshots/rf_t005_rf_f003_20261017.json)と[2026-10-17保存候補24件CSV](https://github.com/miyabimm/reconfigurable-rf-lpf-research/blob/main/data/catalog/phase2_candidate_catalog_20261017.csv)は**歴史的スナップショット**であり、後続の探索を反映した現行最良一覧ではありません。[当時の説明](https://github.com/miyabimm/reconfigurable-rf-lpf-research/blob/main/docs/pareto_rf_t005_rf_f003_20261017.md)と元EXPで出典・訂正を確認します。

正式／試験／旧条件を混ぜてパレートを計算しません。目的関数、実効制約SHA、周波数格子、検証水準が等しい候補だけを比較します。H2/H3最低必須30dBと公称35dB、IL目標0.30dBは別判定です。固定S2Pはモデル由来であり、Q(f)・SRF・EM・公差・実測は未保証です。

[ロードマップ](roadmap.md) ／ [実験入口](https://github.com/miyabimm/reconfigurable-rf-lpf-research/blob/main/experiments/README.md)

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

[EXP-062～065の独立クロスレビュー](https://github.com/miyabimm/reconfigurable-rf-lpf-research/blob/main/docs/results/rf_t008_pr148_151_independent_review_20261020.md)では合計264試行のうち249収束・15非収束を記録し、選別10解の部品・SPD・既存MNA記録との照合を実施しています。**全28区間の独立RF解法でこのPRから再計算したものではなく、連続帯域・EM・実測は未検証**です。元の試行条件と個別結果は[実験索引](https://github.com/miyabimm/reconfigurable-rf-lpf-research/blob/main/data/experiment_index.csv)、[当時の統合スナップショット](https://github.com/miyabimm/reconfigurable-rf-lpf-research/blob/main/data/pareto_snapshots/rf_t008_exp062_065_integrated_20261020.json)から追跡してください。各段階の元文書も[Issue #170](https://github.com/miyabimm/reconfigurable-rf-lpf-research/issues/170)に固定Git blob付きで記録します。

## 旧条件・原本復元の参照先（Issue #170）

以下は**履歴の逆引き**です。現在のRF-F003達成候補、実験再実行、製作・EM検証ではありません。

| 対象 | 参照すべき証拠 | 判定の注意 |
|---|---|---|
| EXP-017／旧RF-F002 | [回収元の追跡](https://github.com/miyabimm/reconfigurable-rf-lpf-research/blob/main/docs/phase2_exp017_checkpoint_provenance_review_20261015.md)、[独立MNA追試記録](https://github.com/miyabimm/reconfigurable-rf-lpf-research/blob/main/data/validation/exp017_rf_f002_recovered_20261015/summary.json)、[結果訂正](https://github.com/miyabimm/reconfigurable-rf-lpf-research/blob/main/docs/result_record_corrections_20261014.md) | 元ZIP本体はGitに未収録。IL 0.301248245dBは旧30dB有限格子の記録であり、0.30dB目標未達 |
| EXP-042／RF-T005 | [Actions元ZIP保全](https://github.com/miyabimm/reconfigurable-rf-lpf-research/blob/main/docs/phase2_w4_exp042_artifact_preservation_20261018.md)、[対応照合](https://github.com/miyabimm/reconfigurable-rf-lpf-research/blob/main/docs/phase2_w4_exp042_artifact_checkpoint_crosswalk_20261018.md)、[未選別3変種の復元](https://github.com/miyabimm/reconfigurable-rf-lpf-research/blob/main/docs/phase2_w4_exp042_missing_variant_recovery_20261018.md) | ZIP内部19件と既存Gitファイルのバイト同一は1件。元ZIPとcheckpointを統合削除しない |
| EXP-046/047 | [131ファイル出典監査](https://github.com/miyabimm/reconfigurable-rf-lpf-research/blob/main/docs/phase2_w4_exp046_exp047_source_review_20261018.md)、[元バイト可逆保全](https://github.com/miyabimm/reconfigurable-rf-lpf-research/blob/main/docs/phase2_bc_wave1_consolidation_20261018.md) | RF-T005と正式RF-F003を分離。EXP-047の訂正前Q割当を合格候補にしない |
| W4/W5の保全判断 | [225ファイル再実行依存](https://github.com/miyabimm/reconfigurable-rf-lpf-research/blob/main/docs/phase2_cleanup_w4_replay_dependencies_20261018.md)、[W5監査時点の記録](https://github.com/miyabimm/reconfigurable-rf-lpf-research/blob/main/docs/phase2_w5_readonly_closure_20261018.md) | 監査完了は原本削除許可ではない |

その他の旧RF-F001/T003、R2/EXP-015、EXP-016および日付固定カタログは、[Issue #170の原典分類](https://github.com/miyabimm/reconfigurable-rf-lpf-research/issues/170#issuecomment-6464898096)から原文へ戻って確認します。特に[旧RF-F002探索報告](https://github.com/miyabimm/reconfigurable-rf-lpf-research/blob/main/docs/rf_f002_full_lpf_phase2_20261013.md)と[2026-10-15保管Paretoの監査](https://github.com/miyabimm/reconfigurable-rf-lpf-research/blob/main/docs/phase2_storage_pareto_review_20261015.md)を現行RF適合と読み替えないでください。

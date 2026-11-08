# data/：研究証拠・歴史的データ

**正式RF数値の現役正本は [rf/constraints/registry.json](../rf/constraints/registry.json)、周波数帯は [rf/bands.csv](../rf/bands.csv)、固定S2Pは [rf/parasitics/](../rf/parasitics/) です。**

旧 `data/constraints/`・`data/bands.csv`・`data/parasitics/` は既存コード・研究履歴の参照互換用です。今後の正式条件更新時に編集・二重同期する場所ではありません。

## 残すデータの役割と原本

| 場所 | 役割・正本との関係 |
|---|---|
| `experiment_index.csv`、`experiment_number_registry.csv` | 実行・検証索引とG0番号予約の中央台帳。原証拠は対応EXP |
| `candidate_index.csv`、`research_*.csv`、`supplemental_experiment_evidence_index.csv`、`experiment_evidence_inventory.csv` | 候補・検証overlay・出典・保管判断の索引。数値原本やEXP manifestを置換しない |
| [catalog/](catalog/README.md) | 2026-10-17固定入力3件と派生CSV2件。集計JSON/Markdownの重複とその専用生成機能は廃止 |
| `pareto_snapshots/` | 当時の選別集合・条件・参照SHA。選別の再現には元集合が必要なため履歴証拠として保持。現行最良一覧ではない |
| `validation/` | EXP外に保存された追試・独立検証・回収checkpoint・当時のcode snapshot。単なるcacheではなく、元EXPと異なる評価深度の証拠。元のJSON/ZIP/ログを保全 |
| [repository_reviews/](repository_reviews/README.md) | W3〜W5等の保全判断、元ZIPの可逆保存、member crosswalk。元SHA・復元情報を含むため削除／丸ごと移管しない |
| `branch_retention_review_*.csv`、`*zip*index*.json`、`external_trial_zip_manifest_*.json` | 旧branch／外部ZIPの追跡。元ZIPが未収録の場合もあり、Gitだけで計算を復元できるとは主張しない |
| `phase2_git_storage_budget.json` | 保存容量の機械検査入力。単なる説明文書と分類しない |
| `constraints/`、`bands.csv`、`design_constraints.json`、`parasitics/` | `rf/`正本を指す旧参照互換symlink。現行コード・歴史的callerが依存するため保全 |

各ファイルのblob・現行参照元・原本・処置は[Issue #352](https://github.com/miyabimm/reconfigurable-rf-lpf-research/issues/352)のDraft PR棚卸しに記録します。
原manifestに直接SHA固定された証拠・checkpointは変更しません。以下の**バイト同一configコピー5件のみ**を削減しました。残す側は原EXP manifestに固定され、コピー側には現役コードcallerがありません。旧保全CSVや元summaryに削除側のパスが記載されていても、その当時の原文は改竄しません。

| 削除した `validation/` 以下のコピー | 現在残るバイト同一原本（同じ親ディレクトリ以下） |
|---|---|
| `rf_f002_checkpoint_warmstarts_20261014/config.json` | `corrected-run/config.json` |
| `rf_f002_grid_refinement_20261014/config.json` | `run/config.json` |
| `rf_f002_recovery_20261014/retry-config-max-attempts-2.json` | `exp036-sigint-resume/config.json` |
| `rf_f002_unscaled_followup_20261014/config.json` | `run/config.json` |
| `rf_f002_warm_start_refinement_20261014/config.json` | `unremapped-import-diagnostic/config.json` |

旧46件保全台帳の全パス存在を要求する時点固定監査は、今回の承認済みコピー削減後のtreeを当時のtreeとして検査しません。[時点固定の監査ガイド](../project/legacy_git_replay.md)に従います。削除側の逐語原本もGit履歴に残り、新たな復元機能は不要です。

研究証拠・監査・候補・台帳（例：`experiment_number_registry.csv` と `experiment_index.csv`）は引き続き `data/` に原本を保存します。通常のPi Codeはこのフォルダを取得せず、全履歴検証と新EXP番号の予約は別の完全環境で行います。旧実験結果・SHA固定の証拠は遡及変更しません。

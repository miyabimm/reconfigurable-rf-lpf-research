# data/：数値正本・実験索引・履歴証拠

**数値正本は本READMEや棚卸しCSVではありません。** 正式RF仕様は[レジストリ](constraints/registry.json)の `active_formal_id` が選ぶ不変 `formal/RF-Fxxx.json`（2026-10-28 main時点はRF-F003）、6設定の帯域は[bands.csv](bands.csv)、固定入出力S2Pは[parasitics/](parasitics/)と正式JSON中のSHAが根拠です。試験用 `RF-Txxx` は正式制約へ自動昇格しません。

## 全パス分類（Issue #170、2026-10-28 main固定）

[353ファイルのpath・Git blob SHA-1・サイズ・役割・同一blob参照の一覧](repository_reviews/issue170_data_path_classification_20261028.csv) は、**main `abd17302b9e5fda20f697e60e691add8514a0f9a` のGit tree**を省略なしで取得した読み取り専用分類結果です。**表は元mainの353件を分類したもので、このCSV自身は後から追加するため353件には含めません**。以下はその元mainでの件数です。

| 分類 | 件数 | 内容・位置付け |
|---|---:|---|
| 正式RF・固定入力の正本 | 7 | [registry](constraints/registry.json)、`constraints/formal/` 3版、[bands.csv](bands.csv)、[固定S2P](parasitics/) 2件。旧正式版も不変保管 |
| 試験用RF版 | 8 | `constraints/trial/RF-T001〜T008.json`。正式版と混ぜない |
| 互換コピー | 1 | [design_constraints.json](design_constraints.json) は [RF-F003.json](constraints/formal/RF-F003.json) とGit blob一致。参照コードの互換パスを維持 |
| 実験番号・実行索引 | 2 | [番号予約台帳](experiment_number_registry.csv) と [実験索引](experiment_index.csv)。正規の実験・状態を追跡 |
| 候補・検証証拠の索引 | 6 | [旧候補索引](candidate_index.csv)、[研究候補台帳](research_candidate_register.csv)、[実験証拠一覧](experiment_evidence_inventory.csv)、補助証拠・追試overlay・研究レビューIssue表 |
| 日付固定の派生ビュー | 26 | `catalog/`の7件（別途README1件）と`pareto_snapshots/`の19件。当時の比較であり現在の最良候補一覧ではない |
| その他の歴史的管理証拠 | 5 | EXP-017元ZIPハッシュ索引、外部trial ZIP索引、旧ブランチ保管、旧ストレージ予算、保存分類結果 |
| 原本照合・保全の監査証拠 | 28 | `repository_reviews/`のデータ28件（別途README1件）。EXP-042のActions ZIP実バイト、未選別6 JSON、EXP-046/047の出典照合、W4/W5の判断記録など |
| 追試・実行過程の証拠 | 266 | `validation/`。旧RF-F002、RF-T003、EXP-016/017、R1、EXP-047索引用adapter。checkpointだけでなく実行ログ・status・失敗/中断/復旧記録も含む |
| README・ポリシー | 4 | `data/`、`constraints/`、`catalog/`、`repository_reviews/`の案内文 |
| **合計（元main）** | **353** | **全ファイルを1件ずつ割当、分類漏れ0件** |

### 重複ファイルと保全境界

元mainの353ファイルは**異なるGit blob 323個**で、同一blobを複数パスに配置したものが**26グループ（関連する56パス、余剰のパス参照30件）**ありました。たとえば`design_constraints.json`と正式`RF-F003.json`は互換のため同一、`catalog/research_candidate_register_20261017.csv`と`research_candidate_register.csv`は日付固定ビューと台帳のため同一です。`validation/`内の同一ログ・config・taskにも**実行場面と証拠連鎖が異なる**場合があります。**バイト同一は削除の十分条件ではありません。**

分類CSVの`git_blob_sha1`は**Gitオブジェクトのblob SHA-1**であり、S2P・元ZIP・正式条件の内容検査に使う**SHA-256とは別物**です。`same_blob_other_paths`は同一Git blobの相手パスを列挙します。元のファイルの実行内容・数値・全参照の独立確認を表すものではありません。

**分類後も全353件を保持**します。CSVの`dependency_review=path_and_blob_classified_full_dependencies_unverified`は全パスのコード・manifest・workflow・動的ロード・原本復元性の監査がまだ終わっていない印です。特に`validation/` 266件と`repository_reviews/`の原本は、歴史的・数値的価値や依存を確認するまで削除・移動しません。重複候補の退出には参照とSHA/CRCの再現性検証、および必要なユーザー承認が別途必要です。

[凍結カタログの条件](catalog/README.md)／[制約版の読み方](constraints/README.md)／[原本復元と判断ゲート](repository_reviews/README.md)／[実験原本](../experiments/README.md)／[Issue #170](https://github.com/miyabimm/reconfigurable-rf-lpf-research/issues/170) を参照してください。Phase 2を継続し、Phase 3は未承認です。

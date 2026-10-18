# Step 4：歴史資料・重複証拠の分類レビュー（2026-10-17）

> **監査と導線整理のみ実行。原研究資料の物理移動・削除なし。** 本書は所有者の削除承認ではない。Phase 2を継続し、Phase 3は未承認。

対象main: `bdb39904379637aeca5cf56ec3096e9e1b15f62a`（全1043追跡ファイル）。 差分PRは元mainのデータを変更せず、派生の目次・台帳を追加した。

## 1. 歴史文書の区分

| 分類 | 件数 | 取り扱い |
|---|---:|---|
| 現行の正本・結果（履歴として移動しない） | 4 | 元pathを保管し、現行正本として参照 |
| 旧RF-T003 系列（当時の計算・試験条件） | 12 | 元pathを保管し、分類目次で案内 |
| 旧RF-F001 / RF-F002 / RF-T004・EXP研究の記録 | 9 | 元pathを保管し、分類目次で案内 |
| 研究方法・基礎理論（実装・物理検証との区別を要する） | 16 | 元pathを保管し、分類目次で案内 |
| 保全・出典・管理・旧計画（当時の状態） | 12 | 元pathを保管し、分類目次で案内 |
| その他の時点付き研究・計画 | 3 | 元pathを保管し、分類目次で案内 |

現行正式RF-F003と試験RF-T005への閲覧導線は [パレート](pareto_rf_t005_rf_f003_20261017.md)と [制約台帳](../data/constraints/registry.json)を先頭にする。 旧RF-T003/F002/T004や理論研究と混同しない。 全56文書の分類は[CSV](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/blob/cd129eabaebb3a5581533d4cfcbd55cef4765117/data/repository_reviews/step4_historical_documents_20261017.csv)、人間向け目次は[docs/archive/README](archive/README.md)に保存。

## 2. 同一Git blob 34グループ／追加path 38件

| 出典上の役割（仮分類） | グループ数 | 処置 |
|---|---:|---|
| `execution_code_snapshot` | 1 | 原パス保持・消去せず個別レビュー |
| `historical_cross_run_source` | 1 | 原パス保持・消去せず個別レビュー |
| `immutable_formal_compatibility_mirror` | 1 | 原パス保持・消去せず個別レビュー |
| `pr_source_provenance` | 7 | 原パス保持・消去せず個別レビュー |
| `run_configuration_or_replay_evidence` | 9 | 原パス保持・消去せず個別レビュー |
| `run_log_restart_evidence` | 9 | 原パス保持・消去せず個別レビュー |
| `run_task_restart_evidence` | 6 | 原パス保持・消去せず個別レビュー |

Git同内容グループ：**34**、追加path：**38**。重複パスのcheckout上の最大理論バイト合計は**159,623 B**（同内容だけに基づく上界の参考値）。Gitの同一blobはcontent-addressedで既に共有されるため、**この数値をGit pack容量の削減見込みに使用してはならない**。

- `data/constraints/formal/RF-F003.json`と`data/design_constraints.json`: 同一blobだが正本＋互換コピーであり**両方を保持**。
- `EXP-020/source_pr38/`にある同一blob: 原PR出典の復旧性と当時のコンテキストを優先して保持。
- `logs/`、`tasks/`、各`config.json`: 失敗／再開／並列ベンチの再現に重要な可能性があり、同じSHAでも条件と意味が異なる。
- `code_snapshot/`と現行スクリプト: 実行時のコード指紋を保護。自動リンク置換や重複除去を禁止。
- `EXP-012/search_cost.py`と`EXP-013/model013.py`: 同一blobでも実験系譜・実行時点を確認するまで双方保持。

[同一blob台帳CSV](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/blob/cd129eabaebb3a5581533d4cfcbd55cef4765117/data/repository_reviews/step4_identical_blob_groups_20261017.csv)にはSHA、全paths、サイズ、仮分類、現在の保全処置を記録する。

## 3. 過去の46件保全レビュー

全**46件**は旧台帳と同じGit blob SHAで現mainに存在。

| 既存レビュー区分 | 件数 |
|---|---:|
| `content_equal_requires_run_role_review` | 9 |
| `experiment_source_not_indexed` | 5 |
| `text_linked_requires_semantic_review` | 32 |

旧台帳の全件`retain_pending_source_context_review`を引き継いだ。Markdownからの参照、PR source、同一blob、独立検証・実行復旧上の役割はファイル内容と関連実験の証拠が揃うまで確定できない。
[46件の照合台帳](../data/repository_reviews/step4_retention_46_20261017.csv) と [元の2026-10-15の出典レビュー](phase2_evidence_triage_20261015.md)を参照。

## 4. 現段階での保全判断と承認ゲート

1. **即時変更：文書の閲覧索引・再生成可能な監査台帳のみ**。元文書、元実験、元S2P、元制約、Git branches、元checkpointは移動・改変・削除しない。
2. **継続レビュー：同一blobの各出典／46要レビュー件**。削除対象確定ではない。個別に元コード参照、run ID、PRとGit履歴の復元、SHA、相対リンク・CIを点検した後、所有者の明示承認を要する。
3. **別PRで扱う：新しい文書ディレクトリへ元ファイルを動かす場合**。依存参照とblob一致、使用例、履歴・旧ブランチを調査し、元パスも追跡可能にする。
4. **Step 5ゲート：既存Phase 2 regression全体のPASS**。EXP-047 manifestの既知問題は本整理作業で修正しない。本Step 4専用監査のPASSと全体CIのPASSは別。

## 5. 再実行と限界

```bash
git fetch origin main
python scripts/audit_repository_reorganization_step4.py --check
```

本監査は指定mainの追跡tree、保存済み46件台帳、文書の先頭見出しを使う一次分類であり、**本文の意味全体、全Git履歴、未追跡出力、動的パス参照の完全調査ではない**。日付や保存時点の「現在」は現行正式条件を意味しない。新たなRFシミュレーション・回路最適化・物理検証を行っていない。

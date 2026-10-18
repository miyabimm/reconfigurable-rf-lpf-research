# Phase 2 W0：全追跡ファイル・リンク・削除候補監査

状態：監査実行済み、元研究ファイル削除0件。Phase 2を継続する。
基準main commit: 055b222c79c73c7fbeacb19383f21c1da0625195

## 基準mainの計数

| 監査 | 結果 |
|---|---:|
| 追跡ファイル | 1092 |
| 非圧縮bytes | 13693027 |
| Markdownファイル | 133 |
| Markdownリンク抽出 | 925 |
| 未解決ローカルリンク候補 | 1 |
| workflow YAMLファイル | 34 |
| 全文静的参照辺 | 6358 |
| 同一blob | 37組・追加41path |
| 旧保全46件 | SHA一致46件 |
| 実削除 | 0件 |

## 未解決リンク候補

Markdownリンクの正規表現抽出。実際の欠落かコード例由来かはW1で手動判定。
外部GitHub URLの実際の到達性とアンカーは確認していない。

| 文書 | 行 | 内容 | 状態 |
|---|---:|---|---|
| experiments/chatgpt_topology_search/runs/EXP-004/README.md | 54 | ../../../../actions/workflows/lpf-target040.yml | missing |

## 削除候補D-001～D-007（リンク元一覧はCSV）

| 候補 | path | Markdownリンク出典 | その他静的path出典 | 扱い |
|---|---|---:|---:|---|
| D-001 | docs/repository_reorganization_plan.md | 2 | 4 | 独自情報と出典の審査待ち、削除不可 |
| D-002 | docs/research_result_governance.md | 2 | 4 | 独自情報と出典の審査待ち、削除不可 |
| D-003 | docs/phase2_actions_ci_repair_20261017.md | 2 | 4 | 独自情報と出典の審査待ち、削除不可 |
| D-004 | docs/repository_storage_audit_20261014.md | 2 | 5 | 独自情報と出典の審査待ち、削除不可 |
| D-005 | docs/phase2_storage_pareto_review_20261015.md | 3 | 6 | 独自情報と出典の審査待ち、削除不可 |
| D-006 | docs/r2_handoff.md | 2 | 4 | 独自情報と出典の審査待ち、削除不可 |
| D-007 | docs/p4_a_scope.md | 2 | 3 | 独自情報と出典の審査待ち、削除不可 |

## 次工程と限界

- W1：現行説明の旧状態を訂正し、抽出されたローカルリンク候補を手動確認する。
- W3：削除候補ごとの固有数値・実行状況・元PR/コミットと文書移設先を確認する。
- 既存46要レビュー資料は元のGit blob SHA一致を確認しただけで、削除可能なことを意味しない。
- Gitの過去コミットからの復元と、現行スクリプト・READMEの参照互換性は別問題。
- 入力は固定mainの追跡tree。Git履歴全体・未追跡成果・動的参照を網羅していない。

詳細は削除前の固定コミット `d0351e507dd9` にある以下の元データを参照する。現在のmainの監査結果ではない。

- [`w0_20261017_summary.json`](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/blob/d0351e507dd9fd39338f7e4a69c2003bae3d531f/data/repository_audits/w0_20261017_summary.json)（旧W0固定時点の成果）
- [`w0_cleanup_20261017_summary.json`](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/blob/d0351e507dd9fd39338f7e4a69c2003bae3d531f/data/repository_reviews/w0_cleanup_20261017_summary.json)（旧W0固定時点の成果）
- [`w0_cleanup_20261017_markdown_links.csv`](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/blob/d0351e507dd9fd39338f7e4a69c2003bae3d531f/data/repository_reviews/w0_cleanup_20261017_markdown_links.csv)（旧W0固定時点の成果）
- [`w0_cleanup_20261017_deletion_decisions.csv`](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/blob/d0351e507dd9fd39338f7e4a69c2003bae3d531f/data/repository_reviews/w0_cleanup_20261017_deletion_decisions.csv)（旧W0固定時点の成果）

# 研究文書（履歴・参照用）

運用指示・現役仕様・ロードマップ等の**唯一の現役正本は [project/](../project/README.md)** に移行しました。正式RF数値の唯一の正本は [rf/](../rf/constraints/registry.json) です。

`docs/`は恒久的な追加先にしません。通常Markdownは `project/` の既存正本へ統合し、日付別の文書を増やさないでください。
Issue #352ではT/π磁気結合9文書の固有理論を[methods](../project/methods.md)へ統合し、再生成可能な候補・構造レポート2件も削減しました。
元path・blob SHA・参照元・処置と復元方法の全件棚卸しは[Issue #352](https://github.com/miyabimm/reconfigurable-rf-lpf-research/issues/352)のDraft PRに記録します。
旧[Issue #170](https://github.com/miyabimm/reconfigurable-rf-lpf-research/issues/170)の数・判定は旧時点の記録です。

## 今回残すものと理由

- 現役文書6パスのsymlinkと運用指示の移転案内：既存参照の互換用。本文の二重管理ではありません。
- `research/`のBSF文献・EXP-021/022解釈、`topology_search_lessons.md`：固有の引用・訂正・探索過程を含む原典。
  [methods](../project/methods.md)から到達できます。今回統合したT/π基礎理論とは別の研究・条件です。
- EXP-016/017、RF-T003、RF-F002、Pareto等の報告：保存データとの解釈・訂正経緯。
  現役結果の入口は[results](../project/results.md)に一本化し、原報告を現行実績へ書き換えません。
- W3/W4/W5、EXP-042/046/047、`archive/`、`r2/`、旧Stage設計・CI棚卸し：
  固定監査の根拠、回収・削除判断、独立確認JSON。固定監査スクリプトからの参照や重要証拠との結び付きがあるため保持します。
  移管・削除の最終判断はPRレビューで行い、原本はこの変更では動かしません。

この残置は `docs/` 廃止完了を意味しません。巨大な別名アーカイブへの移動も行っていません。
古い条件IDや結果を現行条件に読み替えず、歴史監査の再実行は[復元ガイド](../project/legacy_git_replay.md)に従ってください。
通常のPi Codeは `docs/` を取得しません。

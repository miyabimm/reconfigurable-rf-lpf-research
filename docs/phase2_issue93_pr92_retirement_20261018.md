# Issue #93 — PR #92重複workflowの個別退役（2026-10-18）

> **状態：退役専用PRで削除を提案・実施する作業ブランチの記録。mainへの統合と事後CIは別途実際の結果を確認する。**
>
> **ユーザー承認：2026-10-18 18:46 JSTの「退役、削除を許可します。作業を続けて」。** 直前の会話で指した対象がPR #92由来の重複CIの1ファイルであったため、承認の適用範囲はその1ファイルのみに限定する。旧W2/W3/W4監査5件、実験原本・成果・アーカイブ、Git refs等の削除許可として扱わない。Phase 2継続、Phase 3未承認。

## 個別の退役対象と元証拠

| 項目 | 値 |
|---|---|
| 削除対象 | `.github/workflows/phase2_first_wave_retention_parity.yml` |
| 元PR | [PR #92](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/pull/92)、mainマージ `552aa86775aaa2f7364ee441735afe6e07bc71b8` |
| 元Git blob SHA-1 | `12e14df94b18f5c6ce9c8a66528154095279214f` |
| 退役前main基準 | `c3787def0002b86a67684bdeeff1ca1276e5b2dd`（[PR #97](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/pull/97)統合後） |
| 保持する正本 | `.github/workflows/phase2_bc_wave1_consolidated.yml`（[PR #91](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/pull/91)） |
| 今回の削除対象ファイル数 | **1 workflow YAML** |
| その他のworkflow・実験原本・Git refs・制約 | **変更・削除なし** |

元のYAMLはGitコミットおよびGit blobから復元できる。例えば作業ツリーで`git show 552aa86775aaa2f7364ee441735afe6e07bc71b8:.github/workflows/phase2_first_wave_retention_parity.yml`により内容取得可能。Git blob `12e14df94b18f5c6ce9c8a66528154095279214f`も取得済み。将来再導入する場合は元SHA/機能・必要権限を確認し、別PRで通常のレビュー・CIを通す。Git履歴のrewriteやbranch/tag削除はしない。

## 実行済みの前提確認

- [PR #94](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/pull/94)により、PR #92の広範な変更パスを正本workflowの`pull_request.paths`に包含。旧5検査とEXP-046元3 JSONのバイト復元を正本側で保持。
- [PR #95](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/pull/95)の**main同SHA** `a8cf6ee98b06a3f2ce0cee3a5e7f845dfda3d49d`で[正本監査39107751329](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/actions/runs/39107751329)と[Phase 2回帰39107751399](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/actions/runs/39107751399)が双方SUCCESS。
- [PR #97](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/pull/97)の最新HEAD `a88be42494580db08ebcc440070b404d86865804`で12件ActionsすべてSUCCESS、mainに統合済み。mainマージSHA `c3787def0002b86a67684bdeeff1ca1276e5b2dd`の[正本監査39116718356](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/actions/runs/39116718356)はSUCCESS。main回帰はこの文書の作成時点で実行中（完了済みと主張しない）。
- [PR #97直接参照監査](phase2_issue93_reference_consumer_audit_20261018.md)：追跡1196、テキスト1194、バイナリ除外1・自己監査スクリプト除外1、7ファイルに名前のリテラル一致、`scripts/`・`tests/`・`src/`等のコード/設定で一致0。すべての外部利用者の不在を証明しない。
- main metadataは`protected=false`、rulesets一覧`[]`、詳細branch protectionのAPIは403で未確認。過去のGitHub API上の手動`workflow_dispatch`8件にはPR #92 workflowの実行はなかったが、外部システム／動的API呼出しと必須チェックの利用は未確認。

## 互換性判断と限定された残余リスク

- **既存のcheck名は同一ではない**：PR #92は`w2-topology`／`w3-source-restoration`／`exp042-crosswalk`／`exp042-six-original-members`／`exp046-exp047-provenance`の5ジョブ。正本PR #91は`five-original-checks-without-retirement`の単一job。外部required checks・監視に旧名依存があれば停止の影響を受ける。
- **artifactの名称も同一ではない**：PR #92には`first-wave-exp042-crosswalk`、`first-wave-exp042-six-original-members`、`first-wave-exp046-exp047-provenance`があり、正本は`phase2-bc-first-wave-parity-evidence`（30日期限付き）。外部ダウンロード利用者は未特定。
- これは正本化された検査の重複**定義を退役する**決定であり、PR #92の過去run・元Git blob・実験証拠を消さない。歴史文書の相対リンクは削除済みパスを指さず、固定マージコミットへ変更する。
- PR上でmainの固定出典検査、W1リンク、W3/W4/W5、Phase 2回帰がSUCCESSになることを統合ゲートとする。**削除の許可と、未確認の外部利用者への影響がゼロという証明は別の判断**である。

## 統合後の確認ゲート

1. main treeで削除対象が**存在しない**こと、正本と旧5YAMLが残ること、Git blobから歴史的定義を回復できることを確認。
2. 新main SHAのPhase 2回帰と、必要なソース保存監査（PR-head CIでの検証結果を区別）を確認する。
3. [Issue #93](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/issues/93)と[roadmap](roadmap.md)に**この1件だけの実退役**として記録する。残り旧5件の個別退役審査は別途承認が必要。RF-F003正式とRF-T005試験の区分は変更しない。

# 研究文書の旧パス

唯一の現役正本は[project/](../project/README.md)、正式RF数値は[rf/](../rf/constraints/registry.json)です。理論・引用・損失解釈は[methods](../project/methods.md)、結果・訂正・保全境界は[results](../project/results.md)へ統合しました。日付別Markdown・再生成レポートは追加しません。

Issue #352では旧資料を全件再評価し、文献・旧RF-T003・W4/W5・開発WIPを既存正本へ統合して旧文書を削除しました。巨大な別アーカイブや復元機能は作りません。元pathごとの処置・blob・callerは[PR #353](https://github.com/miyabimm/reconfigurable-rf-lpf-research/pull/353)、整理前の逐語原文は[固定Git tree](https://github.com/miyabimm/reconfigurable-rf-lpf-research/tree/3370ea4/docs)から参照できます。[Issue #170](https://github.com/miyabimm/reconfigurable-rf-lpf-research/issues/170)の分類・件数は旧時点の記録です。

残すのは次の具体的依存があるものだけです。

- 現役文書6パスのsymlink：`tests/test_canonical_source_aliases.py`と既存EXP相対リンクの互換契約。本文の二重管理ではありません。
- `chatgpt_project_instructions.md`：同テストと現役リンク監査が読む運用正本への移転案内。
- `archive/w3_consolidated_documents_20261017.md`：`scripts/verify_phase2_cleanup_w3.py`がD-001〜004の出典blobと承認を検査する固定入力。
- `r2/EXP015_COMMON_MODEL_AUDIT.json`：`scripts/audit_exp015_common_model.py`に対応する独立監査の数値原本。旧数値を現行性能へ再分類しません。

`docs/`廃止・移行cutoverの完了とはせず、通常Pi sparse checkoutでは取得しません。原manifest・checkpoint・SHA付き生証拠は今回変更していません。歴史監査は[時点固定の注意](../project/legacy_git_replay.md)に従います。

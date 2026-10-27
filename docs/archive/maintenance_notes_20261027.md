# 旧リポジトリ管理資料の保存索引

この索引は **Issue #170 / PR-2** で現役ツリーから退出した日時付きの**手続き・管理資料**を、元の内容に改変を加えず復元するための案内です。全原文は下記の固定main `0bf0e3a41e2ed2a5ae4e734ccec71bc530c19a53` にあります。元ファイルはGit履歴から参照でき、Gitオブジェクトの復元可能性をテストで確認します。

ここに列挙した過去の計画や実行状況は、現在の承認・研究結果を意味しません。最新の開発状況は[ロードマップ](../roadmap.md)、正式制約は[制約レジストリ](../../data/constraints/registry.json)、現在のCI構成はリポジトリの `.github/workflows/` を参照してください。元SHAを記録したことは、新規RF数値検証や実験を実行したことを意味しません。

## 退出した旧手続き文書（5件）

| 固定Git原文 | 旧ツリーパス | 元Git blob SHA-1 | 保全すべき意味・現在の扱い |
|---|---|---|---|
| [2026-10-17時点の文書・原本整理計画](https://github.com/miyabimm/reconfigurable-rf-lpf-research/blob/0bf0e3a41e2ed2a5ae4e734ccec71bc530c19a53/docs/phase2_repository_cleanup_and_deletion_plan_20261017.md) | `docs/phase2_repository_cleanup_and_deletion_plan_20261017.md` | `88cb034aab4d231c927de3605ded758f5d27153d` | 当時のW0～W3計画と承認ゲート。現在の実施状況ではない。Issue #170に置き換えて追跡する。 |
| [旧CI軽量化の計画と手動再実行例](https://github.com/miyabimm/reconfigurable-rf-lpf-research/blob/0bf0e3a41e2ed2a5ae4e734ccec71bc530c19a53/docs/phase2_stepA_smoke_and_on_demand_checks_20261018.md) | `docs/phase2_stepA_smoke_and_on_demand_checks_20261018.md` | `3c70c0af0d8d7103521a7135443189d6b10bb570` | 旧24件テストの説明は2026-10-27現在のCI構成と一致しない。現行の実行対象はworkflow YAMLで確認する。 |
| [旧監査workflow17件の退役提案](https://github.com/miyabimm/reconfigurable-rf-lpf-research/blob/0bf0e3a41e2ed2a5ae4e734ccec71bc530c19a53/docs/phase2_stepB_workflow_retirement_20261018.md) | `docs/phase2_stepB_workflow_retirement_20261018.md` | `d90f00f1b61b6a145ae6f015649e3e9117de58be` | 当時の17 YAML対象・可逆復旧方針・事前承認境界を含む。PR #101などの事後状態はGitHub履歴で確認する。 |
| [第1波5 workflow同等性の暫定レビュー](https://github.com/miyabimm/reconfigurable-rf-lpf-research/blob/0bf0e3a41e2ed2a5ae4e734ccec71bc530c19a53/docs/phase2_first_wave_workflow_parity_review_20261018.md) | `docs/phase2_first_wave_workflow_parity_review_20261018.md` | `a2f741bfac38cd54d0d0270575b8a7835c2cbf9b` | PR #91側の統合監査とPR #92側の重複経緯。提案・未検証事項を完了事実に昇格させない。 |
| [一時監査スクリプト・テスト15件の整理提案](https://github.com/miyabimm/reconfigurable-rf-lpf-research/blob/0bf0e3a41e2ed2a5ae4e734ccec71bc530c19a53/docs/phase2_stepC_dated_audit_retirement_20261018.md) | `docs/phase2_stepC_dated_audit_retirement_20261018.md` | `95c15a54b0b17e7ae6911410b3f43aa893c32513` | 旧13スクリプト・2テストの候補と保護対象を記録。現行コードの削除許可や実行コマンドではない。 |

## 判断境界・出典

- **旧整理計画:** 承認された削除と旧時点で未承認だった削除を区別します。最新の整理作業は[Issue #170](https://github.com/miyabimm/reconfigurable-rf-lpf-research/issues/170)で判定し、過去の仮計画を現行指示として再使用しません。
- **旧CI・workflow:** 当時の定義・退役した実行経路は元コミットで参照します。旧CIのテスト数、無効になった実行コマンド、退役予定と実際のマージを混同しません。関連する当時の個別監査は[PR #91正本整理](../phase2_issue93_pr91_canonical_reconciliation_20261018.md)・[PR #92退役審査](../phase2_issue93_pr92_retirement_20261018.md)・[歴史workflow原本の復元](../phase2_stepB_historical_experiment_workflow_retirement_20261018.md)に残します。
- **一時監査スクリプト:** 旧Step Cは削除候補の記録です。現在使用可能なプログラムやテストを保証せず、必要なら固定コミットの元ソース・PR・CI記録を確認します。
- **維持する科学的証拠:** `data/constraints/`、`data/bands.csv`、S2P、`data/validation/`・`data/repository_reviews/`、実験元manifest・checkpoint、独立検証、理論・損失分析文書は本PRで変更・削除しません。

## 旧現況・重複ナビゲーション（同じPRの先行整理）

- [旧研究ステータス](https://github.com/miyabimm/reconfigurable-rf-lpf-research/blob/0bf0e3a41e2ed2a5ae4e734ccec71bc530c19a53/docs/current/phase2_status.md)
- [旧未解決課題](https://github.com/miyabimm/reconfigurable-rf-lpf-research/blob/0bf0e3a41e2ed2a5ae4e734ccec71bc530c19a53/docs/current/open_research_questions.md)
- [旧governance目次](https://github.com/miyabimm/reconfigurable-rf-lpf-research/blob/0bf0e3a41e2ed2a5ae4e734ccec71bc530c19a53/docs/governance/README.md)

これらの入口情報は[docs/README.md](../README.md)に集約しました。旧EXP数値は[保存結果の入口](../results/README.md)と各EXP原本を照合してください。

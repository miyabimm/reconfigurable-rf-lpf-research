# プロジェクト作業入口（Phase 2）

**このページは操作の索引です。** 権限と開発規則は[運用正本](instructions.md)、正式数値は[RFレジストリ](../rf/constraints/registry.json)、実績は[ロードマップ](roadmap.md)が優先します。

## 最初に読む文書

| 用途 | 正本・入口 |
|---|---|
| 役割、承認、研究の保存方針 | [instructions.md](instructions.md)／[AGENTS.md](../AGENTS.md) |
| 最新の開発状況、未検証ゲート | [roadmap.md](roadmap.md)／GitHub Issues |
| 回路・RF条件、全6設定／28区間 | [specification.md](specification.md)、[registry.json](../rf/constraints/registry.json)、[bands.csv](../rf/bands.csv) |
| Campaign（開発・正式EXP）の明示API | [campaign_workflow.md](campaign_workflow.md) |
| 新規EXPのG0〜G5・証拠の分類 | [experiment_storage_policy.md](experiment_storage_policy.md) |
| SLSQP反復・停止理由の運用 | [slsqp_iteration_policy.md](slsqp_iteration_policy.md) |
| 回路理論・探索上の判断基準 | [methods.md](methods.md) |
| 観測された候補・失敗・検証深度 | [results.md](results.md)、[EXP索引](../data/experiment_index.csv) |
| 開発ツール／CIの実入口 | [scripts/README.md](../scripts/README.md)、[CI](../.github/workflows/audit.yml) |
| 現行診断の参照先 | [diagnostics/README.md](diagnostics/README.md)（**#397の整理対象外**） |
| 旧パス／固定Git履歴の読み方 | [legacy_git_replay.md](legacy_git_replay.md) |

## 実行環境と科学的境界

- Pi Codeは必要な証拠と中央台帳を含む**完全checkout**で作業する。通常のsparse checkoutを、旧EXP全証拠が揃った環境とみなさない。追加checkoutの作成は事前に承認を得る。
- 正式activeは`rf/constraints/registry.json`の`active_formal_id`。試験RF条件は明示opt-inとし、F003の旧SHAやRF-T008旧条件と混同しない。旧`data/...`は歴史的論理パスで、`src/lpf/constraint_versions.py`が現役`rf/`実体へ解決する。
- 共通数値入口は`src/lpf/rf_core/`、設計検査は`src/lpf/search/`、結合/接続の構造は`src/lpf/topology_management/`。現役の動作と回帰はコードとテストを確認する。
- RF Coreの一致・CI PASS・solver success・保存完了は、それぞれ**全帯域RF適合、独立MNA、連続帯域保証、実測**と同義ではない。SPD、受動性・電力保存、固定S2P、全6設定の別区間評価を維持する。

### 開発用固定definition CLI

正式EXPではない固定definitionの逐次開発用入口：

```bash
uv sync --frozen
uv run --frozen python scripts/run_rf_search.py develop \
  --config <schema2.yaml> --starts <starts.json> --output <未存在のcheckout外system tmpディレクトリ>
```

- `--starts`はseedから完全vector/SHAへの入力。自動clip・補充・別トポロジーへの単純投影はしない。
- 終了コードは0=実行完走＋solver収束、4=照合済み未収束／予算切れ、2=不正・中断状態等、3=production不可。**終了0だけでRF適合とはしない**。
- 開発Campaignの**1件ずつproposal提出**と正式CampaignのG0〜G5は[操作ガイド](campaign_workflow.md)で区別する。

## 廃止済み旧探索入口

- #343で旧`run_phase2_shared.py`、旧multistart・candidate record・post-search・schema1 runnerの現役APIは撤去済み。古い呼出例を再実行しない。
- 旧SLSQP正規化、Sobol、DE/Hybrid/SLP、次回本番予算案は現行APIの保証や実験実施承認ではない。旧比較結果は[methods](methods.md)／[results](results.md)と[固定履歴](legacy_git_replay.md)で確認する。
- Issue #397で旧資料を削減中。ただし**`project/diagnostics/`全体は作業中につき除外**し、旧EXPの元manifest・重要checkpoint・中央台帳を無断改変しない。

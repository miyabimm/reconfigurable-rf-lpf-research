# Phase 2 Step A — 日常CI軽量化と必要時の再現手順（2026-10-18）

> **変更範囲**：GitHub Actionsの`.github/workflows/audit.yml`と古いCIスケジュール前提テストを変更する。研究計算のソース、正式／試験RF制約、実験原本、候補データは変更しない。**Phase 2継続、Phase 3未承認**。

## 日常の方針

研究用リポジトリなので、全過去実験・全ソースハッシュ・保存証拠の検査を毎PRで走らせない。普段は**24の選定ユニットテスト（6ファイル）**だけを動かす。元の325件規模の単体テスト群は残し、変更内容に応じて必要時に実行する。

`audit.yml` は今後「**Phase 2 smoke (lightweight)**」と呼ぶ。起動は、main `push`／`pull_request`のうち`.github/workflows/**`, `src/**`, `scripts/**`, `tests/**`, `data/**`, `candidates/**`, `experiments/**`, `actions/**`および依存関係定義ファイルが更新されたとき、または手動 `workflow_dispatch`のみ。**READMEや`docs/**`だけの変更は本workflowを自動起動しない。** 他の旧workflowの起動条件はStep Aでは変更しない（それらの整理はStep B）。

スモーク検査6ファイルの意味：

| 対象 | 主眼 |
|---|---|
| `test_circuit.py` | 回路ソルバー・電力収支・磁気結合の基本 |
| `test_evaluate.py` | 独立ソルバーとの代表周波数一致、帯域、6設定 |
| `test_rf_f003_t005.py` | RF-F003正式・RF-T005試験の分離、固定S2Pのハッシュとカスケード |
| `test_phase2_candidate_catalog.py` | 正式／試験の候補区別、24件の索引、出典の不変性・訂正 |
| `test_exp047_legacy_manifest_adapter.py` | EXP-047の元manifestを改竄せずに索引する機能 |
| `test_github_actions_yaml_keys.py` | workflow YAMLの基本的な重複入力キーの防止 |

上記は局所的な健全性確認であり、**RF-F003で新規最良候補を探索したことも、全28帯域×6設定で独立MNAが成立したことも、Q(f)・SRF・EM・公差・実機性能が成立したことも意味しない**。スモークで検査していないコードは「検査未実施」と扱う。

## 実行方法

一度だけ依存を同期：

```bash
uv sync --frozen
```

日常スモークをローカル実行（GitHub Actionsと同じファイル選択）：

```bash
for test_file in \
  test_circuit.py test_evaluate.py test_rf_f003_t005.py \
  test_phase2_candidate_catalog.py test_exp047_legacy_manifest_adapter.py \
  test_github_actions_yaml_keys.py; do
  uv run --frozen python -m unittest discover -s tests -p "$test_file" -v || exit 1
done
```

**コード／数値モデル・最良候補を変更する前後、または重要な新結果の確定時**には以下を選択実行する。全テストを毎回走らせる必要はない。

```bash
# 必要時の全単体テスト（Step Aで削除しない）
uv run --frozen python -m unittest discover -s tests -v

# 保存済み24候補／出典に変更がある場合
uv run --frozen python scripts/build_phase2_candidate_catalog.py --check
uv run --frozen python scripts/audit_research_catalog.py

# 実験記録・索引の変更を検証する場合
uv run --frozen python scripts/audit_results.py
uv run --frozen python scripts/audit_experiment_inventory.py

# 歴史的 RF-F002 / EXP-017 の高密度検証が必要な場合のみ
# 出力は実行時の一時成果であり、新しいRF-F003性能の証明ではない
uv run --frozen python scripts/verify_exp017_recovered_mna.py --points 7001 \
  --summary artifacts/phase2_reports/exp017_recovered_fullgrid_validation.json

# 保存済み証拠の整合監査が本当に必要な場合
uv run --frozen python scripts/verify_archived_evidence_packages.py \
  --summary artifacts/phase2_reports/archive_integrity_summary.json
```

これら以外にも旧W0～W5専用の検証器は`scripts/`とGit履歴に残る。**Step Aでは削除しない**。再実行時には対象Git commit、RF条件ID/制約SHA、周波数格子、元seed（不明なら不明）、実行コマンド、結果と独立検証の可否を簡潔に記録する。旧RF-F002の再現と正式RF-F003の実証は混同しない。

## 検証記録とStep Bへの境界

- **旧状態（実行済み）**：main `8e95acf9fa59cd3dc671f65b997698b3affbcf37`の[Phase 2 regression 39117263327](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/actions/runs/39117263327)はSUCCESS。ただしこれは**旧全量workflow**の結果であり、軽量版の実行結果ではない。
- **新状態**：新PRの24テスト件数・CI所要時間・成功可否を実際のActions runから確認して追記する。PR作成時点で軽量版CIに成功したとは主張しない。
- Step Aは**常時CIの内容だけを縮小**する。48 workflowの整理、実験コード／テストの削除、最終結果や実験ログの整理はStep B以降の別作業。ユーザーの「外部システムなし」を前提として、追加の外部consumer監査は要求しない。

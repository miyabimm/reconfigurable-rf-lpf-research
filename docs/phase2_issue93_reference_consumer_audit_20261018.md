# Phase 2 Issue #93：PR #92退役前の直接参照監査（2026-10-18）

> 状態：**監査用コード・CIを追加した段階**。この文書自体は実行結果を主張しない。正本はPR #91の`phase2_bc_wave1_consolidated.yml`。本作業による元研究データ・既存workflowの削除／停止・Phase 3研究は **0件**。

## 対象と目的

[Issue #93](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/issues/93)、[PR #94](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/pull/94)、[PR #95](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/pull/95)、[PR #96](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/pull/96)を引き継ぐ。対象はPR #92由来の`.github/workflows/phase2_first_wave_retention_parity.yml`のみの**退役事前審査**。所有者の正本選択は退役承認を含まない。

現行mainの証拠：PR #95統合main `a8cf6ee98b06a3f2ce0cee3a5e7f845dfda3d49d`では[正本監査run 39107751329](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/actions/runs/39107751329)と[回帰run 39107751399](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/actions/runs/39107751399)がともにSUCCESS。PR #96は、その後の**文書のみの変更**としてmainに統合済み。

## 追加する実行可能な監査

- [監査コード](../scripts/audit_phase2_issue93_consumers.py)は`git ls-files -z`で取得した**追跡ファイル全件**のうちUTF-8テキストを検索する。NULを含むバイナリ・非UTF-8・実体のないパスを**スキップ件数とパスを明示**し、自己言及を避けるため監査スクリプト自体は検索対象から外す。
- 対象リテラル：PR #92 workflowパス・識別子、3個別artifact名、PR #91統合artifact名、PR #91単一job名、PR #92の5 job名。
- 各一致の元path・行番号・検索語・文脈と対象ファイルSHA-256を機械可読JSONに記録。`workflow`/`documentation`/`code_or_config`/`other_tracked`を区別し、同名の文字列を動的依存の証明とは扱わない。
- 正本workflowの単一job末尾で`python3 scripts/audit_phase2_issue93_consumers.py --output-dir artifacts/phase2_reports/bc/issue93_reference_scan`を実行。JSONは既存の期限付きartifact `phase2-bc-first-wave-parity-evidence`に収録し、既存の監査手順・原本は変更しない。
- **再現方法**：Python 3.12およびGitを備えたcheckoutで上記コマンドを実行する。作業ツリーに対する読取検査であり、追跡されていないファイルやGitHub外のAPI利用者を網羅しない。

## 判定と限界

| ゲート | この監査で判定可能か | 観点 |
|---|---|---|
| 既存の追跡UTF-8ソース内の文字列直接参照 | **可**（実行後の出力が必要） | docsに加えてscripts/tests/src/actions/data等も対象 |
| 同名文字列が実際にworkflowを起動／消費しているか | **不可** | 個別コードと呼出し方法のレビューが必要 |
| 動的構築名・変数経由の参照 | **不可** | 実行時／API監査が必要 |
| GitHub required checks・組織／外部CI設定 | **不可** | GitHub UI／該当設定の権限ある確認が必要。branch protection APIは以前403 |
| PR #92の手動dispatchやAPI起動の外部利用者 | **不可** | Actions履歴と運用者の確認が必要 |
| 3つの旧artifact名を外部ジョブがダウンロードするか | **不可** | 名称・パス消費者との互換性確認が必要 |
| 歴史の復元可能性 | **別途確認済み** | 元workflow Git blob `12e14df94b18f5c6ce9c8a66528154095279214f`。この監査では削除しない |

**CIが成功しても、自動的な削除許可・元データの不要判定・物理RF性能検証にはならない。** PR #92由来workflowの個別退役には、外部依存とmanual dispatch・artifact利用者の確認に加え、所有者の**対象ファイルを指定した明示承認と別PR**が必要。旧5workflow、EXP-046元3 batch JSONは今回の退役対象外。Phase 2を継続し、RF-F003正式・RF-T005試験を混同しない。

## 実行記録（次のゲート）

新規PR-head CIのworkflow run ID、対象コミットSHA、スキャン総件数、テキスト・バイナリ内訳、`code_or_config`参照の個票、失敗事項をCI実行後に追記する。実行前に結果を推定値で埋めない。

# Phase 2 Issue #93：PR #92退役前の直接参照監査（2026-10-18）

> 状態：**監査用コード・CIを追加した段階**。この文書自体は実行結果を主張しない。正本はPR #91の`phase2_bc_wave1_consolidated.yml`。本作業による元研究データ・既存workflowの削除／停止・Phase 3研究は **0件**。

> **2026-10-18 後日の運用追記:** 本文はIssue #93監査の当時の手順・実行記録です。重複workflowの退役完了に伴い、全追跡ファイルを毎回走査する一時スクリプトと手動workflow内の該当ステップを退役しました。元ソースは[固定Git版](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/blob/4048a9ed22236f6e0dec4048ffb7fd2ddfe5bde8/scripts/audit_phase2_issue93_consumers.py)から復元できます。手動W2/W3/W4・EXP-046の重要な証拠検証ステップは維持し、本文の旧実行コマンドは現行treeで使用できません。

## 対象と目的

[Issue #93](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/issues/93)、[PR #94](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/pull/94)、[PR #95](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/pull/95)、[PR #96](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/pull/96)を引き継ぐ。対象はPR #92由来の`.github/workflows/phase2_first_wave_retention_parity.yml`のみの**退役事前審査**。所有者の正本選択は退役承認を含まない。

現行mainの証拠：PR #95統合main `a8cf6ee98b06a3f2ce0cee3a5e7f845dfda3d49d`では[正本監査run 39107751329](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/actions/runs/39107751329)と[回帰run 39107751399](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/actions/runs/39107751399)がともにSUCCESS。PR #96は、その後の**文書のみの変更**としてmainに統合済み。

## 追加する実行可能な監査

- [監査コード](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/blob/4048a9ed22236f6e0dec4048ffb7fd2ddfe5bde8/scripts/audit_phase2_issue93_consumers.py)は`git ls-files -z`で取得した**追跡ファイル全件**のうちUTF-8テキストを検索する。NULを含むバイナリ・非UTF-8・実体のないパスを**スキップ件数とパスを明示**し、自己言及を避けるため監査スクリプト自体は検索対象から外す。
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

## 実行記録：PR #97初回HEAD（実行済み）

- **実行CI**：[Phase 2正本統合監査 #39108818212](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/actions/runs/39108818212) **SUCCESS**。既存の5検査とEXP-046原本復元を含むjob `five-original-checks-without-retirement` の各stepはSUCCESS。
- **対象**：PR HEAD `f7a2e5cb8ea7eace5562c745b33319e74e92251b`。GitHub checkoutの合成merge commit `23a24b4f9292dfb53550207d0aac6d0778019504`で`git ls-files`を実行。**この2 SHAを同一視しない**。
- **測定値**：Git追跡**1,196件**、自己監査スクリプト1件を除外、UTF-8として実走査**1,194件／15,921,270 bytes**、バイナリとしてスキップ**1件**（`data/validation/r1_20261012/completed-checkpoint.zip`）、欠落／root外は**0件**。
- **一致ファイル**：**7件**（workflow 3件、文書3件、`data/repository_reviews/`内の固定台帳1件）。**`scripts/`・`tests/`・`src/`・`actions/`・その他`code_or_config`区分の直接一致は0件**。旧workflowの内部自己参照・過去の比較台帳は一致に含むが、外部利用証明ではない。
- **生レポート**：Actions artifact `phase2-bc-first-wave-parity-evidence` 内 `issue93_reference_scan/issue93_tracked_reference_scan.json`。**19,292 bytes、SHA-256 `a5f6a87714f3280ced66edde59196fc2f958b1d7d21aa2d44cfd16f95586317c`**。Artifactは**期限付き（30日）**であり永久保管ではない。元JSONをGitへ固定したとは主張しない。

| 一致区分 | 元Git追跡ファイル | マッチ行の数 |
|---|---|---:|
| workflow | `.github/workflows/phase2_bc_wave1_consolidated.yml` | 4 |
| workflow | `.github/workflows/phase2_first_wave_retention_parity.yml` | 13 |
| workflow | `.github/workflows/phase2_w4_exp046_exp047_provenance.yml` | 1 |
| 固定比較台帳 | `data/repository_reviews/phase2_issue93_pr91_canonical_parity_matrix_20261018.csv` | 14 |
| 文書 | `docs/phase2_first_wave_workflow_parity_review_20261018.md` | 7 |
| 文書 | `docs/phase2_issue93_pr91_canonical_reconciliation_20261018.md` | 16 |
| 文書 | `docs/phase2_issue93_reference_consumer_audit_20261018.md` | 3 |

この7件表は**初回HEAD時点**の固定記録であり、この文書を追記した後のブランチ/CIの一致数は変化し得る。再検査時は元source SHAと出力SHAを新たに記録する。これは**追跡UTF-8ファイルの直接リテラル参照に限った否定結果**であり、required checks・外部消費者・手動workflow/API dispatch・動的利用・バイナリ内部は未確認のまま。**退役承認0、削除・停止0件**。

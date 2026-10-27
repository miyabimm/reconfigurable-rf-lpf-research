# Phase 2 W4：実験出力・旧workflowの意味監査（2026-10-17）

> **状態：W4の非破壊監査を実装しPR CIで検証する段階。削除・移動0件、所有者の個別承認0件。** [W3で承認された旧二次文書4件の削除](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/pull/80)は**今回のE/W区分の自動削除承認ではない**。原研究の[46件保全審査](../data/repository_reviews/step4_retention_46_20261017.csv)は継続。

## 1. 正本とW4の境界

- 作業起点：main `a11e9edc06b1238558cfeff1efb005faf668692b`（2026-10-17、PR #80統合後）。研究Phase 2。Phase 3はユーザー明示承認まで着手しない。
- [運用正本](chatgpt_project_instructions.md)、[追加整理計画](https://github.com/miyabimm/reconfigurable-rf-lpf-research/blob/0bf0e3a41e2ed2a5ae4e734ccec71bc530c19a53/docs/phase2_repository_cleanup_and_deletion_plan_20261017.md)、[W0監査](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/blob/727de04781cf42e6a9aaa710dc33f0ab0fb78b6d/docs/phase2_cleanup_w0_current_main_audit_20261017.md)、[W3個別審査](https://github.com/miyabimm/reconfigurable-rf-lpf-research/blob/0bf0e3a41e2ed2a5ae4e734ccec71bc530c19a53/docs/phase2_cleanup_w3_document_review_20261017.md)を参照。
- E-001 `data/validation/`、E-002 `experiments/chatgpt_topology_search/runs/`、W-001 `.github/workflows/exp042_*.yml`、その他EXP専用workflowを対象。正式RF-F003/試験RF-T005の正本や候補・実験結果には変更しない。
- [W4審査ゲートCSV](../data/repository_reviews/w4_cleanup_decision_gates_20261017.csv)は判断区分、個別承認状態を記録。**ファイル個票はCI runのArtifactsとして生成**し、現時点ではGitに全個票を直接追加しない。

## 2. 新しい実行済み監査との区別

既存の[証拠逆引きツール](../scripts/build_reference_inventory.py)はmanifestにハッシュ登録された証拠、候補台帳checkpoint/verification、補助索引とvalidation overlayを追跡する。**索引未参照は不要の証明にならない。** 中断・再開のlocks／tasks／manager.log、ソースコピー、独立回路検証、旧PRの履歴などに別の役割がある。

W4では[読み取り専用監査スクリプト](../scripts/audit_phase2_cleanup_w4.py)を追加し、最新checkout上の：
- 全tracked E-001/E-002ファイルをGit blob SHA／bytes／実験・validation群／既存機械参照／旧46件保護の有無で区分する。
- `.github/workflows/`を列挙して`workflow_dispatch`の再実行性、contents書込／git push、研究ブランチ固定参照、ソースliteral pathを検出する。
- [W3マージ後main](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/commit/a11e9edc06b1238558cfeff1efb005faf668692b)との差分で**削除0件**を保証し、旧46件の追跡Git blob SHAを照合する。
- 現時点で新たなRF数値計算を行わず、`artifacts/phase2_reports/w4/`に候補ファイルCSV／workflow CSV／要約JSONを作成する。

**注意：** workflowのテキスト解析だけではGitHub Actionsの過去全run数・実際の最終利用日・artifact期限・パラメータ・実行経路・動的な生成pathを網羅できない。`run_id`、source SHA、元PR、再実行と停止再開の依存は**候補ごとの追加レビュー**が必要。履歴の再生手段を消さないため、現在のworkflow存在／未使用を別検査しても即削除しない。

## 3. 監査前の実装上の重要事項（mainの実ファイル本文を確認）

- [EXP-042 RF-T005全系最適化](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/blob/c6c23bab59aeeea70555b016bdec7806f72d239c/.github/workflows/exp042_rf_t005.yml)はmainのEXP番号予約と試験制約を検査し、ユーザー手動`workflow_dispatch`で30/35dB目標を選ぶ。高密度検証jobとArtifacts作成も含む。**機能用途のあるworkflow**であり、「EXP終了＝不要」ではない。
- [EXP-042 manifest再生成workflow](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/blob/c6c23bab59aeeea70555b016bdec7806f72d239c/.github/workflows/exp042_manifest.yml)は特定研究ブランチをcheckoutし、manifest・experiment indexを更新する`contents:write`とpushを持つ。**歴史的な書込副作用、固定参照元の保全と適切な廃止ゲート**を分ける。
- [EXP-042 passband-Q](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/blob/c6c23bab59aeeea70555b016bdec7806f72d239c/.github/workflows/exp042_passband_q.yml)は実行ログ、stdout/stderr、終了コードをArtifactsに集める。欠損・途中中断を含む実行出典の破壊を避ける。
- [EXP-043独立3L MNA](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/blob/c6c23bab59aeeea70555b016bdec7806f72d239c/.github/workflows/exp043_verify_3l.yml)はcheckpointから独立枝電流解析を起動し、再検証可能なコードパスを提供する。
- [EXP番号事前予約workflow](../.github/workflows/reserve_experiment_number.yml)は新規実験着手の中央ゲート。**削除候補に含めない**。

## 4. W4実削除を検討する前の必須ゲート

1. file/runごとに実験ID・制約ID・主source SHA・Git blob SHA・manifest/checkpoint・後日検証の出典を示す。
2. static/dynamic参照、README、元manifest、追試コード、Actions job、再実行可能性・stop/resumeの依存を調査する。利用履歴はGitHubでrun情報を別取得。
3. **旧46件は無許可削除禁止**。類似blobや参照0だけで候補昇格しない。新規E/W削除はファイル/ワークフロー別の所有者承認と別PRが必要。
4. 保存場所・参照更新・`git show`の復元、同条件数値再現（必要時）を実証し、Phase 2回帰とW1リンク監査をPASSしてからマージ。
5. 今回の終了条件は**監査結果と未解決依存がGitHubに残ること**。削除0件を「W4削除の完了」とは扱わない。

## 5. GitHub Actionsで実行済みの数値棚卸し（2026-10-17）

[W4 CI run 39045177622](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/actions/runs/39045177622) は**SUCCESS**。実際に走査したPR検証checkout `410bde44cf4d6b008b42cccb72910a2fc01b3ff1` の結果を[固定JSON](../data/repository_reviews/w4_read_only_audit_20261017_snapshot.json)へ保存した。これは現在のmainを自動更新するlive集計ではなく、後続コミットでは追跡ファイル数が増えることがある。

| 対象 | 追跡ファイル | 機械参照あり（保持） | 旧46保護対象（保持） | 未索引・追加調査（**削除不可**） |
|---|---:|---:|---:|---:|
| E-001 `data/validation/` | **266** | 239 | 26 | **1** |
| E-002 `experiments/.../runs/` | **481** | 239 | 18 | **224** |
| **合計** | **747** | **478** | **44** | **225** |

上記747ファイルの非圧縮合計は**9,185,643 bytes**。旧保護46件はこれらの領域外の2件を含め**46件すべてSHA一致**。期間固定の旧W0集計ではなく、W4の実際のcheckoutを対象にした数値。索引にない225件を不要とみなしていない。

- E-001の1件は`data/validation/exp047_legacy_manifest_adapter_20261017.json`。EXP-047の旧manifest互換出典に関連するため、**候補削除は不可**と判断する。機械索引の単独分類は用途なしを意味しない。
- E-002の224件には`EXP-042/analyze_passband_q.py`、`EXP-042/optimize.py`、旧PR #58/#59のREADME／manifest、個別checkpoint等が含まれる。過去のrun・トポロジー復元・改修履歴と照合するまで保持。
- グループは66件。件数上位はEXP-047の97、旧RF-F002 solver ablationの47、並列benchmarkの46、RF-F002復旧39、EXP-046の36、EXP-042の31ファイル。
- **workflow 39件**のうち**38件に`workflow_dispatch`の手動起動口**がある。EXP-042を名前に含むものは6件。`exp042_manifest.yml`と`exp043_manifest.yml`は書込権限または固定研究ブランチ参照を持ち、個別のセキュリティ／履歴レビューが必要。スクリプトの静的正規表現が拾ったソースpathの欠落は0件だが、動的pathや過去runの正常完了を証明するものではない。
- **承認済みE/W削除0件、実削除0件、新規RF計算0件。**

**結論**：研究結果や再実行機能の喪失リスクを判断できる段階ではないため、W4の削除工程は保留。個別run・workflowの実行履歴と再現要否、静的・動的依存を調査するまではこのまま保持する。

## 6. 更新・実行状態


- GitHubのmainファイル本文に基づく上記workflowの機能確認：**実施済み**。
- W4新スクリプトのGitHub Actionsでの実走査、群別件数：**実行済み**（上記CIの固定スナップショットをGit保存）。全ファイル個票は同CIの`phase2-w4-review-only-reports`成果物として生成済みだが、Git treeへ全量固定はしていない。
- GitHub Actions全履歴の時系列実測調査、物理RF独立検証、新規RF実験：**未実施**。

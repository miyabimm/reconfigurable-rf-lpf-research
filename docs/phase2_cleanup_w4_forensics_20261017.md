# Phase 2 W4追加精査：225件のrun別保全と39 workflowの利用履歴（2026-10-17）

> **位置づけ：** 本書はW4の[初回非破壊監査](phase2_cleanup_w4_evidence_workflow_review_20261017.md)の追加調査。研究原本・workflowの移動・削除は0件。旧W3の文書削除承認を実験証拠・workflowに適用しない。**Phase 2継続、Phase 3未承認。**

## 基準と方法

- 基準main：`26cacd179146bda5f5ca1cdcf0096dd61eb4faae`（前回W4のPR #81統合後）。Git履歴・元ファイルは変更しない。
- [225件の個別解析](../scripts/review_phase2_w4_unindexed.py)では元[機械参照索引](../scripts/build_reference_inventory.py)の`review_only_no_deletion`に該当するE-001/E-002ファイルを抽出。本文での元path一致／解決可能なMarkdownリンク／workflowからの元path一致／basenameのみの弱い言及を別カラムにする。JSONのキー構造、文書、ソースコード、checkpoint、run/検証群を分類。**元path文字列が存在しないことと実際の未使用を同義にしない**。
- [GitHub Actionsの利用履歴解析](../scripts/review_phase2_w4_action_runs.py)ではmainで追跡されていた39 workflowそれぞれのGitHub Actions REST API登録状態、API可視の実行件数、最新3runのID・日時・event・conclusion・source SHAを、CIに渡された読取権限のtokenで取得する。**API可視の件数は保存期間とGitHub表示に依存し、永久の実行履歴ではない**。0件でも未使用とは決定しない。
- 最新ブランチでの非破壊性は前回の[W4保全検証](../scripts/audit_phase2_cleanup_w4.py)（46ファイルGit blob一致と削除0件）を再実行し、RF制約・S2P・実験出典が変更されていないことを別ゲートで検査。
- 実行証拠は[専用CI](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/blob/5a1d32099541f6ab561401494893457bbbd10376/.github/workflows/phase2_cleanup_w4_run_forensics.yml)のCSV/JSON artifactsとrun URLに保存し、重要な固定結果を`data/repository_reviews/`に移記する。**実測CI以前の結果を推測で記入しない**。

## 事前の保全判定

1. EXP-042/043のworkflow直接参照ソース、検証checkpoint、元PRのREADME／旧manifest、`data/validation/exp047_legacy_manifest_adapter_20261017.json`は**保持**。読取専用機械索引がない場合でも再現・訂正・数値の出典になり得る。
2. トレースを持つrunの中断・失敗・再開に必要な`.lock`／`tasks`／`manager.log`、元sourceコピーは無条件削除禁止。元の探索が数値的に再生できても、失敗原因の証拠は別用途。
3. workflowの`workflow_dispatch`は実機再実行の入口。`contents:write`、Git push、固定研究ブランチ参照は副作用と復旧手順を伴い、削除または置換の前に個別run・権限・出典保存のレビューが必要。
4. GitHub Actions APIのrun計数、workflowファイル名の一致、またはGit blobの内容重複**だけでは削除承認にならない**。削除提案は後続の明示owner承認・独立PRで行う。

## CI実行済み結果（GitHub Actions／2026-10-17 UTC）

- [履歴API観測CI 39046668020](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/actions/runs/39046668020)の非破壊ソース監査／認証済みActions API照会は**SUCCESS**。加えて[再分類・保存CSV一致検証 39047041212](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/actions/runs/39047041212)も**SUCCESS**。実行時のPRチェックアウトから生成されたCSVを[225件の固定個票](../data/repository_reviews/w4_unindexed_225_review_20261017.csv)、[39workflowの履歴固定個票](../data/repository_reviews/w4_workflow_runs_20261017.csv)に記録。[観測値・検証範囲JSON](../data/repository_reviews/w4_run_forensics_20261017.json)も参照。
- 基準はmain `26cacd179146bda5f5ca1cdcf0096dd61eb4faae`。API履歴観測は**2026-10-17T15:48:46+00:00**。実際のGitHub登録状況とAPI応答を記録したものであり、過去run全件の無期限保存を意味しない。
- E-001/E-002合計225件／**2,046,501bytes**を7グループに分類。**78件**は他の追跡テキストに正確な元パスを持つか、ローカルMarkdown参照が解決する。うちworkflowから正確な元パスが確認できたのは**20件**。**145件**は今回の静的パス検索で参照が見つからないが、用途不明であり削除候補0件。
- 当初「未分類」に見えた59件は拡張子`.js`の**歴史的JavaScript回路解析・追試コード**であると判明し、元Git blobを改変せず、[225件個票](../data/repository_reviews/w4_unindexed_225_review_20261017.csv)では`source_code_js`、`retain_runner_or_verifier_source_pending_run_lineage`へ再分類。旧EXP-045/046等のin-chat原本であり、これらを一時キャッシュと呼ばない。

### 225件の元run別内訳

| source group | 件数 | bytes | 確認・保全ゲート |
|---|---:|---:|---|
| EXP-047 | 96 | 1,175,082 | 旧形式manifest由来の出典・元ソースを保持、数値再実行不要との断定禁止 |
| EXP-046 | 35 | 345,244 | JS解析と元記録の実行形態を区別、実測／Actions追試と混合禁止 |
| EXP-042 | 30 | 154,928 | 7件のworkflow直接パス参照を含む。最適化・独立検証・旧PRの原本を保持 |
| EXP-045 | 26 | 157,380 | 独立の元PR・再現用プログラム・結果を保全 |
| EXP-043 | 25 | 138,151 | 11件のworkflow直接パス参照を含む。独立MNAの再生可能性を保持 |
| EXP-044 | 12 | 73,770 | 2件のworkflow直接パス参照を含む。旧CI修復と元実験の区別 |
| EXP-047互換overlay | 1 | 1,946 | 旧manifestの互換解釈に必要。削除対象外 |

### 39workflowのGitHub API確認

- 既存39件すべてがGitHub Actions APIに登録され、**32件**には現時点で可視のrun履歴がある。**7件のAPI可視run件数は0**で、`lpf-exp009/010/011/012/013`、`lpf-target040`、**現行のEXP番号予約workflow**が該当。**0＝実行歴なし、不要、廃止可**とは解釈しない。
- EXP-042専用6件のAPI可視run件数は、`exp042-rf-t005-verify` **7**、`exp042_area` **23**、`exp042_manifest` **12**、`exp042_passband_q` **133**、`exp042_pcb` **19**、`exp042_rf_t005` **30**。これらは観測日現在のREST応答件数で、通し番号の保証や永続的run historyではない。
- `exp042_manifest`の直近観測run **38822654644** は`failure`、最終観測日時は2026-10-15T23:17:11Z。ほか5件のEXP-042最新runは`success`であっても、これだけで過去の全stageや現行RF-F003の独立再検証を主張しない。
- 39件のうち、`exp042_manifest`、`exp043_manifest`、`phase2_cleanup_w0`、`phase2_step1_repository_inventory`、`reserve_experiment_number`の5件には、書込み可能権限・Git push・固定ブランチ参照のいずれかが静的に認められるため、運用機能と副作用を個別確認するまで保持。
- API照会はワークフローごとに直近**3件**のrunメタデータのみを記録。実行ログ・Artifacts現物・workflow_dispatch利用者・branchごとの再実行適合性は未検証。

## 次の削除判断ゲート

**現時点の実削除0件、E/W所有者削除承認0件。** 次回は高密度群EXP-047/046、元JSファイル、固定branch workflowについて、元チェックポイント・失敗記録・再実行codeの独立性を個別に照合する。削除の実施前に、ファイルごとのpath／SHA／代替出典／実行可能性／参照更新／別PRと所有者承認が必要。原本の削除承認なしにW5へ移行して全削除完了と呼ばない。

## 最新の実施結果・未実施事項

初回W4の固定数値：対象747ファイル、うち機械索引未参照225件、workflow39件。[固定JSON](../data/repository_reviews/w4_read_only_audit_20261017_snapshot.json)。

**この追加PRの実行値とCI URLはPRチェック完了時に追記する。** 実行後に225件のグループ別分布、ソース参照区分、GitHub ActionsでのAPI可視利用状況を記録する。外部アーカイブにしかない元run・失効したActions Artifact・動的path／ログ全文の再現確認は依然として別作業。元研究証拠の削除は未承認。

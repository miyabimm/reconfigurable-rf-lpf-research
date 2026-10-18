# Phase 2：新規実験のGitHub-only保存ポリシー v1

**ポリシーID：phase2-git-only-v1。** 本変更のmainマージ以降に新規作成する **EXP-048以降**へ適用する。旧EXP-001～047の原manifest／checkpoint／証拠には遡及適用しない。研究はPhase 2、Phase 3は所有者の明示承認まで停止する。

**既存根拠：** [運用正本](../chatgpt_project_instructions.md)、[整理計画（固定履歴版）](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/blob/12b1dfd7a91ab466a6cfbbb8b4db968715e91d5f/docs/phase2_repository_reorganization_plan_20261017.md)、[2026-10-15保存方針案](../experiment_result_storage_policy_proposal_20261015.md)、[既存容量基準](../../data/phase2_git_storage_budget.json)、[EXP番号中央予約](../experiment_number_reservation_policy_20261015.md)。当時の提案・歴史記録は上書きしない。

## 1. A/B/Cの役割

| 区分 | 保存対象 | 基本ルール |
|---|---|---|
| **A 必須** | main予約済みEXP、厳格manifest、実効RF制約/bands/固定S2P SHA、実行コード/環境/seed、探索件数サマリー、重要候補の完全L/C/kと全6設定Cv、検証状態、元path/SHA | GitへコミットしGit HEADからのbyte再取得で照合する |
| **B 選別** | Pareto非劣点、30/35dB境界、異なるトポロジー、代表的な失敗・未収束・停止再開診断 | 実行**前**に選別ルール・top K・予測保存容量を明記する |
| **C 一時** | 全iteration、無差別workerログ、heartbeat、キャッシュ、再生成可能な大量波形、不要lock | 原則Git管理外のresults/。A/Bの保全確認前に削除しない |

ファイル名や拡張子だけで旧原本をCへ分類しない。失敗実験も実行範囲・試行数・理由を保存し、「未実行」「実行済み」「未収束」「独立検証済み」を混同しない。

## 2. ファイル構成・正本

~~~
experiments/chatgpt_topology_search/runs/EXP-NNN/
  manifest.json          # 既存schema 1: 制約・コード・環境・実行/検証・evidenceの正本
  storage_record.json    # 新規schema 1: 選別方針・保存完了状態
  run_summary.json       # 試行/失敗/未開始、選別理由、limitations
  checkpoints/
    <candidate_id>.json  # 完全回路と6設定可変C
data/validation/         # 独立解析・再評価・訂正は別ファイル
results/                 # Git管理外のraw一時出力
~~~

汎用探索の experiments/matching_limit/runs/EXP-NNN/ も同じ扱いとする。元manifestの再評価結果を元実験の結果に改竄せず、別validation overlayへ保存する。Paretoの固定スナップショットも上書きしない。

storage_record.json は以下の形式で探索開始前に作る（**例示のみ、EXP-048が予約・実行済みであるとの意味ではない**）。

~~~json
{
  "schema_version": 1,
  "policy": "phase2-git-only-v1",
  "experiment_id": "EXP-048",
  "phase": "Phase 2",
  "stage": "planned",
  "selection": {
    "top_k": 5,
    "retain": ["best", "pareto", "30db_boundary", "35db_boundary", "topology_diversity", "representative_failure"],
    "rule": "面積-IL非劣点、30/35dB境界、異種トポロジー、代表的失敗を保存。top_kは追加の通常上位解の数であり、独立の重要点を捨てる上限ではない。",
    "estimated_curated_bytes": 250000
  },
  "summary": null,
  "checkpoints": [],
  "validation_overlays": [],
  "supporting_evidence": [],
  "git_readback": "not_run",
  "size_exception": null,
  "limitations": []
}
~~~

stage は planned → running → complete。データが欠落している部分／中断／失敗は preservation_incomplete として不足内容をlimitationsに記録する。**stage=completeは証拠保存完了であり、数値収束、独立MNA、RF目標達成、実装保証の意味ではない。** 実行状態の正本はmanifest.execution.status、検証状態はmanifest.validation。

保存した各checkpointは candidate_id、topology（接続）、components（全L/C・Q・シリーズ・端子）、couplings（符号付きk）、chip_row（物理チップ配置）、fixed_values（固定素子値）、ic_variable_C_pf_by_settingを含む。後者にはB71、B12、B28、B13+B14、B26、B8の6設定分の枝容量配列を入れる。スクリプトは構造と0～3pFの基本型のみを監査し、回路の数値真実性を証明しない。

storage_record.checkpoints の各行は candidate_id / selection_reason / path / sha256。selection_reason は best、pareto、30db_boundary、35db_boundary、topology_diversity、representative_failure、other。validation_overlays は method（independent_mna/grid/spd/power_balance/other）・status（passed/failed/not_run）・path・sha256。**未実施はnot_runのままとする。** 実験固有のソース断片、dirty差分、代表的停止ログなど、checkpoint・summary・検証以外の不可欠な成果のみ supporting_evidence として登録する。各行には path、sha256、role（source_snapshot/dirty_patch/representative_failure/recovery_state/method_note/other）、reason を要求する。**manifest.evidence に登録された全証拠をstorage_record上でも分類**し、分類不能な残余ファイルは保存完了を拒否する。1つの実データを複数の別ファイル名で重複保存しない。

run_summary.json の最低構造は次のとおり。試行（start等）の件数であり関数evaluation数とは区別する。

~~~json
{
  "experiment_id": "EXP-048",
  "attempts": {
    "planned": 100, "attempted": 85, "converged": 20,
    "nonconverged": 60, "failed": 5, "not_started": 15
  },
  "selected_candidate_count": 2,
  "best_found": [],
  "limitations": ["局所探索のみ。連続周波数極値・Q(f)/SRF/EM未検証"]
}
~~~

converged + nonconverged + failed = attempted、attempted + not_started = plannedを厳守。候補ゼロの場合は selected_candidate_count=0 に加え no_candidate_reason を記載する。

## 3. 運用ゲート（EXPを開始するたびに実施）

**G0 予約確定。** 最新mainの中央台帳へ先にEXP番号を予約し、照合PASSを確認。番号の予測・PRブランチ上の仮番号では計算を開始しない。

~~~bash
git fetch origin main
python scripts/experiment_id_registry.py --experiment-id EXP-NNN --owner <GitHub actor>
~~~

**G1 preflight。** 共通manifest生成器で厳格manifestを作る。RF-T005は明示の --allow-trial が必要。目的（matching_only/full_lpf）、RF実効SHA、bands、外部S2P、コードcommit/dirty差分、uv.lock/環境、seed（不明なら不明と明記）、探索範囲・格子・収束/選別基準・予測容量を記録し、storage_recordをplannedで作る。新runのmanifestに保存対象と制約SHAを紐付ける。

~~~bash
python scripts/audit_new_experiment_storage.py preflight EXP-NNN
~~~

**G2 run。** 一時出力は原則 Git管理外の results/EXP-NNN/ に集約し、実行中は原子的に書く。多数のiteration dump、workerログ、同じ候補の毎時コピー、テストの一時fixtureはGitへ追加しない。意味ある候補の完全ベクトルと必要な失敗診断だけをA/Bへ昇格し、Actions Artifactの保持期限やworkerの寿命に依存させない。

**G3 finalize。** 完了・失敗・中断件数をrun_summaryへ集計し、選別checkpoint、独立検証結果（未実行なら未実行）、manifest.evidence、SHAを保存。Gitへコミット後に HEAD:path を実際に読み戻してbyte一致を確認し、storage_recordのstageをcomplete、git_readbackをpassedへ更新する。保存記録自身のコミット後、次のコマンドで再照合する。

~~~bash
python scripts/audit_new_experiment_storage.py finalize EXP-NNN
~~~

PASSまで生rawの自動削除は禁止。証拠が欠落した場合はpreservation_incompleteを記録して必要なrawを保持し、勝手にcompleteへ昇格しない。保存済み候補の独立MNA、6設定の全区間極値、SPD、受動性、電力収支、SRF/EM、温度公差は別に実行し、**実施した範囲のみ**検証結果へ記録する。

**G4 PR/CI。** 次でEXP-048以降のrunを一括監査する。古い実験は監査形式の対象外。

~~~bash
python scripts/audit_new_experiment_storage.py audit
~~~

チェック項目：origin/mainの予約とRF条件、既存厳格manifest、選別計画、証拠のSHA/実ファイル、6設定checkpoint構造、試行件数、Git HEAD byte再取得、保存容量に加え、**未分類のGit追跡ファイル、重複証拠、force-addされた一時ファイル**を拒否する。新しいEXPディレクトリにGit追跡ファイルを置く場合は、manifest/storage_record自身以外の全ファイルをA/B証拠に分類する。テストfixture等の使い捨てファイルをGitへ入れない。

**CIの軽量性：** 従来の常時24代表テスト（6モジュール）は維持。新規保存監査（読取専用）だけは毎PRの通常CIで実行し、保存監査の専用ユニットテストは保存監査スクリプト／そのテスト／workflowが変更されたときだけ起動する。既存の数値的な全歴史テストは引き続き必要時に実行する。**CI PASSは独立RF計算の再実行を意味しない。**

**G5 ローカルCの後片付け。** finalizeがPASSし、runの停止/再開が不要、A/Bへ昇格すべき元データがないことをrun担当者が確認した場合に限り、results/EXP-NNN/ 内のCを消去してよい。ほかのEXPや全resultsをまとめて削除しない。消去前後の「実験ID・finalize PASSのcommit SHA・残したA/B証拠・消去対象」の確認結果はPR本文または短い要約に記録する。finalize未達、preservation_incomplete、再開予定あり、依存不明の場合はそのCを保留し、保留理由と期限（または次のレビュー条件）を管理する。**既存Git原証拠の削除権限とは別のローカル一時作業領域だけの規則。**

## 4. 容量基準・例外

既存の data/phase2_git_storage_budget.json を値の正本とする。単一ファイル128KiB超は手動レビュー目安、1MiB超は原則保存不可。新規EXPの選別済み一式512KiB超はレビュー後に例外承認が必要。tracked総容量25MiBで増加傾向を監査する。これらはGitHub公式の一律hard limitではない。個別例外は storage_record.size_exception に approved_by / approval_url / reason を記録し、**所有者の明示承認**に紐付ける。監査器は1MiBと512KiBを機械判定し、manifestとstorage_record自身もEXP保存容量へ算入する。128KiB超はsoft_file_review_pathsへ報告する。25MiBはGit追跡treeの増加傾向を手動・定期的に再監査するレビュー指標であり、Git pack/全履歴の大きさと混同しない。機械的な旧資料削除の根拠にはしない。

## 5. テスト・コード・文書を増やさない原則

- **常設テストの追加条件：** RFモデルの恒久的不変条件、再発があり得る具体的バグ、共通API／保存規則の契約に対応し、複数回再利用されること。実験1回限りの期待値照合、探索途中の数値比較、使い捨てfixtureは原則 results/EXP-NNN/ に置く。バグ修正時の恒久的退行検知は、専用EXP番号のテストファイルを量産せず既存の共通テストへ集約する。
- **新テストのPRレビュー：** 既存テストで代替できない理由、検出する失敗、常時CIか必要時実行か、古いテストの置換・統合候補を確認する。新しいworkflowや実験ごとの監査スクリプトを無条件に追加しない。
- **古いテスト／一時スクリプトの退役：** 元数値・失敗検出能力・スクリプト参照・再実行依存を確認したうえで削除候補へ記録し、所有者の個別承認と別PRで現行treeから整理する。単に古い/未参照という理由で自動削除しない。
- **ドキュメント：** 現行正本へのリンクを維持し、各EXPの臨時レポートを目的なく新規作成しない。サマリーは原則run_summary、過去の重要な判断は固定SHA付き履歴に残す。

## 5. 再現性と昇格の境界

- **候補再評価可能：** 完全L/C/k・6設定Cv・RF実効SHA・S2P・コード・数値格子等が揃い再評価できる。監査による形式照合は、その数値計算を実行した証明ではない。
- **探索再実行可能：** さらに初期値/seed/依存環境/探索範囲/ジョブ割当とdirty時の実ソースが必要。並列・浮動小数点の非決定性は限界として記録する。
- **全試行厳密再生：** 全iteration/乱数状態等を実際に保管した場合のみ主張。通常保証しない。

formal RF-F003／trial RF-T005／旧制約を混在させない。30dB必須、35dB公称、strict_finite_grid/tolerance_only、同一評価格子の違いも明示。報告値だけでベクトルを欠く候補はreported_onlyに留め、索引へ無根拠に昇格させない。

**本変更は新規実験保存規則の導入のみ。既存原本、旧ZIP、旧workflow、ブランチ・タグ・Git履歴の整理・削除の承認ではない。**

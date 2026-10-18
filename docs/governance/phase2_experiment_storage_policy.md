# Phase 2：新規実験のGitHub-only保存ポリシー v1

**ポリシーID：phase2-git-only-v1。** 本変更のmainマージ以降に新規作成する **EXP-048以降**へ適用する。旧EXP-001～047の原manifest／checkpoint／証拠には遡及適用しない。研究はPhase 2、Phase 3は所有者の明示承認まで停止する。

**既存根拠：** [運用正本](../chatgpt_project_instructions.md)、[整理計画](../phase2_repository_reorganization_plan_20261017.md)、[2026-10-15保存方針案](../experiment_result_storage_policy_proposal_20261015.md)、[既存容量基準](../../data/phase2_git_storage_budget.json)、[EXP番号中央予約](../experiment_number_reservation_policy_20261015.md)。当時の提案・歴史記録は上書きしない。

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
  "git_readback": "not_run",
  "size_exception": null,
  "limitations": []
}
~~~

stage は planned → running → complete。データが欠落している部分／中断／失敗は preservation_incomplete として不足内容をlimitationsに記録する。**stage=completeは証拠保存完了であり、数値収束、独立MNA、RF目標達成、実装保証の意味ではない。** 実行状態の正本はmanifest.execution.status、検証状態はmanifest.validation。

保存した各checkpointは candidate_id、topology（接続）、components（全L/C・Q・シリーズ・端子）、couplings（符号付きk）、chip_row（物理チップ配置）、fixed_values（固定素子値）、ic_variable_C_pf_by_settingを含む。後者にはB71、B12、B28、B13+B14、B26、B8の6設定分の枝容量配列を入れる。スクリプトは構造と0～3pFの基本型のみを監査し、回路の数値真実性を証明しない。

storage_record.checkpoints の各行は candidate_id / selection_reason / path / sha256。selection_reason は best、pareto、30db_boundary、35db_boundary、topology_diversity、representative_failure、other。validation_overlays は method（independent_mna/grid/spd/power_balance/other）・status（passed/failed/not_run）・path・sha256。**未実施はnot_runのままとする。** すべての保存対象をmanifest.evidenceにもpathとSHAで登録する。

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

**G2 run。** Git管理外results/へ原子的に出力。重要な完全ベクトルは途中でもcheckpoint化し、Actions Artifactの保持期限やworkerの寿命に依存させない。

**G3 finalize。** 完了・失敗・中断件数をrun_summaryへ集計し、選別checkpoint、独立検証結果（未実行なら未実行）、manifest.evidence、SHAを保存。Gitへコミット後に HEAD:path を実際に読み戻してbyte一致を確認し、storage_recordのstageをcomplete、git_readbackをpassedへ更新する。保存記録自身のコミット後、次のコマンドで再照合する。

~~~bash
python scripts/audit_new_experiment_storage.py finalize EXP-NNN
~~~

PASSまで生rawの自動削除は禁止。証拠が欠落した場合はpreservation_incompleteを記録して必要なrawを保持し、勝手にcompleteへ昇格しない。保存済み候補の独立MNA、6設定の全区間極値、SPD、受動性、電力収支、SRF/EM、温度公差は別に実行し、**実施した範囲のみ**検証結果へ記録する。

**G4 PR/CI。** 次でEXP-048以降のrunを一括監査する。古い実験は監査形式の対象外。

~~~bash
python scripts/audit_new_experiment_storage.py audit
~~~

チェック項目：origin/mainの予約とRF条件、既存厳格manifest、選別計画、証拠のSHA/実ファイル、6設定checkpoint構造、試行件数、Git HEAD byte再取得、保存容量。**CI PASSは独立RF計算の再実行を意味しない。**

## 4. 容量基準・例外

既存の data/phase2_git_storage_budget.json を値の正本とする。単一ファイル128KiB超は手動レビュー目安、1MiB超は原則保存不可。新規EXPの選別済み一式512KiB超はレビュー後に例外承認が必要。tracked総容量25MiBで増加傾向を監査する。これらはGitHub公式の一律hard limitではない。個別例外は storage_record.size_exception に approved_by / approval_url / reason を記録し、**所有者の明示承認**に紐付ける。監査器は1MiBと512KiBを機械判定する。128KiBと25MiBはレビュー指標であり、機械的な旧資料削除の根拠ではない。

## 5. 再現性と昇格の境界

- **候補再評価可能：** 完全L/C/k・6設定Cv・RF実効SHA・S2P・コード・数値格子等が揃い再評価できる。監査による形式照合は、その数値計算を実行した証明ではない。
- **探索再実行可能：** さらに初期値/seed/依存環境/探索範囲/ジョブ割当とdirty時の実ソースが必要。並列・浮動小数点の非決定性は限界として記録する。
- **全試行厳密再生：** 全iteration/乱数状態等を実際に保管した場合のみ主張。通常保証しない。

formal RF-F003／trial RF-T005／旧制約を混在させない。30dB必須、35dB公称、strict_finite_grid/tolerance_only、同一評価格子の違いも明示。報告値だけでベクトルを欠く候補はreported_onlyに留め、索引へ無根拠に昇格させない。

**本変更は新規実験保存規則の導入のみ。既存原本、旧ZIP、旧workflow、ブランチ・タグ・Git履歴の整理・削除の承認ではない。**

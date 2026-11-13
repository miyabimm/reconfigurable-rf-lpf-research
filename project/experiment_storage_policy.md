# 新規EXPのGitHub-only保存ポリシー v1

**ポリシーID：`phase2-git-only-v1`。対象は新規EXP-050以降。** EXP-001〜049には新形式を遡及要求せず、元manifestの実績を改竄しない。過去資産の削減は[Issue #397](https://github.com/miyabimm/reconfigurable-rf-lpf-research/issues/397)が別途承認済みであり、現行正式実験・新規G0〜G5を緩和しない。運用権限は[instructions](instructions.md)、明示APIは[Campaignガイド](campaign_workflow.md)。

## 1. A/B/Cの役割

| 区分 | 保持範囲 |
|---|---|
| **A 必須** | main予約済EXP・manifest、RF ID/effective SHA、bands/S2P、source/env/seed/plan、件数/停止理由、代表候補の完全L/C/k/端子/物理列と全6設定Cv、検証状態、元証拠path/SHA・Git HEADからの実byte readback |
| **B 事前選別** | Pareto非劣、30/35dB境界、異なる構造、代表的失敗/未収束等。開始**前**に選別rule/top K・予測保存容量を登録 |
| **C 一時** | 全iteration、無差別raw/heartbeat/cache/大量波形。原則Git管理外`results/`。A/Bの完全保全・G5資格確認前に削除不可 |

失敗・中断・未実行・未収束を削除して成功だけにしない。旧manifestが古いファイルを記録していても、過去の元内容を遡及変更しない。旧原証拠は知見抽出と現役依存判定後に削減可能。

## 2. 正本とファイル構成

```text
experiments/chatgpt_topology_search/runs/EXP-NNN/
  manifest.json          # source / RF条件 / 実行・検証・evidence
  storage_record.json    # 選別rule / stage / SHA・容量 / Git readback
  run_summary.json       # 試行数・未実行・失敗・限界
  checkpoints/<candidate_id>.json
  validation/<evidence>.json  # 対象EXPへ紐付ける独立検証等（必要時）
results/EXP-NNN/        # Git管理外の一時raw
```

- `storage_record.schema_version=1`、`policy=phase2-git-only-v1`、`experiment_id`、`phase=Phase 2`、`stage=planned|running|complete`、`selection`（top_k/retain/rule/estimated_curated_bytes）、`summary`、`checkpoints`、`validation_overlays`、`supporting_evidence`、`git_readback`、`size_exception`、`limitations`。具体的schemaと検証は[audit_new_experiment_storage.py](../scripts/audit_new_experiment_storage.py)と実験保存テストを参照する。
- completeは**A/B証拠の保存完了**で、数値収束・RF合格・独立MNA実施の証明ではない。manifestのexecution.statusとvalidationを別に管理する。unknown/欠損は`preservation_incomplete`とlimitationsへ記す。
- checkpointはcandidate_id、接続/topology、素子L/C/Qと端子、couplings signed k、chip_row、固定値、B71/B12/B28/B13+B14/B26/B8の可変Cを完全保存。条件/evidence SHAをmanifestに紐付ける。
- `data/validation/`の旧182件は#397で退役済み。新規証拠は対象EXPの選別領域へ保存し、**歴史の元manifestや登録済みSHAを保存に合わせて書き換えない**。

## 3. G0〜G5：新規EXPを始めるたびに実施

| ゲート | 必須操作と失敗境界 |
|---|---|
| **G0 予約** | 最新main上の`data/experiment_number_registry.csv`へ番号・ownerを**事前予約**し、branchだけの仮番号では実行しない。必要な台帳と履歴の完全checkoutを確認 |
| **G1 preflight** | RF ID/trial opt-in・effective SHA、bands/S2P、承認source・実import origin・dirty・uv.lock/env、完全vector・seed・Plan/grid・予算、選別/容量を照合。`python scripts/audit_new_experiment_storage.py preflight EXP-NNN`は保存準備の監査 |
| **G2 run** | checkout外`results/EXP-NNN/`にrawを原子的に記録。失敗/unknown/中断も保存し、A/Bの選別までrawを維持。勝手にretry/resumeせず予約費用と実消費を分離 |
| **G3 curate/finalize** | run_summaryへ件数/停止理由・限界、A/B候補の完全vector、元証拠SHA・独立検証の実施/未実施を保存。Git commit後にHEAD:pathの**実byte**を読み戻し、段階ごとの記録を照合。`python scripts/audit_new_experiment_storage.py finalize EXP-NNN` |
| **G4 PR/CI** | `python scripts/audit_new_experiment_storage.py audit`。G0/manifest/index・選別・実byte/SHA・件数・未分類追跡ファイル・容量のFAILを見逃さない。PRレビュー後mainへ保存 |
| **G5 cleanup eligibility** | **最新remote main**でA/B実byte再取得、保存監査・原raw一覧・再開要否を再確認。可否判定は**実削除でない**。欠損/unknown/再開予定があれば保留 |

G5は削除可否の判定のみ。A/Bがremote mainで実byte確認済み、rawが不要で再開予定がなく、担当者が削除対象と残す証拠を確認した場合に限り、Git管理外の当該EXPのCを**別操作で**処分できる。誤分類・保存不完全なら保持する。

正式Campaignを呼ぶ前に[操作ガイド](campaign_workflow.md#3-正式expg0g1を先に満たし明示g2を呼ぶ)のG0/G1を満たす。孤立spotチェックや隔離Git fixtureを、全帯域MNA/本物の正式EXPと呼ばない。

## 4. 容量・例外とCI

- 基準は[data/phase2_git_storage_budget.json](../data/phase2_git_storage_budget.json)：**単一ファイル128KiB超はsoft review、1MiB超は原則拒否、新規EXP一式10,000,000 bytes超はowner明示例外**（size_exceptionに承認者/URL/理由）。tracked全体25MiBは増加傾向の手動監査指標。GitHub公式hard limitではない。
- G4ではmanifest・storage自身もEXP容量に数え、未分類のGit追跡raw、重複/未登録証拠、forced-addされた一時ファイルを拒否する。
- 保存専用と明確に分類できるPR/main pushだけ一般RF/optimizer/runner回帰を省略できる。**全新規EXP監査、番号予約・provenanceテストは常時実行**。unknown/混在/削除/renameは一般回帰へfail-closed。G5のremote照合をCIで代用しない。

## 5. 再現性と科学的昇格の境界

- **候補再評価**には完全L/C/kと全6設定Cv、RF実効SHA・固定S2P・格子・参照面・source情報が必要。**探索再実行**には更にseed/初期値/環境・試行順・ソースdirty実bytes等が必要。**全iterationの厳密再生**は原状態を実保存した場合のみ主張する。
- Formal/trial/旧条件、matching_only/full_lpf、solver収束、strict 30dB／公称35dB、IL≤0.30dB、許容差内、独立MNA・電力/受動性、連続帯域保証は別判定。保存形式PASSをRF適合へ昇格しない。
- 新しい常設テストはRF不変条件・現役共通API・G0〜G5・既知バグ再発防止に限定。使い捨てEXPごとのfixture/大きなrawをGitに追加しない。研究史の旧ファイルは#397の知見選別後に削減可能だが、現行正式記録・重要checkpointの改変は別判断。

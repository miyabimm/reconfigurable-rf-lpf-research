# Campaign操作ガイド（現行schema 2）

本書は**既存の明示APIを人が順に呼ぶ手順**。承認権限は[運用正本](instructions.md)、
RF数値は[registry](../rf/constraints/registry.json)、保存規則は[保存ポリシー](experiment_storage_policy.md)を参照する。
APIの詳細・限定実証は[診断索引](diagnostics/README.md)。本書は別の仕様正本でも実験起動指示でもない。
`run_campaign()` の自動ループは **`not_ready`**。自動AI、watcher、並列Scheduler、retry/resumeは提供しない。

## 1. 入力を分けて凍結する

最新 `main` のコードと正本を確認する。RFは `active_formal_id`、trialは明示opt-in。
[全6設定・28個別区間](../rf/bands.csv)と、選択JSONで指定された固定S2P・SHAを使う。
履歴JSONの論理 `data/...` パスはloaderがbyte同一の `rf/` 実体へ解決し、欠落・SHA不一致はSTOP。
旧EXPの条件SHAを現役SHAへ書き換えない。

| 入力・所有者 | 含めるもの／凍結境界 |
|---|---|
| **研究側のCampaign Plan YAML**（schema_version **2**） | `rf`、`objective: full_lpf`、`definition: null`、`seeds`、`arms`の固定steps/solver/options、Job/Trial sample上限、selection、terminal/dense/anytime格子と費用。`campaign`に総topology数・総RF sample予算・構造cap・独立検査対象。開始前にPlan/SHAを凍結し、途中変更しない |
| **AIのdata-only topology proposal YAML**（schema_version **1**） | `proposal_id`, `based_on_state_sha256`, `reason`, `definition`のみ。最新snapshotのSHAと完全な既存 `CircuitDefinition` データを渡す。solver、予算、seed、RF条件、数値x（L/C/k値）、コマンドは含めない |

現在のCampaignは **1 seed × 1 armの固定ルール**。未来の構造/start/Job一覧をPlanに先取りしない。
`campaign`は `max_topologies / max_rf_samples / structure / independent` を必須とし、
structureは節点数・固定/可変C数、許可L/C種類・role、coupling/IC-fixedの可否を制限する。
RF部品上限を拡張する仕組みではない。`independent`は `not_run`かbounded terminal spotのみ。
terminal検査では `max_candidates` をselectionの `top_k` と一致させ、sample indexを明示する。

**入力例の出典：** schema2の基底フィールドは[静的fixture](fixtures/issue313_preflight.yaml)、
Campaign追加キーとproposal生成例は[Campaign契約テスト](../tests/test_issue325_campaign.py)の
`setup_campaign()` / `proposal()`。これらは開発fixtureであり、承認済み研究予算ではない。
構造は既存dataclass全フィールド（枝順・向き、physical_order、符号付き結合slot、IC-fixedを含む）を保つ。
未知/重複キー・不正型は拒否する。詳細は[入力契約](diagnostics/issue325_campaign.md#入力契約)と
[preflight実装](../src/lpf/search/preflight.py)、[proposal loader](../src/lpf/search/proposals.py)。

## 2. 開発（非EXP）：1提案ずつ提出する

以下は呼出側が `campaign_yaml`、`proposal_yaml`、未存在のcheckout外system tmpパス `output` を用意するAPI例。
`submit`は実RF/solverを実行し得るので、read-only検査と混同しない。

```python
from lpf.search.plan import load_preflight
from lpf.search.campaign import (
    begin_development_campaign, submit_development_proposal, campaign_snapshot,
)

plan = load_preflight(campaign_yaml)  # 静的検査・RF/格子/Plan SHA凍結、RF forwardなし
snapshot = begin_development_campaign(plan, output)
# AIはsnapshotのbased_on_state_sha256を参照して1件のproposal_yamlを作る。
snapshot = submit_development_proposal(plan, proposal_yaml, output)
# 次提案も必ず新snapshotを使う。拒否イベントでもSHAは変わる。
```

経路は **proposal → Controller → 完全start/JobSpec → Worker → raw読戻し → 次snapshot**。
Controllerは単一Sobol点から完全xを生成し、部品/role/全L行列SPD等を検査する（clip・補充・再試行なし）。
JobSpecにはdefinition、start、seed、Plan/proposal/state/source SHAを凍結。
親 `campaign.json` は採否・構造SHA・費用・予約を持ち、proposal元bytesとJob rawも保存する。
次Job capを予約しatomic unknown markerを確定してから実行し、raw実bytes/SHA/費用照合後だけ余剰を返す。
主RFのrequested/completedと独立MNA spotsは別計数。snapshotは読み取り用コピーであり台帳編集用ではない。

この経路はsystem tmp限定・`development_only`で、G0/G1/G2〜G5正式運用を満たさない。
開発rawを名前変更して正式EXPへ昇格しない。固定definition向けの既存CLI `develop` は
[project README](README.md#開発用固定definition-cli)を参照（Campaign CLIではない）。

## 3. 正式EXP：G0/G1を先に満たし、明示G2を呼ぶ

具体的なChatGPT起票の実験IssueとユーザーのPi Code起動が着手指示。
IssueがOpenなだけでは起動しない。追加の本人認証は不要だが、**完全checkout・main中央G0予約・G1は必須**。
通常Pi sparse環境で予約や全履歴auditが可能とはみなさない。

1. 最新mainの中央台帳でEXPを予約・照合する（番号の予測やbranch上だけの予約は不可）。
2. `search.gates.prepare_campaign(plan, experiment_id, owner=..., request_id=..., purpose=..., selection=..., root=...)`
   で当該EXPのplanned manifest/storageを作成。既存EXPは上書きせず、予約・commit/push・RF計算もしない。
   `selection`は保存ポリシー形式の事前選別規則・予測容量。将来の未提出Jobはplanned件数にしない。
3. plannedをmainへ保存後、`campaign_preflight(plan, experiment_id, owner=..., request_id=..., root=...)`。
   main/HEAD/作業木の実bytes、予約、Plan、承認code/lock/env等を照合する。
   planned前のapproved sourceとplanned後のruntime source/HEADは別に扱う。
   `preflight_ready`はread-only技術照合のみ（`execution_allowed=False`）。
4. 着手指示の範囲内で `begin_campaign(plan, experiment_id, owner=..., request_id=..., root=...)`、
   次に `submit_campaign_proposal(plan, proposal_yaml, experiment_id, owner=..., request_id=..., root=...)`
   を1件ずつ呼ぶ。これらは `lpf.search.campaign` のAPI。
   Git ignoredな `results/EXP-NNN/` に正式kindの親/Job/rawを保存する。
   各提出・Worker入口・forward/独立spot直前にもG0/G1を再照合する。HEAD進行も自動rebindしない。

**未検証境界：** 正式APIのテストは隔離Git/架空EXP中心であり、実運用source/import同一性の証明ではない。
正式EXP前には実際にimportされるPython実装と承認ソースの同一性を確認する必要がある。
本ガイド・既存CI PASSをその確認や正式実験の成功実績の代わりにしない。

## 4. G2終了後：G3 → G4 → G5（削除しない）

`lpf.search.preservation` の明示APIを、RF実行とは別に呼ぶ。

| 工程 | 操作と境界 |
|---|---|
| G3 curated | `curate_campaign(experiment_id, root=...)`。親/Job/raw/提案/費用を再照合し、保存規則を弱めず合法出力・完全回路/全6設定Cv・失敗/未収束等をcuratedへ保存。unknown/欠落/未分類/容量超過はSTOP |
| G3/G4 Git保存 | curated diffを人が確認後 `finalize_campaign(experiment_id, root=...)`。当該EXP/indexを2段階commitし、HEAD実byte readback・保存監査。自動pushなし。別途PR・CI・独立レビューを経てmainへ保存する |
| G5 eligibilityのみ | `campaign_cleanup_eligibility(experiment_id, root=..., resume_needed=False, classification_complete=True)`。最新remote mainのA/B実bytes・監査・raw inventory不変等を再確認し、当該EXPの一時C一覧と可否を返す。**実削除なし**。未保全/unknown/再開必要なら不可 |

unknown・中断・source/Plan/raw不一致・保存/読戻し障害では**予約とrawを保持して後続STOP**。
自動retry/resumeや結果の成功扱いは禁止。G4 `complete`は保存完了だけで、solver/RF合格ではない。
詳細は[保存ポリシー](experiment_storage_policy.md#3-運用ゲートexpを開始するたびに実施)と
[保存実装](../src/lpf/search/preservation.py)。

## 5. 最小検証と報告

文書入口/リンク回帰は完全checkoutで以下を実行する。Campaign回帰は通常/sparse CI共通の既存モジュール。
本書の例を新EXPとして実行するコマンドではない。

```bash
uv sync --frozen
uv run --frozen python -m unittest discover -s tests -p test_phase2_current_status_review.py -v
uv run --frozen python scripts/verify_phase2_cleanup_w1_links.py --active-only
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 PYTHONPATH=tests \
  uv run --frozen python -m unittest -v test_issue325_campaign test_issue325_campaign_gates test_issue321_development_cli
# 正式保存監査のみ。完全checkoutの証拠が必要。
uv run --frozen python scripts/audit_new_experiment_storage.py audit
```

現行CIは[通常smoke](../.github/workflows/audit.yml)と[Pi sparse](../.github/workflows/pi-sparse-rf.yml)。
保存専用CIの軽量化は[#332](https://github.com/miyabimm/reconfigurable-rf-lpf-research/issues/332)／[PR #334](https://github.com/miyabimm/reconfigurable-rf-lpf-research/pull/334)でmainへ統合済み。保存専用と確実に分類できる場合のみ一般回帰を省き、全新規EXP保存監査と予約・provenance検証は常時実行する。不明・混在・対象外ファイルは通常回帰へ戻す。

報告はIssue/範囲、branch/HEAD/dirty差分、PR、RF ID/effective SHA・bands/S2P、Plan/提案/start、
予算/格子/seed/環境、requested/completed/reserved、停止理由、保存先と実施チェックを示す。
**ソフトウェア配線PASS／solver収束／strict finite-grid／独立MNAの点数・範囲／G3-G5保存／科学的未検証**を別欄にする。
全6設定・28不連続区間を橋渡しせず評価し、sample予算やsolver nfevを独立検証深度の代用にしない。
独立1 spotは全帯域MNAではない。denseは現Workerで `not_run`。
有限格子PASSでも連続周波数・SRF/Q(f)/EM/公差/実測・物理成立や大域最適性は保証しない。
研究はPhase 2を維持する。

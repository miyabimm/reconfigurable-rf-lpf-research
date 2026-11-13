# Campaign操作ガイド（現行schema 2）

**既存APIを明示的に順に呼ぶ操作手順。** 承認と着手は[運用正本](instructions.md)、G0〜G5の保存規則は[保存ポリシー](experiment_storage_policy.md)、正式RF数値は[registry](../rf/constraints/registry.json)。`run_campaign()`自動ループは`not_ready`で、AI自動起動・scheduler・parallel・retry/resumeは未提供。

## 1. 入力を分けて凍結する

| 入力 | 契約 |
|---|---|
| 研究側Campaign Plan YAML（schema_version **2**） | RF ID/実効SHA、`objective: full_lpf`、`definition: null`、seed、1 seed×1 arm固定steps/solver、Job/Trial予算、selection・terminal/dense/anytime格子、`campaign`の総topology/sample上限・構造許可範囲・独立検証上限を開始前に凍結 |
| AIのdata-only proposal YAML（schema_version **1**） | `proposal_id`、`based_on_state_sha256`、`reason`、完全な既存`CircuitDefinition`の`definition`のみ。solver・予算・seed・RF条件・L/C/kの数値vector・コマンドは含めない |

- RFはactive formal、trialは明示opt-in。6設定／28の**不連続**区間・UL/DL/H2/H3と固定S2PをSHA照合。旧EXPの実効SHAを現役の制約に読み替えない。
- `campaign.max_topologies/max_rf_samples/structure/independent`は必須。structureは節点・L/C数・役割・結合/IC-fixedの可否を制限する。independentは`not_run`か上限つきterminal spot、対象数は`selection.top_k`と一致。未知/重複キー、不正型を拒否する。
- 旧条件パス`data/...`は[constraint_versions.py](../src/lpf/constraint_versions.py)で現役`rf/`実体へ解決し、欠落/SHA不一致はSTOP。サンプル数は全区間と選別・独立観測を明示して予約する。
- **step格子 #363**：`arms[].steps[].stop_points_per_interval`（任意、整数2以上）はH2/H3だけの点数を変更し、UL/DL・固定追加区間・S2P・terminal/dense/anytimeは不変。通常2/阻止3では28+21+21=**70 samples/forward**。各区間端点を含みB13/B14は分割を維持。Hybrid(sum)は残差二乗和なので56点の目的値と単純比較できない。格子切替はstep間のみ。
- 開発fixtureは[issue313_preflight.yaml](fixtures/issue313_preflight.yaml)と[Campaign契約テスト](../tests/test_issue325_campaign.py)。実験承認済みPlanではない。APIの実契約は[preflight.py](../src/lpf/search/preflight.py)・[proposals.py](../src/lpf/search/proposals.py)を確認。

## 2. 開発（非EXP）：1提案ずつ提出する

呼出側が`campaign_yaml`、`proposal_yaml`、checkout外の未存在system tmpパス`output`を用意する。`submit`は**実RFとsolverを実行し得る**。

```python
from lpf.search.plan import load_preflight
from lpf.search.campaign import begin_development_campaign, submit_development_proposal
plan = load_preflight(campaign_yaml)  # 静的検査のみ
snapshot = begin_development_campaign(plan, output)
# AIは最新snapshotのbased_on_state_sha256へ1件だけ提案する
snapshot = submit_development_proposal(plan, proposal_yaml, output)
# 拒否でも状態SHAは更新。次の提案には新snapshotを使う。
```

- 経路：proposal→Controller（Sobol 1点から完全x、clip・補充なし）→Gates/JobSpec→Worker→raw再読込→次snapshot。
- Definition・全L/C/k・物理列、SPD/role、Plan/proposal/seed/state/source SHAと予算を固定する。Job予約/unknown markerを先に永続化し、実byte/SHA照合後だけ残予算を返す。
- 開発は`development_only`でG0/G1〜G5の正式EXPではない。固定definition CLIは[project README](README.md#開発用固定definition-cli)を参照。

## 3. 正式EXP：G0/G1を先に満たし、明示G2を呼ぶ

具体的Issue範囲とユーザーのPi Code起動を着手指示とし、追加のowner認証を求めない。ただし**完全checkout・main中央番号予約・remote main/G1の実ソース照合は省略不可**。

1. 最新mainの[中央番号台帳](../data/experiment_number_registry.csv)でEXPを**事前予約**し、登録ID/ownerを照合。branchだけの仮番号では計算しない。
2. `lpf.search.gates.prepare_campaign(plan, experiment_id, owner=..., request_id=..., purpose=..., selection=..., root=...)`でplanned manifest/storageを生成し、mainへ保存。既存EXPの上書きや予約・RF計算は行わない。
3. `campaign_preflight(plan, experiment_id, owner=..., request_id=..., root=...)`でmain/HEAD/実byte、Plan、承認されたcheckout/import origin・環境・予約を照合。`preflight_ready`はread-onlyで、実行許可そのものではない。
4. 指示範囲で`lpf.search.campaign.begin_campaign(plan, experiment_id, owner=..., request_id=..., root=...)`、続いて`submit_campaign_proposal(plan, proposal_yaml, experiment_id, owner=..., request_id=..., root=...)`を**1件ずつ**呼ぶ。
5. G2 rawはcheckout外のGit無視`results/EXP-NNN/`へ原子的に保存。提出時・Worker入口・forward/独立MNA直前にもG0/G1を再確認し、HEAD進行で勝手にsourceを付け替えない。

origin検証は別checkout・検索パス混入を拒否する限定的配線であり、改変されたメモリ上コード・bytecodeを証明しない。正式運用は承認checkoutの新規Pythonプロセスで行う。実Campaignの成功実証は未完了。

## 4. G2終了後：G3 → G4 → G5（削除しない）

| ゲート | 操作とSTOP条件 |
|---|---|
| G3 curated | `lpf.search.preservation.curate_campaign(experiment_id, root=...)`。親/Job/raw/提案/費用のSHA・分類・容量を確認し、完全ベクトル/6設定Cv、失敗/未収束も選別保存。不明/欠落/容量超過はSTOP |
| G3/G4 Git保存 | `finalize_campaign(experiment_id, root=...)`。EXP/indexを2段階commitし、実byte readback/保存監査。**自動pushなし**。PR・CI・独立レビューでmain反映 |
| G5 eligibilityのみ | `campaign_cleanup_eligibility(experiment_id, root=..., resume_needed=False, classification_complete=True)`で最新remote mainのA/B実bytesとraw不変を照合し、一時Cの削除**可否だけ**を返す。実削除はしない |

unknown/中断/不一致では予約とrawを保持してSTOP。自動retry・resumeや成功への丸めをしない。`complete`は保存完了で、solver収束・strict RF PASS・独立MNAを意味しない。

## 5. 検証と報告

```bash
uv sync --frozen
uv run --frozen python scripts/verify_phase2_cleanup_w1_links.py --active-only
PYTHONPATH=tests uv run --frozen python -m unittest -v test_issue325_campaign test_issue325_campaign_gates test_issue321_development_cli
uv run --frozen python scripts/audit_new_experiment_storage.py audit
```

通常CIは[audit.yml](../.github/workflows/audit.yml)。保存専用変更でも新EXP保存・番号・provenance監査は必須、不明/混在差分は一般回帰へ戻す。
報告はIssue/承認範囲、HEAD/dirty、RF ID/実効SHA・bands/S2P、Plan/proposal/seed・grid/費用・環境、requested/completed/unknown、保存証拠SHAと各G0〜G5を区別する。solver収束／strict有限格子／独立MNAの点数と範囲／未実施項目を別に示す。
全6設定・28区間/H2/H3、SPD・受動性・電力保存・固定S2Pを維持する。独立1 spotは全帯域検証ではなく、有限格子PASSは連続帯域・Q(f)/SRF/EM/公差/実測の保証ではない。研究はPhase 2継続。

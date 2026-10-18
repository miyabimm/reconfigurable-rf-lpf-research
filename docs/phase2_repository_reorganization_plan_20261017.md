# Phase 2：リポジトリ整理計画（2026-10-17）

> **後日の完了状況（2026-10-17）：** 本書は策定時点の未実施計画として原文を保存する。Step 1～5の実装・統合検証は[PR #71](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/pull/71)でmainへマージ済み（`055b222c79c73c7fbeacb19383f21c1da0625195`）。不要文書の削除を含む追加整理は[PR #72（Draft）](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/pull/72)で計画中。以下の「未実施」は**計画を作成した当時の記述**であり、現行の実施状況ではない。

> **状態：整理計画のみ／未実施。** 本文の作成は研究の新規実行・最適化・原本移動・削除・RF仕様変更を意味しない。実施前にはmainの最新コミットと監査結果を再確認する。
>
> **適用フェーズ：Phase 2継続。Phase 3は所有者の明示承認まで停止。**
>
> **長期保管方針：GitHub-only。** 外部アーカイブや期限付きGitHub Actions artifactを研究成果の唯一の保存先にしない。重要な証拠をGitの追跡対象として選別保全する。
>
> **対象：** `MasayaTakagi/reconfigurable-rf-lpf-research`。作成時のmainの直近確認コミットは `bdb39904379637aeca5cf56ec3096e9e1b15f62a`（2026-10-17、パレートスナップショットへのロードマップ追記）。

## 1. 目的と非目標

目的は、**現行の制約・候補・パレート解・検証状況に短い導線で到達でき、旧研究の原証拠と再現性を失わない構成**へ段階的に整理すること。

1. READMEから現行正式条件、試験条件、最新パレート、現行課題、研究フェーズが分かる。
2. 3L/4L、面積、IL、H2/H3、トポロジー、部品数、実験ID、原ベクトル、検証状態で候補を検索できる。
3. 「正式／試験／旧仕様」「実行済み／未実行／未収束」「有限格子／独立MNA／物理検証」を混同しない。
4. 既存のrunと検証原本は、Git blob・SHA・実験ID・検証overlayから追跡できる。
5. 新しい実験が増えても保存場所、索引、成果昇格、監査のルールが明確である。

非目標：本計画の保存に伴う新規EXP採番、RF-F003やRF-T005の変更、新規最適化、Phase 3移行、旧ブランチ削除、Git履歴書換え、既存研究原本の無断移動・削除。最新パレートを大域最適性・物理保証とみなすこともしない。

## 2. 現状の確認結果と重要な基準

### 2.1 制約・研究状態

- 運用指示の正本：[chatgpt_project_instructions.md](chatgpt_project_instructions.md)。
- 数値制約の正本：[`data/constraints/registry.json`](../data/constraints/registry.json) が指定する **RF-F003** と [正式制約JSON](../data/constraints/formal/RF-F003.json)。[`data/design_constraints.json`](../data/design_constraints.json) は互換コピーであり削除しない。
- 周波数帯の正本：[`data/bands.csv`](../data/bands.csv)。外部入力・出力固定寄生S2Pは [`data/parasitics/`](../data/parasitics/) に保存され、RF-F003のSHA-256指定を維持する。
- [RF-T005](../data/constraints/trial/RF-T005.json) は **RF-F003ベースで可変Cの最大枝数のみ2→3に緩和した試験条件**。正式版に自動昇格しない。
- 研究はPhase 2。実際の外部S2Pは回路図に基づくモデル由来であり実測ではない。Q(f)、SRF、EM、温度・公差、製造・量産・実測や連続帯域極値の検証状態を区別する。

### 2.2 現在のパレート成果

- 2026-10-17保存の [RF-T005 / RF-F003パレート比較](pareto_rf_t005_rf_f003_20261017.md) と [機械可読スナップショット](../data/pareto_snapshots/rf_t005_rf_f003_20261017.json) を**整理前の固定基準**とする。
- RF-T005は保存済み非支配候補 **6点**（面積3～6、IL 0.944268～0.805149dB）。正式RF-F003は **4点**（面積4⅔～6⅔、IL 0.882647～0.833188dB）。主な完全ベクトル・検証出典はEXP-042/043/045/047。
- いずれも「既存の探索で発見され、H2/H3必須30dBを有限格子で満たす候補集合内のbest-found」であり、数学的な全域パレート最適性を意味しない。公称35dB・IL≤0.30dBは未達。
- 比較表での **EXP-047の4GJM候補**は原独立検証JSONの`chip_area=6`が誤記であり、正しくは **6⅔**。元証拠を改竄せず訂正根拠を別管理する。

### 2.3 情報構造上の課題

| 優先 | 課題 | 対応 |
|---|---|---|
| P0 | [ルートREADME](../README.md)冒頭が2026-10-15/RF-F002当時の現況で、後続の正式RF-F003より古い | 短い現行入口と過去時点の説明を分離 |
| P0 | [旧研究候補台帳](../data/research_candidate_register.csv) と最新 [パレートスナップショット](../data/pareto_snapshots/rf_t005_rf_f003_20261017.json) が別系統 | 出典を保った共通索引・スナップショット生成方法を設計 |
| P1 | [roadmap](roadmap.md) が日付付き追記で長文化し、現在のタスクを判別しにくい | 現況／次アクション／履歴へ責務分割 |
| P1 | 実験フォルダ、validation、旧PR原資料、README内リンクが複雑 | path・blob SHA・参照元の逆引きを先に完成 |
| P2 | 各種文書、監査、探索／検証スクリプトの用途が一目で分からない | 用途別目次・配置規則を導入 |

**注意：最新treeの全ファイル数はこの計画時点で未再計測。** 2026-10-15に [保存最適化レビュー](phase2_repository_optimization_review_20261015.md) が記録した731 tracked path / 8,449,154 Bは過去基準であり、2026-10-17現在値として流用しない。同監査では研究対象535ファイルを不変60・参照あり429・要レビュー46に分類し、46件すべて削除・移動未承認。46件の内訳は [証拠レビュー](phase2_evidence_triage_20261015.md) と [台帳](../data/research_storage_triage.csv) を参照。

## 3. 保全区分（全ファイルに付与する属性）

| 区分 | 対象例 | 保存・整理原則 |
|---|---|---|
| **A：不変正本** | 正式・試験RF制約、bands、外部S2P、実験番号台帳、元checkpoint、原manifest、出典SHA | 原則移動・変更・削除しない。正本pathを維持 |
| **B：現行研究成果** | RF-F003/RF-T005代表候補、パレート、完全ベクトル、独立検証サマリー | 入口と横断索引を整備。原実験証拠は単一出典を参照 |
| **C：研究履歴** | RF-F001/F002・RF-T004結果、旧LPF候補、過去の失敗例、計算環境・訂正記録 | 条件・日時・検証深度を明記してアーカイブ索引から参照 |
| **D：意味の確認が必要** | 未参照扱い46ファイル、同一blobの別path、旧runのlock/log/task、元PR資料 | 原因・復元用途・参照と原コミットを確認するまで保持 |
| **E：新規runの一時出力** | 各iteration dump、キャッシュ、再生成可能な大量グリッド、完了後の空lock等 | 原則Git管理外 `results/`。重要証拠に当たる例外は明示採用 |

`uv.lock`は環境再現の正本であり、runの`.lock`とは区別する。同一Git blobの別pathであっても、run出所・証拠の役割・相対参照が異なるなら自動削除しない。逆に、今後の新規runでは未選別の生出力を無差別にコミットしない。

## 4. 目標ディレクトリ構造（提案・未作成）

```text
reconfigurable-rf-lpf-research/
├── README.md                           # 現在の入口・最短ナビ
├── pyproject.toml / uv.lock / requirements.txt
├── docs/
│   ├── README.md                       # 文書の総合目次（新規）
│   ├── chatgpt_project_instructions.md # 運用正本・既存path維持
│   ├── specification.md                # 設計仕様・既存path維持
│   ├── roadmap.md                      # 現行ゲート・既存path維持
│   ├── current/                        # 状況・未解決事項の短い解説
│   ├── results/                        # パレート・トポロジー比較の読み物
│   │   ├── README.md
│   │   ├── pareto/
│   │   └── topology_comparison/
│   ├── methods/                        # 回路・数値計算方法
│   ├── governance/                     # 番号予約・保管ルール
│   └── archive/                        # RF-F001/F002等の歴史文書
├── data/
│   ├── README.md                       # データ正本と索引の案内（新規）
│   ├── bands.csv
│   ├── design_constraints.json         # 正式条件の互換コピー
│   ├── constraints/                    # registry・正式・試験
│   ├── parasitics/                     # S2P原本・固定path
│   ├── pareto_snapshots/               # 日付付き不変の成果
│   ├── catalog/                        # 将来の候補・実験索引／案内
│   └── validation/                     # 元検証証拠・原則path維持
├── candidates/                         # 既存・歴史候補
├── experiments/
│   ├── README.md                       # EXP索引（新規）
│   └── chatgpt_topology_search/runs/   # EXP-NNN元原本・path維持
├── src/lpf/                             # 共通MNA等のライブラリ
├── scripts/                             # 探索・検証・監査、README索引追加
├── tests/                               # 回帰検査
└── .github/workflows/                   # CI・予約・研究ワークフロー
```

この段階では**物理的な大規模移動を前提にしない**。まず目次・索引を追加し、証拠・参照・CI上の固定pathを調べたうえで必要な文書のみ段階移設する。上記の新設先は提案名であり、確定済み配置ではない。

## 5. 最新候補の管理統合

### 5.1 一意な情報経路

```text
README（現況）
  → docs/results/README.md（条件・構成別の見取り図）
    → データ候補台帳（検索・比較用）
      → data/pareto_snapshots/...（日時固定）
        → EXP-NNN/checkpoint（完全L/C/k・全6設定Cv）
          → manifest、実行コードSHA、独立検証、訂正overlay
```

- 既存の [research_candidate_register.csv](../data/research_candidate_register.csv) と [候補生成スクリプト](../scripts/report_research_pareto.py) の契約を調べ、別の正本候補台帳を無計画に増やさない。移行中は互換性を維持する。
- 今回の10件は`constraint_class/constraint_id/effective_constraint_sha256`、`objective=full_lpf`、H2/H3要求30dB、`strict_finite_grid`などの分類と検証深度に基づいて追加候補として紐付ける。RF-T005と正式RF-F003のパレートを一つに混ぜない。
- 必須メタデータ：候補ID、EXP/run/stage、Lの種類・本数、GJM/PCB-C/可変C数、接続と物理列順・結合符号、チップ面積、最悪IL、H2/H3、元完全ベクトル（全設定Cv）、元blob SHA、使用制約/帯域/S2P/コードSHA、実行状態、収束状態、格子分解能、独立MNAの照合範囲、物理未検証事項。
- データが不足した候補は`reported_only`、`source_unknown`等を明示し、完全checkpointがないのに「再現済み」へ昇格しない。
- 数値の訂正は原ファイルを上書きせず、出典付きの訂正レコードと表示値の選択規則により表現する。
- Paretoレポートは制約ID・ハッシュ・目的・減衰要求・成立分類を揃えて算出する。比較格子／検証深度が異なる場合は厳密な優越関係の保証を控える。

### 5.2 スナップショットの扱い

2026-10-17の [JSON](../data/pareto_snapshots/rf_t005_rf_f003_20261017.json) と [説明文書](pareto_rf_t005_rf_f003_20261017.md) は研究の固定チェックポイントとして残す。候補が後に追加・改善されても既存記録を「最新値」で上書きせず、新たな日時・条件に紐づくスナップショットを追加する。

## 6. 実施ステップ、成果物、完了ゲート

### Step 1 — 最新main棚卸し・依存関係監査（最初に実施）

- main SHA、再帰tree（切り詰め有無含む）、追跡path、サイズ、blob SHA、参照元、保全区分、実験ID、正本／派生関係を確定する。
- [build_reference_inventory.py](../scripts/build_reference_inventory.py)、[triage_unlinked_evidence.py](../scripts/triage_unlinked_evidence.py)、既存監査台帳を再利用。README内相対リンク、設定ファイル、テスト、workflows、原manifest、ソース内ハードコードパスも対象とする。
- 10月15日既存46件の採否を新mainベースで再レビュー。**レビュー対象＝削除可能ではない**。
- 成果物：整理対象台帳（現パス、提案先、保全理由、参照元、SHA、処置、リスク、承認要否）＋棚卸しサマリー。
- 完了ゲート：最新追跡ファイルの集計が再現可能、参照破壊リスクが抽出済み。ここでは移動・削除を行わない。

### Step 2 — README・ドキュメント導線の整理

- ルートREADMEは現行RF-F003、RF-T005試験、Phase 2、保存済みパレート、未解決課題、各フォルダへの最短導線に絞る。
- `docs/README.md`、`docs/current/phase2_status.md`等の目次・現況文書を追加。
- `docs/roadmap.md`は正本pathを維持して現行ゲートを先頭に明示し、古い計画を日付付き履歴へ案内する。当時の文書を現在の事実へ一括書換えしない。
- 成果物：現行入口・説明目次。完了ゲート：現行仕様／候補／未完課題の参照が数クリックで可能、全MarkdownリンクPASS。

### Step 3 — RF候補・Pareto索引の統合

- 最新10候補と旧14件など既存登録候補の一意ID・比較条件・原checkpoint・検証参照を突合。
- 既存の候補台帳と`report_research_pareto.py`を拡張する際は、旧スキーマ互換・新旧条件分離・原値の検証をテストする。
- 候補の独立MNA・有限格子・収束・実装評価を別属性として表現。未検証項目は未検証のまま保持。
- 成果物：条件別候補検索とパレート生成結果。完了ゲート：スナップショット10件の数値・出典が一致し、RF-T005とRF-F003を混合しない。

### Step 4 — 歴史文書・重複候補の整理

- 文書は現行・手法・運用・履歴へ分類。動かすときは旧path／新path／blob SHA／全参照更新を記録する。
- `experiments/`、`data/validation/`、`candidates/`の原証拠は原則そのまま。古い実験の「元実行」と「後日独立検証」を区別する。
- 同一内容コピー、source snapshot、run lock/log/taskは、実験再開・出典復元の役割を見て個別判断。削除・branch整理は別レビュー・所有者承認。
- 成果物：履歴索引と個別保全判定。完了ゲート：候補・実験から歴史証拠へ追跡できる。

### Step 5 — CI・参照整合・保全結果の検査

- [Phase 2 regression](../.github/workflows/audit.yml) に既存のRF回帰、候補・EXP番号・証拠・ストレージ監査を維持する。
- 移動を伴うPRでは、全リンク／元manifest／候補台帳／コード内path／workflow参照の整合、原ファイルのbyte等価性、Git blob SHAと指定SHA-256を照合する。
- 重要なRF数値を再計算する場合は、整理監査の再評価と新規研究探索を分離し、検証器・格子・条件を明記する。
- 成果物：変更前後パス表、CI結果、保全レポート。完了ゲート：全既存回帰PASS、データ消失と条件混同なし。

## 7. 更新の運用規則

- **1 PR = 1主目的**（棚卸し／文書ナビ／候補統合／履歴移設／監査）。最初に読み取り専用の棚卸しPRを推奨する。
- 新規実験は新規EXPを **mainの実験番号台帳へ事前予約し照合PASS後**に着手する。整理作業だけで新EXPを消費しない。
- 生runはまずGit管理外の`results/`で管理。GitHub-only保全に適する重要な完全ベクトル・実行条件・再評価根拠を選別コミットする。
- 新しい正本の重複を作らない。旧APIや既存相対パスの互換は必要に応じて維持し、削除前に読取り側を移行する。
- 既存の保全レビュー [2026-10-15](phase2_repository_optimization_review_20261015.md) と [保存方針提案](experiment_result_storage_policy_proposal_20261015.md) を参照する。後者は段階導入中の**提案**であり、全項目実装済みとはみなさない。

## 8. 明示承認を要する事項

1. mainへのPRマージと、リポジトリの運用ルールを確定的に変える判断。
2. 原証拠・歴史的manifest・checkpointを移動／削除する判断（参照再生検査と別レビューが前提）。
3. ブランチやtagの削除、Git履歴rewrite／force push。
4. RF正式制約の変更、trialの正式化、研究Phase 3への移行。

**本計画の保存時点では、整理の実施・移動・削除・新規実験をいずれも行わない。**

## 9. 完成後の閲覧入口

| ユーザーが知りたいこと | 入口 |
|---|---|
| 現在の研究状態 | `README.md` |
| Phase 2次の課題 | `docs/roadmap.md` |
| 現行パレート・3L/4L代表 | `docs/results/README.md` → 条件別候補索引 |
| 正式RF条件 | `data/constraints/registry.json` |
| 元のL/C/k・全設定Cv | 候補索引 → `experiments/.../EXP-NNN/` |
| 実験と実行状態 | `experiments/README.md` → EXP原manifest |
| 古い研究 | `docs/archive/` の目次 |
| スクリプトの用途 | `scripts/README.md` |
| 未解決課題 | `data/research_review_issues.csv` |

**最初の着手判断：Step 1の最新main全ファイル棚卸しから実施する。** その結果を根拠に移動候補と保全対象を確定し、その後に段階的な構造整理を行う。

---

## 2026-10-17 Step 1実行追補（計画の進捗）

**Step 1：実行済み（自動棚卸し・一次保全分類・代表的原証拠照合）。** 監査対象main SHAは `bdb39904379637aeca5cf56ec3096e9e1b15f62a`。

- [全追跡ファイル・参照監査レポート](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/blob/d0351e507dd9fd39338f7e4a69c2003bae3d531f/docs/repository_audits/step1_20261017_report.md)：1,043ファイル、12,859,345B、静的参照2,943、同一Git blob34組、A66/B717/C214/D46。
- [機械可読集計・分割CSV](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/blob/d0351e507dd9fd39338f7e4a69c2003bae3d531f/data/repository_audits/step1_20261017_summary.json)：全ファイル、依存辺、同内容blob、未解決リンクの逆引きデータ。
- [事後ソース照合と既存CI課題](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/blob/d0351e507dd9fd39338f7e4a69c2003bae3d531f/docs/repository_audits/step1_20261017_review_notes.md)：リンク候補2件（実文書の修正候補1、テスト用フィクスチャ1）。既存Phase 2 regressionはEXP-047 manifest形式の監査エラーで失敗。Step 1専用監査の実施・保存と全CI PASSを混同しない。
- RF-F003互換コピー、2つのS2P SHA256、パレート10候補の元完全ベクトルblob SHAは照合PASS。静的抽出外の動的参照、履歴全体、削除可否の最終判断は未実施。
- **元研究ファイルの移動・削除は0件、RF制約変更は0件、新規EXP・新規最適化なし。Phase 2継続。**

次のステップは **Step 2：README・文書導線の整理**。ただし既存CI異常は別ゲートとして修復計画と検証を要する。

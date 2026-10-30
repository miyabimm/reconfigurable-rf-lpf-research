# Pi Codeの通常作業範囲

Piの通常作業は `project/`・`rf/`・`src/`・`scripts/`・`tests/`・`.github/` とリポジトリ直下ファイルで行う。
`docs/`・`data/`・`experiments/` は通常ローカルに取得しない。過去のEXP再検証・全研究証拠の監査は、これらを明示的に取得した**別の完全検証環境**で行う。

```bash
git clone --filter=blob:none --depth=1 --sparse https://github.com/miyabimm/reconfigurable-rf-lpf-research.git
cd reconfigurable-rf-lpf-research
git sparse-checkout set --cone project rf src scripts tests .github
```

- 現行の正式・試験RF入力は `rf/constraints/`、全28区間は `rf/bands.csv`、固定S2Pは `rf/parasitics/`。
- `rf/constraints/registry.json` の `active_formal_id` が現行正式版。承認済みJSONは**上書きしない**。新正式条件は所有者承認後に新IDとして追加し、active指定を変更する。trialは自動昇格させない。
- 不変の旧RF JSON内の `data/...` は**保存時の論理パス**であり、`src/lpf/constraint_versions.py` が新 `rf/` 実体へ解決する。JSON内容・実効SHA・S2P SHAは維持する。ファイル欠落やSHA不一致時は失敗させる。
- 各EXPの原manifest、重要証拠、番号台帳は従来の `experiments/`・`data/` に保全する。通常のPi sparse環境で新EXPの番号予約・保存監査が可能とはみなさない。着手は[運用正本](instructions.md)のIssueスコープとユーザーのPi Code起動指示に従い、完全checkoutでG0/G1を満たす（追加の二重承認は不要）。
- Piの最低限の作業ツリーテストは `.github/workflows/pi-sparse-rf.yml`、全履歴・保存監査は通常の完全CI／個別実行とする。CI PASSは新RF性能の科学的保証ではない。

## 限定1-start driver（RF-T005 / RF-T008 rev3・合法3L/4L）

`scripts/run_phase2_shared.py` の `prepare_one_start` / `one_start_gate` は引き続きread-only。
実験Issueの具体的スコープとユーザーの起動指示があるときだけ、別関数
`scripts.run_phase2_one_start.run_one_start(root, experiment_id, **one_start_args)` を明示的に呼ぶ。
`one_start_args` は `prepare_one_start` と同一のG0/G1・回路・完全vector・seed・v2予算・格子引数。
全検査後に既存 `run_c1_staged(..., optimize_stage=scipy_slsqp_stage)` を1 startだけ実行する。
回路は既存 `TopologySpace` / `enumerate_topologies` の候補または明示的な
`CircuitDefinition` を使い、条件別 `build_nominal_circuit` の合法性検査と完全なplanned入力照合を通す。
RF-T005とRF-T008 rev3だけを実driverで許可し、T007（共通モデルには残す）・未知trial・F003/T006、
異なるdefinition/vector/policy SHAの混同、一般multistart、独自予算は拒否する。
T008のIC固定Cは設定共通・Q60、可変Cは6設定・Q35の別部品として同端子に保持する。
Cvar=0でも固定Cは残り、容量合算や単一Qへの置換はしない。

- 完全checkoutの予約済みplanned manifestと、既存保存形式のplanned storage recordが必要。
  選別は事前に `top_k=0, retain=["pareto"]` とし、ruleでchecked Pareto選別と全除外診断の保持を明記し、容量を見積もる。
- 格子は各不連続区間の1/2/3点**診断限定**。研究上の評価条件と主張の範囲は後続実験Issueで固定する。
- 任意の `timeout_seconds` はstage境界での協調停止でありSciPy内部を強制停止しない。
  `results/EXP-NNN/STOP`、例外、KeyboardInterruptでも別startへ自動再試行しない。
  外部killでは直前の原子的raw snapshotを残す。既存rawがあれば再実行を拒否し、人手で調査する。
- rawと各stage記録はGit管理外 `results/EXP-NNN/run.json` に、選別候補／全除外理由は既存EXP形式へ保存する。
  保存diff確認後、`finalize_one_start(root, experiment_id)` を**別途明示的に**呼ぶと、そのEXPのみをcommit、
  実HEAD byte読戻し、storage record確定commit、既存finalize/auditを行う。pushやraw削除は行わない。
  未開始・未分類partial・読戻し／容量監査失敗は `preservation_incomplete` のままrawを保持する。
- Git保存PASSはRF科学PASSではない。独立MNA/power/dense/物理/連続帯域は `not_run`、候補昇格は禁止。
  `optimize_stage` の注入は隔離テスト用で、実SciPyとは異なる実行種別を記録する。実験実行はコードレビューとは別判断。

### 複数回路研究の次回Issueで固定するもの

1. ChatGPT回路案＋有限列挙から候補を提案し、事前selectionと条件を固定する。
   候補総数・条件別件数、各stage予算（標準v2）、seed、完全vector、格子、容量、停止条件、
   比較可能な証拠深度を次回実EXP Issueに記載する。この実装自体は実験実行許可ではない。
2. **1回路・1 start・1 EXP**。完全checkoutの最新mainで候補ごとにG0正式予約を確定し、
   G1 planned manifest/storageをmainへ統合する。実行ソース・環境・入力SHAの一致を確認してから、
   Issueスコープとユーザー起動指示に従ってG2実SciPyを呼ぶ。バッチ／自動次候補実行は提供しない。
3. G3/G4で候補ゼロ・失敗・未収束も含めGitHubへ証拠保存する。既存raw、入力／環境／ソース不一致、
   非法構造、STOP、timeout、例外、容量／readback／audit失敗時は停止・証拠保持し、自動再試行しない。
4. 保存済みIL/H2/H3、部品／box違反、数値失敗、面積、回路多様性からPi Codeが次の構成を提案できる。
   **次EXPは別途定義・条件を固定してから起動**し、実験途中のdefinition／制約／生rawを書き換えない。
   比較は同一条件ID・実効SHA・参照面・格子・検証深度内だけとし、T005群とT008群を混合しない。

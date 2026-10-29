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

## 限定1-start driver（RF-T005・既存3Lのみ）

`scripts/run_phase2_shared.py` の `prepare_one_start` / `one_start_gate` は引き続きread-only。
実験Issueの具体的スコープとユーザーの起動指示があるときだけ、別関数
`scripts.run_phase2_one_start.run_one_start(root, experiment_id, **one_start_args)` を明示的に呼ぶ。
`one_start_args` は `prepare_one_start` と同一のG0/G1・回路・完全vector・seed・v2予算・格子引数。
全検査後に既存 `run_c1_staged(..., optimize_stage=scipy_slsqp_stage)` を1 startだけ実行する。
未対応trial/formalや別レイアウトへの転用、一般multistart、独自予算は拒否する。

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

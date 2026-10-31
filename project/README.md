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

## Issue #231：多start準備・mock比較（本番EXPなし）

`lpf.phase2_models.multistart` は既存1-start driverとは別の**synthetic専用**経路。
`generate_starts(SampledEpigraph(circuit, 2), nominal_vector, seed=23)` で、
同一schema/接続の設計値1本＋scrambled Sobol 2本を順序固定で返す。
Sobolは16点の固定blockを一度だけ検査し、合法な異なる3本を確保できなければ理由付き停止。
open lower boundにepsilonを足すことも、設計値の自動clipも行わない。
Q・全6設定Cv・IC固定C併設・signed k・全L行列SPD・接続roleは既存policy/APIで検査する。
各startは完全vector、seed、生成法、Sobol index、RF/definition/schema/vector SHA、C1記録を保持。
互換warm startは `warm_checkpoint` と期待するファイル `warm_sha256` を両方指定した場合だけ
設計値を置換する。JSONの `policy_id/policy_sha256/definition_sha256/parameter_schema/vector/vector_sha256`
を照合する（既存 `CandidateRecord` の対応列を利用可能）。別接続の単純射影は行わない。
歴史的checkpointをこの形式へ遡及書換えしない。

`run_multistart_preview(circuit, generated, temp_checkpoint, optimize_stage=mock,
historical_benchmarks=benchmarks, max_new_starts=None)` は既存 `run_synthetic` と
`run_c1_staged` を使用し、coarse2/fine3点・v2予算を不変更でdispatchする。
checkpointはリポジトリ外のsystem temp限定。既存rawの読戻し、中断marker、callback失敗後の
後続start停止を維持し、自動再試行しない。`max_new_starts` は正常なstart境界での停止のみ。
中断結果不明は例外とmarkerで保持し、成功・未開始へ丸めない。実SciPy接続・EXP exportは提供しない。

`unique_topologies` は構成リストのexact key重複だけを除去する（同一構成のstart/vectorは消さない）。
`two_axis_report` は既存CandidateRecordの再検査/厳密30dB判定/Pareto群を流用し、収束・部品/box/role/SPD・
IL/H2/H3・面積fraction・実効SHA・格子・検証深度を別列で保持する。
`finite_grid_eligible` は有限格子適合の意味のみ。境界直下値も丸めや許容誤差でPASSにしない。
syntheticと実SLSQPの比較群は混在しない。診断候補の理由・値も残し、RF認定・正式Paretoへ昇格しない。
`historical_benchmarks` は必須で、source、policy_id/SHA、objective、reference_planes、grid、validationと
保存済み数値を渡す。同一条件以外は拒否し、歴史的1001点値は常時**外部参照**として表示するだけで粗格子と順位付けしない。
完全checkoutでは `data/pareto_snapshots/rf_t008_exp062_exp063_exp064_cross_pr_20261020.json` の
`observed_nondominated` を出典SHA・manifest条件/格子/深度とともに使えるが、snapshot中の過去のDraft状態は
当時の記録であり現在の状態へ書き換えない。Pi sparse環境では履歴取得なしに比較PASSを主張しない。

`intermediate_scan(circuit, vector)` は既存forward evaluatorによる6設定/28個別区間×17点のread-only診断。
構成/値/入力/ソースSHAを保持し、CandidateRecordの1/2/3点制約は変更しない。
SPD/部品検査と、未実施の最終1001点・独立MNA84点・電力収支/受動性の `not_run` は別。
同じ端点で歴史値と一致してもdense再実行や連続帯域保証を意味しない。

### 次回本番の予算案（未承認・未実行）

RF-T008 rev3 / full_lpf、面積<=4の3L0GJM・3L1GJM・4L0GJMを提案対象とし、
Piの回路理論案＋既存TopologySpaceで多様性を確保する。20構成の固定列挙を要求しない。
Stage A 20構成×3start=60 → Stage B 上位5構成×**追加**5=25 →
Stage C 上位2構成×**追加**8=16、最大101start・各最大4stage、総最大404stage。
各stage粗500/精280を絶対上限とする現行v2回復規則以外は増額しない。
選別は厳密適合→面積/ILの同条件非劣性、構造多様性、異なるstartでの再現性を重視し、ILだけで選ばない。
実際の予算・選定規則・停止条件は**別Issueでユーザー意思決定後**に固定する。

本番への接続にはG0最新main事前予約、G1完全checkout/remote main SHA・科学入力・ソース/環境・
start別完全vector/seed/格子/選別/予測容量の照合、G2各start原子的raw/中断保存、
G3/G4候補ゼロ・失敗・未開始も含む証拠のGit byte読戻し/遠隔照合/保存監査が必要。
これらを省く本番multistart driverは本Issueに存在しない。kill/STOP/timeout/不一致/保存失敗で停止し、
rawを保持。新EXP・実探索・独立MNA大規模再実行・Phase 3は未実施。

数値余裕の調査：`SampledEpigraph.mandatory_stop_db` はpolicyの正式30dBを直接読み、
`residuals` は `IL - mandatory_stop_db`、`scipy_slsqp_stage` はこの残差を直接制約化している。
内部30.005dBは境界直下のstrict FAILを減らす可能性があるが探索条件変更であり、ここでは不変更。
別Issue案：評価用30dBと探索用guardを明示分離し、owner判断後、同一予算・同一初期値で
strict適合率/ILの影響を比較する（歴史的guard使用値と無guard値を混同しない）。

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

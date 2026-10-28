# Issue #189 / PR-S4B：完全候補記録と条件別Pareto

対象は開発Stage 4後半のコード・限定回帰。研究はPhase 2継続。
S4Aの独立レビュー・main統合（`17d6bb3`）・post-merge CIを開始前に確認した。
本機能は新EXP・本番最適化・dense評価・Stage 5保存runnerの実施承認ではない。

## APIと記録内容

`src/lpf/phase2_models/candidate_records.py`:

- `record_candidate(id, circuit, vector, ...)`：S4Aの公開nominal回路と完全vectorを受け取り、
  immutableな`CandidateRecord`を返す。保存やoptimizer実行はしない。
- `CandidateRecord.to_json()` / `.as_dict()`：スナップショットの出力（dictは防御コピー）。
- `CandidateRecord.from_json(text)`：構造・policy・全6設定・schema/Q・key・面積・状態の
  整合性を検査して読む。重複JSON keyや数値NaN/Infinityを拒否する。
- `recheck_record(record)`：同一ソース／入力条件で観測を再計算し、保存記録と照合。
  **JSON由来のPASSフラグだけで比較資格を与えない**。
- `pareto_report(records)`：理由付き除外と、同一比較条件内だけの面積–IL非支配集合。

形式は`schema=s4b-candidate-record-v1`。定義、順序／向き付きL枝と端子、物理順、C種別・役割、
完全vector（L、固定C、符号付きk、IC固定C、全6設定の可変C）、decode済み全6行、
parameter schema、stampされるQ／T007寄生／T008 IC固定C、構造／vector keyを保持する。
policy ID＋実効SHA、回路・vector SHA、policy由来の面積／出典、実際のsource tree・
commit／dirty状態／環境とbands／固定S2P入力SHAも保持する。

実装は既存`candidate_audit.audit_candidate`、`limited_candidate_evidence`のidentity gateと
再計算・照合、`problem_seed`、S4Aのkey/面積、C2のgrid fingerprint/v2制御を再利用する。
新規候補記録の本体から履歴EXP実行器や既存台帳をimportしない。

## C1 seed / C2 attemptとの接続

`seed_record=`は既存C1の決定的seedをそのままJSON snapshotにし、既存C1でリプレイ照合する。
seedだけを添付する場合、候補vectorはseed出力（epigraphを除く）と一致する必要がある。
`staged_record=`はC2のseed、全stage call、attempt、予算、収束状態、例外、元の観測・
時間／実行環境／出典を改変せず保持する（JSONではtupleはlistになる）。

- 完了したC2記録は、保存されたcallback出力・statusを既存`run_c1_staged`へリプレイして、
  seed、warm start、予算、status、attempt、controller、有限RF観測／格子を照合する。
  **実SciPy optimizerは呼び出さない**。1/2/3点を超える格子は本限定APIでは対象外。
- 候補vectorは最終C2出力（epigraph除外）と一致する必要がある。
- `converged`は「報告されたoptimizer statusが既存v2制御と整合する」の意味のみ。
  実SciPyが本当に実行されたことの署名・認証、RF可行性、独立検証ではない。
- `not_converged`も全attemptを保持する。`failed`は例外と不正出力（C2の`"nan"`等）も保持する。
  失敗runを添付する候補vectorは有限な**failure anchor**であり、最終成功vectorとは呼ばない。
  失敗診断自体は再実行せず、比較から除外する。
- コールバック契約に反する値・statusをC2がfailedとして保持した場合も、勝手に成功へ直さない。
  完了記録に矛盾するstatus／収束状態／観測、異policy・異seed・異vectorの接続は拒否する。

## 観測と未実施ゲート

既定はcomponent／roleチェックのみ。部品範囲やSPDが不適合の有限vectorも失敗記録として
残せるが、比較対象にはしない。非有限・不完全な主vectorは拒否する。

- `sampled_points=1/2/3`を明示した場合のみ、canonical 28個の**別々の**区間・全6設定の
  forward観測を行う。`forward_only`クラスで、独立MNA／電力は`not_run`。
- `limited_points=2/3`を明示した場合のみ、既存限定auditがforward／独立MNA／受動電力を
  再計算する。既存の1e-9 dB／1e-12 Wの照合を再利用し、成功時は
  `limited_independent`クラス。metricsもそのbound evidenceのsummaryから取得する。
  失敗時は`failed`を保持し、forward観測があっても比較資格を与えない。
- 両方のgrid引数を指定する場合は同一点数に限定する。
- `dense_rf`、`continuous_frequency`、`physical`、`owner_approval`は常に`not_run`。
  これらをPASSとしたJSONや昇格／認定フラグの改変は拒否する。
- `series`の物理的成立未証明は既存role auditのまま残し、比較からも除外する。

`candidate_promotion_blocked=true`、`rf_compliance_certified=false`は常に維持する。

## 出典と比較条件

`source_provenance=`は既存C2と同じく**呼出側が宣言する実行／入力出典**。
提供時は最低限、以下が必要（未提供は`not_supplied`として残し比較不可）：

```python
source = {
    "kind": "synthetic",  # synthetic / frozen / recorded（vectorの出典クラス）
    "optimizer_kind": "synthetic_callback",  # synthetic_callback / reported_slsqp
    "git_head": "...40桁の実行元commit...",
    "dirty_patch_sha256": "...64桁...",  # cleanなら空patchのSHA、dirtyなら別途patchを保全
    "input_source_sha256": "...64桁の入力fixture等のSHA...",
}
```

`optimizer_kind`が不明でも記録できるが、収束記録の比較には使わない。
C2側にprovided出典があればそれを採用し、明示引数と異なる場合は拒否する。
C2側の実行出典欠落を、後付けの記録出典だけで補完して比較可能にはしない。
これら宣言hashは元ファイルを自動認証するものではない。別途原本・dirty patchの保全と
SHA照合が必要。現在の観測コード／RF入力hashは既存identity APIで実ファイルから取得する。

比較keyはpolicy ID/SHA、full_lpf目的／閾値／外部reference plane、正確な格子SHAと点数、
証拠クラス、検証深度、入力hash、現在のsource tree／環境、vector出典クラス、
optimizer証拠クラスを含む。異trial、異格子、forwardのみと独立検証済み、syntheticと
reported実行は**別group**とし、group間の優劣を出さない。正式F003/T006や旧仕様の
記録形式は非対応として拒否し、現trialに読み替えない。

未実行、未収束、例外、構造／部品／role未検証、出典不足、JSON未再検証、独立検証失敗、
有限格子H2/H3必須値未達は、除外理由と観測値を結果に残す。
forward-only内の比較は新鮮な有限forward値と報告収束による**診断上の順位**であり、
独立RF検証済みやowner昇格対象という意味ではない。

閾値は承認済みpolicyから取得し、H2/H3必須30 dBを比較資格に用いる。
公称35 dBとIL0.30 dBは独立した目標達成フラグであり、必須制約へ勝手に変更しない。
支配関係は既存`report_research_pareto.py`と同じ「面積／IL両方が以下、少なくとも一方が未満」。
同値点は全件残し、異なる候補を構造keyで捨てない。大域最適の主張はしない。

JSON読み戻しは過去の計測・出典を認証する操作ではないため、一時的な再検証済み属性を
シリアライズしない。`recheck_record`は必要なら限定MNAも再計算し、既存evidence比較APIで
照合する。commit／source／入力が変わった場合は旧記録を書換えず、新規観測として別記録を作る。
この型は暗号署名・不正なPython呼出側に対するセキュリティ境界ではない。

## 検証範囲

`test_phase2_candidate_records.py`はsynthetic callback／小規模回路の回帰。
比較用の人工summaryは順位計算の単体テストのみで、RF性能の観測結果ではない。
`test_phase2_candidate_records_frozen.py`はSHA固定fixtureをread-onlyで利用し、
`LPF_EVIDENCE_ROOT`を明示した完全checkoutで実行する（sparseでは2件skip）。
通常CIは完全checkoutのrootを明示して凍結回帰を実施し、Pi sparse CIはsynthetic回帰を実施する。
旧inventory 45/66 FAIL（#170）は未解消。コード回帰／storage監査PASSで免責しない。

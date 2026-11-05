# Issue #313 — Stage 4A 静的preflight（非EXP）

## APIと境界

```python
from lpf.search.plan import load_preflight
plan = load_preflight('project/fixtures/issue313_preflight.yaml')
requested_grid = plan.requested_grid('terminal')
# Stage 3側へ応答とは独立に渡す。ここではforwardを起動しない。
# evaluate_requirements(response, requirements, requested_grid=requested_grid)
print(plan.sha256)
```

`performance.build_evaluation_grid(requirements, points_per_interval)` は各Intervalを
宣言順、周波数昇順で配置する。元CSVのsegment/settingを維持し、B13/B14や重複周波数を
統合しない。通常区間は両端込み2点以上、追加stopbandはJSON指定のstepで両端込み。
T006 fullでは通常28区間のほか3001点×6設定、matchingでは14区間だけ。
直接マージンはcompile済みの端点を使い、S2P外挿しない。
`Requirements`にはS2P許容範囲もfingerprint対象として含める。
巨大指定は格子あたり1,000,000 samplesのメモリ保護上限で拒否（科学的予算の既定値ではない）。

新経路のYAMLは **schema_version: 2 の1種類のみ**。
旧 `plan.load()` / CLI / Runnerのschema 1は従来のsynthetic fixture用として未変更。
新schemaを旧runへ渡しても実行できない。ロード成功はG0/G1承認ではない。
`Plan.requested_grid()`はグリッド配列をimmutable bytesから再構成し、SHAを照合する。

## YAMLキー

完全例は `project/fixtures/issue313_preflight.yaml`（開発fixture、実験計画ではない）。
未知・重複キーと省略は拒否する。

- `rf: {constraint_id, allow_trial}`：正式IDも明示。trialはboolean trueが必要。
- `objective`：`full_lpf` / `matching_only`。
- `definition`：未選定なら明示null。存在するなら
  `{path, source_sha256, definition_sha256}`。repository-local JSONの実バイトSHAと
  canonical JSON SHAを照合する。回路構築・部品/SPD合法性の認定ではない。
- `seeds`：重複しない非負整数。各seedが独立したTrialとなる計画上のラベル。
  Trial上限は1 seed内の全armsを対象とし、seed数を乗算したCampaign予算は今回対象外。
- `arms`：各`{name, steps, max_requested_samples}`。1 arm = 1 Job。
- `steps`：各`{name, solver, aggregation, points_per_interval, max_requested_samples, options}`。
  solverはslsqp/hybrid/slp。既存のoptionsキーを使用する。step上限は正整数、
  少なくとも1 full forwardが必要。solver max_evaluationsは別の停止条件であり、
  nfevからRF費用や実行済み回数を推定しない。
- `selection: {rule, top_k, max_candidates, points_per_interval}`：
  ruleは`mandatory_vmax_vsum_il_sha`（Stage 3）。全step後の選抜を1回だけ計画する。
  `max_candidates`は選抜前に再評価できる候補数の上限、top_kは終端枠数の上限。
- `validation: {terminal_points, dense_points, max_candidates, max_requested_samples}`：
  terminalはJob内、denseは独立検証枠。denseの候補数とsample上限も必須。
- `anytime_points_per_interval`と`anytime_samples`：各milestoneでincumbent 1件を評価する枠。
  milestonesは厳密増加の正整数リスト（明示空リストで無効）。milestoneは当該Jobの
  **探索stepに要求したsamplesの累計**に対する閾値。scan自身、selection、terminalは
  閾値カウンタに含めないが、Job/Trial予算には含む。step上限合計を超える閾値は拒否。
  1 batchが複数閾値を跨ぐ場合も全scan枠を予約し、実行有無は後続の台帳の責務。
- `max_trial_requested_samples`：全armのJob上限合計を予約できる必要がある。

点数・sample上限・milestoneに17/1001/476などの暗黙補完はない。
solverの数値tolerance/default解決やforward配線はStage 4B以降であり、本APIはsolverを起動しない。

## 予算の意味

1 forward費用は`len(grid.frequency_hz)`。同一区間の指標数では乗算しない。

- step：明示sample上限を**上限予約**。solver上限による早期終了はあり得る。
- selection：1 forward費用×max_candidatesを上限予約。
- terminal：1 forward費用×top_kを**固定枠予約**。
- anytime：1 forward費用×milestone数を固定枠予約。
- Job：step上限合計＋selection上限予約＋terminal/anytime固定枠予約がJob上限以内。
- Trial：全Job上限合計がTrial上限以内。
- dense：1 forward費用×validation.max_candidatesが独立検証上限以内。

固定枠予約も「全候補が存在する」「閾値に到達する」「実行完了する」という主張ではない。
実際の消費は全て0、全段階`not_run`。dense上限はJob/Trial探索予算へ混ぜない。
`runtime_reserved_samples`はselection＋terminal＋anytime。
各stepの`reserved_after_step`にはさらに後続step上限を加え、将来のfull batchを保護する。

`preflight.check_next_batch(...)`は副作用のない整数比較関数。
step/Job/Trialのremaining（予約込み未消費量）と、まだ保持すべきJob/Trial予約を渡す。
`batch <= step_remaining`かつ`batch + reserved <= remaining`が全て成立しなければ
forward前STOP。予約対象を実行するときはその枠のみ解放してから照合する。
Worker/Runnerからの自動呼出しや予約台帳の実装ではない（Stage 4B/C対象）。
上限額を勝手に増額しない。

## 凍結と出典

Planのcanonical JSON/SHAには入力YAMLの全内容、mode、RF ID/effective SHA、Requirementsの
全区間・要求・fingerprint、全格子配列・区間別実点数・grid SHA、点数、全予算と予約、
bands/S2P実物SHAと論理パス、definition/source参照を記録する。
出典ファイルはread-only。実験番号予約、履歴監査、RF性能、MNA、連続帯域・物理成立の証拠ではない。

## 再現検証

```bash
uv sync --frozen
uv run --frozen python -m unittest discover -s tests -p test_issue313_preflight.py -v
uv run --frozen python -m unittest discover -s tests -p test_rf_search.py -v
```

5 RF ID×2 modeの格子、T006 complete step、上下端、マージン、determinism、欠損応答拒否、
YAML不正、sample予算STOPをsynthetic応答で確認する。T006 wideband実RF forwardと新EXPは実施しない。
通常smoke/sparse CIの両方へ新規テストを追加する。

# scripts/：現役操作・監査の入口

実行前に[運用正本](../project/instructions.md)、[GitHub Issues](https://github.com/miyabimm/reconfigurable-rf-lpf-research/issues)／[PR](https://github.com/miyabimm/reconfigurable-rf-lpf-research/pulls)と最新`main`の実装・CI、[RF制約](../rf/constraints/registry.json)を確認する。スクリプトの存在は新規EXPや本番計算の承認ではない。

| 用途 | スクリプト／扱い |
|---|---|
| 登録済みRF profile固定definitionの逐次開発 | [run_rf_search.py](run_rf_search.py)、下記。正式EXPへ自動昇格しない |
| RF評価・保存済み候補の監査 | [audit_results.py](audit_results.py)。旧EXP-047非標準manifestは[experiment_manifest.py](../src/lpf/experiment_manifest.py)のSHA固定index-only viewで索引照合 |
| 候補の台帳照合 | [audit_research_catalog.py](audit_research_catalog.py)、[report_research_pareto.py](report_research_pareto.py)。同条件・同格子・同検証深度のみ比較 |
| 新規EXP番号の予約・照合 | [reserve_experiment_number.py](reserve_experiment_number.py)、[experiment_id_registry.py](experiment_id_registry.py) |
| 新規EXP保存ゲート | [audit_new_experiment_storage.py](audit_new_experiment_storage.py)、[experiment_manifests.py](experiment_manifests.py) |
| CI差分・選択回帰 | [classify_storage_ci.py](classify_storage_ci.py)、[select_ci_tests.py](select_ci_tests.py)、[audit.yml](../.github/workflows/audit.yml) |

## RF profile 開発Run

### 標準Plan入力の生成

有効な既存develop config（以下 `plan.yaml`。定義参照・全seed/arm・solver・grid・予算を含む）から、RF forwardなしで一組を生成する。標準設定は [`develop_search_limits.yaml`](develop_search_limits.yaml) の `search_limits.GJM01.max: 10.0` pF。固定GJM01の上限だけを物理上限との小さい方にし、Lを含む他の全座標・下限は物理範囲のまま。全物理範囲を使う場合は設定ファイルのコピーを `search_limits: {}` とし、将来の上限変更もその値だけを編集する。設定は入力生成専用でありRunner configには追加しない。

```bash
uv run --frozen python scripts/generate_develop_inputs.py \
  --config plan.yaml --settings scripts/develop_search_limits.yaml \
  --spot-checks '{"terminal":[0]}' --output /tmp/new-plan-inputs
uv run --frozen python scripts/run_rf_search.py develop \
  --config /tmp/new-plan-inputs/config.yaml --starts /tmp/new-plan-inputs/starts.json \
  --search-bounds /tmp/new-plan-inputs/bounds.json \
  --output /tmp/new-run --spot-checks '{"terminal":[0]}'
```

生成先は未存在を指定。`settings.yaml`、`config.yaml`、`starts.json`、`bounds.json` と `manifest.json` を一緒に保存する。manifestは各入力の原byte SHA、Job別Sobol seed、spot/checkpoint指定、preflight Plan SHAとbounds SHAを記録する。実行時は同じspotとcheckpoint間隔（省略時1000）を指定する。Planは入力と実行コード等が同じ場合に照合できる。生成時は既存の単点scrambled Sobolを使用し、各seedの先頭armはそのseedを使用、追加armは全config seedを避けて0から順に未使用の非負整数をseed順・arm順に割り当てる。各Jobを別々に生成し、不正startは修復・再抽選せずSTOPする。これはsingle-arm従来方式を維持する入力割当であり、比較条件のpaired startを暗黙に意味しない。Plan凍結はgrid・予算・start等のpreflightのみであり、実行許可やRF性能検証ではない。

### Runner直接指定

```bash
uv run --frozen python scripts/run_rf_search.py develop \
  --config plan.yaml --starts starts.json \
  --output /tmp/未存在のrun --spot-checks '{"terminal":[0]}'
```

登録済みschema 1 profile（RF-T009、RF-T010等）を明示opt-inする。未対応の物理baseはRF Coreが拒否する。Plan入力例（`definition`は完全なCircuitDefinitionのインラインmapping、またはここに示すリポジトリ内JSON参照）：

```yaml
schema_version: 1
rf: {constraint_id: RF-T009, allow_trial: true}
definition: {path: path/in/repo.json, source_sha256: REPLACE, definition_sha256: REPLACE}
seeds: [23]
terminal_points: 4
budget: {rf_samples: 224, rf_forwards: 3, independent_mna_samples: 1}
arms:
  - name: demo
    steps:
      - name: coarse
        solver: trf
        objective: signed_margin_db
        aggregation: sum
        points_per_interval: 2
        options: {max_evaluations: 2}
```

- `source_sha256` はdefinition JSON原byteのSHA、`definition_sha256` はcanonical JSONのSHA。`starts.json` は `{"23":{"demo":{"vector":[…],"vector_sha256":"…"}}}`。全seed×armの完全vectorを明示し、同じseedでも別armへ流用しない。vector SHAは `lpf.search.storage.vector_sha` で計算する。RunはYAML記載のseed順→arm順。
- TRF の `restart_sigma` は省略時0.1、明示 `null` で単発。前回局所終点から正規化座標を摂動し、`max_evaluations` を全 run 共通の感度 forward 上限とする。`ftol` 省略時1e-6、`x_scale` 省略時1.0。局所成功と全体の予算終了は区別する。
- L-BFGS-Bの `ftol` は有限正数で任意。指定時はL-BFGS-Bの `ftol` として渡し、省略時はSciPy既定を使う。TRFのftolと収束条件は同等ではない。
- L-BFGS-Bの `restart_sigma` は有限正数で任意（省略時0.1）。`batch_fd` はSciPy workersによる数値微分バッチ（既定true）。旧逐次評価は `batch_fd: false` を明示する。true時の `max_evaluations` は評価グループ開始の名目上限で、開始済みバッチは完了する。PlanはSearchに最大 `N + max(自由座標数 - 1, 0)` forwardとそのRF/MNA sampleを予約し、Terminalは別途予約する。グループまたは局所run境界でbestをcheckpointし、実施数はraw/receiptに記録する。false時は従来どおり厳密上限。旧schema 2 preflightは自由座標を凍結しないためtrueを拒否する。
- 開発L-BFGS-Bの `partial_fd` は設定別計算省略（既定は `batch_fd` と同値、通常true）。通常バッチだけを使う場合は `batch_fd: true, partial_fd: false`、逐次の場合は `batch_fd: false` を指定する。`partial_fd: true` は `batch_fd: true` を必要とする。単独RF基準に対し設定別可変Cを1変数だけ変更した摂動は、その設定だけ再計算する。`off`/`lk` cacheのみ部分化し、`response`/`both`は通常batchに委譲する。各候補のforward・全grid要求sample、予約、Terminalは変わらない。性能と適用範囲の診断は [#484](../project/diagnostics/issue484/README.md)。
- 実効値はPlanの `effective_options` に記録し、step rawの `local_runs` は完了または予算停止した局所探索の回数（再始動回数は `max(0, local_runs - 1)`）。各stepの `stop_points_per_interval` は任意。TerminalはすべてのSearch区間より密にする。SLSQP／SLPの `options` は `max_iterations` と `max_evaluations`。目的式とaggregationは[profile文書](../project/minimax_profile.md)参照。
- `--search-bounds PATH.json` は全Job共通の完全vector順の閉区間。未指定は物理bounds。clip・修復なし。`--checkpoint-interval-forwards` は正整数（既定1000）。`--spot-checks` はstage→index配列、`terminal` 必須、Searchは `arm/step` を明示した場合のみ、毎forwardに独立照合する。`budget` はRun全体の3費目の上限で、RF前に全Job分の予約成立を検査する。
- `--rf-cache-mode {off,lk,response,both}` はSearch Evaluator内のL/k・設定別応答LRUを切り替える（既定 `lk`、各容量16）。Terminalは常に非キャッシュ。`--timing-output` 指定時のみ診断JSONの各step `rf_cache` に検索・HIT/MISS・L/k実計算・再計算sample数を記録し、計時regionとは区別する。response/bothでは存在する設定に対する全MISS・部分HIT・全HIT別のforward/sample数も記録する。deepの `rf/cache/*` は検索・MISS抽出・計算・保存・再配置を計測し、`missing_compute` は他のRF演算計時を包含するため合算しない。
- 任意の `--timing-output /tmp/new-run-timing.json` でJob別L1/L2計時を有効化する。新規の非Gitファイルを指定し、科学 `--output` とその子・親を避ける。無指定はplain。計測はメモリ集計し終了時に一度保存、保存失敗は警告のみ。強制終了時は欠測し得る。区間はinclusiveで重複し、合算や残余をSciPy時間と解釈できない。L-BFGS-Bの局所run詳細は科学raw、wallは診断JSON（イベント欠測は未観測）に記録する。raw・receipt・台帳が正本。
- `--timing-output PATH --timing-level deep` はSearchのRF evaluator内部にL3を追加する。`--timing-level timed` は既定のL1/L2、level明示にはoutput必須。JSONのlevelとregionはJob別。`rf/port_admittance` は `rf/node_admittance` を含み、nodeは `rf/matrices` を含む。`rf/cascade` はforward当たり2回、decodeとpower_responseは各1回。`rf/matrices/`・`rf/node/`・`rf/port/`・`rf/power/`と `rf/y_to_s_solve`・`rf/response_build` は各関数内の主要演算を計測する。matricesの構築はSPD前の `build` とSPD後の `build_h_incidence` に分かれる。内部ノードなしならSchur区間は発生しない。`evaluator_setup` はSearchごとに1回の格子/S2P準備で、forwardとは別。TerminalはL3対象外。包含区間は合算せず、同一runの親−子差もtimer呼出し、検査、例外などを含む未計測残差である。タイマー自体の負荷は測定時間に含まれ、区間間の記録処理も親に含まれる。演算単位の異常終了はsolve系のみ失敗を記録し、他は親の失敗として記録する。deepは逐次Runner専用の一時的な計測であり、例外時も復元する。
- TRF解析Jacobianのdeepでは `rf/node_jacobian`、`rf/cascade_jacobian`、`jacobian_residual` を追加する。前者2つは `rf_evaluate` に含まれ、cascade感度はforward当たり2回。その他の感度演算は `rf_evaluate` 内の未分解時間であり、SciPy時間ではない。計測によりplain結果の数値・停止契約は変えない。
- `plan.json` は凍結済み実効Plan、`run.json` は親台帳。事前に全額を `not_started` として記録し、開始前に対象だけ `unknown` を永続化する。`job-NNNN/` の `input.json`、`result.json`、`receipt.json`、`checkpoints/` の原byteを照合したときだけ `completed` として差額を解放する。異常後は後続を開始せず再試行・resumeしない。ストレージ全面障害で書戻しも失敗した場合は台帳の耐久性未確認としてSTOPする。
- 終了コードは0＝全Job照合済みかつ数値収束、4＝全Job照合済みで数値未収束あり、2＝入力不正・異常停止。収束・有限格子閾値・物理実装・正式RF適合は別。RF-F003/T005〜T008の旧schema2探索、weighted/Selection、旧Campaign、旧monitor/ベンチCLIは撤去。診断履歴は当時の固定Git履歴で読む。

## 新規EXPの保存と通常回帰

```bash
uv sync --frozen
python scripts/audit_new_experiment_storage.py preflight EXP-NNN
python scripts/audit_new_experiment_storage.py finalize EXP-NNN
python scripts/audit_new_experiment_storage.py audit
uv run --frozen python -m unittest discover -s tests -v
```

G0〜G5は開発Runの外部。詳細は[正式EXP管理](../project/campaign_workflow.md)と[保存ポリシー](../project/experiment_storage_policy.md)。G5適格性判定はraw削除ではない。新形式の正式Campaignは未接続・保留。

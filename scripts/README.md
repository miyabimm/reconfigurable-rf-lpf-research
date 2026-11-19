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
        solver: hybrid
        objective: signed_margin_db
        aggregation: sum
        points_per_interval: 2
        options: {max_search_forwards: 2, restart_sigma: 0.1}
```

- `source_sha256` はdefinition JSON原byteのSHA、`definition_sha256` はcanonical JSONのSHA。`starts.json` は `{"23":{"demo":{"vector":[…],"vector_sha256":"…"}}}`。全seed×armの完全vectorを明示し、同じseedでも別armへ流用しない。vector SHAは `lpf.search.storage.vector_sha` で計算する。RunはYAML記載のseed順→arm順。
- Hybridの `restart_sigma` は有限正数で任意（省略時0.1）。実効値はPlanの `effective_options` に記録し、step rawの `local_runs` は完了または予算停止した局所探索の回数（再始動回数は `max(0, local_runs - 1)`）。各stepの `stop_points_per_interval` は任意。TerminalはすべてのSearch区間より密にする。SLSQP／SLPの `options` は `max_iterations` と `max_evaluations`。目的式とaggregationは[profile文書](../project/minimax_profile.md)参照。
- `--search-bounds PATH.json` は全Job共通の完全vector順の閉区間。未指定は物理bounds。clip・修復なし。`--checkpoint-interval-forwards` は正整数（既定1000）。`--spot-checks` はstage→index配列、`terminal` 必須、Searchは `arm/step` を明示した場合のみ、毎forwardに独立照合する。`budget` はRun全体の3費目の上限で、RF前に全Job分の予約成立を検査する。
- 任意の `--timing-output /tmp/new-run-timing.json` でJob別L1/L2計時を有効化する。新規の非Gitファイルを指定し、科学 `--output` とその子・親を避ける。無指定はplain。計測はメモリ集計し終了時に一度保存、保存失敗は警告のみ。強制終了時は欠測し得る。区間はinclusiveで重複し、合算や残余をSciPy時間と解釈できない。Hybridの局所run詳細は科学raw、wallは診断JSON（イベント欠測は未観測）に記録する。raw・receipt・台帳が正本。
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

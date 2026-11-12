# scripts/：現役操作・監査の入口

実行前に[運用正本](../project/instructions.md)、[現在地](../project/roadmap.md)、[RF制約](../rf/constraints/registry.json)を確認する。**スクリプトの存在は新規EXPや本番計算の承認ではない。**

## 現役の用途

| 用途 | スクリプト／扱い |
|---|---|
| schema2固定definitionの開発CLI | [run_rf_search.py](run_rf_search.py)、詳細は[project README](../project/README.md#開発用固定definition-cli)。正式EXPへ自動昇格しない |
| RF評価・保存済み候補の監査 | [audit_results.py](audit_results.py)。旧EXP-047非標準manifestは[experiment_manifest.py](../src/lpf/experiment_manifest.py)のSHA固定index-only viewで索引照合。**削除済み専用adapterは使わない** |
| 候補の台帳照合 | [audit_research_catalog.py](audit_research_catalog.py)、[report_research_pareto.py](report_research_pareto.py)。同条件・同格子・同検証深度のみ比較 |
| 新規EXP番号の予約・照合 | [reserve_experiment_number.py](reserve_experiment_number.py)、[experiment_id_registry.py](experiment_id_registry.py) |
| 新規EXP保存ゲート | [audit_new_experiment_storage.py](audit_new_experiment_storage.py)、[experiment_manifests.py](experiment_manifests.py) |
| CI差分・選択回帰 | [classify_storage_ci.py](classify_storage_ci.py)、[select_ci_tests.py](select_ci_tests.py)、[audit.yml](../.github/workflows/audit.yml) |
| 一時的なMinimalWorker開発ベンチ | [benchmark_minimal_worker.py](benchmark_minimal_worker.py)。非EXP・RF性能認定外 |

## 開発ベンチ（正式EXPではない）

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  uv run --frozen python scripts/benchmark_minimal_worker.py \
  --config project/diagnostics/issue377/baseline.yaml \
  --starts project/diagnostics/issue401_starts_1002.json \
  --arm hybrid --seed 1002 --mode plain > result.json
```

- `plain`は無計時、`timed`はL1/L2、`deep`はL3内訳も記録。包含区間は二重加算しない。
- source/Plan/RF条件・grid・seed/完全vector・環境とscript SHAを記録する。`worker.solve()`と後段の追加`best_x`観測forwardは費用・時間境界を分離する。
- `--expected-source-sha256` / `--expected-script-sha256`は任意の不一致拒否。旧新比較はwarmup除外・順序交替・分布と外れ値の提示を要する。
- 利用価値と限界は[methods](../project/methods.md#minimalworker性能診断の運用401408)・[results](../project/results.md#minimalworker性能診断issue-401)に集約。`project/diagnostics/`のファイル自体はIssue #397で変更しない。

## 新規EXPの保存と通常回帰

```bash
uv sync --frozen
python scripts/audit_new_experiment_storage.py preflight EXP-NNN
python scripts/audit_new_experiment_storage.py finalize EXP-NNN
python scripts/audit_new_experiment_storage.py audit
uv run --frozen python -m unittest discover -s tests -v
```

- G0 main予約→G1入力・source照合→G2 run→G3選別保存→G4 PR/CI→G5 remote readback/cleanup eligibility。詳細は[保存ポリシー](../project/experiment_storage_policy.md)。G5の可否判定はraw削除ではない。
- 旧`full_lpf_checkpoint_import.py`、旧W0/W3監査、旧matching facade、廃止済みcurationは現役汎用入口ではない。古い実験コマンドの再実行は[固定Git履歴](../project/legacy_git_replay.md)と依存環境を確認する。
- RF数値の新規採用には全6設定・28区間、SPD・受動性・電力保存、固定S2P、独立MNAを条件・検証深度つきで報告する。CI PASSだけで正式RF適合としない。

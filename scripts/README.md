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

## weighted逐次開発（正式EXPではない）

```bash
uv run --frozen python scripts/run_rf_search.py develop \
  --config <新形式のschema2-plan.yaml> \
  --starts project/diagnostics/issue401_starts_1002.json \
  --output /tmp/未存在のrun --objective-mode weighted_violation \
  --max-search-forwards N --spot-checks '{"terminal":[0,111]}'
```

単一seedも複数seedも同じ親台帳を通す。任意の `--search-bounds PATH.json` は完全vector順の有限閉区間で、物理hard boundsの内側かつ全startを含む必要がある。clip・修復はしない。未指定は物理全域。Job `input.json` に実際のboxとSHAを保存する。

`--objective-mode weighted_violation --max-search-forwards N` を併用する。Nは正整数で、探索callbackだけの上限。設定はRF-T008 trial opt-in／full_lpf、1 arm・1 Hybrid/sum step、anytimeなし、search pass 2点・H2/H3 3点、terminal 17点/区間に限定する。stepの `options` と `selection` を省略し、CLIで予算を指定する。`max_requested_samples` は凍結前に導出し直す。その他のschema2項目は必要。旧 `project/diagnostics/issue433/hybrid.json` と `issue377/baseline.yaml` は履歴入力であり、旧solver設定を含むため新入口では拒否される。原本を変更しない。

HybridのPlan設定は `max_search_forwards=N` のみで、solver内部では `max_evaluations=maxiter=N`、`restart_sigma=0.1` を導出する。局所終了後も残予算があれば再始動するため、旧 `max_restarts=0` の単発実行とは探索挙動が異なる。旧固定Hybrid Planは自動変換せず拒否し、歴史的再生には旧ソースが必要。weighted開発Planは探索 `N×70`、terminal `1×476` を静的予約し、最終探索stepの最小J vectorを直接terminalで評価する。独立denseは別枠で予約のみ・実行しない。独立MNA spotは別費用で、実行sample数をstage別に記録。実績と予約、Plan・grid・目的のSHAはinput/resultで照合できる。失敗時のcheckpointは最後の保存時点であり、例外時に未保存の改善を保証しない。通常のselectionなし固定Jobは最終stepのOptimizer出力をTerminalへ渡し、Campaignは従来のselection契約を保持する。両経路は同一の評価条件ではない。

目的は `J=max(0, worst_pass_IL−0.30)^2 + 100×mean(max(0, 30.01−H2/H3 attenuation)^2)`、探索70点全6設定・28区間から1 callback/1 RF forwardで計算する。30.01 dBは探索余裕のみ、元のmandatory 30 dB・nominal 35 dBを変更しない。重み・余裕達成・収束の性能妥当性は未検証。Hybridが観測したJの最小値を選び、同値は先着vectorを保持する。Workerは独自スコアで順位付けせず、Optimizerの観測結果と返却x・Jを照合する。Terminalの詳細RF結果と独立spotは別判定であり、有限格子strict PASSも連続周波数・物理実装・実測の保証ではない。

出力はcheckout外のsystem temp内に限り、既存のディレクトリを上書きしない。親台帳に予約・unknownを記録し、各Jobに `input.json`、追記型 `checkpoints/` と `result.json` を残す。失敗・中断後も再試行／resumeしない。`--spot-checks`はstage名→sample index配列のJSON。weightedの完走は終了コード4、異常は2であり、いずれもRF適合の認定ではない。本番・正式EXP用のG0〜G5とは別である。

## RF-T009 単一Job開発

```bash
uv run --frozen python scripts/run_rf_search.py develop \
  --config <明示opt-inのRF-T009 schema2-plan.yaml> \
  --starts <設定seedの完全vectorとSHAを持つJSON> \
  --output /tmp/未存在のrun --spot-checks '{"terminal":[0]}' \
  --checkpoint-interval-forwards 1000
```

Planは1 arm・1 seed、複数step可、Selectionなし。各stepに`objective: signed_margin_db`とsolverごとの予算・aggregationを明示する。詳細と目的式の違いは[profile文書](../project/minimax_profile.md)。Search boundsは任意の `--search-bounds PATH.json`、checkpoint間隔は任意正整数（既定1000）。Terminal spotの指定は必須。事前予約・hard cap・停止・readbackを伴う限定APIを呼び、outputに予約を含む`input.json`、checkpointと`result.json`を保存する。成功時のledgerはRF sampleと独立MNA sampleを別計上し、未使用予約を解放する。失敗時は`failure.json`に予約全額をunknownの保守的上限として記録し、途中で記録できなかった場合も`input.json`の予約は残る。完走コード4は開発Jobの終了を意味し、数値収束・RF適合の認定ではない。既存outputへの再試行や正式Campaignは対象外。

## 複数seed weighted開発のcheckpoint

`scripts/run_rf_search.py develop --objective-mode weighted_violation` では `--checkpoint-interval-forwards` に正整数を指定でき、既定は1000。探索forward通算の指定間隔と末尾にbestを保存し、間隔はPlanとJob入力に凍結する。これは保存頻度であり、forward実行前の親台帳による費用予約とは別である。親台帳およびJobには局所run件数・成功件数・callback回数の集計を保存し、各runの詳細は共通Optimizer結果に含めない。

## 開発ベンチ（正式EXPではない）

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  uv run --frozen python scripts/benchmark_minimal_worker.py \
  --config <新形式のschema2-plan.yaml> \
  --starts project/diagnostics/issue401_starts_1002.json \
  --arm hybrid --seed 1002 --mode plain > result.json
```

- `plain`は無計時、`timed`はL1/L2、`deep`はL3内訳も記録。包含区間は二重加算しない。
- source/Plan/RF条件・grid・seed/完全vector・環境とscript SHAを記録する。`worker.solve()`と後段の追加`x`観測forwardは費用・時間境界を分離する。
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

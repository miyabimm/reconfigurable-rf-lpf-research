# Issue #317 — Stage 4C-1 開発用固定step Worker

対象: #306 v1.0 / #301。**非EXP・単一プロセス・system tmp raw限定**。
本APIはG1承認済みJobSpecではなく `development_only`。
正式CLI、親Campaign/Trial台帳、Scheduler、G0–G5、本番探索、再開は未接続。
schema 1 `load()/run()/execute_job()` のfixture経路は変更しない。

## APIと責務

- `worker.freeze_development_job(plan, definition, policy, arm, seed, x, *, spot_checks=None)`:
  schema 2 `load_preflight()` のPlan、完全な合法x/SHA、arm/seedを既存の不変
  `JobSpec` に保存。RF/effective SHA、definition/bands/S2P、全格子/予算、
  solver options（数値既定値も含む）、物理box、source bytes/HEAD/dirty patch、
  Python/NumPy/SciPy・thread環境を凍結する。新YAML schemaはない。
- `worker.execute_development_job(spec, fresh_tmp_checkpoint, *, solver_kind='scipy')`:
  同じ凍結レコードを再生成して完全一致を確認し、固定順にstepを実行。
  `solver_kind='fixture'` はテストでpatchしたsolverの表示専用。RF backendは実RF core。
- 内部 `FixedJobEvaluation` は既存 `FixedStageEvaluation` のforward、要求評価、
  原子的保存、独立branch-current MNA/受動性/電力検査を再利用する。
  旧T008 forward、旧score/rank_keyや固定17/1001/476は使用しない。

### solverと引継ぎ

SLSQP/SLPは既存 `Problem.from_fixed_stage()` のmandatory callbackを使う。
SLSQPの単一残差は `sqrt(worst_IL)`（squared sum/maxでworst ILを最小化）、
SLP signed_maxは `[worst_IL]`。Hybridはその残差とmandatory sampleの正の違反を
連結する罰則探索であり、厳密合否とは別。nominal要求はhard化しない。
平方残差に使えない負/非有限ILはSTOPし、数値infをfloorしない。

次stepはSLSQP/SLPの `out.x`、Hybridの `out.best_x` を引き継ぐ。
Hybrid endpoint/bestおよび各step出力を候補として保持するが、step間のRF選抜はない。
非収束は記録して固定次stepへ進む。候補なし、不合法な引継ぎ、数値失敗、
予算停止、中断、保存失敗では停止し、暗黙の救済/retryはしない。
solverのnfevは説明値のみで、sample費用に変換しない。

### 共通選抜・terminal・anytime

最後のstep後だけselectionを起動。完全x SHAで重複除去し、SHA昇順の固定候補集合に
`max_candidates` を適用する。不合法/上限超過/未評価候補は別集合へ。
実RF再評価後の順位はStage 3 `rank_candidates()` のみを使い、上位 `top_k` だけ
YAML指定terminal格子で再評価する。selection中の失敗では既評価の部分順位と
失敗候補を保持してSTOPする。

anytimeは探索step由来の**requested累計だけ**が閾値を跨ぎ、合法観測が完了した際に、
その観測をYAML格子で再評価する。scan/selection/terminalは閾値に算入しない。
未到達/候補なしは `not_run`、開始後の失敗/中断/unknownは別状態。
denseは独立予算と格子を保持して常に `not_run`。

### 共有予約と保存

step・selection候補・terminal候補・各anytime milestoneを個別に予約。
実行中の枠だけを解放して `check_next_batch()` を適用する。
stepの確定終了時のみその未消費枠を解放し、他step/scan/他Jobの枠は保持する。
別Jobは全capを予約したまま。これは**1 Job限定のTrial算術**で、親共有台帳ではない。

全batchの `unknown/requested=N/completed=0` をfsync/atomic replaceしてからforward。
同じxのcallbackも毎回full batch課金し、全応答と全要求の評価成功時だけcompleted加算。
既存checkpointは常に拒否する。unknownの返金・自動resume/retryはしない。
保存失敗後は再保存せず、最後のdurable rawを維持する（外部kill時も同じ）。
独立監査内での保存失敗に対する再保存を禁止するRED→GREEN回帰も追加した。

`spot_checks={'terminal': [0, 111], 'anytime': [0]}` のように、
格子名→明示sample index列をJobへ凍結すると、その格子の各完了batchで独立検査を行う。
未指定は各batchで `not_run`。独立検査のrequested/completedはprimary RFとは別欄。
部分sample PASSは全帯域認定でもG1通過でもない。

## 限定検証・費用（各テスト内の代表1 Job）

全RF-F003 forwardは6設定・28別区間を保持。2点forwardは56 samples。

| ケース | 探索requested | anytime | selection | terminal | primary requested/completed |
|---|---:|---:|---:|---:|---:|
| 2-step / fixture SLSQP、同じxを4 callback | 224 | 168 | 84 | 112 | 588 / 588 |
| 2-step / 実SciPy SLSQP、各callback予算2 | 224 | 0 | 84 | 112 | 420 / 420 |
| fixture Hybrid→SLP、候補2・top_k=2 | 168 | 168 | 168 | 224 | 728 / 728 |
| anytime=5点、terminal=6点 | 224 | 280 | 84 | 168 | 756 / 756 |
| 第2step枠111で2回目の56 batchを拒否 | 168 | 168 | 0 | 0 | 336 / 336 |
| selection forward数値失敗 | 224 | 0 | 84 | 0 | 308 / 224 |

実SciPyは各step `max_iterations=1, max_evaluations=2` の接続smokeのみ。
両stepとも `evaluation_budget_exhausted` / 未収束であり、最適化性能比較ではない。
RF-T006はmatching_onlyの小格子のみ。18,006追加点の実full-LPF計算はしない。
独立sample指定のテストは588 primary samplesに加え、anytime各1点＋terminal2点の
計4独立監査samplesを別計上する。

再現コマンド（通常のソフトウェアテストであってEXPではない）:

```bash
uv sync --frozen
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  PYTHONPATH=tests uv run --frozen python -m unittest -v \
  test_issue315_fixed_stage test_issue317_fixed_worker test_rf_search
```

通常smokeとPi sparse smokeの両workflowへ追加。sparseテストはdocs/data/experimentsが
存在しないcheckoutを要求するため、完全checkoutで `PI_SPARSE_RF=1` を付けただけでは
PASSしない。CIでは同一PR HEADに対して別checkoutを使用する。

コード検証、有限格子評価、独立sample検査、solver収束、正式RF適合、G0/G1本番許可は
独立判定。連続帯域、Q(f)/SRF、EM、実装、測定は未検証。新EXP/Phase 3への移行はない。

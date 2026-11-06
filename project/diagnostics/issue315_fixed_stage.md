# Issue #315 — Stage 4B 固定stage開発接続

## 境界

`FixedStageEvaluation` はschema 2 `load_preflight()` のPlanを使う、1プロセス・1固定Job内の**単一stage専用の開発API**。CLI、`execute_job`、solver本番反復、Controller、複数step完走、G0/G1、EXP保存には接続していない。旧schema 1 fixture APIは維持する。Phase 2のままで、RF条件・科学的閾値・履歴原本を変更しない。

## APIと契約

```python
# definition: 呼出側のCircuitDefinition（Planの定義JSONとcanonical SHA一致）
# policy: load_constraint()で明示opt-in済みの承認条件
# raw_dir: tempfile.TemporaryDirectory()、リポジトリ外
meter = FixedStageEvaluation(plan, definition, policy, 'demo', 'coarse',
                             Path(raw_dir) / 'checkpoint.json')
candidate = meter.evaluate(x)
# Stage 3 rank_candidates([candidate]) に直接渡せる。
meter.spot_check(candidate['batch_index'], [0, 55])  # 指定sampleのみ、任意
problem = Problem.from_fixed_stage(meter)
# problem.objective(x), problem.constraints(x): 各callbackが実forwardを1回行う。
# 実solverの反復を開始するAPIではない。キャッシュや重複forwardの無料化なし。
```

- 初期化および各forward前にPlan自身のSHAとStage 4Aのread-only再コンパイル結果を照合する。現在のRF ID/effective SHA、mode、Requirements fingerprint、全要求格子、bands/S2P実byte SHA、定義source/canonical SHA、`CircuitDefinition`を照合。`definition: null`は実行拒否。
- 候補を完全コピーし、完全x/SHAを固定。`validate_values()`で閉区間、六設定、Q/role、全L SPDをforward前に検査する。無言のclip/repairなし。
- `build_rf_model(definition, approved_policy).evaluator(plan_grid).evaluate(x)` → `evaluate_requirements(..., requested_grid=plan_grid)`。Stage 3の区間×指標×mandatory/nominal、sample残差、Vmax/Vsum、worst ILをそのまま使用する。
- `Problem`の目的callbackはworst IL、制約callbackはmandatoryの`g=-e`のみ。nominalはhard化しない。正当な`+inf`は数値のまま返す。利用solverが扱えない場合の無断floor/clampはしない。
- 候補のvector/grid SHAを付けて返し、`rank_candidates()`が供給済みSHAとの不一致を拒否する。比較条件の照合と物理値の再検査は既存Stage 3順位APIに任せる。旧`score()/rank_key()`は新経路から呼ばない。

## 費用・durable raw

実格子の`len(grid.frequency_hz)`をfull batchで確保し、`check_next_batch()`でstep/Job/Trialの上限を検査する。他stepの上限、selection/terminal/anytimeの全予約、他Jobの全上限を保持する。選択したstage以外の枠は**一切解放しない**保守的な単一stage仕様。denseは独立validation枠で`not_run`。solver nfevから費用を推定しない。

`storage.atomic()`で、開始前の`unknown/requested=N/completed=0`をfsync/replaceした**後**にevaluateを呼ぶ。完全なforward＋Stage 3評価が正常終了したときだけcompletedを加算。途中例外・KeyboardInterrupt・保存失敗ではSTOPし、同じオブジェクトで再試行しない。既存rawパスでの再初期化も拒否し、不明費用を返還しない。外部kill時には最後の原子的な記録が残る。ディスク自体の喪失・fsync不履行を保証するものではない。

rawにはPlan/grid/policy/definition/requirements fingerprint、完全grid/x、各batchのSHA・phase・終了理由・requested/completed・予約・前後残高、完成した全外部S（real/imag）とIL/APL/InRL/OutRL、Stage 3全評価を保存する。forward完成後に評価が例外になった場合も応答を保持し、completedは0。JSON上の非有限値は`{"nonfinite":"+inf"}`等で明示し、巨大な有限定数に置換しない。不正入力のNaNは拒否理由とともに保存できるが、合法なRF応答として扱わない。

独立検査は指定sampleの既存`evaluate_independent_response()`によるbranch-current MNA・全S/指標照合・受動性・電力収支。primary RF requested/completedと別にaudit requested/completedを保存する。未指定なら理由付き`not_run`、指定sample PASSでも`whole_band_checked=false`。独立検査失敗もSTOP。dense、連続帯域保証、Q(f)/SRF/EM/実測、RF科学的認定は未実施。

## 再現テストと小規模費用

```bash
uv sync --frozen
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  uv run --frozen python -m unittest discover -s tests -p test_issue315_fixed_stage.py -v
```

`test_actual_all_models_and_full_trace`では以下を実RFで評価し、一時rawを読み戻して同一x/grid/Plan/条件の結合を検査する。**性能改善・RF仕様適合の主張ではない**。

| 条件 | mode | 主forward要求/完了 | 独立MNA指定sample |
|---|---|---:|---:|
| RF-F003 | full_lpf | 56/56（28区間×2点、六設定） | 2 |
| RF-T005 | full_lpf | 56/56 | 2 |
| RF-T007 | full_lpf | 56/56 | 2 |
| RF-T008 | full_lpf | 56/56 | 2 |
| RF-T006 | matching_only | 28/28（14通過区間×2点、六設定） | 2 |

このテストの合計primary費用は252/252、独立spotは10 samples。T006の3–6 GHz追加帯域の実全点scanは行わない。その他のテストは小格子の失敗注入・境界・重複callback・合成の正当な無限dB等を検査する。5点格子の試験は実140 samples/forwardで請求し、固定56等を実装へ埋め込まない。

RF-F003の実効SHA：`e12c42b11d12db7f20983c48cfa441ea96e362e533450d5862aa8a271c82af86`。
小規模fixtureは既存`test_issue307_constraints.make()`の閉区間中点、couplingは0。F003の定義SHAは`80fb297d24276dca474c9e2f9922bfb8b7c4813e3288b828490e21f00ef8d6b4`、完全x SHAは`8219198da8b3b7da872cfbdbcc8af54a463e97c0cd58123985cf55e377d82085`。ベクトル（schema単位nH/pF/k）：

```json
[13.7,28.1,13.7,13.7,1.005,1.005,1.005,50.05,0.11,0.11,0,0,0,0,1.5,1.5,1.5,1.5,1.5,1.5,1.5,1.5,1.5,1.5,1.5,1.5]
```

rawの状態抜粋（実際には上記の完全grid/x/全応答/全評価も含む）：

```json
{"status":"ready","requested":56,"completed":56,"dense":"not_run",
 "batches":[{"status":"completed","phase":"completed","requested":56,"completed":56,
 "reason":"forward_and_requirements_completed"}]}
```

失敗注入`test_failure_unknown_checkpoint_and_no_retry`の抜粋：

```json
{"status":"failed","requested":56,"completed":0,
 "reason":"RuntimeError: injected numerical/evaluation failure"}
```

最終保存失敗を注入するとdurable rawは直前の`unknown/56/0`を保持し、再試行・再初期化しない。契約・物理・予算の拒否は`stopped`、該当batch requested=0。SPD拒否は既存検査の例外注入でforward前STOPを確認し、実SPD計算の検証は制約/branch-MNA回帰で行う。一時ディレクトリはテスト終了時に破棄し、EXP原本やチェックポイントへ書かない。Plan SHAは一時sourceのpathも含むため実行ごとに変わり、raw内のその実行のSHAと照合する。

通常smokeとsparse RF CIの両方に新テストを追加。コード/CI PASS、有限格子での評価完了、指定点独立MNA PASS、RF適合、G0/G1実行承認は別判定。Stage 4Cおよび新EXPはこのAPIから起動しない。

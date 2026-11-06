# Issue #321 — Stage 4C-3A 開発用最小E2E

## 範囲・承認境界

#301/#306 v1.0・#321 の更新済みスコープに従い、#320 の既存逐次APIへ入口と終了処理を接続する。
単一プロセス・固定seed→arm順。新Runner/Workflow/Scheduler、並列化、resume/retry、
seed生成、RF制約/数式/solver/共通順位の変更、新EXP・中央台帳更新はない。
開始元mainは `97c76d9`（PR #320統合）。RF-F003 effective SHA:
`e12c42b11d12db7f20983c48cfa441ea96e362e533450d5862aa8a271c82af86`。

## 入口

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
uv run --frozen python scripts/run_rf_search.py develop \
  --config <schema2.yaml> --starts <starts.json> \
  --spot-checks '{"terminal":[0]}' --output /tmp/<未存在ディレクトリ>
```

YAMLは既存schema2のまま。`definition` にcheckout内の完全なCircuitDefinition JSONの
path/source SHA/canonical SHAを必須指定する。`project/fixtures/issue313_preflight.yaml` は
read-only用のnull definition・1 step例であり、そのまま実行する入力ではない。
設定をコードが自動生成・書換えすることはない。

starts JSONの形式（山括弧は説明用で、実入力ではない）:

```json
{"23":{"vector":["<完全物理xの数値配列>"],"vector_sha256":"<float64 little-endian bytes SHA256>"}}
```

seedキーはcanonicalな非負整数文字列。全Plan seedと完全一致が必要。
重複JSONキー、完全x/SHA不一致、物理closed bounds/Q/role/SPD不正はSTOP。
clip・retry・代替start補充はしない。独立spotは任意で、未指定なら`not_run`。
`terminal`等の共通stageに加え`demo/coarse`等の凍結stage名でsample indexを指定できる。
複数armでは全Jobがそのmappingを検査するので、共通stage指定が最も簡潔。

`load_preflight()` → definition/policy/starts読込 → `run_development()` →
`finalize_development()` のみ。Job投入前と各forward前の既存SHA照合を維持し、
source identityにCLI本体のbytes/dirty patchも追加した。
旧schema1の`preflight`/`run --mode fixture`は維持する。

## 最終読戻し・結果契約

既存親Runnerの最後のatomic保存後、親`run.json`の**実bytes**を返却stateと照合する。
Plan/content SHA、JobSpec/source SHA、Trial/Campaign費用を再確認し、
取込済み各Job rawをファイルから再読込して既存`_development_readback()`で
JobSpec/Plan/RF/grid/各batch費用・予約・独立費用・evidenceを再照合する。
この工程にRF forward、nfev→sample換算、再選抜、予算解放はない。

`summary.json`をatomic保存し、その実bytesも再読込する。stdoutにも同じJSONを出す。
親・Job rawが正本で、summaryは開発用の派生集計にすぎない。
不明Jobは未照合rawの費用を推定せず、親のunknown/予約をそのまま報告する。

| 終了コード | 意味 |
|---|---|
| 0 | 全Jobの費用・raw照合済み、開発フロー完走かつ全Workerがsolver収束を報告 |
| 4 | 全Job照合済みだがbudget exhaustedまたはsolver未収束。開発経路の実装失敗ではない |
| 2 | 不正入力、unknown/interrupted/failed、証拠欠落/不一致、保存失敗STOP |
| 3 | `--mode production`未認可。forward/出力作成前に拒否 |

0もRF合格ではない。strict finite-gridとnominalはbatchごとに別表示する。
収束・厳密有限格子適合・独立spot・科学的/運用ゲート承認を混同しない。
`G0_G1`/`G2_G5`は`not_ready`、dense/全帯域独立MNA/保存監査は`not_run`。
連続帯域・物理実現性は`not_verified`、RF認定は常にfalse。
全sample、完全vector、区間×指標の観測・違反・最悪点は元Job rawに保持し、summaryに複製しない。

親保存失敗時は既存Runnerどおり即例外・再保存なし。summary失敗時も親/Job rawを書換えずSTOP。
既存出力先は自動resumeしない。完了済みsummaryの上書きもしない。

## 限定検証・費用の例

```bash
uv sync --frozen
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
uv run --frozen python -m unittest discover -s tests -p test_issue321_development_cli.py -v
```

7テスト。主E2Eは**実subprocess CLI起動、Workerはその中で同一プロセス**。
既存 `test_issue307_constraints.make()` のRF-F003合法完全xを明示JSONへ保存し、
1 seed×1 arm×固定2 steps、各step SLSQP `max_iterations=1/max_evaluations=1`で検証する。
この予算では数値収束を期待しない。各callbackに実RF forward、全6設定・28個別区間、
既存Stage 3評価、共通selection、terminal/anytime、terminal index 0の独立MNAを通す。

実CLI結果の抜粋（SHAは実行ソース/一時definition pathに依存するため元ファイルに保存）:

```json
{
  "exit_code":4,
  "exit_reason":"reconciled_budget_or_solver_not_converged",
  "development_flow":"completed",
  "solver_converged":false,
  "rf_compliance_certified":false,
  "interval_count":28,
  "setting_count":6,
  "dense":"not_run",
  "gates":{"G0_G1":"not_ready","G2_G5":"not_ready"}
}
```

元Job rawのbatch requested/completedは順に
`[56,84,56,84,112]` = coarse search、anytime、fine search、selection、terminal。
合計 **392 requested / 392 completed samples**、独立MNA **1 requested / 1 completed** は別枠。
solver nfevは各1だがRF sampleと交換しない。
親cap1500、解放1108、保留0。terminal finite-grid strictはFAIL、nominalも別集計。
terminal/anytime/selectionはcompleted、独立指定spotのみpass、denseはnot_run。

1 seed×2 armsの別テストはsolver収束だけをmockし、RFは実計算。
合計784 samples＋独立2 samples、Trial全Job初期予約3000を確認する。
この0出口テストは**数学的収束の実証ではない**。strict FAILでもRF認定を出さない回帰である。
budget STOP回帰はstepの2番目callback前に止まり、56 search＋84 anytime＝140 samples、
照合後の出口4、terminal not_run、予約0を確認する。

入力不正/seed/SHA/予算不足/definition SHA、production、既存出力先、
親/raw byte改変・欠落、summary保存失敗、親保存失敗、中断unknownを追加検査。
Plan/grid/source/bands/S2P改変・数値例外・unknown・後続停止・予約保持の詳細は
既存#315/#317/#319のfault injectionを再利用する。実RF-T006追加18,006点は実行しない。
通常smokeとPi sparse CIに本moduleを追加した。

## 未実施・解釈限界

正式G0番号予約、完全checkout/remote readbackのG1、G2–G5保存監査、dense、
全帯域独立MNA、SRF/Q(f)/EM/公差/実測、科学的最適性・物理実現性の認定は未実施。
テストの小格子結果は有限格子に限る。Phase 2のままでありproductionは解禁しない。
独立レビューとCI判定はDraft PRで確認する。

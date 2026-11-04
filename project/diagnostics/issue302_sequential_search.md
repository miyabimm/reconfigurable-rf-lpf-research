# Issue #302 — 逐次search runner（開発fixture限定）

#301のうち、固定順序・同一プロセスの最小経路を実装する。新EXP、本番最適化、
RF性能認定、Phase移行は含まない。#299 / PR #300の旧経路は変更しない。

## 入口とデータ

```bash
uv run --frozen python scripts/run_rf_search.py preflight --config project/experiments/rf_search_fixture.yaml
# 新しいディレクトリのみ。全solver callbackと17点scanは人工IL。
uv run --frozen python scripts/run_rf_search.py run --config project/experiments/rf_search_fixture.yaml --output results/rf-search-fixture
uv run --frozen python -m unittest discover -s tests -p test_rf_search.py -v
```

YAMLを読むのは`lpf.search.plan`のみ。schema 1のみ、未知/重複キー、RF試験opt-in、
definitionのbyte/canonical SHA、固定S2P SHA、格子、solver/目的、予算を静的照合する。
`preflight`はread-onlyで、G0/G1許可ではない。数値solverの既定tolerance/stepも
解釈後のPlanへ展開して凍結する。例の予算は小さなソフトウェアfixture用であり、
#285の未承認予算・比較計画を採用したものではない。

- `starts`: seedごとにscrambled Sobolの先頭1点のみ。物理全vectorとlittle-endian
  float64 SHAを全armで共有。生成時の物理不正は完全vector/理由を保存し全体STOP。
  clip、再抽選、checkpoint流用、epigraph混入はしない。
- `controller`: seed順→YAML arm順のみ。`runner`が不変JobSpecを作り直接workerを呼ぶ。
  JobSpecはID、trial、Plan/source SHAと凍結JSON（完全x/SHA、box、RF、definition、
  target、steps、stage/job上限、出典等）だけで、callbackや回路instanceを含まない。
- `worker`: SLSQP / Hybrid / SLP / Hybrid→fine3 best-1→SLP。
  Hybridの候補は返されたlocal endpointとbest観測点をSHAで重複排除し、共通strict順位で
  機械的にbest-1を選ぶ。他のstepも出力をfine3で再検査する。候補選別費も当該stepへ算入。
- SLSQPは**既存汎用optimizerの二乗sum/max**であり、旧SLSQP v2の`min t`やrescueを
  移植したものではない。Hybridも二乗sum/max。SLPはsigned最大pass ILとstop制約。
  二乗maxとsigned maxを混同せず、未対応組合せはpreflightでSTOPする。
- 数式は1 dB尺度・等重みの`r=[IL_pass,max(0,target−IL_stop)]`, `e=IL_pass`,
  `g=IL_stop−target>=0`。targetはpolicyの必須値。正式RF-F003への代用や変更はない。
  RF-T008 rev3/full_lpf effective SHAは
  `7de08611f8dd15b40fdfb7946e8c93de5796d026641bdca0f12e992962d05fd4`。

## 評価・保存

RFコアが6設定・28別区間・外部ポート固定S2Pを構成する。callback前にbox/open端、
部品/Q/接続role、全L行列SPDを検査し、違法点は例外で停止する。候補cacheなし。
各forwardのrequested/completed、失敗、stage/grid、CPU/wallを記録し、batch全量を
入口前に照合する。nfevをsample費用へ換算しない。stage/jobは同じmeter、trialは
全job上限を事前に確保し、親台帳で実消費を照合する。

終端476 samplesを常時予約する。明示milestoneを設定した場合は最後の実検査済み点で
17点anytime scanを行い、その費用も同じ枠に含める。終端は**最後の合法・有限forward観測点**を
再検査する（solverが未検査で返したxは使わない）。sample予算停止でも予約枠で検査可能。
失敗/interrupt後には追加forwardを行わない。観測なしならterminalは`not_run`。
観測に全x/SHA、格子、strict指標、最悪setting/segment/frequencyを含める。

`run.json`、`job.json`、`step-N.json`をtemp→fsync→replaceで保存する。forward前は
in-flight `unknown`とrequestedを保存し、正常return後のみcompletedへ計上する。
stepの未完了raw、最後の合法観測、例外理由を残し、failed/interrupted/unknownでは後続jobを
not_startedのまま停止する。sourceはHEAD、dirty patch本体/SHA、未追跡source snapshot、
各source/lock SHA、Python/依存version/thread環境を記録する。再開/上書きは実装しない。
プロセスkill時の最終`unknown`を成功へ読み替えない。保存障害では処理をSTOPし、
最後にdurableだった記録以降の保全を保証しない。raw自動削除はない。

共通17点順位はstrict可行→IL、不適合はVmax→Vsum→IL、同点SHA/ID順。
面積はpolicy由来の固定トポロジー公称値としてPlanに記録する。
`validation.dense_candidate`は明示選別されたstrict候補のみ1001点へ渡す境界、
`independent_sample`は既存独立branch-current MNAの生のgain/power/loss/residualへ接続する境界。
これらは集約受動性/電力保存/独立SPDの合否認定APIではなく、自動起動しない。
候補なし・dense/MNA/passivity/power未実施は`not_run`。solver successとは独立で、
全結果はcandidate promotion blocked。

## 再利用と移植

新`lpf.search`の旧`phase2_models`への直接importは次のRF coreのみ（ASTテストで制限）：

- `api`: policy-bound回路構築（不可欠なT005/T007/T008 backend依存を含む）
- `circuit_layout`: 端子・L-tree・C placement
- `nominal_inductors`: policy L/Q範囲（role/部品/SPDはcore内部の既存検査）
- `independent_rf`: 独立MNA/固定S2P/電力計算とその不可欠な依存

`problem_seed.circuit_box`のT008物理boundsとfingerprint規則、
`optimizer_comparison`のstrict順位、`rf_pipeline_adapter`の数式を責務別に移植した。
面積計上は`topology_enumeration.nominal_area`を参考にT008の最小処理を移植した。
これら旧探索/保存モジュール、`experiment_config/run`、旧pipelineはruntime importしない。
汎用`optimizers/{slsqp,hybrid,slp}`は直接再利用し変更しない。旧コード/履歴は削除しない。

## ゲートと未実装（本番は常にSTOP）

CLIの`--mode production`もworkerの非fixture backendも`not_ready`で拒否する。
fixture用保存をmanifest/storage auditのPASSと称さない。将来本番を接続するには、
既存運用正本・保存ポリシーのまま次を接続する必要がある（別承認規格は作らない）：

1. 完全evidence checkout、最新mainの中央台帳G0予約/照合
   （既存`experiment_id_registry.py`）。本Issueでは予約しない。
2. G1 manifest/storage planned、RF/bands/S2P/definition、全x、source/env/lock、
   固定steps/予算/選別/保存容量の凍結、main/remote byte読戻しと既存storage preflight。
3. G2のrawからA/B選別証拠、manifest/execution/validation、storage_record、run_summaryへの
   接続。G3/G4既存finalize/auditとGit/remote byte読戻し。G5はそのPASS後の個別判断。
4. dense1001・全区間独立MNA/受動性/電力保存/独立SPDの集約gateと別枠費用。

`gates.G0_G1/G2_G5=not_ready`は上記未接続点を隠さないための状態であり、
独自の承認フラグやEXP保存形式ではない。並列scheduler、AI、Continuation、box緩和、
任意DAG、旧record変換は実装しない。有限格子結果は連続周波数、SRF/Q(f)/EM、公差、実測や
物理実現性の保証ではなく、best-foundも大域最適性の証明ではない。

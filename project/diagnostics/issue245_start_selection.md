# Issue #245 A — 粗2点Sobol RF選別（opt-in）

## 範囲・API

実装基点は最新main `0add390c03ab032b16270b1c0a591aaeac433326`。
正式active RF-F003は変更せず、対象は明示trial RF-T008 rev3/full_lpf、実効SHA
`7de08611f8dd15b40fdfb7946e8c93de5796d026641bdca0f12e992962d05fd4`。
B/C、ソルバー、RF数学、bounds、SLSQP v2、歴史EXPは変更していない。

```python
from lpf.phase2_models.multistart import generate_starts
from lpf.phase2_models.sampled_epigraph import SampledEpigraph
from lpf.phase2_models.start_selection import StartSelectionError

try:
    generated = generate_starts(SampledEpigraph(circuit, 2), complete_vector,
        seed=23, selection='rf_pareto', max_initial_samples=952)
except StartSelectionError as exc:
    partial_diagnostic = exc.report  # 部分候補を完成済み3-startとして使わない
```

`selection=None`が既定。既存の完全vector・順序・SHA・記録形式は不変更。
選別はRF-T008 / coarse2 / count=3だけを許可し、nominalまたは既存のSHA・条件・schema照合済warmを先頭に固定する。
同seedのscrambled Sobol 16点blockを一度だけ検査し、clip、epsilon、修復、再生成は行わない。
GJM01=0、未証明series roleは既存同様 `for_exploration=True` のみ許容し、最終昇格はblocked。

## 決定規則と限界

全6設定・28不連続区間の既存forward / `sampled_score` を使う。
Fは最大通過IL、Vは最大H2/H3不足量。30dBを丸めず比較し、地域別不足量・合計不足量も残す。
Sobol合法点についてF/Vの非劣群から `(F,V,合計不足量,Sobol index)` 最小を低IL側に選ぶ。
その点を除いた候補の非劣群から、V最小を制約側に選ぶ。
同Vでは低IL側からの正規化vector距離の二乗が最大の候補を優先し、
その後F、V、合計不足量、Sobol indexで確定する。固定座標の距離寄与は0。
最初の非劣群が1点だけなら、2本目はその点を除いたPareto層から選ぶ。
nominal/warmはこのSobol間順位には参加しない。

Vだけで2本を選ぶことも、加重和・新しいRF hard cutoffも導入しない。
ただし制約側の代表が高ILになることはあり、最終IL改善の保証はない。
有限16点・粗2点は探索初期値の選別にすぎず、17点/1001点適合、連続帯域、物理成立の証明ではない。

## 費用・例外

seed生成時のforwardを採点にも使い、再評価しない。全候補について完全vector/SHA、seed、Sobol index、
score、H2/H3不足量、採用/除外理由、例外、候補別 `EvaluationCost` 差分を保持する。
`selection_report` は条件/definition/schema SHA、格子、全体費用、旧方式の先頭3本SHAと費用差も保持。
時間欄は実測で変動するが、選別は時間に依存しない。
メーター未指定でも内部で作成し、指定時は同じメーターに加算する。
`max_initial_samples` は今回の初期化だけの追加requested sample上限で、次の56 sampleを消費する前に検査する。

最大17 forward = 952 sample、従来3 forward = 168 sample、差784 sample。
非法/重複点はforwardせず、合法なSobolが2本未満なら理由付き停止する。
forward例外、非有限score、予算切れ、中断は途中結果/費用を `StartSelectionError.report` に残して停止し、
残り点への自動継続・再試行はしない。失敗forwardもrequestedへ課金し、未完了sampleをcompletedに加えない。
SLSQP nfevとの同一視はしない。

## 実施した検証

- Python 3.12.15、`uv sync --frozen`。
- 既存 `test_phase2_problem_seed.py` に4テストとwarmの選別検査を追加。
  既定3本の固定SHA、全設定/区間、再現性、固定座標、部品/SPD拒否、重複全棄却、
  GJM=0/未証明roleの探索と最終の区別、30dB直下FAIL、劣後する高IL点の除外、距離tie、
  予算途中停止、forward例外、実forwardのscore照合を検査。
- `.github/workflows/pi-sparse-rf.yml` の15 unittestモジュールを同じコマンドでローカル実行：
  **120件中119 PASS、実SciPy smoke 1件は既存opt-in条件によりSKIP**。
  shared-entryのEXP-050表示は隔離一時fixture内で、本リポジトリのEXP実行/保存ではない。
- 同workflowの `run_phase2_shared.py synthetic --mock --policy RF-T005 --inductors 3` PASS。
- `git diff --check` PASS。GitHub CIはPRの実行結果で別途確認する。

小規模read-only診断は `tests/test_phase2_problem_seed.py::make('RF-T008', 3)` の開発fixtureに対し、
`x[6]=0; SampledEpigraph(circuit,2); seed=23` で再現可能。
保存3構成の歴史checkpoint対照ではない（通常sparse workspaceに完全証拠なし）。
全17点が合法、17 forward / 952 requested・completed、失敗0。
選択はnominal、Sobol index 3、13となった：

| 種別 | vector SHA | F (dB) | V (dB) |
|---|---|---:|---:|
| nominal | `b6a098b045772b02fee8ed619e5324481ed72cbcf3008cc522783df5009ba591` | 1.047826727 | 22.585414398 |
| 低IL側 index 3 | `018ce4c924410539972af77368654dfbc58dcd1d116209ef81c9c404815fb483` | 5.345951849 | 25.270692114 |
| 制約側 index 13 | `6ee6f5bdeb0ef16660b9ce1da3158bc88f306680f8e11100d78ce682717ad26a` | 21.240006270 | 23.019762355 |

全て粗格子strict FAIL。これは動作確認であり性能改善の研究的証拠ではない。
17点/1001点、独立MNA、電力収支/passivity、SRF/Q(f)/EM/公差はこの診断では未実施。
新EXP、実SLSQP/DE/L-SHADE探索、歴史監査、Phase 3は実施していない。

## 後続（本PRでは未承認・未実装）

B/CはAの限定診断だけで拡張を支持できず、未実装。
別の実SLSQP対照Issueで、保存3構成×同seed×3-start×従来/Aの計18 startを提案対象とし、
初期化費用を含む同一総sample上限を事前固定する必要がある。
Aは追加最大784 sampleをソルバー側の利用可能費用から差し引く（v2の反復上限自体は変えない）。
現driverにはこの総費用での安全停止/保存接続がないため、実行前に実装・独立レビューを要する。
G0番号予約、G1完全checkout・同一definition/入力/環境/SHA・予算、G2停止/原子的raw保存、
G3/G4失敗/候補ゼロを含むGit byte読戻し・保存監査を必須とする。
17点strict30適合率/最良IL/最大不足量/費用/停止理由を比較し、可行点のみ既存1001点・独立MNA・
電力/SPD/passivity gateへ進める。具体的総予算・seed・source checkpointと実行開始は別Issueで確定する。

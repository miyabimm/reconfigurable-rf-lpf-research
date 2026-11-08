# Issue #361 Pilot 中断レビュー（ChatGPT独立レビュー用）

## 要約・レビュー依頼

[Issue #361](https://github.com/miyabimm/reconfigurable-rf-lpf-research/issues/361) の開発用探索は、Pilot seed 1001 の実行途中で中断した。実行ツールは `Command aborted` を返し、親Jobとstepは `unknown` のまま。**Pilotは未完了、Main/Extensionは未開始**。last pointは途中の評価点にすぎず、solverが確定した候補や最良点ではない。実験を再実行・再開していない。

ChatGPTに確認してほしい事項：

1. 不明な実行費用と中断rawの保持、再実行の可否・条件（本PRは再実行の承認ではない）。
2. 後述の長い実時間について、計測を追加して原因を切り分ける方針。評価・RF条件や証拠保存の意味を変更する提案は別途承認が必要。
3. 消失したローカル一時原本の所在確認・復旧方法。**PRにraw全体は含まれず、原本の所在も未確認**のため、本PRだけではrawの独立再集計・費用照合はできない。

これはPhase 2のschema2開発実行であり、正式Campaign・新EXP・G0〜G5通過・RF適合認証ではない。

## 時系列・終了状態

| 日時（2026-11-08、JST） | 観測 |
|---|---|
| 14:08:16.734 | Pilot CLI起動。BLAS 1 thread、逐次実行 |
| 14:08:18.143 | 親 `run.json` 作成。seed 1001を開始 |
| 16:12:16.834 | seed 1001 rawの最後の更新 |
| 16:12:42.713 | 実行ツール結果 `Command aborted`。ユーザーの中断操作の可能性はあるが発生元・シグナルはログ未記録 |

消失前のrawについて、保存された全393 batchはいずれも70 samples requested/completedで、raw上は **27,510 / 27,510** と報告した。これは最後の保存時点の記録であり、親 `run.json` は `status=unknown`、campaign費用の確定値は0のまま、unknown費用上限250,000、予約500,000を保持していた。親の確定値0は未照合の保全上の状態であり、RF評価が0回だったという意味ではない。Job rawも `status=unknown`、`evaluation_status=ready`、coarse stepは `unknown`、solver result未保存。最後の保存済batchは `completed`。**未照合費用を確定費用と扱わない**。原本が所在不明のため、これらは現在GitHub上で独立readbackできない未検証の二次証拠である。

| 対象 | 状態 |
|---|---|
| Pilot seed 1001 | 実行途中で中断、収束・終了理由不明 |
| Pilot seed 1002 | `not_started` |
| selection / terminal / anytime | `not_run`（最初のanytime閾値70,000未到達） |
| Main 1003–1008 / Extension 1009–1012 | `not_started` |
| summary / 17点terminal / dense / 独立MNA | `not_run` |

stdout、stderr、`/usr/bin/time` の出力は全て空。例外・数値エラー・シグナル・終了コードの記録はない。393回は残差callbackで、有限差分を含むためiteration回数ではない。指定timeoutは24時間であり、約2時間4分でその設定に到達していない。

## 途中の探索スナップショット（70点格子）

停止直前に**保存された最後の評価batch**を記す。最良点探索・再選別を行うことを意図した資料ではなく、solverのaccepted iterate、最終候補、収束結果とも限らない。実際の停止までに保存されなかった処理の有無は不明。詳細な物理vector、SHA、物理検査結果は [`issue361/observations.json`](issue361/observations.json) に記録。

| 量 | 最初のbatch | 最後に保存されたbatch #393 |
|---|---:|---:|
| 最悪pass IL [dB] | 24.999945 | 16.445167 |
| 最小H2 [dB] | 4.775246 | 4.962139 |
| 最小H3 [dB] | 5.573160 | 9.054281 |
| 30 dB未達の高調波sample | 42 / 42 | 41 / 42 |
| Hybrid sum目的値 | 22511.121106 | 11619.956138 |
| strict有限格子判定 | FAIL | FAIL |

目的値はworker実装どおり `worst_IL + sum(max(0, -mandatory_g)**2)` を対応batchから算出。値の低下は途中観測であり再現成功を意味しない。全393保存batchにstrict可行点はなかった。70点探索格子での観測であり、17点・1001点検証の代用ではない。最後のvector SHA: `b254dab9f5eca90d0af82e821e699c17631dc2007a68cfb35465e33fec99af29`。

## ベンチマーク・条件

- ソース: `experiments/chatgpt_topology_search/runs/EXP-062/checkpoints/a6_best.json`、byte SHA256 `4fbd86e8b46ad7bcb550ba327672b0983e8b58e9ce4b2a9364f8c6557a812b4b`。回路定義はEXP-115 manifest中の定義とEXP-062 checkpointの接続、素子、coupling順、完全vectorを照合。canonical definition SHA `bc50042a1b0b1ebf19c0272fb2ee944b52cd76e14eb8d44673bfa57f6033c068`。
- RF-T008 trialを明示opt-in、**現行**effective SHA `e682165c72d3a8b9f1384a2529f71bacfebfc9d17164d4af5af879e4a138b532`。bands SHA `1b1182e4c947059cb263c1af52ddf64236bd1fd9e83770cc844126576c7865fe`。固定S2P input `ad266111ba1dc2b92f235d39f4a647ff271050bc11941c217661dd299ee59945`、output `b3cfc861bc0c8221f49328598c9d7d0766a6e94e42e990b6a50f6c90bf9a84da`。
- Pi Codeの報告では、ベンチマークvectorを現行評価器・全6設定・28個別区間×17点で別途評価：最悪IL **0.827841148462847 dB**、最小H2 **30.004999999866506 dB**、最小H3 **30.00499999993071 dB**、strict PASS。component/role/SPD検査は通過。旧参考値をそのまま流用していない。別枠476 forward frequency samples。これは原本所在不明の報告に基づく限定有限格子評価であり、seed 1001中断結果、dense、連続帯域や科学的RF認定ではない。今回dense1001・独立MNA・電力・受動性は未実施。
- Pilotの凍結探索格子はpass 14×2、H2 7×3、H3 7×3＝70 points/forward、SHA `6805740a36f6100d7dec3e7308924242e909255f1ea2d287b7c734c400f98f26`。selection 3点、terminal 17点は未実行。

## Planと再現情報

実行ソースHEAD `5609cc84f9f738cc93041f35363b57c3188bc1bc`、Python 3.12.15 / NumPy 2.5.4 / SciPy 1.18.1、`OPENBLAS_NUM_THREADS=OMP_NUM_THREADS=MKL_NUM_THREADS=1`。Job source identity SHA `3d9e18e0520ba8739edf1f0ec9b23e3f7b5ab78659ccff5ecec6439261804828`。source identity対象のtracked dirty patch SHAは空SHA `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`。回路定義 `.issue361-definition.json` はcheckout内の**未追跡入力**で、後述の参照ファイルとしてbyte SHAを凍結した。

| Plan | seed | 1 Job上限 | step上限 | max_evaluations | max_restarts | Plan canonical SHA256 |
|---|---|---:|---:|---:|---:|---|
| Pilot | 1001–1002 | 250,000 | 220,000 | 3,000 | 1 | `8e472fd5a223eaef4aab24cc48e9dbcae6796f3930355b7871b62d3c76ab9ac4` |
| Main | 1003–1008 | 650,000 | 575,000 | 8,000 | 2 | `b023fd1f9ccea7d4651830e5795b7a0515613fa5513cad35b91799d7dba3e24a` |
| Extension | 1009–1012 | 650,000 | 575,000 | 8,000 | 2 | `0d32e89afdfd3e2e70a86a087f7a5908732eae946316965d413401e020705b30` |

各PlanはHybrid単独、`aggregation=sum`、local `maxiter=150`、`restart_sigma=0.1`、逐次実行。予約上限はPilot 221,064 / 250,000、Main・Extension 576,148 / 650,000で静的preflight PASS。全12 seedは `generate_for_definition` で各1 scrambled Sobol pointを生成し、事前合法性検査PASS。補修・再抽選・過去ベストの初期値への注入なし。12本の完全vectorとvector SHAは [`issue361/`](issue361/) の各 `*-starts.json` に保存。Extensionの実行判定はPilot前に `extension-decision.txt` として固定したが、その判定に至っていない。

同ディレクトリのYAML、starts、definition、準備スクリプトは当時のファイルのbyte copy。YAMLは元のcheckout root `.issue361-definition.json` を参照し、格納先の `definition.json` はそのbyte-identical copy（SHA `e8ac857c063e0b9d2eb8eaf629c2e4b700a694e9241f3bbc596d99f6374487f6`）。スクリプトには当時のsystem tmp絶対パスが含まれ、**再実行指示ではない**。Plan JSONの元コピーは後述のとおり所在不明。上表はcanonical Plan SHA（ファイルbyte SHAとは別）。

## 実時間と原因の限界

| 区間 | 実経過 |
|---|---:|
| 起動 → 親記録作成 | 約1.4秒 |
| 親記録作成 → 最終raw更新 | 約2時間3分59秒 |
| 最終raw更新 → ツールabort通知 | 約26秒 |
| 起動 → ツールabort通知 | 約2時間4分26秒 |

親記録作成から最終更新までを393 forwardで割ると平均約18.9秒/forward。ただしこれはRF計算だけでなくcallbackの照合、計算、保存、待ち時間を含む。個別batchの時刻、CPU時間、区間別時間は記録されていない。最後の26秒に行われた処理も不明で、実測のRF／I/O／CPU内訳は復元できない。

実装上、各評価でPlan/ソース等を照合し、増大するraw全体を原子的に保存する。最終rawは27,566,355 bytes。時間の要因となり得るが、**プロファイルしておらず主因は未特定**。平均の単純外挿を完走時間としない。

## 原本・保全状態

元Plan・starts・ベンチマーク評価・ログ・rawの元保存先 `/tmp/issue361-dev-7RxpB4OQ/` は、PR準備中の再確認時には**存在しなかった**。消失原因・別の保存先は不明。Pi Codeは削除・正式EXPへの昇格をしていない。system tmpは永続保存を保証しない。原本が存在した時点で次のSHAを記録したが、現時点でbyte再照合はできない。

| 元のローカル原本 | 確認時のbyte SHA256 |
|---|---|
| `pilot-output/run.json` | `3a31cde3ad522702f04291fba077cc2d7d2a852c3fa10a100f37a3eda94405ba` |
| `pilot-output/development-hybrid-1001.json` | `fd6d4fc576c659b1b23c985b6b7528928818bb267537bd00f081f042ffdf25eb` |
| `benchmark-preflight.json` | `08eb6e482916fb870b8a514df34bab51f3283460390596573749b1dabe12bb2d` |

上記の過去SHAと派生観測値は、原本がない現在、独立照合できない**未検証の二次証拠**であり、PR上でrawのGit readbackやremote照合を実施したことを意味しない。raw全体はPRに含まれず、GitHubで独立に再集計できない。PR内に原本消失前にコピーした小さな入力と最後の評価点の派生スナップショットは残るが、原本保全の代替ではない。**証拠保全は不完全**。原本を回収できた場合は既存SHAを照合してから独立再集計し、元データを改変せずresumeもしない。計測・保全方針の独立レビュー前にPilotやMainを再開しない。連続帯域、Q(f)、SRF、EM、実測、公差、物理実装性および大域最適性は未検証。

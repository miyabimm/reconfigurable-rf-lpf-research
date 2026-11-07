# Issue #330 — 実SciPy・Campaign配線検証（非EXP）

## 範囲と実行

最新main / 科学コード実行HEAD `5ad36d618cf50adbc763d37a155e8f8687f47efa`、
RF-F003 effective SHA `e12c42b11d12db7f20983c48cfa441ea96e362e533450d5862aa8a271c82af86`。
開発Campaign 1 Jobと、隔離Gitの架空EXP-050で1 Jobを実行。各々1構造、seed 23、1 arm、
各step `max_iterations=1, max_evaluations=1, max_requested_samples=56` の2固定steps。
Job capとCampaign max_rf_samplesは各1500、構造capは1。Sobol単一点を既存生成器で合法判定し、
clip/補完/retryなし。提案は定義のみで、予算・数値vectorを含まない。

実行スクリプトは `project/diagnostics/issue330_real_scipy.py` とbyte同一。実行時はcheckout外に
コピーして呼んだ（次のコマンドで同じ内容を新しいtmpにコピーできる）。明示起動するとRF計算を行う。
自身をCIに追加したものではない。fixtureを再利用し、一時directoryとrawは自動削除しない。

```bash
uv sync --frozen
RUN_DIR=$(mktemp -d /tmp/issue330-replay-XXXXXX)
cp project/diagnostics/issue330_real_scipy.py "$RUN_DIR/run.py"
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 PYTHONPATH=.:tests \
  uv run --frozen python "$RUN_DIR/run.py" > "$RUN_DIR/run.log" 2>&1
```

実ログ `/tmp/issue330-evidence-spumvC/run2.log` SHA256
`f59dafbec6f7e3a38a61fe91ad0e605f96572c165c20c0d1c9a0450619a74f85`、終了0。
初回は `PYTHONPATH=tests` だけで `scripts` importに失敗し、Campaign作成・RF実行前に終了。
`PYTHONPATH=.:tests` に修正して上記を一度実行した。Python 3.12.15、NumPy 2.5.4、SciPy 1.18.1、
BLAS/OMP/MKL各1 thread。`slsqp_minimize` と `RFEvaluator.evaluate` はpatchしていない。
既存Campaign/Workerによるraw readbackに加え、スクリプトで元proposal bytes、JobSpec SHA、
plan/definition、全batch・独立費用・6設定28区間を照合した。

## 共通指紋と結果

| 項目 | SHA256 |
|---|---|
| Campaign Plan | `2f40b26219c28392e335b5e6ccdfb4171b1e1192628d65e2c069d098e48d964d` |
| Job Plan | `0f3641d65a1e3136610d1f1caac436b89c34e5370e44ee7a07a8af2e87b3f8fd` |
| definition | `3f187eccd0ad77dce303ea72b51e0967315dc0be80ad1f9066e890509a6fb8de` |
| start vector | `d149de119c24662a75541e9b24b135c4e0e453b86f3b4c6016608e3f557875d3` |
| proposal original bytes | `1610b279459104cbf9c077e341e4556a3d77acebbc5c16205282d4f963a27b27` |
| proposal canonical | `90b4036813b1abdf1e4c8207bec348e02977d260b67914ce2ac104b0f4bf176e` |
| bands | `1b1182e4c947059cb263c1af52ddf64236bd1fd9e83770cc844126576c7865fe` |
| input S2P | `ad266111ba1dc2b92f235d39f4a647ff271050bc11941c217661dd299ee59945` |
| output S2P | `b3cfc861bc0c8221f49328598c9d7d0766a6e94e42e990b6a50f6c90bf9a84da` |

両経路とも構造採用1、主RF batch requested/completedは順に
`56/56, 84/84, 56/56, 84/84, 112/112`、合計**392/392**、予約0、未使用解放1108。
独立MNA terminal index 0は別計数**1/1**、その点のpassivity/power balanceはpass。
selection/terminal/anytimeはcompleted。各stepは`not_converged`、`nfev=1`、
`evaluation_budget_exhausted`、SciPy success/statusはnull（予算例外による中断であり成功としない）。
全5 batchの有限格子strictはFAIL。rawのsolver_execution_kindは`scipy`、workerは
`not_converged`、job exitは`fixed_steps_completed`。収束・RF合格とは別に接続完了を記録する。

| | 開発 | 隔離Git架空EXP |
|---|---|---|
| source SHA | `480edf9b9cfecfaa48aeb4f730224933a187d8bbe0d8f589e587765ea31d4434` | `fda7cf196018e3699c726aaf7def9f943676d09410d4146aa30217f642985271` |
| JobSpec SHA | `0d2ac56f571a3bf09fe8f4be9d88d6a83faad1bdcdcdd7e08cc937ce43603795` | `35dbc5ed96e9ec40fa5fc61a3db011e086ffc57641f7c0bd6244d4e397e7742c` |
| parent byte SHA | `0ae2f85f50706db2d0ea1ecc2a02e4022c5963cd614615299516c34cc824c04a` | `a6be26258f5742aa096426c6a52d5299fc09325ade7c0974135dbe7fad3ac480` |
| raw byte SHA | `696e0f6227f6c9dce34ad336a0e30565feceee0aaab5ac97e524ebc2a702ac5c` | `395349f5a3dfdcfbbca45daf4e1ce80545668f5d18f578dfd32d6020d0e2b4b0` |

開発親/rawは `/tmp/tmp98i29uk0/campaign-1/` に保持。開発source HEADは上記main、
dirty patch SHAは空bytesのSHA。隔離fixtureの親/rawは `/tmp/tmpam_jumfl/work/results/EXP-050/`、
local bare originは `/tmp/tmpam_jumfl/origin.git`。fixtureのsource identityは**架空Git内のダミーsource bytes**を
指し、実際のimportされたPython実装は上記mainからのもの。正式source同一性の実運用検証ではない。
一時pathはホスト上の保全場所であり永続アーカイブではない。実行時fixture補助入力は
`/tmp/issue330-evidence-spumvC/` に移動保全した。

## G0〜G5と停止・保全

隔離環境で `prepare_campaign → planned commit/local bare origin publish → campaign_preflight →
begin_campaign → submit_campaign_proposal → curate_campaign → finalize_campaign → local bare origin main publish →
campaign_cleanup_eligibility` を順に実行。G1 `preflight_ready`、G3 attempted 1/nonconverged 1/unknown 0、
G4 stage `complete`・committed readback true、G5 `eligible=true, deleted=false`。
G5前後のraw inventory全SHAが一致。G4の保存完了はRF/solver合格ではない。
本物の中央EXP予約、GitHubへの実験証拠push、raw削除は行っていない。

unknown/費用不明時の予約保持、後続停止、raw欠落・改変時の保存不可は既存
`test_issue325_campaign*.py` fault-injectionで検査し、今回の実solverはunknownになっていない。
#306依存整理の新たな必須箇所は発見していない。

## 非回帰と限界

- 本実行HEADの実sparse checkoutで `.github/workflows/pi-sparse-rf.yml` のunittestコマンド：112 tests PASS。
  実ログ `/tmp/issue330-evidence-spumvC/actual-sparse.log` SHA256
  `ee9441ebf6caac70384b6aa18ef99299543a94172e6522cd6547c7235ebea154`。
- 最初に既存作業ツリーで同コマンドを実行した際は112 tests中1失敗。理由は `docs/` が存在し
  sparse前提の `test_pi_sparse_rf` に反したため。実sparse別checkoutで再検証した。
- 正式EXP、実運用G0/G1、本番探索、dense/全帯域MNA、連続周波数、SRF/Q(f)/EM/公差/実測、
  物理成立・大域最適性は未実施・未認定。Phase 2のまま。

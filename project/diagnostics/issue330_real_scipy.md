# Issue #330 — 実SciPy・Campaign配線検証（非EXP）

## レビュー是正と範囲

PR #331レビューの指摘どおり、旧設定 `max_evaluations=1` はSciPy本体を呼ぶ前の初期residualで予算を使い切っていた。旧392 samplesの結果は**SciPy本体実行の証拠ではない**。保存済み旧raw・ログは変更していない。

是正実行は最新main `5ad36d618cf50adbc763d37a155e8f8687f47efa` を基礎とする実行時HEAD `187971f3da605230d6608e8dfc6320f98d9c7a73`、RF-F003 effective SHA `e12c42b11d12db7f20983c48cfa441ea96e362e533450d5862aa8a271c82af86`。実行時、下記スクリプトのみ未commitで、科学コードのdirty patchは空bytes SHA。開発Campaignと隔離Git架空EXP-050で各1構造・1 Job・seed 23・1 arm、2固定steps。合法なSobol単一点を既存生成器で使用し、clip/補完/retryなし。提案には回路定義のみ。

各stepは `max_iterations=1, max_evaluations=3, max_requested_samples=168`、1 callbackは56 samples。事前凍結時の各step予約336＋selection/terminal/anytime予約364＝**700**、Job/Campaign cap各1500以内であることを計算前に検査。正式EXPや本番計算ではない。

## 再現とSciPy到達の証拠

`project/diagnostics/issue330_real_scipy.py` をcheckout外にコピーし、以下を明示起動するとRF計算を行う。CIには組み込んでいない。一時fixture/rawは自動削除しない。

```bash
uv sync --frozen
RUN_DIR=$(mktemp -d /tmp/issue330-replay-XXXXXX)
cp project/diagnostics/issue330_real_scipy.py "$RUN_DIR/run.py"
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 PYTHONPATH=.:tests \
  uv run --frozen python "$RUN_DIR/run.py" > "$RUN_DIR/run.log" 2>&1
```

今回のscript SHA256 `9a2528ecf41dcda9d24861193a67e5cb7a9cbf086d774a3e872e9d9fc0bfe006`、ログ `/tmp/issue330-review-pqzHP9/run.log` SHA256 `89a72c4f29db975fd7d45437fc865a1fe1fb1defe1925d2e30489f1a4b20a7b7`、終了0。Python 3.12.15、NumPy 2.5.4、SciPy 1.18.1、BLAS/OMP/MKL各1 thread。`slsqp_minimize`、SciPy `minimize`、`RFEvaluator.evaluate` はpatchしていない。

**両Jobの両stepで `nfev=2, ncev=1, evaluations=3`、各stepのRF batchは56/56を3回。** Workerは物理constraintsを渡し、`slsqp_minimize` は初期residualと初期constraintsを各1回評価した後、自由座標がなければreturn、それ以外は `scipy.optimize.minimize(method='SLSQP')` を呼ぶ。3回目のcallbackはこの呼出し内にしかなく、各callbackはキャッシュなしで実RF batchを実行する。従って実SciPy内部で少なくとも1 RF callbackが走ったとコード経路とrawから確認できる。`nfev=2`だけでSciPyが正常終了したとは意味しない。

## 観測結果と指紋

両経路とも主RF batchのrequested/completedは順に `56, 84, 56, 56, 56, 56, 56, 84, 112` の各同数、合計**616/616**、予約0、未使用解放884。最初の84はanytime、最後の84はselection、112はterminal。各gridは6設定・28個別区間を確認。独立MNA terminal index 0は別計数**1/1**、その点のpassivity/power balanceはpass。selection/terminal/anytimeはcompleted。全9 batchの有限格子strictはFAIL。

各stepは`not_converged`、`evaluation_budget_exhausted`、SciPy success/statusはnull（SciPyから正常returnせず予算例外で中断）。workerは`not_converged`、job exitは`fixed_steps_completed`。接続完了は収束・RF合格ではない。

| 項目 | SHA256 |
|---|---|
| Campaign Plan | `dea05dbbbe93d93b14cb9b21eacf154d9dab26fc6311d9431a8a0d3ede4f0f84` |
| Job Plan | `b841c5d9edd821300e8838d753761f1a2946c65e6931fcc70330c4d6e609f380` |
| definition | `3f187eccd0ad77dce303ea72b51e0967315dc0be80ad1f9066e890509a6fb8de` |
| start vector | `d149de119c24662a75541e9b24b135c4e0e453b86f3b4c6016608e3f557875d3` |
| proposal original bytes / canonical | `c3e998481cdbc55bb594b9f733a0b69a8e45c72b27dad7d85de34ab4963c3121` / `21b1f72585f400ed30be514b29732164f5ca755fc5d66693aef4a87c28bc1ef7` |
| bands | `1b1182e4c947059cb263c1af52ddf64236bd1fd9e83770cc844126576c7865fe` |
| input / output S2P | `ad266111ba1dc2b92f235d39f4a647ff271050bc11941c217661dd299ee59945` / `b3cfc861bc0c8221f49328598c9d7d0766a6e94e42e990b6a50f6c90bf9a84da` |

| | 開発 | 隔離Git架空EXP |
|---|---|---|
| source SHA | `73cbb1ecf97c84534cb1c785abe2968cfdedf08ff18987b2e8303d26c75f80ea` | `4659bc34a30d820f34bf3d9fe690802efbb149b54c16e3af6a3f9428b5fd39d1` |
| JobSpec SHA | `e1f8494bd715ef227cf07459ded0b9742211a406c2aed6ba394917addeff3a5b` | `b16c8b66cc417b9aab9c112cc98f4771ecfa65dac2d5d22a6cf3e1f3ffd90113` |
| parent byte SHA | `bfc0b69dfdcb0bfad400ee936df4bac1df34314561a39382ef5ed7ec5358188f` | `2674cbf172cfa2e3648d85cb9ea37464d4b2d7db8d03645691f329b71414108c` |
| raw byte SHA | `0ac1acc1e528655ece478bf09362f377a744f944239c3ec3207799327beeec87` | `acc7348d6116769867df340b985dd0bf5d5d24b8a45725300a167a1c35e83c46` |

開発親/rawは `/tmp/tmp63uersg0/campaign-1/`、隔離親/rawは `/tmp/tmpt7qhrw_w/work/results/EXP-050/`、bare originは `/tmp/tmpt7qhrw_w/origin.git`。fixture補助入力は実行後 `/tmp/issue330-review-pqzHP9/` に移動保全。tmpは永続アーカイブではない。隔離fixtureのsource identityは架空Git内のダミーsource bytesを指し、importされた実Python実装は上記実行時HEADのもの。正式source同一性の実運用検証ではない。

## G0〜G5と限界

隔離環境で `prepare_campaign → planned commit/local bare origin publish → campaign_preflight → begin_campaign → submit_campaign_proposal → curate_campaign → finalize_campaign → local bare origin main publish → campaign_cleanup_eligibility` を順に実行。G1 `preflight_ready`、G3 attempted 1/nonconverged 1/unknown 0、G4 stage `complete`・committed readback true、G5 `eligible=true, deleted=false`、fixture remote main `e4c25a7c3d79ee2bbcef235dca0d40abbda5d601`。G5前後のraw inventory全SHA一致。G4はRF/solver合格ではない。本物の中央EXP予約、GitHubへの実験証拠push、raw削除は行っていない。

是正後、`OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 PYTHONPATH=tests uv run --frozen python -m unittest -v test_issue325_campaign test_issue325_campaign_gates test_issue321_development_cli` は33 tests PASS（`/tmp/issue330-review-pqzHP9/regression.log`）。unknown/費用不明時の予約保持、後続停止、raw欠落・改変時の保存不可は既存fault-injectionで検査し、今回の実solverはunknownになっていない。#306依存整理の新たな必須箇所は発見していない。

旧1-evaluation runのログ `/tmp/issue330-evidence-spumvC/run2.log` SHA `f59dafbec6f7e3a38a61fe91ad0e605f96572c165c20c0d1c9a0450619a74f85`、開発raw `/tmp/tmp98i29uk0/campaign-1/`、隔離raw `/tmp/tmpam_jumfl/work/results/EXP-050/` はそのまま保持。旧実行時mainの実sparse 112 tests PASS（ログ `/tmp/issue330-evidence-spumvC/actual-sparse.log`）。最初の非sparse作業ツリーでは `docs/` 存在によりsparse必須テスト1件失敗し、実sparse別checkoutで再検証した。

正式EXP、実運用G0/G1、本番探索、dense/全帯域MNA、連続周波数、SRF/Q(f)/EM/公差/実測、物理成立・大域最適性は未実施・未認定。Phase 2のまま。

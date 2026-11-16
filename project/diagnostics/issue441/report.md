# Issue #441 開発限定 smoke / 検証記録

正式EXP・性能探索ではない。#439原本は変更していない。

- 実行コード HEAD: `e8de43e16885317d6c1f2b33595c29933c9ce72c`（後続の文書追加は実行していない）。RF-T008 trial明示opt-in / `full_lpf`、effective SHA `e682165c72d3a8b9f1384a2529f71bacfebfc9d17164d4af5af879e4a138b532`。source identity SHA `9827995886058faec7bf97c62d4c84e0bb22a3addb9ffbfc457fd8040f3d97ea`、Plan SHA `1c1138e82f0bf2d08ff07a4a351999648a03d35a19e7d53c4aeffa460f37d4bb`。
- 25変数中24変数を固定し最後のCv座標のみ自由とする**人工的な縮小box**。固定値は`recommended_box.json`内Sobol seed 1001から生成。2 seedともこのbox内の独立Sobol start。これは4L2Cの25変数探索でも、一般的なrestart収束性能の評価でもない。
- seed 1001 / 1002、1 Jobあたり探索1001 forward×70 samples、Selection 84、Terminal 476。各70,630 primary samples、合計141,260。探索以外の確認として最良点Jを各1回再評価し、別途140 primary samples。Terminal独立MNAは各2点、計4点。denseは未実行。
- 共通CLI `scripts/run_rf_search.py develop --sobol --objective-mode weighted_violation --max-search-forwards 1001 --search-bounds <smoke-box> --spot-checks '{"terminal":[0,111]}'`。`OPENBLAS_NUM_THREADS=OMP_NUM_THREADS=MKL_NUM_THREADS=1`。終了コード4は予算終了でありSolver収束・RF合格ではない。
- 全6設定、28別区間、探索70点。seed順1001→1002、各1001 forwardで予算終了、局所run数は331／346（局所success 330／345）。checkpoint forwardは各 `[1000,1001]`。J再計算は両seedとも保存値 `47641.173946656185` と一致。Terminal strict 30 FAIL、worst IL 33.27893974892873 dB、30.01目標も未達。これらは人工boxの動作確認値であり候補性能の結論ではない。
- Terminal独立branch-current MNAの指定2点／seedで既存比較・受動性・電力収支がpass。全帯域の独立MNA、dense、連続帯域保証、SRF・Q(f)・EM・公差・測定、物理実装性は未検証。
- 実行rawと入力は `/tmp/lpf-issue441-smoke-h8M7yv/final-code-run/` に一時保存（system tmp、永続性保証なし）。同じ一時ディレクトリのコード変更前の初回smokeも2×1001 search forward、141,260 primary samples、MNA計4点を消費。今回の2回とJ確認を通算すると **282,660 primary samples、MNA計8点**。いずれも探索証拠を含むため自動削除しない。

## ソフトウェア検証

Python 3.12、`uv sync --frozen`。`test_issue441*.py`、`test_generic_slsqp.py`、`test_slsqp_budget.py`、`test_slp.py`、`test_constraint_versioning.py`、`test_issue307_constraints.py`、`test_issue319_parent_runner.py`、`test_issue435_weighted_development.py`、`test_issue429_development_runner.py`、`test_issue427_development_worker.py`、`test_hybrid_optimizer.py`、`test_phase2_branch_mna.py`、`scripts/audit_new_experiment_storage.py audit`を実行。旧mode回帰と有限小規模試験であり、CI・独立レビュー・RF設計認証とは別。

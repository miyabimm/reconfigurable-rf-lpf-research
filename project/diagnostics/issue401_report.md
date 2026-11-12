# Issue #401 MinimalWorker 時間内訳（開発診断）

## 範囲と証拠

正式Workerではなく `MinimalWorker` のみ。Aの上限を使い切り、**26 run、2,600 forward / 182,000 requested samples**（各warmupを含む）。各100 nfev、70 samples/forward。P/T各warmup 1、P→T→T→Pを5セット、L2でRFが支配的だったためDeep warmup 1＋測定3。各runは独立process、追加RF観察・再試行なし。`issue401_raw/` に事前凍結、各開始予約、stdout/stderr、終了状態、全solver結果と計時集計を保存。warmupは統計から除外。これは正式EXPでもRF認定でもない。

P/TのHEADは `4e7c53f7f78f127182e4514b6b2673b75b1c6c2b`、L3追加計測は後からタイマーを追加した `20b8ca330b573b6c56b4793868d10d575854900b`。P/Tは同一HEAD・同一スクリプトであり、L3は別HEADである。L3前に全 `src`・環境・対象dirty patchの一致、同一CPU affinityを確認した。変更は診断コード／テストのみ。各段階のsource identity、対象dirty patch SHA（空patch）、スクリプトSHAはそれぞれ `freeze.json` と `deep-freeze.json` に固定した。既存未追跡 `.issue361-definition.json` は入力として使っていない。P/Tのソースは上記HEADのコードを参照すること。現HEADの拡張済みスクリプトは当時のscript SHAとは異なる。

RF-T008 trial明示opt-in、full_lpf、seed 1002、Hybrid restart 0 / max 100、6設定・28個別区間、既存coarse格子。policy effective SHA `e682165c72d3a8b9f1384a2529f71bacfebfc9d17164d4af5af879e4a138b532`、Plan `8ac7bab9567918ae5c656fd449807ad2c38c1e1cad9e39c8ed217b95a569043e`、grid `6805740a36f6100d7dec3e7308924242e909255f1ea2d287b7c734c400f98f26`、vector `6203467121a4e37baaa51c471aaecb3174f3374f9ab955d6fbf101f7b5ce935f`、starts file `63b671ea269656843df118230b7d920e91515188235809b6dd0efd667ac997ab`。bandsおよびS2Pの全SHAは各rawの `rf_inputs` に記録。Worker SHAは#394の新版と同じ `74c47f29637ed73bdf57fbc3ab64e6f928de59f020eb29bd030c6c7f41600b15`。

環境はPython 3.12.15、NumPy 2.5.4、SciPy 1.18.1、OPENBLAS/OMP/MKL各1 thread、WSL2 Linux x86_64、Ryzen 7 PRO 4750G、CPU affinity 0。共有ホストの他負荷やCPU周波数は制御していない。

## Plain / Timed（100 forwardあたりms）

| 指標 | Plain 中央値 [範囲] / 標本標準偏差 | Timed 中央値 [範囲] / 標本標準偏差 |
|---|---:|---:|
| solve wall | 85.435 [81.826, 133.969] / 15.569 | 88.230 [86.226, 121.019] / 10.436 |
| solve CPU | 84.825 [81.806, 133.751] / 15.551 | 88.185 [86.226, 120.931] / 10.426 |
| setup wall | 241.913 [238.227, 247.507] / 3.227 | 242.463 [238.160, 287.203] / 15.315 |

中央値差は +2.795 ms / +3.27%。各群の順番対応10組の差の中央値 +2.666 ms、範囲 −46.224〜+36.724 ms。外れ値と順序・共有環境の影響が大きく、10反復は統計的保証でない。小さい差はノイズと区別できず、正確なtimer負荷は未確定。これは性能改善率ではない。

**計測上の制約:** plainの `solve_wall` は `worker.solve()` 全体で、Hybrid本体だけでなくsolver前box検査、後段物理検査、計測の外側処理を含む。Timedの `hybrid_minimize` は下表の通り分離されるが、plainで同区間を分離測定していない。従ってこの表を厳密な「plain hybrid solver wall」とは呼べず、その比較は未達。追加予算は使用しない。setupにはsourceチェック・preflight・Worker初期化を含む。

## Timed L1/L2（中央値ms、10本）

| inclusive region | count/run | 中央値 [範囲] |
|---|---:|---:|
| solve_total | 1 | 88.082 [86.084, 120.820] |
| hybrid_minimize | 1 | 86.952 [85.021, 119.465] |
| postsolve_validation | 2 | 0.935 [0.884, 1.142] |
| solver_callback | 100 | 80.276 [78.637, 110.074] |
| rf_forward | 100 | 73.165 [71.681, 100.017] |
| requirements | 100 | 3.958 [3.795, 5.103] |
| residual | 100 | 1.602 [1.556, 2.735] |

全count・失敗数はraw参照、failedは0。`solve_total` ⊃ `hybrid_minimize` ⊃ `solver_callback` ⊃ `rf_forward` / `requirements` / `residual`、後段検査はsolve内の別領域。regionはinclusiveであり親子を合計しない。実際の `_solver_residuals` 入口に100回入り、RF/requirements/residualも各100回。各runのRF/callback比は90.9–91.4%。

## Deep L3（高頻度timerを含む順位用、測定3本）

| inclusive region | count/run | 中央値ms [範囲] |
|---|---:|---:|
| rf_forward | 100 | 73.596 [73.296, 74.100] |
| port_admittance | 100 | 31.352 [31.319, 31.576] |
| node_admittance | 100 | 22.288 [22.022, 22.312] |
| matrices | 100 | 7.084 [6.920, 7.117] |
| power_response | 100 | 13.862 [13.527, 13.929] |

包含は `rf_forward` ⊃ `port_admittance` ⊃ `node_admittance` ⊃ `matrices`、`power_response` はportとは別。runごとの `node − matrices` は15.102–15.228 ms、`port − node` は9.040–9.297 ms。前者にはC stamping・einsum等、後者にはSchur等と周辺処理を含み、個々の演算単独時間ではない。未計測のdecode/encode、Y→S、cascade等は分離できない。L3の値からplain速度改善率を推定しない。

## 同等性、限界、次の候補

全26 runのsolver record（best_x、best_fun、各end_x、nfev、終了理由等）はJSON上完全一致、全て `evaluation_budget_exhausted`、未収束。best_fun 27088.776754855604。測定自体では各callbackの複素S・RF指標・requirements配列をplain/timed間で保存・比較していないため、それらの実測run全軌道の直接同等性は**未検証**。instrumentationは戻り値を変更せず例外を再送出し、fixtureテストでplain/timed solver一致・呼出数・RF失敗伝播を確認。別の既存回帰で複素S、IL/APL/RL、requirements、境界、SPD、独立MNAを確認したが、実測条件での新たな独立MNA・電力収支/受動性・dense検証ではない。有限格子、Q(f)/SRF、EM、製造ばらつき、測定による物理実現性は未検証。

レビュー後に検討する候補は最大2つ（まだ実装・効果実証なし）:
1. `node_admittance` の構造固定なC incidence等の再構築を、モデル構築時の不変な準備に移せるか検討。数値演算順、SPD検査、例外意味を変えず、全設定・格子と境界/異常の回帰が必要。
2. `power_response` の固定source/load正規化情報・定数配列の再構築削減を検討。複素S・IL/APL/RL、異常入力/電力収支・受動性・独立MNAを確認する。効果は未確定であり小さければ採用しない。

どちらもA結果の独立レビュー後に範囲を確定し、別承認のB（同一plain条件・旧新各warmup 1＋10、最大2,200 forward/候補）を要する。正式Worker変更、Phase 3、最適化実装、B、追加EXPは未実施。

## 実行したソフトウェア検査

`PYTHONPATH=src uv run --frozen python -m unittest discover -s tests -p 'test_issue401_timing.py' -v` 5件、`test_issue394_physical_path.py` 5件、`test_issue389_minimal_worker.py` 4件、`test_phase2_branch_mna.py` 6件はPASS。後者は単体回帰であり今回の全solver軌道の独立検証ではない。`uv run --frozen python scripts/audit_new_experiment_storage.py audit` 終了0（既存EXPの状態をそのまま出力、今回EXPなし）。初回のテスト起動は `PYTHONPATH` 未設定でimport失敗し、その後上記条件で再実行した。

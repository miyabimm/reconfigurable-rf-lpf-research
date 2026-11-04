# Issue #283: Sobol → Hybrid → SLP（合成問題用）

`lpf.optimizers.pipeline.minimize_pipeline` は有限box上の汎用数値関数であり、RF adapter、実験runner、物理実現性や大域最適性の証明ではない。呼出し元が `residuals(x)` と符号付き `errors(x)` の意味・尺度、および任意の `constraints(x)>=0` を定義する。Hybridの `weights` は二乗和のみに適用し、SLPに渡さない。

```python
from lpf.optimizers.pipeline import minimize_pipeline

result = minimize_pipeline(
    lambda x: [x[0] - 0.1],
    lambda x: [x[0] - 1, -x[0]], [(0, 1)],
    seed=7, sobol_m=1, starts=[[0.1]], max_evaluations=500,
    hybrid_max_evaluations=40, hybrid_maxiter=30,
    hybrid_max_restarts=0, restart_sigma=0.1,
    slp_max_evaluations=80, slp_max_iterations=30, max_slp_candidates=1)
```

この合成例では候補選別の符号付きmaxが約 **-0.4207400093 → -0.5** に低下する。Hybridの `best_fun` は別尺度（二乗和）であり、この前後比較・最終順位に使わない。改善は常に起こるとは限らない。

明示startを先、Sobolの `2**sobol_m` 点を後に生成し、固定軸を除く正規化ユークリッド距離で近接重複を除く。Hybridごとのbest・各local endpoint・元startを候補とし、同一規則で重複除去する。候補を順に評価し、可行性優先・非可行時は違反量優先・その後符号付きmaxで最初の候補を選ぶ。残りは可行性・違反量の後に選択済集合からの最小正規化距離、その後符号付きmaxを優先する。候補は有限個だけSLPに渡す。未評価や非有限値は選ばない。制約可行性は `constraint_tolerance`（既定1e-7）による数値判定である。

返値は `starts`（seedから導出する各Hybrid seed、Sobol index、start、重複、Hybrid全runと終了状態）、`candidates`（出所、評価、選別理由、SLP前後、採否、収束と可行性）、`selected`、`best`、`counts`、`nfev`、`stop_reason` を含む。`best.success` は採用されたSLP結果の成功を示し、SLP前の点は成功と呼ばない。SLPの `score_improved` と `feasibility_improved`、採否、成功は別々に記録する。未収束の改善点も成功と誤認せず採用しうる。SLP失敗や無効値ではSLP前を保持する。コールバック自身の例外は呼出し元へ伝播する。

`max_evaluations` は残差・誤差・制約の実呼出し総数（差分を含む）、各solver上限はstartまたは候補ごと。全Hybridの後に候補選別し、その後SLPを実行するため、総予算や各上限が不足すると後段は未実行になる。制約ありでは完全な誤差＋制約評価に最低2回必要で、足りない場合は隠れた評価をせず停止する。開始点生成自体はコールバックを呼ばない。結果・収束は有限計算による観測のみである。

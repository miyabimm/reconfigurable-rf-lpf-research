# Issue #291: 汎用SLSQP（合成関数用）

`lpf.optimizers.slsqp.slsqp_minimize` はRF用 `slsqp_budget.py` とは独立。
`aggregation="sum"` は `sum(w*r**2)`、`"max"` は各 `t >= w_i*r_i**2`
を持つエピグラフを最小化する。`weights` 省略時は全1。符号付き `signed_max`
は対象外。`constraints(x)` は物理座標上のベクトル `g >= 0`。
有限box、固定座標および初期非可行に対応する。

`max_iterations` と `max_evaluations` は必須。後者は残差と追加制約の
**実callback呼出し合計**であり、SciPy有限差分と最終検証も課金する。
上限・非有限等で中断後の隠れた評価・再実行はない。中断時は検証済みsolver
終端点がないため、初期点と取得済み初期値だけを返す（未取得は `None`、
可行性不明は `feasible=False`）。入力不正・重み長不一致は `ValueError`。
`nfev`、`ncev` と `evaluations` は失敗したcallbackも含む。callback自体の
例外は伝播する。

通常終端では新たに課金して完全xの目的値と物理制約を再評価する。`success`
はSciPy成功だけでなく物理可行性と、maxの場合エピグラフ制約および
`t` と実最大値の差が許容差以内であることを要する。`solver_success`、
`status`、`message`、`stop_reason`、`feasible` は別々の情報。全固定では
SciPyを呼ばず直接評価する。局所solverの成功や有限許容差は大域最適性、
RF適合、物理実現性の保証ではない。

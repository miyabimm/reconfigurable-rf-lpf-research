# Issue #282: 汎用 MiniMax 近似（合成問題のみ）

`lpf.optimizers.minimax.minimize_minimax(errors, x0, bounds, *, max_iterations,
max_evaluations, constraints=None, ...)` は `max(errors(x))` の符号付き
エピグラフを有限差分で線形化し、SciPy HiGHS LP で解く限定的な逐次LP実装。
ADSの公開概念の近似であり、ADSの内部実装ではない。誤差のスケーリングは呼出側が明示する。

- `bounds` は有限 `(lower, upper)` の列、`x0` はその範囲内。固定変数も許可。
  `errors(x)` は有限・非空の1次元配列、任意の `constraints(x)` は有限1次元配列
  `g(x)>=0`。各出力サイズは一定。入力・出力の契約違反は `ValueError`。
- LPは各bounds幅を基準としたtrust boxと線形化制約を使用し、実関数値で受理／縮小する。
  初期非可行時は違反の減少を優先。LP infeasible時はboxを最大1まで拡大して再試行。
  非線形可行性は証明しない。SLSQP精密化は実装しておらず、`slsqp.reason=not_run`。
- 予算は必須。`max_iterations` はLP呼出し回数、`max_evaluations` は初期・有限差分・
  棄却試行を含む `errors` と `constraints` の個々の呼出しの合計。途中で予算を使い切った
  評価は返却点に採用しない。`slp` / `slsqp` は終了理由、LP反復数、callback回数を記録。
- 結果は完全 `x`、`max_error`、`max_violation=max(0,-min(g))`、`feasible`、`success`。
  `success` は制約許容差内かつ線形化局所停留の数値判定で、大域最適性の証明ではない。
  可行でもLP失敗、予算切れ、step縮小限界などは未成功。有限差分誤差・LP許容差や
  非線形性によって、解付近でも未収束または局所停留と判定され得る。

例（合成関数のみ）:

```python
from lpf.optimizers.minimax import minimize_minimax
r = minimize_minimax(lambda x: [x[0], 1 - x[0]], [0.1], [(0., 1.)],
                     max_iterations=100, max_evaluations=1000)
# r.x ≈ [0.5], r.max_error ≈ 0.5; r.success と r.feasible は別々に確認
```

既存SLSQP v2、RF条件、研究結果、EXP、Phase 3には接続・変更しない。

# SLSQP反復・停止理由の運用（Phase 2、v2）

**現行2段階SLSQPの標準は`slsqp-staged-v2`。** これは探索計算の停止基準であり、RF制約・物理モデル・新EXPのG0〜G5を変更しない。正本実装は[src/lpf/slsqp_budget.py](../src/lpf/slsqp_budget.py)、[回帰テスト](../tests/test_slsqp_budget.py)。旧v1は歴史記録としてGit履歴へ残し、過去EXPに遡及適用しない。

## v2の反復上限と回復条件

| 場合 | 粗 maxiter | 精密 maxiter | 処理 |
|---|---:|---:|---|
| 通常（各start） | **240** | **120** | 2段階を記録 |
| 粗status4/8等で停止、精密だけ正常収束 | 240 | 120 | 精密最終vectorから**同予算**で1回ウォーム再始動 |
| 粗が真のiteration-limit（status9または明示limit） | **500** | **280** | 精密最終vectorから粗・精密を各1回救済 |
| 粗正常収束・精密だけstatus9 | — | **280** | 精密段階だけ1回救済 |
| 粗status4/8かつ精密も非収束 | — | — | 増額せず失敗を保存。別start／制約・数値尺度を診断 |

- **1 startあたりSLSQP段階呼出し最大4回**、各stageの絶対上限は粗500／精密280。回復を繰り返さない。非収束・線探索失敗・タイムアウトを数学的不可能性の証明としない。
- 各stageの`status/message/nit/nfev`、初期/終端完全vector、回復tier、source/seed/格子/予算、失敗・中断を保存。元manifestの未収束状態を成功に書き換えない。
- 出力のsolver収束とRF strict適合は別。全6設定／28区間のUL/DL/H2/H3、固定S2P、SPD、受動性・電力保存、必要な独立MNAで候補を判定する。

## 実証と限界

- [EXP-060](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/actions/runs/39434590336)：126試行、両段階収束62／未収束64。粗status4=31、8=29、9=4、粗240反復到達0。精密120反復到達4はすべて粗status4後であり、280への延長で両段階収束0。
- [EXP-061](https://github.com/MasayaTakagi/reconfigurable-rf-lpf-research/actions/runs/39439246405)：粗status4/8・精密status0の保存20点を**同じvectorから**通常240/120と増額500/280で対照再始動し、双方20/20で両段階収束・30dB適合・独立9×9MNA PASS。当該20点では増額の実質IL利益を観測せず、他の未収束点へ一般化しない。
- 旧EXP-055→056のウォーム再探索6/6収束は**初期vectorとiteration上限を同時変更**したため、上限増額の単独因果効果ではない。通常240/120の大域最適性・全帯域の保証ではない。
- 古いv1は`run_staged_slsqp`（初回240/120・真のlimit時500/280救済）の当時仕様。新規は`run_termination_aware_slsqp`を使用し、過去の`iteration_policy_id=slsqp-staged-v1`を上書きしない。

```python
from lpf.slsqp_budget import run_termination_aware_slsqp
result = run_termination_aware_slsqp(
    coarse_evaluator, fine_evaluator, compatible_saved_vector,
    30.005, optimize_stage=optimize_stage,
)
# 各stage/attempt/停止理由を保存し、RFと独立MNAは別途評価する。
```

**未実証：** 一般の収束率改善、最適な反復上限、大域最適解、連続周波数、Q(f)/SRF/EM/実測。個別の実験予算や正式EXP着手には[運用正本](instructions.md)と[保存規則](experiment_storage_policy.md)が適用される。
